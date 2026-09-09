from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_platform.runtime.service import advance_case_run
from app.config import Settings
from app.database import Database
from app.discovery import (
    ListingCandidate,
    ListingDiscoveryError,
    ListingRepresentation,
    discover_datatables_configuration,
    parse_datatables_page,
    parse_listing,
)
from app.embedding_store import embed_current_chunks, queue_embedding_job
from app.embeddings import build_embedding_generator_for_job
from app.enums import JobStatus, RunStatus, ScopeStatus
from app.fda_client import FdaClient, FdaSystemicAcquisitionError
from app.ingestion import ingest_html
from app.models import (
    CaseSource,
    DiscoverySnapshot,
    Document,
    DocumentChunk,
    DocumentVersion,
    IngestionRun,
    ProcessingJob,
    WarningLetter,
    utcnow,
)
from app.notifications import dispatch_pending_notifications, ensure_default_email_subscription
from app.parsing import build_chunks, parse_warning_letter_html
from app.retention import (
    is_within_discovery_window,
    retire_expired_letters,
    retire_local_illustrative_letters,
    years_before,
)
from app.security.auth import Principal
from app.seed import _fixture_manifest, ensure_derived_content
from app.storage import ImmutableObjectStore, build_object_store


@dataclass(frozen=True)
class WorkerResult:
    job_id: str
    status: str
    metrics: dict[str, int]


@dataclass(frozen=True)
class _JobClaim:
    job_id: str
    attempt_count: int


_LIVE_DISCOVERY_CHECKPOINT_KEY = "live_discovery_checkpoint"
_LIVE_DISCOVERY_CHECKPOINT_VERSION = 1
_CANDIDATE_KEY_VERSION = "canonical-url-sha256-v1"
_MAX_CHECKPOINT_HASHES = 10_000
_MAX_CHECKPOINT_BYTES = 1_000_000
_DISCOVERY_CUMULATIVE_KEYS = ("fetched", "in_scope", "out_of_scope", "ambiguous")
_DISCOVERY_PROGRESS_KEYS = (*_DISCOVERY_CUMULATIVE_KEYS, "failed")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_DISCOVERY_JOB_TYPES = frozenset(
    {"discovery", "reconcile", "lifecycle_sweep", "backfill", "lifecycle"}
)
INGESTION_JOB_TYPES = (*sorted(_DISCOVERY_JOB_TYPES), "reprocess", "embed", "integrity_sample")
# Short transaction lock; safe with Supabase's transaction pooler. Never held over HTTP work.
INGESTION_CLAIM_LOCK = 74219183
# ``available_at`` doubles as a lease deadline while a job is RUNNING. This keeps
# the durable queue portable (no database-specific lease column) and lets another
# standalone worker recover a job after a process or pod disappears. The
# heartbeat is intentionally much shorter than the lease, so an ordinary slow
# provider request does not look abandoned.
_JOB_LEASE_SECONDS = 300
_JOB_HEARTBEAT_SECONDS = 30
_STALE_JOB_RECOVERY_LIMIT = 100
logger = logging.getLogger("uvicorn.error")


class DiscoveryCheckpointCorrupt(RuntimeError):
    pass


class DiscoveryCheckpointTooLarge(RuntimeError):
    pass


def _nonnegative_counter(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _candidate_digest(canonical_url: str) -> str:
    return hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()


def _load_live_discovery_checkpoint(
    job: ProcessingJob, source_url: str
) -> tuple[date | None, set[str], set[str], dict[str, int], bool]:
    checkpoint = (job.payload or {}).get(_LIVE_DISCOVERY_CHECKPOINT_KEY)
    if checkpoint is None:
        return None, set(), set(), {}, False
    if not isinstance(checkpoint, dict):
        raise DiscoveryCheckpointCorrupt("Live discovery checkpoint is not an object")
    if (
        checkpoint.get("version") != _LIVE_DISCOVERY_CHECKPOINT_VERSION
        or checkpoint.get("source_url") != source_url
        or checkpoint.get("candidate_key_version") != _CANDIDATE_KEY_VERSION
    ):
        raise DiscoveryCheckpointCorrupt("Live discovery checkpoint identity is invalid")
    try:
        cutoff = date.fromisoformat(str(checkpoint["cutoff_date"]))
    except (KeyError, TypeError, ValueError):
        raise DiscoveryCheckpointCorrupt("Live discovery checkpoint cutoff is invalid") from None

    completed_values = checkpoint.get("completed_url_hashes")
    failed_values = checkpoint.get("failed_url_hashes")
    if not isinstance(completed_values, list) or not isinstance(failed_values, list):
        raise DiscoveryCheckpointCorrupt("Live discovery checkpoint hash sets are invalid")
    if len(completed_values) + len(failed_values) > _MAX_CHECKPOINT_HASHES:
        raise DiscoveryCheckpointTooLarge("Live discovery checkpoint has too many URL hashes")
    if len(json.dumps(checkpoint, separators=(",", ":")).encode("utf-8")) > _MAX_CHECKPOINT_BYTES:
        raise DiscoveryCheckpointTooLarge("Live discovery checkpoint exceeds its size limit")
    if any(
        not isinstance(value, str) or not _SHA256_PATTERN.fullmatch(value)
        for value in [*completed_values, *failed_values]
    ):
        raise DiscoveryCheckpointCorrupt("Live discovery checkpoint contains an invalid URL hash")

    completed = set(completed_values)
    failed = set(failed_values)
    if len(completed) != len(completed_values) or len(failed) != len(failed_values):
        raise DiscoveryCheckpointCorrupt("Live discovery checkpoint contains duplicate URL hashes")
    if completed.intersection(failed):
        raise DiscoveryCheckpointCorrupt("Live discovery checkpoint has conflicting URL states")
    failed.difference_update(completed)
    raw_metrics = checkpoint.get("metrics")
    if not isinstance(raw_metrics, dict) or any(
        _nonnegative_counter(raw_metrics.get(key)) != raw_metrics.get(key)
        for key in _DISCOVERY_PROGRESS_KEYS
    ):
        raise DiscoveryCheckpointCorrupt("Live discovery checkpoint metrics are invalid")
    metrics = {key: int(raw_metrics[key]) for key in _DISCOVERY_PROGRESS_KEYS}
    if metrics["failed"] != len(failed):
        raise DiscoveryCheckpointCorrupt("Live discovery checkpoint failure count is inconsistent")
    if metrics["fetched"] != len(completed) or (
        metrics["in_scope"] + metrics["out_of_scope"] + metrics["ambiguous"] != metrics["fetched"]
    ):
        raise DiscoveryCheckpointCorrupt("Live discovery checkpoint result counts are inconsistent")
    return cutoff, completed, failed, metrics, True


def _save_live_discovery_checkpoint(
    job: ProcessingJob,
    *,
    source_url: str,
    cutoff: date,
    completed: set[str],
    failed: set[str],
    metrics: dict[str, int],
) -> None:
    if len(completed) + len(failed) > _MAX_CHECKPOINT_HASHES:
        raise DiscoveryCheckpointTooLarge("Live discovery checkpoint has too many URL hashes")
    metrics["failed"] = len(failed)
    if metrics.get("fetched") != len(completed) or (
        metrics.get("in_scope", 0) + metrics.get("out_of_scope", 0) + metrics.get("ambiguous", 0)
        != metrics.get("fetched")
    ):
        raise DiscoveryCheckpointCorrupt("Live discovery checkpoint result counts are inconsistent")
    checkpoint = {
        "version": _LIVE_DISCOVERY_CHECKPOINT_VERSION,
        "source_url": source_url,
        "cutoff_date": cutoff.isoformat(),
        "candidate_key_version": _CANDIDATE_KEY_VERSION,
        "updated_at": utcnow().isoformat(),
        # Store hashes rather than source URLs so the durable job payload stays
        # bounded and does not duplicate source metadata already held elsewhere.
        "completed_url_hashes": sorted(completed),
        "failed_url_hashes": sorted(failed),
        "metrics": {
            key: _nonnegative_counter(metrics.get(key)) for key in _DISCOVERY_PROGRESS_KEYS
        },
    }
    if len(json.dumps(checkpoint, separators=(",", ":")).encode("utf-8")) > _MAX_CHECKPOINT_BYTES:
        raise DiscoveryCheckpointTooLarge("Live discovery checkpoint exceeds its size limit")
    payload = dict(job.payload or {})
    payload[_LIVE_DISCOVERY_CHECKPOINT_KEY] = checkpoint
    # JSON columns are not mutation-tracked by default; assign a new object so
    # SQLAlchemy always persists the checkpoint before the candidate commit.
    job.payload = payload


async def _bootstrap_legacy_live_checkpoint(
    session: AsyncSession,
    run: IngestionRun,
    eligible_urls: set[str],
) -> tuple[set[str], dict[str, int]]:
    """Recover progress for a live run created before checkpoints existed."""

    if not run.started_at or not eligible_urls:
        return set(), {}
    rows = (
        await session.execute(
            select(WarningLetter.canonical_url, WarningLetter.scope_status)
            .join(Document, Document.warning_letter_id == WarningLetter.id)
            .join(DocumentVersion, DocumentVersion.id == Document.current_version_id)
            .where(
                Document.canonical_url == WarningLetter.canonical_url,
                WarningLetter.last_seen_at >= run.started_at,
                DocumentVersion.last_seen_at >= run.started_at,
            )
        )
    ).all()
    completed: set[str] = set()
    metrics = {key: 0 for key in _DISCOVERY_PROGRESS_KEYS}
    for canonical_url, scope_status in rows:
        if canonical_url not in eligible_urls:
            continue
        completed.add(_candidate_digest(canonical_url))
        metrics["fetched"] += 1
        if scope_status == ScopeStatus.IN_SCOPE_DRUGS.value:
            metrics["in_scope"] += 1
        elif scope_status == ScopeStatus.OUT_OF_SCOPE.value:
            metrics["out_of_scope"] += 1
        else:
            metrics["ambiguous"] += 1
    # Legacy runs did not identify which failures were unresolved. Every
    # non-completed candidate is retried, and failure state is rebuilt from that
    # attempt rather than carrying an unactionable aggregate forward.
    metrics["failed"] = 0
    return completed, metrics


async def recover_interrupted_local_jobs(session: AsyncSession) -> int:
    """Requeue jobs left RUNNING by a terminated embedded development worker."""

    jobs = list(
        (
            await session.scalars(
                select(ProcessingJob).where(ProcessingJob.status == JobStatus.RUNNING.value)
            )
        ).all()
    )
    if not jobs:
        return 0
    run_ids = {job.ingestion_run_id for job in jobs if job.ingestion_run_id}
    now = utcnow()
    for job in jobs:
        job.status = JobStatus.PENDING.value
        job.attempt_count = max(0, job.attempt_count - 1)
        job.last_error_code = "WorkerRestarted"
        job.available_at = now
        job.completed_at = now
    if run_ids:
        await session.execute(
            update(IngestionRun)
            .where(
                IngestionRun.id.in_(run_ids),
                IngestionRun.status == RunStatus.RUNNING.value,
            )
            .values(status=RunStatus.PENDING.value)
        )
    await session.flush()
    return len(jobs)


def _claim_job_statement(
    *, claimed_at: datetime, dialect_name: str, job_types: tuple[str, ...] | None = None,
    single_active: bool = False,
):
    """Build one atomic queue claim, using SKIP LOCKED on PostgreSQL."""

    candidate = (
        select(ProcessingJob.id)
        .where(
            ProcessingJob.status == JobStatus.PENDING.value,
            ProcessingJob.available_at <= claimed_at,
        )
        .order_by(ProcessingJob.created_at, ProcessingJob.id)
        .limit(1)
    )
    if job_types is not None:
        candidate = candidate.where(ProcessingJob.job_type.in_(job_types))
    if single_active:
        running = select(ProcessingJob.id).where(
            ProcessingJob.status == JobStatus.RUNNING.value,
            ProcessingJob.available_at > claimed_at,
            ProcessingJob.job_type.in_(job_types or INGESTION_JOB_TYPES),
        ).correlate(None).exists()
        candidate = candidate.where(~running)
    if dialect_name == "postgresql":
        candidate = candidate.with_for_update(skip_locked=True)
    candidate_id = candidate.scalar_subquery()
    return (
        update(ProcessingJob)
        .where(
            ProcessingJob.id == candidate_id,
            ProcessingJob.status == JobStatus.PENDING.value,
            ProcessingJob.available_at <= claimed_at,
        )
        .values(
            status=JobStatus.RUNNING.value,
            attempt_count=ProcessingJob.attempt_count + 1,
            last_error_code=None,
            started_at=claimed_at,
            completed_at=None,
            available_at=claimed_at + timedelta(seconds=_JOB_LEASE_SECONDS),
        )
        .returning(
            ProcessingJob.id,
            ProcessingJob.attempt_count,
            ProcessingJob.ingestion_run_id,
        )
    )


async def _claim_next_job(
    database: Database, *, job_types: tuple[str, ...] | None = None,
    single_active: bool = False,
) -> _JobClaim | None:
    """Atomically move the oldest available job from PENDING to RUNNING."""

    claimed_at = utcnow()
    async with database.session_factory() as session:
        dialect_name = session.get_bind().dialect.name
        if single_active and dialect_name == "postgresql":
            await session.execute(select(func.pg_advisory_xact_lock(INGESTION_CLAIM_LOCK)))
        row = (
            await session.execute(
                _claim_job_statement(
                    claimed_at=claimed_at, dialect_name=dialect_name, job_types=job_types,
                    single_active=single_active,
                )
            )
        ).one_or_none()
        if row is None:
            await session.rollback()
            return None
        job_id, attempt_count, ingestion_run_id = row
        if ingestion_run_id:
            await session.execute(
                update(IngestionRun)
                .where(IngestionRun.id == ingestion_run_id)
                .values(
                    status=RunStatus.RUNNING.value,
                    started_at=func.coalesce(IngestionRun.started_at, claimed_at),
                )
            )
        await session.commit()
    return _JobClaim(job_id=str(job_id), attempt_count=int(attempt_count))


async def recover_stale_worker_jobs(
    database: Database,
    *,
    recovered_at: datetime | None = None,
    job_types: tuple[str, ...] | None = None,
) -> int:
    """Recover a bounded batch of RUNNING jobs whose heartbeat lease expired.

    The consumed attempt is retained. A job that has exhausted ``max_attempts``
    is dead-lettered instead of being recovered forever.
    """

    now = recovered_at or utcnow()
    recovered = 0
    async with database.session_factory() as session:
        statement = (
            select(
                ProcessingJob.id,
                ProcessingJob.ingestion_run_id,
                ProcessingJob.attempt_count,
                ProcessingJob.max_attempts,
            )
            .where(
                ProcessingJob.status == JobStatus.RUNNING.value,
                ProcessingJob.available_at <= now,
            )
            .order_by(ProcessingJob.available_at, ProcessingJob.id)
            .limit(_STALE_JOB_RECOVERY_LIMIT)
        )
        if job_types is not None:
            statement = statement.where(ProcessingJob.job_type.in_(job_types))
        if session.get_bind().dialect.name == "postgresql":
            statement = statement.with_for_update(skip_locked=True)
        rows = (await session.execute(statement)).all()
        for job_id, ingestion_run_id, attempt_count, max_attempts in rows:
            exhausted = int(attempt_count) >= int(max_attempts)
            target_status = JobStatus.DEAD_LETTER.value if exhausted else JobStatus.PENDING.value
            transition = await session.execute(
                update(ProcessingJob)
                .where(
                    ProcessingJob.id == job_id,
                    ProcessingJob.status == JobStatus.RUNNING.value,
                    ProcessingJob.attempt_count == attempt_count,
                    ProcessingJob.available_at <= now,
                )
                .values(
                    status=target_status,
                    last_error_code=("StaleLeaseExhausted" if exhausted else "StaleLeaseExpired"),
                    available_at=now,
                    started_at=None if not exhausted else ProcessingJob.started_at,
                    completed_at=now if exhausted else None,
                )
            )
            if transition.rowcount != 1:
                continue
            recovered += 1
            if ingestion_run_id:
                await session.execute(
                    update(IngestionRun)
                    .where(
                        IngestionRun.id == ingestion_run_id,
                        IngestionRun.status == RunStatus.RUNNING.value,
                    )
                    .values(
                        status=(RunStatus.FAILED.value if exhausted else RunStatus.PENDING.value),
                        error_code="StaleLeaseExhausted" if exhausted else None,
                        completed_at=now if exhausted else None,
                    )
                )
        await session.commit()
    return recovered


async def _renew_job_lease(database: Database, claim: _JobClaim) -> bool:
    renewed_at = utcnow()
    async with database.session_factory() as session:
        result = await session.execute(
            update(ProcessingJob)
            .where(
                ProcessingJob.id == claim.job_id,
                ProcessingJob.status == JobStatus.RUNNING.value,
                ProcessingJob.attempt_count == claim.attempt_count,
            )
            .values(available_at=renewed_at + timedelta(seconds=_JOB_LEASE_SECONDS))
        )
        await session.commit()
        return result.rowcount == 1


async def _heartbeat_job_lease(
    database: Database,
    claim: _JobClaim,
    stop: asyncio.Event,
    owner_task: asyncio.Task[object] | None,
) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=_JOB_HEARTBEAT_SECONDS)
            return
        except TimeoutError:
            pass
        try:
            if await _renew_job_lease(database, claim):
                continue
        except Exception:
            # A transient database failure still leaves most of the five-minute
            # lease available. Retry on the next heartbeat rather than causing a
            # duplicate provider request immediately.
            logger.exception("Could not renew worker lease for job %s", claim.job_id)
            continue
        logger.error("Worker lease ownership was lost for job %s", claim.job_id)
        if owner_task and not owner_task.done():
            owner_task.cancel()
        return


def _content_type(path: Path) -> str:
    return {
        ".csv": "text/csv",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }.get(path.suffix.casefold(), "text/html")


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def _fixture_files(fixture_dir: Path) -> list[Path]:
    return sorted(
        path for path in fixture_dir.rglob("*.html") if "listing" not in path.stem.casefold()
    )


def _candidate_fixture(
    candidate: ListingCandidate,
    fixture_dir: Path,
    files: list[Path],
    manifest: dict[str, str],
) -> Path | None:
    for relative, url in manifest.items():
        if url == candidate.canonical_url:
            path = (fixture_dir / relative).resolve()
            if path.is_file() and fixture_dir.resolve() in path.parents:
                return path
    url_slug = _slug(Path(urlsplit(candidate.canonical_url).path).name)
    for path in files:
        stem = _slug(path.stem)
        if stem and (stem in url_slug or url_slug in stem):
            return path
    if candidate.company_name:
        company_slug = _slug(candidate.company_name)
        for path in files:
            if _slug(path.stem) in company_slug or company_slug in _slug(path.stem):
                return path
    return None


async def _record_snapshot(
    session: AsyncSession,
    settings: Settings,
    run: IngestionRun,
    representation: ListingRepresentation,
    content: bytes,
    object_store: ImmutableObjectStore,
    *,
    redirect_chain: list[str] | None = None,
    etag: str | None = None,
    last_modified: str | None = None,
) -> None:
    existing = await session.scalar(
        select(DiscoverySnapshot).where(
            DiscoverySnapshot.source_url == representation.source_url,
            DiscoverySnapshot.sha256 == representation.raw_sha256,
        )
    )
    if existing:
        return
    key, digest = object_store.put("fda-discovery", content)
    session.add(
        DiscoverySnapshot(
            ingestion_run_id=run.id,
            source_url=representation.source_url,
            final_url=representation.final_url,
            redirect_chain=redirect_chain or [],
            sha256=digest,
            raw_object_key=key,
            etag=etag,
            last_modified=last_modified,
            detected_columns=representation.detected_columns,
            schema_fingerprint=representation.schema_fingerprint,
            row_count=len(representation.candidates),
            parser_version=settings.parser_version,
            source_client_version=settings.fda_source_client_version,
            http_anomalies=representation.warnings,
        )
    )


async def _fixture_discovery(
    session: AsyncSession,
    settings: Settings,
    run: IngestionRun,
    fixture_dir: Path,
    reference_date: date,
) -> dict[str, int]:
    fixture_dir = fixture_dir.resolve()
    if not fixture_dir.is_dir():
        raise FileNotFoundError(fixture_dir)
    object_store = build_object_store(settings)
    listing_path = next(
        (
            path
            for name in (
                "listing_export.xlsx",
                "listing_export.csv",
                "listing.html",
                "warning_letters_listing.html",
            )
            if (path := fixture_dir / name).is_file()
        ),
        None,
    )
    files = _fixture_files(fixture_dir)
    manifest = _fixture_manifest(fixture_dir)
    if listing_path:
        content = listing_path.read_bytes()
        representation = parse_listing(
            content,
            source_url=settings.fda_listing_url,
            final_url=settings.fda_listing_url,
            content_type=_content_type(listing_path),
            allowed_hosts=settings.fda_allowed_hosts,
        )
        await _record_snapshot(session, settings, run, representation, content, object_store)
        candidates = representation.candidates
    else:
        candidates = [
            ListingCandidate(
                canonical_url=(
                    "https://www.fda.gov/inspections-compliance-enforcement-and-criminal-"
                    f"investigations/warning-letters/{_slug(path.stem)}"
                ),
                company_name=path.stem.replace("_", " ").title(),
                listing_ordinal=index,
            )
            for index, path in enumerate(files)
        ]
    metrics = {
        "listing_rows": len(candidates),
        "outside_backfill_window": 0,
        "fetched": 0,
        "in_scope": 0,
        "out_of_scope": 0,
        "ambiguous": 0,
        "failed": 0,
    }
    discovery_cutoff = years_before(reference_date, settings.corpus_backfill_years)
    used: set[Path] = set()
    for candidate in candidates:
        path = _candidate_fixture(candidate, fixture_dir, files, manifest)
        if not is_within_discovery_window(
            posted_date=candidate.posted_date,
            issue_date=candidate.issue_date,
            cutoff=discovery_cutoff,
        ):
            metrics["outside_backfill_window"] += 1
            if path:
                used.add(path)
            continue
        if not path:
            metrics["failed"] += 1
            continue
        used.add(path)
        result = await ingest_html(
            session,
            settings,
            candidate.to_ingestion_metadata(settings.fda_listing_url),
            path.read_bytes(),
            object_store=object_store,
        )
        metrics["fetched"] += 1
        if result.scope_status.value == "IN_SCOPE_DRUGS":
            metrics["in_scope"] += 1
        elif result.scope_status.value == "OUT_OF_SCOPE":
            metrics["out_of_scope"] += 1
        else:
            metrics["ambiguous"] += 1
    # A fixture corpus may intentionally include scope-negative documents omitted
    # from a short listing sample; process them to exercise the fail-closed gate.
    for path in files:
        if path in used:
            continue
        relative = path.relative_to(fixture_dir).as_posix()
        canonical_url = manifest.get(relative) or manifest.get(path.name)
        if not canonical_url:
            canonical_url = (
                "https://www.fda.gov/inspections-compliance-enforcement-and-criminal-"
                f"investigations/warning-letters/{_slug(path.stem)}-fixture"
            )
        result = await ingest_html(
            session,
            settings,
            candidate=ListingCandidate(canonical_url=canonical_url).to_ingestion_metadata(
                settings.fda_listing_url
            ),
            html=path.read_bytes(),
            object_store=object_store,
        )
        metrics["fetched"] += 1
        if result.scope_status.value == "IN_SCOPE_DRUGS":
            metrics["in_scope"] += 1
        elif result.scope_status.value == "OUT_OF_SCOPE":
            metrics["out_of_scope"] += 1
        else:
            metrics["ambiguous"] += 1
    return metrics


async def _recent_candidate_urls(
    session: AsyncSession, candidates: list[ListingCandidate], refresh_before: str | None,
) -> set[str]:
    """Daily scheduling revisits new/changed/stale sources without a daily full refetch."""
    if not refresh_before or not candidates:
        return set()
    cutoff = datetime.fromisoformat(refresh_before)
    if cutoff.tzinfo is None:
        raise ValueError("Scheduled refresh cutoff must include its timezone")
    rows = (await session.execute(
        select(WarningLetter, DocumentVersion.http_provenance)
        .join(DocumentVersion, DocumentVersion.id == WarningLetter.current_version_id)
        .where(WarningLetter.canonical_url.in_([item.canonical_url for item in candidates]))
    )).all()
    known = {letter.canonical_url: (letter, provenance or {}) for letter, provenance in rows}
    recent = set()
    for candidate in candidates:
        stored = known.get(candidate.canonical_url)
        if not stored:
            continue
        letter, provenance = stored
        last_seen = letter.last_seen_at
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=UTC)
        metadata_same = all(
            value is None or value == getattr(letter, field)
            for field, value in (
                ("posted_date", candidate.posted_date), ("issue_date", candidate.issue_date),
                ("company_name", candidate.company_name), ("subject", candidate.subject),
            )
        ) and (
            not candidate.issuing_office or candidate.issuing_office in letter.issuing_offices
        ) and all(
            getattr(candidate, field) == provenance.get(field)
            for field in ("response_url", "closeout_url")
        )
        if last_seen >= cutoff and metadata_same:
            recent.add(candidate.canonical_url)
    return recent


async def _live_discovery(
    session: AsyncSession,
    settings: Settings,
    job: ProcessingJob,
    run: IngestionRun,
    source_url: str,
    reference_date: date,
) -> dict[str, int]:
    illustrative_retired = await retire_local_illustrative_letters(session, settings)
    await session.commit()
    client = FdaClient(settings)
    object_store = build_object_store(settings)
    fetched = await client.fetch(source_url)
    representation = parse_listing(
        fetched.content,
        source_url=fetched.requested_url,
        final_url=fetched.final_url,
        content_type=fetched.content_type,
        allowed_hosts=settings.fda_allowed_hosts,
    )
    await _record_snapshot(
        session,
        settings,
        run,
        representation,
        fetched.content,
        object_store,
        redirect_chain=fetched.redirect_chain,
        etag=fetched.headers.get("etag"),
        last_modified=fetched.headers.get("last-modified"),
    )
    # A live backfill can take many hours while honoring FDA's crawl delay.
    # Checkpoint immutable listing evidence so local SQLite does not hold one
    # write transaction for the entire network-bound run.
    await session.commit()
    (
        checkpoint_cutoff,
        completed_hashes,
        failed_hashes,
        checkpoint_metrics,
        checkpoint_valid,
    ) = _load_live_discovery_checkpoint(job, source_url)
    discovery_cutoff = checkpoint_cutoff or years_before(
        reference_date, settings.corpus_backfill_years
    )
    candidates = list(representation.candidates)
    listing_total = len(candidates)
    datatables = discover_datatables_configuration(
        fetched.content,
        page_url=fetched.final_url,
        allowed_hosts=settings.fda_allowed_hosts,
    )
    if datatables:
        candidates = []
        listing_total = datatables.total_items
        seen_urls: set[str] = set()
        page_size = 1000
        start, draw = 0, 0
        while start < listing_total:
            draw += 1
            if draw > 100 or len(candidates) > _MAX_CHECKPOINT_HASHES:
                raise ListingDiscoveryError("FDA listing exceeded the bounded discovery window")
            page_url = datatables.page_url(
                start=start,
                length=page_size,
                draw=draw,
                allowed_hosts=settings.fda_allowed_hosts,
            )
            page_fetch = await client.fetch(page_url)
            snapshot_url = f"{datatables.ajax_url}?draw={draw}&start={start}&length={page_size}"
            page_representation = parse_datatables_page(
                page_fetch.content,
                source_url=snapshot_url,
                columns=datatables.columns,
                allowed_hosts=settings.fda_allowed_hosts,
            )
            await _record_snapshot(
                session,
                settings,
                run,
                page_representation,
                page_fetch.content,
                object_store,
                redirect_chain=page_fetch.redirect_chain,
                etag=page_fetch.headers.get("etag"),
                last_modified=page_fetch.headers.get("last-modified"),
            )
            await session.commit()
            if page_representation.total_items is not None:
                listing_total = page_representation.total_items
            if not page_representation.candidates:
                if start >= listing_total and candidates:
                    break
                raise ListingDiscoveryError("FDA listing ended before all advertised rows arrived")
            previous_count = len(seen_urls)
            for candidate in page_representation.candidates:
                if candidate.canonical_url not in seen_urls:
                    candidates.append(candidate)
                    seen_urls.add(candidate.canonical_url)
            if len(seen_urls) == previous_count:
                raise ListingDiscoveryError("FDA listing repeated a page instead of advancing")
            start += page_representation.row_count or len(page_representation.candidates)
            # FDA sorts the table by posted date descending. Once a whole page
            # predates the rolling window, every subsequent page is older too.
            if all(
                item.posted_date is not None and item.posted_date < discovery_cutoff
                for item in page_representation.candidates
            ):
                break
    elif representation.export_url and representation.export_url != fetched.final_url:
        # Older FDA page variants exposed canonical links inside their XLSX.
        # Current exports omit those links, so retain the valid HTML rows if the
        # export cannot be represented without guessing.
        try:
            export_fetch = await client.fetch(representation.export_url)
            export_representation = parse_listing(
                export_fetch.content,
                source_url=representation.export_url,
                final_url=export_fetch.final_url,
                content_type=export_fetch.content_type,
                allowed_hosts=settings.fda_allowed_hosts,
            )
        except ListingDiscoveryError:
            pass
        else:
            representation = export_representation
            candidates = list(representation.candidates)
            listing_total = len(candidates)
            await _record_snapshot(
                session,
                settings,
                run,
                representation,
                export_fetch.content,
                object_store,
                redirect_chain=export_fetch.redirect_chain,
                etag=export_fetch.headers.get("etag"),
                last_modified=export_fetch.headers.get("last-modified"),
            )
            await session.commit()
    eligible_candidates = [
        candidate
        for candidate in candidates
        if is_within_discovery_window(
            posted_date=candidate.posted_date,
            issue_date=candidate.issue_date,
            cutoff=discovery_cutoff,
        )
    ]
    metrics = {
        "listing_rows": len(candidates),
        "listing_total": listing_total,
        "outside_backfill_window": len(candidates) - len(eligible_candidates),
        "fetched": 0,
        "in_scope": 0,
        "out_of_scope": 0,
        "ambiguous": 0,
        "failed": 0,
        "illustrative_fixtures_retired": max(
            illustrative_retired,
            _nonnegative_counter((run.metrics or {}).get("illustrative_fixtures_retired")),
        ),
    }
    for key in _DISCOVERY_CUMULATIVE_KEYS:
        metrics[key] = max(metrics[key], checkpoint_metrics.get(key, 0))
    metrics["failed"] = len(failed_hashes)

    if not checkpoint_valid:
        legacy_hashes, legacy_metrics = await _bootstrap_legacy_live_checkpoint(
            session,
            run,
            {candidate.canonical_url for candidate in eligible_candidates},
        )
        completed_hashes.update(legacy_hashes)
        for key in _DISCOVERY_CUMULATIVE_KEYS:
            # Pre-checkpoint aggregates can include duplicate fetches after a
            # restart. Reconstruct unique, evidenced progress from the database.
            metrics[key] = legacy_metrics.get(key, 0)
        metrics["failed"] = len(failed_hashes)

    _save_live_discovery_checkpoint(
        job,
        source_url=source_url,
        cutoff=discovery_cutoff,
        completed=completed_hashes,
        failed=failed_hashes,
        metrics=metrics,
    )
    run.metrics = dict(metrics)
    await session.commit()
    recent_urls = await _recent_candidate_urls(
        session, eligible_candidates, job.payload.get("refresh_before"),
    )
    metrics["skipped_recent"] = 0
    await session.commit()
    for candidate in eligible_candidates:
        candidate_hash = _candidate_digest(candidate.canonical_url)
        if candidate_hash in completed_hashes:
            continue
        if candidate.canonical_url in recent_urls:
            metrics["skipped_recent"] += 1
            continue
        try:
            detail = await client.fetch(candidate.canonical_url)
            async with session.begin_nested():
                result = await ingest_html(
                    session,
                    settings,
                    candidate.to_ingestion_metadata(representation.final_url),
                    detail.content,
                    object_store=object_store,
                )
            metrics["fetched"] += 1
            if result.scope_status.value == "IN_SCOPE_DRUGS":
                metrics["in_scope"] += 1
            elif result.scope_status.value == "OUT_OF_SCOPE":
                metrics["out_of_scope"] += 1
            else:
                metrics["ambiguous"] += 1
            completed_hashes.add(candidate_hash)
            failed_hashes.discard(candidate_hash)
        except FdaSystemicAcquisitionError as exc:
            # One origin-wide outage must stop this pass. The exception is
            # handled by the durable worker retry path, while the checkpoint
            # from the previously completed candidate remains committed.
            logger.warning(
                "discovery_acquisition_circuit_open candidate_hash=%s reason=%s",
                candidate_hash,
                exc.reason_code,
            )
            raise
        except Exception:
            failed_hashes.add(candidate_hash)
        metrics["failed"] = len(failed_hashes)
        _save_live_discovery_checkpoint(
            job,
            source_url=source_url,
            cutoff=discovery_cutoff,
            completed=completed_hashes,
            failed=failed_hashes,
            metrics=metrics,
        )
        run.metrics = dict(metrics)
        await session.commit()
    return metrics


async def _run_discovery(
    session: AsyncSession,
    settings: Settings,
    job: ProcessingJob,
    run: IngestionRun,
    reference_date: date,
) -> dict[str, int]:
    fixture_dir = job.payload.get("fixture_dir")
    if fixture_dir:
        return await _fixture_discovery(
            session, settings, run, Path(str(fixture_dir)), reference_date
        )
    source = str(job.payload.get("source") or run.source)
    source_url = source if source.startswith("https://") else settings.fda_listing_url
    return await _live_discovery(session, settings, job, run, source_url, reference_date)


async def _reprocess(
    session: AsyncSession, settings: Settings, job: ProcessingJob
) -> dict[str, int]:
    letter = await session.get(WarningLetter, job.warning_letter_id)
    version = await session.get(DocumentVersion, job.document_version_id)
    if not letter or not version:
        raise RuntimeError("Reprocess target no longer exists")
    stages = set(job.payload.get("stages") or [])
    metrics = {"stages_completed": 0, "chunks_created": 0}
    if "scope" in stages:
        if version.scope_status != "IN_SCOPE_DRUGS":
            raise RuntimeError("Source version is not eligible for the Drug corpus")
        metrics["stages_completed"] += 1
    if "parse" in stages:
        if not version.raw_object_key:
            raise RuntimeError("Source version has no retained raw object")
        raw = build_object_store(settings).get(version.raw_object_key)
        if hashlib.sha256(raw).hexdigest() != version.raw_sha256:
            raise RuntimeError("Retained raw object failed integrity verification")
        parsed = parse_warning_letter_html(raw)
        if parsed.canonical_hash != version.canonical_hash:
            raise RuntimeError("Reparse does not reproduce the retained canonical hash")
        extraction_metadata = {
            **(version.extraction_metadata or {}),
            "title": parsed.title,
            "company_name": parsed.company_name,
            "recipient_country": parsed.recipient_country
            or (version.extraction_metadata or {}).get("recipient_country"),
            "body_non_empty": bool(parsed.normalized_text),
        }
        pinned_case_source_id = await session.scalar(
            select(CaseSource.id).where(CaseSource.document_version_id == version.id).limit(1)
        )
        pinned_payload_changed = pinned_case_source_id is not None and any(
            (
                version.normalized_markdown != parsed.normalized_markdown,
                version.normalized_text != parsed.normalized_text,
                (version.source_anchors or []) != parsed.anchors,
                (version.source_links or []) != parsed.source_links,
                version.parser_version != settings.parser_version,
                (version.parser_warnings or []) != parsed.warnings,
                (version.extraction_metadata or {}) != extraction_metadata,
            )
        )
        if pinned_payload_changed:
            raise RuntimeError(
                "Reparse would change a case-pinned source version; retain it and "
                "ingest a separately versioned source instead"
            )
        if pinned_case_source_id is None:
            version.normalized_markdown = parsed.normalized_markdown
            version.normalized_text = parsed.normalized_text
            version.source_anchors = parsed.anchors
            version.source_links = parsed.source_links
            version.parser_version = settings.parser_version
            version.parser_warnings = parsed.warnings
            version.extraction_metadata = extraction_metadata
        if (
            parsed.recipient_country
            and not letter.country
            and letter.current_version_id == version.id
        ):
            letter.country = parsed.recipient_country
        metrics["stages_completed"] += 1
    if {"chunk", "index", "embed"}.intersection(stages):
        existing = await session.scalar(
            select(DocumentChunk.id).where(
                DocumentChunk.document_version_id == version.id,
                DocumentChunk.chunker_version == settings.chunker_version,
            )
        )
        if not existing:
            for value in build_chunks(version.source_anchors or []):
                session.add(
                    DocumentChunk(
                        document_version_id=version.id,
                        warning_letter_id=letter.id,
                        ordinal=value["ordinal"],
                        section_path=value["section_path"],
                        source_anchor=value["source_anchor"],
                        content=value["content"],
                        token_estimate=value["token_estimate"],
                        drug_subtypes=letter.drug_subtypes,
                        regulatory_references=value["regulatory_references"],
                        chunker_version=settings.chunker_version,
                    )
                )
                metrics["chunks_created"] += 1
        if "embed" in stages:
            await queue_embedding_job(
                session,
                settings,
                warning_letter_id=letter.id,
                document_version_id=version.id,
            )
        metrics["stages_completed"] += len({"chunk", "index", "embed"}.intersection(stages))
    if "summarize" in stages:
        await ensure_derived_content(session, settings, letter)
        metrics["stages_completed"] += 1
    if "validate" in stages:
        await ensure_derived_content(session, settings, letter)
        metrics["stages_completed"] += 1
    if "notify" in stages:
        metrics["stages_completed"] += 1
    if "publish" in stages:
        metrics["stages_completed"] += 1
    return metrics


async def _integrity_sample(
    session: AsyncSession, settings: Settings, job: ProcessingJob
) -> dict[str, int]:
    requested = int((job.payload.get("options") or {}).get("sample_size", 100))
    sample_size = max(1, min(requested, 1_000))
    versions = list(
        (
            await session.scalars(
                select(DocumentVersion)
                .where(DocumentVersion.raw_object_key.is_not(None))
                .order_by(DocumentVersion.created_at.desc())
                .limit(sample_size)
            )
        ).all()
    )
    store = build_object_store(settings)
    failures = sum(
        not store.verify(version.raw_object_key or "", version.raw_sha256) for version in versions
    )
    if failures:
        raise RuntimeError("Immutable source integrity sample failed")
    return {"objects_verified": len(versions), "integrity_failures": failures}


async def process_next_job(
    database: Database,
    settings: Settings,
    *,
    reference_date: date | None = None,
    job_types: tuple[str, ...] | None = None,
    continuation_on_cancel: bool = False,
    single_active: bool = False,
) -> WorkerResult | None:
    effective_reference_date = reference_date or utcnow().date()
    claim = await _claim_next_job(database, job_types=job_types, single_active=single_active)
    if claim is None:
        return None
    job_id = claim.job_id
    lease_stop = asyncio.Event()
    lease_heartbeat = asyncio.create_task(
        _heartbeat_job_lease(database, claim, lease_stop, asyncio.current_task()),
        name=f"worker-lease-{job_id}",
    )

    try:
        async with database.session_factory() as session:
            job = await session.scalar(
                select(ProcessingJob).where(
                    ProcessingJob.id == job_id,
                    ProcessingJob.status == JobStatus.RUNNING.value,
                    ProcessingJob.attempt_count == claim.attempt_count,
                )
            )
            if not job:
                return None
            run = (
                await session.get(IngestionRun, job.ingestion_run_id)
                if job.ingestion_run_id
                else None
            )
            await ensure_default_email_subscription(session, settings)
            # Do not keep the subscription bootstrap write transaction open
            # while a network-bound acquisition or embedding provider call is
            # in flight. In particular, SQLite otherwise blocks another local
            # worker from even observing that this job is already claimed.
            await session.commit()
            requeue_partial = False
            if job.job_type in _DISCOVERY_JOB_TYPES:
                if not run:
                    raise RuntimeError("Discovery job is missing its ingestion run")
                metrics = await _run_discovery(
                    session, settings, job, run, effective_reference_date
                )
                metrics["retired_from_active_corpus"] = await retire_expired_letters(
                    session,
                    settings,
                    reference_date=effective_reference_date,
                )
                run.metrics = metrics
                requeue_partial = bool(metrics.get("failed")) and (
                    job.attempt_count < job.max_attempts
                )
                if requeue_partial:
                    run.status = RunStatus.PENDING.value
                    run.completed_at = None
                else:
                    run.status = (
                        RunStatus.PARTIAL.value
                        if metrics.get("failed")
                        else RunStatus.SUCCEEDED.value
                    )
                    run.completed_at = utcnow()
            elif job.job_type == "reprocess":
                metrics = await _reprocess(session, settings, job)
            elif job.job_type == "embed":
                generator = build_embedding_generator_for_job(settings, job.payload)
                if generator is None:
                    raise RuntimeError("Embedding generation is not configured")
                embedding_metrics = await embed_current_chunks(
                    session,
                    generator=generator,
                    batch_size=settings.embedding_batch_size,
                    chunker_version=generator.chunker_version,
                    warning_letter_id=job.warning_letter_id,
                    document_version_id=job.document_version_id,
                )
                metrics = embedding_metrics.as_dict()
            elif job.job_type == "integrity_sample":
                if not run:
                    raise RuntimeError("Integrity job is missing its ingestion run")
                metrics = await _integrity_sample(session, settings, job)
                run.metrics = metrics
                run.status = RunStatus.SUCCEEDED.value
                run.completed_at = utcnow()
            elif job.job_type == "orchestrate_case_run":
                case_run_id = str((job.payload or {}).get("run_id", ""))
                if not case_run_id:
                    raise RuntimeError("Orchestrator job has no case run binding")
                metrics = await advance_case_run(
                    session,
                    run_id=case_run_id,
                    request_id=f"worker:{job.id}",
                    actor=Principal(
                        subject="orchestrator-worker",
                        roles=frozenset({"service"}),
                        actor_type="service",
                    ),
                )
            else:
                raise RuntimeError(f"Unsupported job type: {job.job_type}")
            await session.refresh(job, attribute_names=["status", "attempt_count"])
            if job.status != JobStatus.RUNNING.value or job.attempt_count != claim.attempt_count:
                raise RuntimeError("Job lease ownership was lost")
            if requeue_partial:
                job.status = JobStatus.PENDING.value
                job.last_error_code = "DiscoveryPartialRetry"
                job.available_at = utcnow() + timedelta(seconds=min(300, 2**job.attempt_count))
                job.completed_at = None
            else:
                job.status = JobStatus.SUCCEEDED.value
                job.completed_at = utcnow()
            await session.commit()
            result_status = job.status
            result_job_id = job.id
            result_run_id = run.id if run else None
        try:
            async with database.session_factory() as session:
                notification_metrics = await dispatch_pending_notifications(session, settings)
        except Exception:
            notification_metrics = {"notifications_dispatch_error": 1}
        metrics = {**metrics, **notification_metrics}
        if result_run_id:
            async with database.session_factory() as session:
                result_run = await session.get(IngestionRun, result_run_id)
                if result_run:
                    result_run.metrics = metrics
                    await session.commit()
        return WorkerResult(result_job_id, result_status, metrics)
    except asyncio.CancelledError:
        # Graceful local/API shutdown must not strand a durable job in RUNNING.
        # A later worker can safely resume because acquisition and ingestion are
        # idempotent and live runs checkpoint after every accepted document.
        async with database.session_factory() as session:
            job = await session.scalar(
                select(ProcessingJob).where(
                    ProcessingJob.id == job_id,
                    ProcessingJob.status == JobStatus.RUNNING.value,
                    ProcessingJob.attempt_count == claim.attempt_count,
                )
            )
            if job:
                job.status = JobStatus.PENDING.value
                job.last_error_code = (
                    "WorkerTimeSlice" if continuation_on_cancel else "WorkerCancelled"
                )
                if continuation_on_cancel:
                    # A bounded slice is a continuation, not a failed attempt.
                    # Keep attempt_count monotonic: it fences stale worker writes.
                    job.max_attempts += 1
                job.completed_at = utcnow()
                job.available_at = utcnow() + timedelta(seconds=2)
                if job.ingestion_run_id:
                    run = await session.get(IngestionRun, job.ingestion_run_id)
                    if run and run.status == RunStatus.RUNNING.value:
                        run.status = RunStatus.PENDING.value
                await session.commit()
        raise
    except Exception as exc:
        async with database.session_factory() as session:
            job = await session.scalar(
                select(ProcessingJob).where(
                    ProcessingJob.id == job_id,
                    ProcessingJob.status == JobStatus.RUNNING.value,
                    ProcessingJob.attempt_count == claim.attempt_count,
                )
            )
            if job:
                job.last_error_code = type(exc).__name__[:120]
                job.completed_at = utcnow()
                exhausted = job.attempt_count >= job.max_attempts
                job.status = JobStatus.DEAD_LETTER.value if exhausted else JobStatus.PENDING.value
                if not exhausted:
                    job.available_at = utcnow() + timedelta(seconds=min(300, 2**job.attempt_count))
                if job.ingestion_run_id:
                    run = await session.get(IngestionRun, job.ingestion_run_id)
                    if run:
                        if exhausted:
                            run.status = RunStatus.FAILED.value
                            run.error_code = job.last_error_code
                            run.completed_at = utcnow()
                        else:
                            run.status = RunStatus.PENDING.value
                            run.completed_at = None
                await session.commit()
            return WorkerResult(job_id, job.status if job else "failed", {})
    finally:
        lease_stop.set()
        await lease_heartbeat


async def run_worker(
    database: Database,
    settings: Settings,
    *,
    once: bool = False,
    poll_seconds: float = 2.0,
) -> int:
    processed = 0
    while True:
        await recover_stale_worker_jobs(database)
        result = await process_next_job(database, settings)
        if result:
            processed += 1
        elif once:
            return processed
        else:
            await asyncio.sleep(poll_seconds)
        if once:
            return processed
