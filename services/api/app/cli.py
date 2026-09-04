from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import uuid
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import select

from app.config import SERVICE_ROOT, Settings, get_settings
from app.database import Database
from app.embedding_store import EmbeddingBackfillError, embed_current_chunks
from app.embeddings import build_embedding_generator
from app.enums import JobStatus, RunStatus
from app.models import IngestionRun, ProcessingJob, WarningLetter
from app.seed import seed_demo
from app.storage import build_object_store
from app.worker import (
    _DISCOVERY_JOB_TYPES,
    DiscoveryCheckpointCorrupt,
    DiscoveryCheckpointTooLarge,
    _load_live_discovery_checkpoint,
    _reprocess,
    process_next_job,
    run_worker,
)


class PartialDiscoveryRequeueError(ValueError):
    pass


class EmbeddingCliError(ValueError):
    pass


def _default_fixture_dir() -> Path:
    local = SERVICE_ROOT / "tests" / "fixtures" / "fda"
    workspace = SERVICE_ROOT.parents[1] / "tests" / "fixtures" / "fda"
    return local if local.is_dir() else workspace


async def _init_db(settings: Settings) -> None:
    database = Database(settings.database_url)
    try:
        await asyncio.to_thread(build_object_store(settings).healthcheck)
        await database.create_schema()
    finally:
        await database.dispose()


async def _seed(settings: Settings, fixture_dir: Path) -> None:
    database = Database(settings.database_url)
    try:
        await database.create_schema()
        async with database.session_factory() as session:
            results = await seed_demo(session, settings, fixture_dir)
        counts: dict[str, int] = {}
        for result in results:
            counts[result.scope_status.value] = counts.get(result.scope_status.value, 0) + 1
        print(json.dumps({"fixtures": len(results), "scope_counts": counts}, indent=2))
    finally:
        await database.dispose()


async def _discover(settings: Settings, fixture_dir: Path | None, source_url: str | None) -> None:
    database = Database(settings.database_url)
    try:
        if settings.auto_create_schema:
            await database.create_schema()
        run_idempotency = f"cli-discovery:{uuid.uuid4()}"
        async with database.session_factory() as session:
            run = IngestionRun(
                run_type="discovery",
                source=source_url or f"fixture:{fixture_dir}",
                status=RunStatus.PENDING.value,
                requested_by="cli",
                idempotency_key=run_idempotency,
                parser_version=settings.parser_version,
                scope_rule_version=settings.drug_scope_rule_version,
                metrics={},
            )
            session.add(run)
            await session.flush()
            session.add(
                ProcessingJob(
                    ingestion_run_id=run.id,
                    job_type="discovery",
                    status=JobStatus.PENDING.value,
                    idempotency_key=f"{run_idempotency}:job",
                    payload={
                        "source": source_url or settings.fda_listing_url,
                        **({"fixture_dir": str(fixture_dir.resolve())} if fixture_dir else {}),
                    },
                )
            )
            await session.commit()
        result = await process_next_job(database, settings)
        print(json.dumps(result.__dict__ if result else {"processed": 0}, indent=2))
    finally:
        await database.dispose()


async def _worker(settings: Settings, once: bool, poll_seconds: float) -> None:
    database = Database(settings.database_url)
    try:
        if settings.auto_create_schema:
            await database.create_schema()
        count = await run_worker(database, settings, once=once, poll_seconds=poll_seconds)
        if once:
            print(json.dumps({"processed": count}))
    finally:
        await database.dispose()


async def _embed_current(
    settings: Settings,
    *,
    limit: int | None,
    letter_id: str | None,
) -> None:
    """Resumably backfill embeddings for current authorized corpus chunks."""

    if limit is not None and limit < 1:
        raise EmbeddingCliError("limit must be at least 1")
    normalized_letter_id = _validated_uuid(letter_id, "letter_id") if letter_id else None
    generator = build_embedding_generator(settings)
    if generator is None:
        raise EmbeddingCliError(
            "Set EMBEDDING_ENABLED=true and provide GEMINI_API_KEY server-side first"
        )
    database = Database(settings.database_url)
    try:
        if settings.auto_create_schema:
            await database.create_schema()
        async with database.session_factory() as session:
            try:
                metrics = await embed_current_chunks(
                    session,
                    generator=generator,
                    batch_size=settings.embedding_batch_size,
                    max_items=limit,
                    warning_letter_id=normalized_letter_id,
                )
            except EmbeddingBackfillError as exc:
                print(
                    json.dumps(
                        {
                            "state": "partial",
                            **exc.metrics.as_dict(),
                            "model_id": generator.model_id,
                            "dimensions": generator.dimensions,
                            "resume": "Run embed-current again; committed chunks are skipped.",
                        },
                        indent=2,
                    )
                )
                raise EmbeddingCliError(str(exc)) from exc
        print(
            json.dumps(
                {
                    "state": "complete",
                    **metrics.as_dict(),
                    "model_id": generator.model_id,
                    "dimensions": generator.dimensions,
                },
                indent=2,
            )
        )
    finally:
        await database.dispose()


def _validated_uuid(value: str, label: str) -> str:
    try:
        return str(uuid.UUID(value))
    except (AttributeError, TypeError, ValueError):
        raise PartialDiscoveryRequeueError(f"{label} must be a valid UUID") from None


async def _requeue_partial_discovery(
    settings: Settings,
    *,
    run_id: str | None = None,
    job_id: str | None = None,
    retry_attempts: int = 3,
) -> dict[str, object]:
    """Requeue one completed partial live discovery without replacing its checkpoint."""

    if (run_id is None) == (job_id is None):
        raise PartialDiscoveryRequeueError("Provide exactly one of run_id or job_id")
    if not 1 <= retry_attempts <= 10:
        raise PartialDiscoveryRequeueError("retry_attempts must be between 1 and 10")

    database = Database(settings.database_url)
    try:
        async with database.session_factory() as session:
            if job_id is not None:
                job = await session.get(ProcessingJob, _validated_uuid(job_id, "job_id"))
                if job is None or job.job_type not in _DISCOVERY_JOB_TYPES:
                    raise PartialDiscoveryRequeueError("Discovery job was not found")
                run = (
                    await session.get(IngestionRun, job.ingestion_run_id)
                    if job.ingestion_run_id
                    else None
                )
            else:
                run = await session.get(IngestionRun, _validated_uuid(run_id or "", "run_id"))
                if run is None:
                    raise PartialDiscoveryRequeueError("Discovery run was not found")
                jobs = list(
                    (
                        await session.scalars(
                            select(ProcessingJob).where(
                                ProcessingJob.ingestion_run_id == run.id,
                                ProcessingJob.job_type.in_(sorted(_DISCOVERY_JOB_TYPES)),
                            )
                        )
                    ).all()
                )
                if len(jobs) != 1:
                    raise PartialDiscoveryRequeueError(
                        "Discovery run must have exactly one durable discovery job"
                    )
                job = jobs[0]

            if run is None or job.ingestion_run_id != run.id:
                raise PartialDiscoveryRequeueError("Discovery job has no matching ingestion run")

            source = str((job.payload or {}).get("source") or run.source)
            source_url = source if source.startswith("https://") else settings.fda_listing_url
            try:
                _, _, failed_hashes, _, checkpoint_valid = _load_live_discovery_checkpoint(
                    job, source_url
                )
            except (DiscoveryCheckpointCorrupt, DiscoveryCheckpointTooLarge) as exc:
                raise PartialDiscoveryRequeueError(
                    "Discovery job has an invalid live discovery checkpoint"
                ) from exc
            if not checkpoint_valid:
                raise PartialDiscoveryRequeueError(
                    "Discovery job has no valid live discovery checkpoint"
                )
            if not failed_hashes:
                raise PartialDiscoveryRequeueError(
                    "Discovery checkpoint has no unresolved candidate failures"
                )

            if run.status != RunStatus.PARTIAL.value:
                raise PartialDiscoveryRequeueError("Discovery run is not PARTIAL")
            if job.status != JobStatus.SUCCEEDED.value:
                raise PartialDiscoveryRequeueError(
                    "PARTIAL discovery job must be succeeded before it can be requeued"
                )

            identity = hashlib.sha256(
                (
                    f"{job.id}:{settings.parser_version}:"
                    f"{settings.drug_scope_rule_version}"
                ).encode()
            ).hexdigest()[:32]
            resume_idempotency = f"cli-partial-discovery-resume:{identity}"
            existing_run = await session.scalar(
                select(IngestionRun).where(
                    IngestionRun.idempotency_key == resume_idempotency
                )
            )
            if existing_run is not None:
                existing_job = await session.scalar(
                    select(ProcessingJob).where(
                        ProcessingJob.ingestion_run_id == existing_run.id,
                        ProcessingJob.idempotency_key == f"{resume_idempotency}:job",
                    )
                )
                if existing_job is None:
                    raise PartialDiscoveryRequeueError(
                        "Existing resume run is missing its deterministic job"
                    )
                return {
                    "state": "already_created",
                    "source_run_id": run.id,
                    "source_job_id": job.id,
                    "run_id": existing_run.id,
                    "job_id": existing_job.id,
                    "job_status": existing_job.status,
                    "unresolved_failures": len(failed_hashes),
                    "attempts_remaining": max(
                        0, existing_job.max_attempts - existing_job.attempt_count
                    ),
                }

            resumed_run = IngestionRun(
                run_type=run.run_type,
                source=run.source,
                status=RunStatus.PENDING.value,
                requested_by="cli:partial-discovery-resume",
                idempotency_key=resume_idempotency,
                parser_version=settings.parser_version,
                scope_rule_version=settings.drug_scope_rule_version,
                metrics={},
            )
            session.add(resumed_run)
            await session.flush()
            resumed_payload = copy.deepcopy(job.payload or {})
            resumed_payload["resumed_from_run_id"] = run.id
            resumed_payload["resumed_from_job_id"] = job.id
            resumed_payload["resumed_from_parser_version"] = run.parser_version
            resumed_payload["resumed_from_scope_rule_version"] = run.scope_rule_version
            resumed_job = ProcessingJob(
                ingestion_run_id=resumed_run.id,
                job_type=job.job_type,
                status=JobStatus.PENDING.value,
                idempotency_key=f"{resume_idempotency}:job",
                payload=resumed_payload,
                max_attempts=retry_attempts,
            )
            session.add(resumed_job)
            await session.commit()
            return {
                "state": "requeued",
                "source_run_id": run.id,
                "source_job_id": job.id,
                "run_id": resumed_run.id,
                "job_id": resumed_job.id,
                "job_status": resumed_job.status,
                "unresolved_failures": len(failed_hashes),
                "attempts_remaining": resumed_job.max_attempts,
            }
    finally:
        await database.dispose()


async def _print_requeue_partial_discovery(
    settings: Settings,
    *,
    run_id: str | None,
    job_id: str | None,
    retry_attempts: int,
) -> None:
    result = await _requeue_partial_discovery(
        settings,
        run_id=run_id,
        job_id=job_id,
        retry_attempts=retry_attempts,
    )
    print(json.dumps(result, indent=2))


async def _reparse_current(settings: Settings) -> None:
    """Rebuild current parsed representations from retained immutable source objects."""

    database = Database(settings.database_url)
    updated = 0
    recovered_countries = 0
    failed = 0
    try:
        if settings.auto_create_schema:
            await database.create_schema()
        async with database.session_factory() as session:
            targets = list(
                (
                    await session.execute(
                        select(
                            WarningLetter.id,
                            WarningLetter.current_version_id,
                            WarningLetter.country,
                        ).where(
                            WarningLetter.current_in_scope.is_(True),
                            WarningLetter.current_version_id.is_not(None),
                        )
                    )
                ).all()
            )
            for letter_id, version_id, prior_country in targets:
                try:
                    async with session.begin_nested():
                        await _reprocess(
                            session,
                            settings,
                            SimpleNamespace(
                                warning_letter_id=letter_id,
                                document_version_id=version_id,
                                payload={"stages": ["parse"]},
                            ),
                        )
                        refreshed = await session.get(WarningLetter, letter_id)
                        if not prior_country and refreshed and refreshed.country:
                            recovered_countries += 1
                    updated += 1
                except RuntimeError:
                    failed += 1
            await session.commit()
        print(
            json.dumps(
                {
                    "current_records": len(targets),
                    "reparsed": updated,
                    "recipient_countries_recovered": recovered_countries,
                    "failed": failed,
                    "parser_version": settings.parser_version,
                },
                indent=2,
            )
        )
    finally:
        await database.dispose()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fda-intel", description="FDA Drug warning-letter intelligence service tools"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db", help="Create local development database tables")

    seed = commands.add_parser("seed-demo", help="Load the synthetic FDA fixture corpus")
    seed.add_argument("--fixture-dir", type=Path, default=_default_fixture_dir())

    discover = commands.add_parser("discover", help="Run one bounded discovery cycle")
    source = discover.add_mutually_exclusive_group()
    source.add_argument("--fixture-dir", type=Path)
    source.add_argument("--source-url")

    worker = commands.add_parser("worker", help="Process durable jobs")
    worker.add_argument("--once", action="store_true")
    worker.add_argument("--poll-seconds", type=float, default=2.0)
    embed = commands.add_parser(
        "embed-current",
        help="Resumably embed current in-scope Drug chunks into the configured cloud/local DB",
    )
    embed.add_argument("--limit", type=int)
    embed.add_argument("--letter-id")
    commands.add_parser(
        "reparse-current",
        help="Reparse current in-scope letters from retained immutable source objects",
    )
    requeue = commands.add_parser(
        "requeue-partial-discovery",
        help="Retry a PARTIAL live discovery while preserving its durable checkpoint",
    )
    target = requeue.add_mutually_exclusive_group(required=True)
    target.add_argument("--run-id")
    target.add_argument("--job-id")
    requeue.add_argument("--retry-attempts", type=int, default=3)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    settings = get_settings()
    if args.command == "init-db":
        asyncio.run(_init_db(settings))
    elif args.command == "seed-demo":
        asyncio.run(_seed(settings, args.fixture_dir))
    elif args.command == "discover":
        fixture_dir = args.fixture_dir
        if not fixture_dir and not args.source_url:
            fixture_dir = _default_fixture_dir()
        asyncio.run(_discover(settings, fixture_dir, args.source_url))
    elif args.command == "worker":
        asyncio.run(_worker(settings, args.once, args.poll_seconds))
    elif args.command == "embed-current":
        try:
            asyncio.run(
                _embed_current(
                    settings,
                    limit=args.limit,
                    letter_id=args.letter_id,
                )
            )
        except (EmbeddingCliError, PartialDiscoveryRequeueError) as exc:
            parser.error(str(exc))
    elif args.command == "reparse-current":
        asyncio.run(_reparse_current(settings))
    elif args.command == "requeue-partial-discovery":
        try:
            asyncio.run(
                _print_requeue_partial_discovery(
                    settings,
                    run_id=args.run_id,
                    job_id=args.job_id,
                    retry_attempts=args.retry_attempts,
                )
            )
        except PartialDiscoveryRequeueError as exc:
            parser.error(str(exc))


if __name__ == "__main__":
    main()
