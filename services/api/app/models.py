from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.enums import (
    DocumentType,
    JobStatus,
    ReviewState,
    RunStatus,
    ScopeStatus,
)
from app.vector import PortableVector


def new_uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class AgentCaseStatus(StrEnum):
    DRAFT = "DRAFT"
    PLANNING = "PLANNING"
    AWAITING_PLAN_APPROVAL = "AWAITING_PLAN_APPROVAL"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING_FOR_INPUT = "WAITING_FOR_INPUT"
    WAITING_FOR_REVIEW = "WAITING_FOR_REVIEW"
    NEEDS_REVISION = "NEEDS_REVISION"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    STALE = "STALE"


class AgentRunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class RegistryReleaseStatus(StrEnum):
    DRAFT = "DRAFT"
    DEVELOPMENT = "DEVELOPMENT"
    TESTING = "TESTING"
    STAGING = "STAGING"
    APPROVED = "APPROVED"
    PRODUCTION = "PRODUCTION"
    SUSPENDED = "SUSPENDED"
    RETIRED = "RETIRED"


class PolicyEffect(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


class ArtifactVersionStatus(StrEnum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ToolInvocationStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    DENIED = "DENIED"
    FAILED = "FAILED"


class AgentInvocationStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class InternalAssetVersionStatus(StrEnum):
    DRAFT = "DRAFT"
    EFFECTIVE = "EFFECTIVE"
    OBSOLETE = "OBSOLETE"
    RETIRED = "RETIRED"


class AssetRelationStatus(StrEnum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ImpactHypothesisStatus(StrEnum):
    PROPOSED = "PROPOSED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class VerificationStatus(StrEnum):
    PASS = "PASS"
    REVISE = "REVISE"
    BLOCK = "BLOCK"


class EvaluationRunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"


class ReleaseDecisionStatus(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class WarningLetter(TimestampMixin, Base):
    __tablename__ = "warning_letters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    canonical_url: Mapped[str] = mapped_column(String(2048), unique=True, nullable=False)
    company_name: Mapped[str] = mapped_column(String(500), nullable=False)
    country: Mapped[str | None] = mapped_column(String(120))
    marcs_cms_number: Mapped[str | None] = mapped_column(String(80), index=True)
    fda_reference_number: Mapped[str | None] = mapped_column(String(120))
    subject: Mapped[str | None] = mapped_column(String(1000))
    posted_date: Mapped[date | None] = mapped_column(Date, index=True)
    issue_date: Mapped[date | None] = mapped_column(Date, index=True)
    issuing_offices: Mapped[list[str]] = mapped_column(JSON, default=list)
    drug_subtypes: Mapped[list[str]] = mapped_column(JSON, default=list)
    lifecycle_status: Mapped[str] = mapped_column(String(40), default="active", index=True)

    fda_product_raw: Mapped[list[str]] = mapped_column(JSON, default=list)
    normalized_product_classes: Mapped[list[str]] = mapped_column(JSON, default=list)
    scope_status: Mapped[str] = mapped_column(
        String(32), default=ScopeStatus.UNVERIFIED.value, index=True
    )
    scope_rule_version: Mapped[str | None] = mapped_column(String(80))
    scope_source_anchor: Mapped[str | None] = mapped_column(String(255))
    scope_decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_in_scope_version_id: Mapped[str | None] = mapped_column(String(36))
    current_version_id: Mapped[str | None] = mapped_column(String(36))
    current_in_scope: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    documents: Mapped[list[Document]] = relationship(
        back_populates="warning_letter", cascade="all, delete-orphan"
    )
    events: Mapped[list[ChangeEvent]] = relationship(
        back_populates="warning_letter", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_warning_letters_scope_posted", "current_in_scope", "posted_date"),)


class Document(TimestampMixin, Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    warning_letter_id: Mapped[str] = mapped_column(
        ForeignKey("warning_letters.id", ondelete="CASCADE"), index=True
    )
    parent_document_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    document_type: Mapped[str] = mapped_column(
        String(32), default=DocumentType.WARNING_LETTER.value, index=True
    )
    canonical_url: Mapped[str] = mapped_column(String(2048), unique=True, nullable=False)
    title: Mapped[str | None] = mapped_column(String(1000))
    issue_date: Mapped[date | None] = mapped_column(Date)
    current_version_id: Mapped[str | None] = mapped_column(String(36))
    current_in_scope: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    source_available: Mapped[bool] = mapped_column(Boolean, default=True)

    warning_letter: Mapped[WarningLetter] = relationship(back_populates="documents")
    parent: Mapped[Document | None] = relationship(remote_side="Document.id")
    versions: Mapped[list[DocumentVersion]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_object_key: Mapped[str | None] = mapped_column(String(1024))
    raw_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    normalized_markdown: Mapped[str | None] = mapped_column(Text)
    normalized_text: Mapped[str | None] = mapped_column(Text)
    source_anchors: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    source_links: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    http_provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    parser_version: Mapped[str] = mapped_column(String(80), nullable=False)
    parser_warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    fda_product_raw: Mapped[list[str]] = mapped_column(JSON, default=list)
    normalized_product_classes: Mapped[list[str]] = mapped_column(JSON, default=list)
    scope_status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    extraction_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    document: Mapped[Document] = relationship(back_populates="versions")

    __table_args__ = (
        UniqueConstraint(
            "document_id", "version_number", name="uq_document_versions_document_version"
        ),
        UniqueConstraint(
            "document_id", "canonical_hash", name="uq_document_versions_document_hash"
        ),
    )


class ScopeDecision(Base):
    __tablename__ = "scope_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    warning_letter_id: Mapped[str] = mapped_column(
        ForeignKey("warning_letters.id", ondelete="CASCADE"), index=True
    )
    source_version_id: Mapped[str] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), index=True
    )
    canonical_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    fda_product_raw: Mapped[list[str]] = mapped_column(JSON, default=list)
    normalized_product_classes: Mapped[list[str]] = mapped_column(JSON, default=list)
    scope_status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    scope_rule_version: Mapped[str] = mapped_column(String(80), nullable=False)
    scope_source_anchor: Mapped[str | None] = mapped_column(String(255))
    decision_method: Mapped[str] = mapped_column(
        String(80), default="deterministic_parser", nullable=False
    )
    decision_fingerprint: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    rationale: Mapped[str] = mapped_column(String(500), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChangeEvent(Base):
    __tablename__ = "change_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    warning_letter_id: Mapped[str] = mapped_column(
        ForeignKey("warning_letters.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    source_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("document_versions.id", ondelete="SET NULL")
    )
    previous_source_version_id: Mapped[str | None] = mapped_column(String(36))
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    before_state: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after_state: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    deduplication_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notification_state: Mapped[str] = mapped_column(String(32), default="pending")

    warning_letter: Mapped[WarningLetter] = relationship(back_populates="events")


class AiSummary(Base):
    __tablename__ = "ai_summaries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    document_version_id: Mapped[str] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), index=True
    )
    parent_summary_id: Mapped[str | None] = mapped_column(
        ForeignKey("ai_summaries.id", ondelete="SET NULL")
    )
    revision: Mapped[int] = mapped_column(Integer, default=1)
    language: Mapped[str] = mapped_column(String(12), default="en")
    executive_summary: Mapped[str] = mapped_column(Text, nullable=False)
    structured_output: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    validation_report: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    provider: Mapped[str] = mapped_column(String(120), default="deterministic-local")
    model_id: Mapped[str] = mapped_column(String(160), default="none")
    prompt_version: Mapped[str] = mapped_column(String(80), default="not-applicable")
    schema_version: Mapped[str] = mapped_column(String(80), default="summary-schema-v1")
    taxonomy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    review_state: Mapped[str] = mapped_column(
        String(32), default=ReviewState.PENDING.value, index=True
    )
    reviewer_id: Mapped[str | None] = mapped_column(String(255))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("document_version_id", "language", "revision"),)


class DocumentTranslation(Base):
    """Immutable, validated translation cache for one retained FDA source version."""

    __tablename__ = "document_translations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    document_version_id: Mapped[str] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), index=True
    )
    language: Mapped[str] = mapped_column(String(12), default="ko", index=True)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    translated_sections: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    validation_report: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    provider: Mapped[str] = mapped_column(String(120), nullable=False)
    model_id: Mapped[str] = mapped_column(String(160), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(80), nullable=False)
    schema_version: Mapped[str] = mapped_column(
        String(80), default="document-translation-v2", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        UniqueConstraint(
            "document_version_id",
            "language",
            "source_hash",
            "model_id",
            "prompt_version",
            name="uq_document_translation_cache_key",
        ),
    )


class Finding(Base):
    __tablename__ = "violations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    document_version_id: Mapped[str] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), index=True
    )
    summary_id: Mapped[str | None] = mapped_column(
        ForeignKey("ai_summaries.id", ondelete="SET NULL"), index=True
    )
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    categories: Mapped[list[str]] = mapped_column(JSON, default=list)
    process_lenses: Mapped[list[str]] = mapped_column(JSON, default=list)
    finding_text: Mapped[str] = mapped_column(Text, nullable=False)
    regulatory_references: Mapped[list[str]] = mapped_column(JSON, default=list)
    evidence: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    fda_requested_actions: Mapped[list[str]] = mapped_column(JSON, default=list)
    comparison_points: Mapped[list[str]] = mapped_column(JSON, default=list)
    attention_level: Mapped[str | None] = mapped_column(String(32))
    confidence: Mapped[float | None] = mapped_column(Float)
    review_state: Mapped[str] = mapped_column(String(32), default=ReviewState.PENDING.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    document_version_id: Mapped[str] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), index=True
    )
    warning_letter_id: Mapped[str] = mapped_column(
        ForeignKey("warning_letters.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    section_path: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_anchor: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_estimate: Mapped[int] = mapped_column(Integer, nullable=False)
    drug_subtypes: Mapped[list[str]] = mapped_column(JSON, default=list)
    categories: Mapped[list[str]] = mapped_column(JSON, default=list)
    regulatory_references: Mapped[list[str]] = mapped_column(JSON, default=list)
    corpus_id: Mapped[str] = mapped_column(String(80), default="fda-drugs", index=True)
    acl: Mapped[dict[str, Any]] = mapped_column(JSON, default=lambda: {"roles": ["viewer"]})
    chunker_version: Mapped[str] = mapped_column(String(80), nullable=False)
    # Kept only for backward compatibility with early local databases. New embeddings are
    # immutable/versioned rows in ``chunk_embeddings`` so PostgreSQL can use pgvector without
    # making the source chunk itself provider-specific.
    embedding: Mapped[list[float] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    embeddings: Mapped[list[ChunkEmbedding]] = relationship(
        back_populates="document_chunk",
        cascade="all, delete-orphan",
    )

    __table_args__ = (UniqueConstraint("document_version_id", "chunker_version", "ordinal"),)


class ChunkEmbedding(Base):
    """A versioned embedding for one immutable source chunk.

    PostgreSQL resolves ``PortableVector`` to pgvector's ``vector(1536)``. The local SQLite
    profile stores the same values as JSON, which keeps development and tests dependency-free.
    A model/content change creates a new row instead of silently overwriting prior provenance.
    """

    __tablename__ = "chunk_embeddings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    document_chunk_id: Mapped[str] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model_id: Mapped[str] = mapped_column(String(120), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False, default=1_536)
    input_schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_input_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(PortableVector(1_536), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    document_chunk: Mapped[DocumentChunk] = relationship(back_populates="embeddings")

    __table_args__ = (
        UniqueConstraint(
            "document_chunk_id",
            "provider",
            "model_id",
            "dimensions",
            "input_schema_version",
            "content_sha256",
            "provider_input_sha256",
            name="uq_chunk_embedding_space_input",
        ),
        Index(
            "ix_chunk_embeddings_space",
            "provider",
            "model_id",
            "dimensions",
            "input_schema_version",
        ),
    )


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    summary_id: Mapped[str] = mapped_column(
        ForeignKey("ai_summaries.id", ondelete="CASCADE"), index=True
    )
    resulting_summary_id: Mapped[str | None] = mapped_column(
        ForeignKey("ai_summaries.id", ondelete="SET NULL")
    )
    reviewer_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    before_value: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    after_value: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    run_type: Mapped[str] = mapped_column(String(40), default="discovery")
    source: Mapped[str] = mapped_column(String(2048), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=RunStatus.PENDING.value, index=True)
    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    parser_version: Mapped[str] = mapped_column(String(80), nullable=False)
    scope_rule_version: Mapped[str] = mapped_column(String(80), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    ingestion_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("ingestion_runs.id", ondelete="SET NULL"), index=True
    )
    warning_letter_id: Mapped[str | None] = mapped_column(
        ForeignKey("warning_letters.id", ondelete="CASCADE"), index=True
    )
    document_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), index=True
    )
    job_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default=JobStatus.PENDING.value, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Subscription(TimestampMixin, Base):
    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    owner_id: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(1_000), default="", nullable=False)
    criteria: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    frequency: Mapped[str] = mapped_column(String(20), default="immediate")
    channel: Mapped[str] = mapped_column(String(20), default="email")
    destination_id: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_subscriptions_owner_name"),)


class NotificationDelivery(Base):
    """Immutable-address notification outbox and delivery audit record."""

    __tablename__ = "notification_deliveries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    change_event_id: Mapped[str] = mapped_column(
        ForeignKey("change_events.id", ondelete="CASCADE"), index=True
    )
    subscription_id: Mapped[str] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    destination_identifier: Mapped[str] = mapped_column(String(320), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(500))
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(120))
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    request_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    object_type: Mapped[str] = mapped_column(String(80), nullable=False)
    object_id: Mapped[str | None] = mapped_column(String(255))
    before_hash: Mapped[str | None] = mapped_column(String(64))
    after_hash: Mapped[str | None] = mapped_column(String(64))
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(1000))
    application_version: Mapped[str] = mapped_column(String(80), nullable=False)
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class RagQuery(Base):
    __tablename__ = "rag_queries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    actor_id: Mapped[str] = mapped_column(String(255), index=True)
    query_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    query_length: Mapped[int] = mapped_column(Integer, nullable=False)
    language: Mapped[str] = mapped_column(String(12), default="auto")
    filters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    retrieved_chunk_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    evidence_sufficient: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChatThread(TimestampMixin, Base):
    """A server-owned conversation boundary.

    ``owner_subject`` is always copied from the verified OIDC/development principal.  There is
    intentionally no password, provider token, or client-controlled owner field in this table.
    """

    __tablename__ = "chat_threads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    owner_subject: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="새 대화")
    model_preference: Mapped[str] = mapped_column(String(20), nullable=False, default="auto")
    retrieval_preference: Mapped[str] = mapped_column(String(20), nullable=False, default="auto")
    active_letter_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="ChatMessage.sequence",
    )
    focus: Mapped[ChatThreadFocus | None] = relationship(
        back_populates="thread",
        cascade="all, delete-orphan",
        uselist=False,
        lazy="selectin",
    )

    __table_args__ = (Index("ix_chat_threads_owner_activity", "owner_subject", "last_message_at"),)


class ChatMessage(TimestampMixin, Base):
    """Persisted chat turn containing only user-visible output and stable routing metadata."""

    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    thread_id: Mapped[str] = mapped_column(
        ForeignKey("chat_threads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="completed")
    client_message_id: Mapped[str | None] = mapped_column(String(100))
    in_reply_to_id: Mapped[str | None] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="SET NULL"), index=True
    )
    rag_query_id: Mapped[str | None] = mapped_column(
        ForeignKey("rag_queries.id", ondelete="SET NULL"), index=True
    )
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    route_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    model_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    thread: Mapped[ChatThread] = relationship(back_populates="messages")

    __table_args__ = (
        UniqueConstraint("thread_id", "sequence", name="uq_chat_messages_thread_sequence"),
        UniqueConstraint(
            "thread_id",
            "client_message_id",
            name="uq_chat_messages_thread_client_message",
        ),
        Index("ix_chat_messages_thread_created", "thread_id", "created_at"),
    )


class ChatThreadFocus(Base):
    """Server-resolved provenance for the one document currently anchoring a chat.

    The client selects a citation chunk from an existing assistant answer. The API resolves
    and persists every parent identifier instead of trusting client-supplied document scope.
    """

    __tablename__ = "chat_thread_focus"

    thread_id: Mapped[str] = mapped_column(
        ForeignKey("chat_threads.id", ondelete="CASCADE"), primary_key=True
    )
    warning_letter_id: Mapped[str] = mapped_column(
        ForeignKey("warning_letters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_version_id: Mapped[str] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_chunk_id: Mapped[str] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_message_id: Mapped[str] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    selected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    thread: Mapped[ChatThread] = relationship(back_populates="focus")

    __table_args__ = (
        Index(
            "ix_chat_thread_focus_document_version",
            "document_version_id",
            "thread_id",
        ),
    )


class DiscoverySnapshot(Base):
    __tablename__ = "discovery_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    ingestion_run_id: Mapped[str] = mapped_column(
        ForeignKey("ingestion_runs.id", ondelete="CASCADE"), index=True
    )
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    final_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    redirect_chain: Mapped[list[str]] = mapped_column(JSON, default=list)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    etag: Mapped[str | None] = mapped_column(String(255))
    last_modified: Mapped[str | None] = mapped_column(String(255))
    detected_columns: Mapped[list[str]] = mapped_column(JSON, default=list)
    schema_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    parser_version: Mapped[str] = mapped_column(String(80), nullable=False)
    source_client_version: Mapped[str] = mapped_column(String(80), nullable=False)
    http_anomalies: Mapped[list[str]] = mapped_column(JSON, default=list)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("source_url", "sha256"),)


class AgentVersion(Base):
    """One content-addressed, immutable agent manifest version.

    Release status is deliberately separate from manifest identity so a deployment can be
    suspended without rewriting the reviewed definition.
    """

    __tablename__ = "agent_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    agent_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    release_status: Mapped[str] = mapped_column(
        String(20), default=RegistryReleaseStatus.DRAFT.value, nullable=False, index=True
    )
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        UniqueConstraint("agent_key", "version", name="uq_agent_versions_key_version"),
        UniqueConstraint(
            "agent_key", "manifest_sha256", name="uq_agent_versions_key_manifest_hash"
        ),
        CheckConstraint("length(manifest_sha256) = 64", name="agent_versions_manifest_hash_length"),
        CheckConstraint(
            "release_status IN ('DRAFT', 'DEVELOPMENT', 'TESTING', 'STAGING', "
            "'APPROVED', 'PRODUCTION', 'SUSPENDED', 'RETIRED')",
            name="agent_versions_release_status",
        ),
    )


class SkillVersion(Base):
    """One content-addressed, immutable skill manifest version."""

    __tablename__ = "skill_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    skill_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    release_status: Mapped[str] = mapped_column(
        String(20), default=RegistryReleaseStatus.DRAFT.value, nullable=False, index=True
    )
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        UniqueConstraint("skill_key", "version", name="uq_skill_versions_key_version"),
        UniqueConstraint(
            "skill_key", "manifest_sha256", name="uq_skill_versions_key_manifest_hash"
        ),
        CheckConstraint("length(manifest_sha256) = 64", name="skill_versions_manifest_hash_length"),
        CheckConstraint(
            "release_status IN ('DRAFT', 'DEVELOPMENT', 'TESTING', 'STAGING', "
            "'APPROVED', 'PRODUCTION', 'SUSPENDED', 'RETIRED')",
            name="skill_versions_release_status",
        ),
    )


class ToolVersion(Base):
    """One content-addressed tool contract; the runtime still authorizes every invocation."""

    __tablename__ = "tool_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    tool_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    server_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    risk_class: Mapped[str] = mapped_column(String(40), nullable=False, default="READ_ONLY_PUBLIC")
    side_effecting: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    release_status: Mapped[str] = mapped_column(
        String(20), default=RegistryReleaseStatus.DRAFT.value, nullable=False, index=True
    )
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        UniqueConstraint("tool_key", "version", name="uq_tool_versions_key_version"),
        UniqueConstraint("tool_key", "manifest_sha256", name="uq_tool_versions_key_manifest_hash"),
        CheckConstraint("length(manifest_sha256) = 64", name="tool_versions_manifest_hash_length"),
        CheckConstraint(
            "release_status IN ('DRAFT', 'DEVELOPMENT', 'TESTING', 'STAGING', "
            "'APPROVED', 'PRODUCTION', 'SUSPENDED', 'RETIRED')",
            name="tool_versions_release_status",
        ),
    )


class WorkflowTemplateVersion(Base):
    """Immutable, releasable workflow template loaded by the orchestrator."""

    __tablename__ = "workflow_template_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    workflow_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    release_status: Mapped[str] = mapped_column(
        String(20), default=RegistryReleaseStatus.DRAFT.value, nullable=False, index=True
    )
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "workflow_key", "version", name="uq_workflow_template_versions_key_version"
        ),
        UniqueConstraint(
            "workflow_key",
            "manifest_sha256",
            name="uq_workflow_template_versions_key_manifest_hash",
        ),
        CheckConstraint(
            "length(manifest_sha256) = 64",
            name="workflow_template_versions_manifest_hash_length",
        ),
        CheckConstraint(
            "release_status IN ('DRAFT', 'DEVELOPMENT', 'TESTING', 'STAGING', "
            "'APPROVED', 'PRODUCTION', 'SUSPENDED', 'RETIRED')",
            name="workflow_template_versions_release_status",
        ),
    )


class Case(TimestampMixin, Base):
    """Mutable header whose state hash covers only plan-relevant objective and source scope.

    Status changes and case events do not change ``current_state_hash``. Objective, workflow,
    or source-pin changes do, making approvals for older plan-input state safely stale.
    """

    __tablename__ = "agent_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=AgentCaseStatus.DRAFT.value, nullable=False, index=True
    )
    owner_subject: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    workflow_key: Mapped[str] = mapped_column(String(160), nullable=False)
    current_state_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    sources: Mapped[list[CaseSource]] = relationship(
        back_populates="case", order_by="CaseSource.created_at", passive_deletes=True
    )
    events: Mapped[list[CaseEvent]] = relationship(
        back_populates="case", order_by="CaseEvent.sequence", passive_deletes=True
    )
    plans: Mapped[list[CasePlan]] = relationship(
        back_populates="case", order_by="CasePlan.version", passive_deletes=True
    )
    runs: Mapped[list[CaseRun]] = relationship(
        back_populates="case", order_by="CaseRun.created_at", passive_deletes=True
    )
    approvals: Mapped[list[ApprovalRequest]] = relationship(
        back_populates="case", order_by="ApprovalRequest.created_at", passive_deletes=True
    )
    policy_decisions: Mapped[list[PolicyDecision]] = relationship(
        back_populates="case", order_by="PolicyDecision.created_at", passive_deletes=True
    )
    artifacts: Mapped[list[Artifact]] = relationship(
        back_populates="case", order_by="Artifact.created_at", passive_deletes=True
    )
    tool_invocations: Mapped[list[ToolInvocation]] = relationship(
        back_populates="case", order_by="ToolInvocation.created_at", passive_deletes=True
    )
    impact_hypotheses: Mapped[list[ImpactHypothesis]] = relationship(
        back_populates="case", order_by="ImpactHypothesis.created_at", passive_deletes=True
    )
    verification_reports: Mapped[list[VerificationReport]] = relationship(
        back_populates="case", order_by="VerificationReport.created_at", passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint("length(current_state_hash) = 64", name="agent_cases_state_hash_length"),
        CheckConstraint(
            "status IN ('DRAFT', 'PLANNING', 'AWAITING_PLAN_APPROVAL', 'READY', "
            "'RUNNING', 'WAITING_FOR_INPUT', 'WAITING_FOR_REVIEW', 'NEEDS_REVISION', "
            "'COMPLETED', 'BLOCKED', 'FAILED', 'CANCELLED', 'STALE')",
            name="agent_cases_status",
        ),
        Index("ix_agent_cases_owner_status", "owner_subject", "status"),
    )


class CaseSource(Base):
    """An immutable pin to one exact retained source version and hash."""

    __tablename__ = "case_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("agent_cases.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    document_version_id: Mapped[str] = mapped_column(
        ForeignKey("document_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_role: Mapped[str] = mapped_column(String(40), nullable=False, default="PRIMARY")
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    pinned_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    case: Mapped[Case] = relationship(back_populates="sources")
    document_version: Mapped[DocumentVersion] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "case_id",
            "document_version_id",
            "source_role",
            name="uq_case_sources_case_version_role",
        ),
        UniqueConstraint(
            "id",
            "case_id",
            "document_version_id",
            "source_sha256",
            name="uq_case_sources_bound_identity",
        ),
        CheckConstraint("length(source_sha256) = 64", name="case_sources_hash_length"),
    )


class CaseEvent(Base):
    """Append-only, hash-chain-capable history for one case."""

    __tablename__ = "case_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("agent_cases.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    request_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    previous_event_hash: Mapped[str | None] = mapped_column(String(64))
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    state_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )

    case: Mapped[Case] = relationship(back_populates="events")

    __table_args__ = (
        UniqueConstraint("case_id", "sequence", name="uq_case_events_case_sequence"),
        UniqueConstraint("case_id", "idempotency_key", name="uq_case_events_case_idempotency"),
        CheckConstraint("sequence >= 1", name="case_events_positive_sequence"),
        CheckConstraint("length(event_hash) = 64", name="case_events_event_hash_length"),
        CheckConstraint("length(state_hash) = 64", name="case_events_state_hash_length"),
        CheckConstraint(
            "previous_event_hash IS NULL OR length(previous_event_hash) = 64",
            name="case_events_previous_hash_length",
        ),
        Index("ix_case_events_case_occurred", "case_id", "occurred_at"),
    )


class CasePlan(Base):
    """Canonical immutable plan version generated from one exact case state."""

    __tablename__ = "case_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("agent_cases.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    plan_schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    plan_definition: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    plan_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    based_on_state_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    workflow_template_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("workflow_template_versions.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    case: Mapped[Case] = relationship(back_populates="plans")
    steps: Mapped[list[CasePlanStep]] = relationship(
        back_populates="plan", order_by="CasePlanStep.position", passive_deletes=True
    )

    __table_args__ = (
        UniqueConstraint("case_id", "version", name="uq_case_plans_case_version"),
        UniqueConstraint("case_id", "plan_sha256", name="uq_case_plans_case_hash"),
        UniqueConstraint(
            "id",
            "case_id",
            "version",
            "plan_sha256",
            "based_on_state_hash",
            name="uq_case_plans_bound_identity",
        ),
        CheckConstraint("version >= 1", name="case_plans_positive_version"),
        CheckConstraint("length(plan_sha256) = 64", name="case_plans_hash_length"),
        CheckConstraint("length(based_on_state_hash) = 64", name="case_plans_state_hash_length"),
    )


class CasePlanStep(Base):
    """Immutable typed projection of one canonical plan step."""

    __tablename__ = "case_plan_steps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    plan_id: Mapped[str] = mapped_column(
        ForeignKey("case_plans.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    step_key: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    agent_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_versions.id", ondelete="RESTRICT"), index=True
    )
    depends_on: Mapped[list[str]] = mapped_column(JSON, default=list)
    skill_version_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    tool_version_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    output_schema_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(40), nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    limits: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    plan: Mapped[CasePlan] = relationship(back_populates="steps")
    agent_version: Mapped[AgentVersion | None] = relationship()

    __table_args__ = (
        UniqueConstraint("plan_id", "position", name="uq_case_plan_steps_plan_position"),
        UniqueConstraint("plan_id", "step_key", name="uq_case_plan_steps_plan_key"),
        CheckConstraint("position >= 1", name="case_plan_steps_positive_position"),
    )


class CaseRun(Base):
    """Durable execution state bound to the exact immutable plan it executes."""

    __tablename__ = "case_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("agent_cases.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    plan_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    plan_version: Mapped[int] = mapped_column(Integer, nullable=False)
    plan_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    bound_state_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=AgentRunStatus.PENDING.value, nullable=False, index=True
    )
    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    checkpoint: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(120))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    case: Mapped[Case] = relationship(back_populates="runs")
    events: Mapped[list[RunEvent]] = relationship(
        back_populates="run", order_by="RunEvent.sequence", passive_deletes=True
    )
    invocations: Mapped[list[AgentInvocation]] = relationship(
        back_populates="run", order_by="AgentInvocation.created_at", passive_deletes=True
    )
    approvals: Mapped[list[ApprovalRequest]] = relationship(
        back_populates="run",
        order_by="ApprovalRequest.created_at",
        passive_deletes=True,
        overlaps="approvals,case",
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["plan_id", "case_id", "plan_version", "plan_sha256", "bound_state_hash"],
            [
                "case_plans.id",
                "case_plans.case_id",
                "case_plans.version",
                "case_plans.plan_sha256",
                "case_plans.based_on_state_hash",
            ],
            name="fk_case_runs_bound_plan",
            ondelete="RESTRICT",
        ),
        CheckConstraint("plan_version >= 1", name="case_runs_positive_plan_version"),
        CheckConstraint("length(plan_sha256) = 64", name="case_runs_plan_hash_length"),
        CheckConstraint("length(bound_state_hash) = 64", name="case_runs_state_hash_length"),
        CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'PAUSED', 'WAITING_FOR_APPROVAL', "
            "'COMPLETED', 'BLOCKED', 'FAILED', 'CANCELLED')",
            name="case_runs_status",
        ),
        UniqueConstraint("id", "case_id", name="uq_case_runs_id_case"),
        Index("ix_case_runs_case_status", "case_id", "status"),
    )


class RunEvent(Base):
    """Append-only, hash-chained event stream for one durable case run."""

    __tablename__ = "run_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    case_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    request_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    previous_event_hash: Mapped[str | None] = mapped_column(String(64))
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )

    run: Mapped[CaseRun] = relationship(back_populates="events")

    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "case_id"],
            ["case_runs.id", "case_runs.case_id"],
            name="fk_run_events_run_case",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("run_id", "sequence", name="uq_run_events_run_sequence"),
        UniqueConstraint("run_id", "idempotency_key", name="uq_run_events_run_idempotency"),
        CheckConstraint("sequence >= 1", name="run_events_positive_sequence"),
        CheckConstraint("length(event_hash) = 64", name="run_events_event_hash_length"),
        CheckConstraint(
            "previous_event_hash IS NULL OR length(previous_event_hash) = 64",
            name="run_events_previous_hash_length",
        ),
        Index("ix_run_events_run_occurred", "run_id", "occurred_at"),
    )


class AgentInvocation(Base):
    """One bounded specialist attempt within an exact plan step."""

    __tablename__ = "agent_invocations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    case_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    plan_step_id: Mapped[str] = mapped_column(
        ForeignKey("case_plan_steps.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    step_key: Mapped[str] = mapped_column(String(160), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    agent_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_versions.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(
        String(32), default=AgentInvocationStatus.PENDING.value, nullable=False, index=True
    )
    input_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    input_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    output_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    output_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    output_schema_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    limits: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    usage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(120))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    run: Mapped[CaseRun] = relationship(back_populates="invocations")

    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "case_id"],
            ["case_runs.id", "case_runs.case_id"],
            name="fk_agent_invocations_run_case",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "run_id", "step_key", "attempt", name="uq_agent_invocations_run_step_attempt"
        ),
        CheckConstraint("attempt >= 1", name="agent_invocations_positive_attempt"),
        CheckConstraint("length(input_sha256) = 64", name="agent_invocations_input_hash_length"),
        CheckConstraint(
            "output_sha256 IS NULL OR length(output_sha256) = 64",
            name="agent_invocations_output_hash_length",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'WAITING_FOR_APPROVAL', 'COMPLETED', "
            "'BLOCKED', 'FAILED', 'CANCELLED')",
            name="agent_invocations_status",
        ),
        Index("ix_agent_invocations_run_status", "run_id", "status"),
    )


class PolicyDecision(Base):
    """One attributable, hash-bound policy evaluation; rows are append-only."""

    __tablename__ = "policy_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_cases.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    bound_state_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agent_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_versions.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    tool_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("tool_versions.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    request_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    principal_subject: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    effect: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    policy_key: Mapped[str] = mapped_column(String(160), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    policy_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    input_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    decision_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    reason_codes: Mapped[list[str]] = mapped_column(JSON, default=list)
    decision_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    evaluated_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    case: Mapped[Case | None] = relationship(back_populates="policy_decisions")

    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "case_id"],
            ["case_runs.id", "case_runs.case_id"],
            name="fk_policy_decisions_run_case",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(case_id IS NULL AND bound_state_hash IS NULL) OR "
            "(case_id IS NOT NULL AND bound_state_hash IS NOT NULL)",
            name="policy_decisions_case_state_pair",
        ),
        CheckConstraint(
            "run_id IS NULL OR case_id IS NOT NULL",
            name="policy_decisions_run_requires_case",
        ),
        CheckConstraint(
            "bound_state_hash IS NULL OR length(bound_state_hash) = 64",
            name="policy_decisions_state_hash_length",
        ),
        CheckConstraint("length(policy_sha256) = 64", name="policy_decisions_policy_hash_length"),
        CheckConstraint("length(input_sha256) = 64", name="policy_decisions_input_hash_length"),
        CheckConstraint(
            "length(decision_sha256) = 64", name="policy_decisions_decision_hash_length"
        ),
        CheckConstraint(
            "effect IN ('ALLOW', 'DENY', 'REQUIRE_APPROVAL')",
            name="policy_decisions_effect",
        ),
        Index("ix_policy_decisions_case_created", "case_id", "created_at"),
        Index("ix_policy_decisions_run_created", "run_id", "created_at"),
    )


class ToolInvocation(Base):
    """Access-controlled, immutable record of one returned structured observation."""

    __tablename__ = "tool_invocations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("agent_cases.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    run_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    agent_version_id: Mapped[str] = mapped_column(
        ForeignKey("agent_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    tool_version_id: Mapped[str] = mapped_column(
        ForeignKey("tool_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    policy_decision_id: Mapped[str] = mapped_column(
        ForeignKey("policy_decisions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    request_id: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    principal_subject: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    runtime_service: Mapped[str] = mapped_column(String(160), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(160), nullable=False)
    agent_version: Mapped[str] = mapped_column(String(80), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    tool_version: Mapped[str] = mapped_column(String(80), nullable=False)
    arguments_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_effect: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    structured_result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provenance: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    case: Mapped[Case] = relationship(back_populates="tool_invocations")

    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "case_id"],
            ["case_runs.id", "case_runs.case_id"],
            name="fk_tool_invocations_run_case",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("run_id", "idempotency_key", name="uq_tool_invocations_run_idempotency"),
        UniqueConstraint("policy_decision_id", name="uq_tool_invocations_policy_decision"),
        CheckConstraint(
            "length(arguments_sha256) = 64",
            name="tool_invocations_arguments_hash_length",
        ),
        CheckConstraint("length(result_sha256) = 64", name="tool_invocations_result_hash_length"),
        CheckConstraint(
            "policy_effect IN ('ALLOW', 'DENY', 'REQUIRE_APPROVAL')",
            name="tool_invocations_policy_effect",
        ),
        CheckConstraint(
            "status IN ('SUCCEEDED', 'DENIED', 'FAILED')",
            name="tool_invocations_status",
        ),
        CheckConstraint(
            "(policy_effect = 'ALLOW' AND status IN ('SUCCEEDED', 'FAILED')) OR "
            "(policy_effect <> 'ALLOW' AND status = 'DENIED')",
            name="tool_invocations_policy_status",
        ),
        CheckConstraint("latency_ms >= 0", name="tool_invocations_nonnegative_latency"),
        CheckConstraint("completed_at >= started_at", name="tool_invocations_timestamp_order"),
        Index("ix_tool_invocations_case_created", "case_id", "created_at"),
        Index("ix_tool_invocations_run_created", "run_id", "created_at"),
        Index("ix_tool_invocations_tool_status", "tool_name", "status"),
    )


class VerificationReport(Base):
    """Immutable independent challenge of an exact set of impact hypotheses."""

    __tablename__ = "verification_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("agent_cases.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    plan_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    plan_version: Mapped[int] = mapped_column(Integer, nullable=False)
    plan_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    bound_state_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    correction_iteration: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    checks: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    issues: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    verified_hypothesis_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    report_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    verifier_name: Mapped[str] = mapped_column(String(160), nullable=False)
    verifier_version: Mapped[str] = mapped_column(String(80), nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    case: Mapped[Case] = relationship(back_populates="verification_reports")

    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "case_id"],
            ["case_runs.id", "case_runs.case_id"],
            name="fk_verification_reports_run_case",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["plan_id", "case_id", "plan_version", "plan_sha256", "bound_state_hash"],
            [
                "case_plans.id",
                "case_plans.case_id",
                "case_plans.version",
                "case_plans.plan_sha256",
                "case_plans.based_on_state_hash",
            ],
            name="fk_verification_reports_plan_binding",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "case_id",
            "input_sha256",
            "correction_iteration",
            name="uq_verification_reports_input_iteration",
        ),
        CheckConstraint(
            "correction_iteration >= 0 AND correction_iteration <= 2",
            name="verification_reports_correction_limit",
        ),
        CheckConstraint("plan_version >= 1", name="verification_reports_plan_version"),
        CheckConstraint(
            "status IN ('PASS', 'REVISE', 'BLOCK')",
            name="verification_reports_status",
        ),
        CheckConstraint("length(plan_sha256) = 64", name="verification_reports_plan_hash"),
        CheckConstraint("length(bound_state_hash) = 64", name="verification_reports_state_hash"),
        CheckConstraint("length(input_sha256) = 64", name="verification_reports_input_hash"),
        CheckConstraint("length(report_sha256) = 64", name="verification_reports_report_hash"),
        Index("ix_verification_reports_case_created", "case_id", "created_at"),
    )


class Artifact(Base):
    """Stable, case-owned grouping for immutable artifact revisions."""

    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("agent_cases.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    artifact_key: Mapped[str] = mapped_column(String(160), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    case: Mapped[Case] = relationship(back_populates="artifacts")
    versions: Mapped[list[ArtifactVersion]] = relationship(
        back_populates="artifact", order_by="ArtifactVersion.version", passive_deletes=True
    )

    __table_args__ = (
        UniqueConstraint("case_id", "artifact_key", name="uq_artifacts_case_key"),
        UniqueConstraint("id", "case_id", name="uq_artifacts_id_case"),
    )


class ArtifactVersion(Base):
    """Content-addressed artifact revision bound to one exact case-plan state."""

    __tablename__ = "artifact_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    artifact_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    case_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    plan_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    plan_version: Mapped[int] = mapped_column(Integer, nullable=False)
    plan_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    bound_state_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    verification_report_id: Mapped[str | None] = mapped_column(
        ForeignKey("verification_reports.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    content_schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    evidence_manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=ArtifactVersionStatus.DRAFT.value, nullable=False, index=True
    )
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    artifact: Mapped[Artifact] = relationship(back_populates="versions")
    evidence: Mapped[list[ArtifactEvidence]] = relationship(
        back_populates="artifact_version",
        order_by="ArtifactEvidence.created_at",
        passive_deletes=True,
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["artifact_id", "case_id"],
            ["artifacts.id", "artifacts.case_id"],
            name="fk_artifact_versions_artifact_case",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["plan_id", "case_id", "plan_version", "plan_sha256", "bound_state_hash"],
            [
                "case_plans.id",
                "case_plans.case_id",
                "case_plans.version",
                "case_plans.plan_sha256",
                "case_plans.based_on_state_hash",
            ],
            name="fk_artifact_versions_bound_plan",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["run_id", "case_id"],
            ["case_runs.id", "case_runs.case_id"],
            name="fk_artifact_versions_run_case",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("artifact_id", "version", name="uq_artifact_versions_number"),
        UniqueConstraint(
            "artifact_id",
            "content_sha256",
            "evidence_manifest_sha256",
            name="uq_artifact_versions_content_evidence",
        ),
        UniqueConstraint("id", "case_id", name="uq_artifact_versions_id_case"),
        UniqueConstraint(
            "id",
            "artifact_id",
            "case_id",
            "version",
            "content_sha256",
            "evidence_manifest_sha256",
            name="uq_artifact_versions_bound_identity",
        ),
        CheckConstraint("version >= 1", name="artifact_versions_positive_version"),
        CheckConstraint("plan_version >= 1", name="artifact_versions_positive_plan_version"),
        CheckConstraint("length(plan_sha256) = 64", name="artifact_versions_plan_hash_length"),
        CheckConstraint(
            "length(bound_state_hash) = 64", name="artifact_versions_state_hash_length"
        ),
        CheckConstraint(
            "length(content_sha256) = 64", name="artifact_versions_content_hash_length"
        ),
        CheckConstraint(
            "length(evidence_manifest_sha256) = 64",
            name="artifact_versions_evidence_hash_length",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'APPROVED', 'REJECTED')",
            name="artifact_versions_status",
        ),
        Index("ix_artifact_versions_case_status", "case_id", "status"),
    )


class ArtifactEvidence(Base):
    """Immutable evidence membership resolving through an exact case source pin."""

    __tablename__ = "artifact_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    artifact_version_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    case_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    case_source_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    document_version_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    anchor: Mapped[str] = mapped_column(String(500), nullable=False)
    excerpt_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_role: Mapped[str] = mapped_column(String(40), nullable=False, default="SUPPORTING")
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    artifact_version: Mapped[ArtifactVersion] = relationship(back_populates="evidence")

    __table_args__ = (
        ForeignKeyConstraint(
            ["artifact_version_id", "case_id"],
            ["artifact_versions.id", "artifact_versions.case_id"],
            name="fk_artifact_evidence_version_case",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["case_source_id", "case_id", "document_version_id", "source_sha256"],
            [
                "case_sources.id",
                "case_sources.case_id",
                "case_sources.document_version_id",
                "case_sources.source_sha256",
            ],
            name="fk_artifact_evidence_case_source",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "artifact_version_id",
            "case_source_id",
            "anchor",
            "excerpt_sha256",
            name="uq_artifact_evidence_membership",
        ),
        CheckConstraint("length(source_sha256) = 64", name="artifact_evidence_source_hash_length"),
        CheckConstraint(
            "length(excerpt_sha256) = 64", name="artifact_evidence_excerpt_hash_length"
        ),
        CheckConstraint("length(trim(anchor)) > 0", name="artifact_evidence_anchor_nonempty"),
    )


class ApprovalRequest(Base):
    """Human decision request whose authorization scope cannot drift from its plan."""

    __tablename__ = "approval_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("agent_cases.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    plan_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    plan_version: Mapped[int] = mapped_column(Integer, nullable=False)
    plan_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    bound_state_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    plan_step_id: Mapped[str | None] = mapped_column(
        ForeignKey("case_plan_steps.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    step_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    artifact_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    artifact_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    artifact_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    artifact_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    artifact_evidence_manifest_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approval_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20), default=ApprovalStatus.PENDING.value, nullable=False, index=True
    )
    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
    assigned_reviewer_id: Mapped[str | None] = mapped_column(String(255), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    decision_by: Mapped[str | None] = mapped_column(String(255))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    case: Mapped[Case] = relationship(back_populates="approvals", overlaps="approvals")
    run: Mapped[CaseRun | None] = relationship(
        back_populates="approvals", overlaps="approvals,case"
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["plan_id", "case_id", "plan_version", "plan_sha256", "bound_state_hash"],
            [
                "case_plans.id",
                "case_plans.case_id",
                "case_plans.version",
                "case_plans.plan_sha256",
                "case_plans.based_on_state_hash",
            ],
            name="fk_approval_requests_bound_plan",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["run_id", "case_id"],
            ["case_runs.id", "case_runs.case_id"],
            name="fk_approval_requests_run_case",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "artifact_version_id",
                "artifact_id",
                "case_id",
                "artifact_version",
                "artifact_sha256",
                "artifact_evidence_manifest_sha256",
            ],
            [
                "artifact_versions.id",
                "artifact_versions.artifact_id",
                "artifact_versions.case_id",
                "artifact_versions.version",
                "artifact_versions.content_sha256",
                "artifact_versions.evidence_manifest_sha256",
            ],
            name="fk_approval_requests_artifact_target",
            ondelete="RESTRICT",
        ),
        CheckConstraint("plan_version >= 1", name="approval_requests_positive_plan_version"),
        CheckConstraint("length(plan_sha256) = 64", name="approval_requests_plan_hash_length"),
        CheckConstraint(
            "length(bound_state_hash) = 64", name="approval_requests_state_hash_length"
        ),
        CheckConstraint(
            "(artifact_version_id IS NULL AND artifact_id IS NULL "
            "AND artifact_version IS NULL AND artifact_sha256 IS NULL "
            "AND artifact_evidence_manifest_sha256 IS NULL) OR "
            "(artifact_version_id IS NOT NULL AND artifact_id IS NOT NULL "
            "AND artifact_version IS NOT NULL AND artifact_sha256 IS NOT NULL "
            "AND artifact_evidence_manifest_sha256 IS NOT NULL)",
            name="approval_requests_artifact_target_complete",
        ),
        CheckConstraint(
            "(approval_type = 'ARTIFACT_APPROVAL' AND artifact_version_id IS NOT NULL) OR "
            "(approval_type <> 'ARTIFACT_APPROVAL' AND artifact_version_id IS NULL)",
            name="approval_requests_artifact_target_type",
        ),
        CheckConstraint(
            "approval_type IN ('PLAN_APPROVAL', 'STEP_APPROVAL', 'ARTIFACT_APPROVAL')",
            name="approval_requests_type",
        ),
        CheckConstraint(
            "(approval_type = 'STEP_APPROVAL' AND run_id IS NOT NULL "
            "AND plan_step_id IS NOT NULL AND step_key IS NOT NULL) OR "
            "(approval_type <> 'STEP_APPROVAL' AND run_id IS NULL "
            "AND plan_step_id IS NULL AND step_key IS NULL)",
            name="approval_requests_step_target_type",
        ),
        CheckConstraint(
            "artifact_version IS NULL OR artifact_version >= 1",
            name="approval_requests_positive_artifact_version",
        ),
        CheckConstraint(
            "artifact_sha256 IS NULL OR length(artifact_sha256) = 64",
            name="approval_requests_artifact_hash_length",
        ),
        CheckConstraint(
            "artifact_evidence_manifest_sha256 IS NULL "
            "OR length(artifact_evidence_manifest_sha256) = 64",
            name="approval_requests_artifact_evidence_hash_length",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED', 'CANCELLED', 'EXPIRED')",
            name="approval_requests_status",
        ),
        CheckConstraint(
            "status NOT IN ('APPROVED', 'REJECTED') OR "
            "(decision_by IS NOT NULL AND decided_at IS NOT NULL)",
            name="approval_requests_decision_metadata",
        ),
        CheckConstraint("expires_at > created_at", name="approval_requests_expiry_order"),
        Index(
            "ix_approval_requests_reviewer_status",
            "assigned_reviewer_id",
            "status",
        ),
        Index(
            "uq_approval_requests_pending_artifact",
            "artifact_version_id",
            unique=True,
            postgresql_where=text("artifact_version_id IS NOT NULL AND status = 'PENDING'"),
            sqlite_where=text("artifact_version_id IS NOT NULL AND status = 'PENDING'"),
        ),
    )


class InternalAsset(TimestampMixin, Base):
    """Synthetic or governed internal quality-system asset identity."""

    __tablename__ = "internal_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    asset_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    asset_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    domain: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    classification: Mapped[str] = mapped_column(
        String(40), nullable=False, default="INTERNAL_SYNTHETIC"
    )
    synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    lifecycle_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="ACTIVE", index=True
    )
    current_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)

    versions: Mapped[list[InternalAssetVersion]] = relationship(
        back_populates="asset", order_by="InternalAssetVersion.revision", passive_deletes=True
    )
    acl_entries: Mapped[list[InternalAssetAcl]] = relationship(
        back_populates="asset", order_by="InternalAssetAcl.created_at", passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint(
            "classification IN ('INTERNAL_SYNTHETIC', 'INTERNAL', 'CONFIDENTIAL')",
            name="internal_assets_classification",
        ),
        CheckConstraint(
            "lifecycle_status IN ('ACTIVE', 'RETIRED')",
            name="internal_assets_lifecycle_status",
        ),
        Index("ix_internal_assets_type_domain", "asset_type", "domain"),
    )


class InternalAssetVersion(Base):
    """Content-addressed revision whose effective/obsolete state is explicit."""

    __tablename__ = "internal_asset_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    asset_id: Mapped[str] = mapped_column(
        ForeignKey("internal_assets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=InternalAssetVersionStatus.DRAFT.value, nullable=False, index=True
    )
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    anchors: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    asset_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    search_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(PortableVector(64), nullable=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    asset: Mapped[InternalAsset] = relationship(back_populates="versions")

    __table_args__ = (
        UniqueConstraint("asset_id", "revision", name="uq_internal_asset_versions_revision"),
        UniqueConstraint(
            "asset_id", "content_sha256", name="uq_internal_asset_versions_content_hash"
        ),
        CheckConstraint("revision >= 1", name="internal_asset_versions_positive_revision"),
        CheckConstraint(
            "length(content_sha256) = 64",
            name="internal_asset_versions_content_hash_length",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'EFFECTIVE', 'OBSOLETE', 'RETIRED')",
            name="internal_asset_versions_status",
        ),
    )


class InternalAssetAcl(Base):
    """Positive read grant evaluated before an asset enters retrieval ranking."""

    __tablename__ = "internal_asset_acl"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    asset_id: Mapped[str] = mapped_column(
        ForeignKey("internal_assets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    principal_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    principal_value: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    permission: Mapped[str] = mapped_column(String(20), nullable=False, default="READ")
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    asset: Mapped[InternalAsset] = relationship(back_populates="acl_entries")

    __table_args__ = (
        UniqueConstraint(
            "asset_id",
            "principal_kind",
            "principal_value",
            "permission",
            name="uq_internal_asset_acl_grant",
        ),
        CheckConstraint(
            "principal_kind IN ('ROLE', 'SUBJECT')", name="internal_asset_acl_principal_kind"
        ),
        CheckConstraint("permission = 'READ'", name="internal_asset_acl_permission"),
    )


class AssetRelation(Base):
    """Reviewable relationship edge; proposed edges never act as approved knowledge."""

    __tablename__ = "asset_relations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    source_asset_id: Mapped[str] = mapped_column(
        ForeignKey("internal_assets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    target_asset_id: Mapped[str] = mapped_column(
        ForeignKey("internal_assets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    relation_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20), default=AssetRelationStatus.PROPOSED.value, nullable=False, index=True
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_by: Mapped[str] = mapped_column(String(255), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    evidence: Mapped[list[RelationEvidence]] = relationship(
        back_populates="relation", order_by="RelationEvidence.created_at", passive_deletes=True
    )

    __table_args__ = (
        UniqueConstraint(
            "source_asset_id",
            "target_asset_id",
            "relation_type",
            name="uq_asset_relations_edge",
        ),
        CheckConstraint(
            "source_asset_id <> target_asset_id", name="asset_relations_distinct_assets"
        ),
        CheckConstraint(
            "status IN ('PROPOSED', 'APPROVED', 'REJECTED')",
            name="asset_relations_status",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="asset_relations_confidence"),
    )


class RelationEvidence(Base):
    """Exact internal revision anchors supporting a relation edge."""

    __tablename__ = "relation_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    relation_id: Mapped[str] = mapped_column(
        ForeignKey("asset_relations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    asset_version_id: Mapped[str] = mapped_column(
        ForeignKey("internal_asset_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    anchor: Mapped[str] = mapped_column(String(255), nullable=False)
    excerpt_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_role: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    relation: Mapped[AssetRelation] = relationship(back_populates="evidence")

    __table_args__ = (
        UniqueConstraint(
            "relation_id",
            "asset_version_id",
            "anchor",
            name="uq_relation_evidence_anchor",
        ),
        CheckConstraint(
            "length(content_sha256) = 64", name="relation_evidence_content_hash_length"
        ),
        CheckConstraint(
            "length(excerpt_sha256) = 64", name="relation_evidence_excerpt_hash_length"
        ),
    )


class ImpactHypothesis(Base):
    """Evidence-linked, explicitly non-conclusive internal-impact hypothesis."""

    __tablename__ = "impact_hypotheses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("agent_cases.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    finding_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    asset_id: Mapped[str] = mapped_column(
        ForeignKey("internal_assets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    asset_version_id: Mapped[str] = mapped_column(
        ForeignKey("internal_asset_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    relationship_type: Mapped[str] = mapped_column(String(80), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    known_facts: Mapped[list[str]] = mapped_column(JSON, default=list)
    derived_relationships: Mapped[list[str]] = mapped_column(JSON, default=list)
    assumptions: Mapped[list[str]] = mapped_column(JSON, default=list)
    counterevidence: Mapped[list[str]] = mapped_column(JSON, default=list)
    unknowns: Mapped[list[str]] = mapped_column(JSON, default=list)
    recommended_verification: Mapped[list[str]] = mapped_column(JSON, default=list)
    external_evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    internal_evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    review_priority: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=ImpactHypothesisStatus.PROPOSED.value, nullable=False, index=True
    )
    hypothesis_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    case: Mapped[Case] = relationship(back_populates="impact_hypotheses")

    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "case_id"],
            ["case_runs.id", "case_runs.case_id"],
            name="fk_impact_hypotheses_run_case",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "case_id",
            "finding_id",
            "asset_version_id",
            "relationship_type",
            name="uq_impact_hypotheses_case_mapping",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="impact_hypotheses_confidence"),
        CheckConstraint(
            "review_priority IN ('LOW', 'MEDIUM', 'HIGH')",
            name="impact_hypotheses_priority",
        ),
        CheckConstraint(
            "status IN ('PROPOSED', 'ACCEPTED', 'REJECTED')",
            name="impact_hypotheses_status",
        ),
        CheckConstraint(
            "length(hypothesis_sha256) = 64",
            name="impact_hypotheses_hash_length",
        ),
        Index("ix_impact_hypotheses_case_status", "case_id", "status"),
    )


class EvaluationSuite(Base):
    """Immutable versioned evaluation definition and its deterministic release gates."""

    __tablename__ = "evaluation_suites"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    suite_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    target_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    gates: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    suite_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        UniqueConstraint("suite_key", "version", name="uq_evaluation_suites_key_version"),
        CheckConstraint(
            "target_kind IN ('AGENT_VERSION', 'WORKFLOW_VERSION')",
            name="evaluation_suites_target_kind",
        ),
        CheckConstraint("length(suite_sha256) = 64", name="evaluation_suites_hash"),
    )


class EvaluationCase(Base):
    """Curated or synthetic case whose expected environment outcome is explicit."""

    __tablename__ = "evaluation_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    suite_id: Mapped[str] = mapped_column(
        ForeignKey("evaluation_suites.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    case_key: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    input: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    expected_outcome: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    critical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    case_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        UniqueConstraint("suite_id", "case_key", name="uq_evaluation_cases_suite_key"),
        CheckConstraint("length(case_sha256) = 64", name="evaluation_cases_hash"),
    )


class EvaluationRun(Base):
    """Outcome-bearing evaluation of one exact candidate version."""

    __tablename__ = "evaluation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    suite_id: Mapped[str] = mapped_column(
        ForeignKey("evaluation_suites.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    target_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    target_version_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    target_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    baseline_version_id: Mapped[str | None] = mapped_column(String(36), index=True)
    trial_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    total_trials: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    passed_trials: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    critical_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    total_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        CheckConstraint("trial_count >= 3 AND trial_count <= 20", name="evaluation_runs_trials"),
        CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'PASSED', 'FAILED')", name="evaluation_runs_status"
        ),
        CheckConstraint("length(target_sha256) = 64", name="evaluation_runs_target_hash"),
        CheckConstraint("total_trials >= 0 AND passed_trials >= 0", name="evaluation_runs_counts"),
        CheckConstraint("critical_failures >= 0", name="evaluation_runs_critical_failures"),
    )


class EvaluationTrial(Base):
    """One independently graded execution with inspectable trajectory and final state."""

    __tablename__ = "evaluation_trials"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    evaluation_run_id: Mapped[str] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    evaluation_case_id: Mapped[str] = mapped_column(
        ForeignKey("evaluation_cases.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    trial_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    trajectory: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    final_state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    output_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        UniqueConstraint(
            "evaluation_run_id",
            "evaluation_case_id",
            "trial_number",
            name="uq_evaluation_trials_identity",
        ),
        CheckConstraint("trial_number >= 1", name="evaluation_trials_number"),
        CheckConstraint("status IN ('PASSED', 'FAILED')", name="evaluation_trials_status"),
        CheckConstraint("length(output_sha256) = 64", name="evaluation_trials_output_hash"),
        CheckConstraint(
            "token_count >= 0 AND cost_usd >= 0 AND latency_ms >= 0", name="evaluation_trials_usage"
        ),
    )


class EvaluationGrade(Base):
    __tablename__ = "evaluation_grades"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    evaluation_trial_id: Mapped[str] = mapped_column(
        ForeignKey("evaluation_trials.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    grader_type: Mapped[str] = mapped_column(String(24), nullable=False)
    metric: Mapped[str] = mapped_column(String(80), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    critical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    graded_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        UniqueConstraint(
            "evaluation_trial_id", "grader_type", "metric", name="uq_evaluation_grades_metric"
        ),
        CheckConstraint(
            "grader_type IN ('DETERMINISTIC', 'MODEL', 'HUMAN')", name="evaluation_grades_type"
        ),
        CheckConstraint("score >= 0 AND score <= 1", name="evaluation_grades_score"),
    )


class ReleaseApproval(Base):
    """Human release decision bound to one passing evaluation and rollback target."""

    __tablename__ = "release_approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    evaluation_run_id: Mapped[str] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    target_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    target_version_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    target_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    target_status: Mapped[str] = mapped_column(String(20), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    rollback_target_id: Mapped[str | None] = mapped_column(String(36))
    decided_by: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        CheckConstraint("decision IN ('APPROVED', 'REJECTED')", name="release_approvals_decision"),
        CheckConstraint(
            "target_kind IN ('AGENT_VERSION', 'WORKFLOW_VERSION')",
            name="release_approvals_target_kind",
        ),
        CheckConstraint(
            "target_status IN ('STAGING', 'PRODUCTION')", name="release_approvals_target_status"
        ),
        CheckConstraint("length(target_sha256) = 64", name="release_approvals_target_hash"),
    )


class ProductionFeedback(Base):
    """Append-only feedback link; it never mutates a released prompt or manifest."""

    __tablename__ = "production_feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_cases.id", ondelete="RESTRICT"), index=True
    )
    run_id: Mapped[str | None] = mapped_column(String(36), index=True)
    artifact_version_id: Mapped[str | None] = mapped_column(String(36), index=True)
    agent_version_id: Mapped[str | None] = mapped_column(String(36), index=True)
    signal_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    submitted_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        CheckConstraint("length(payload_sha256) = 64", name="production_feedback_hash"),
        CheckConstraint(
            "signal_type IN ('APPROVAL', 'REJECTION', 'EDIT', 'INTERRUPTION', "
            "'UNRESOLVED_QUESTION', 'TOOL_FAILURE', 'NEGATIVE_FEEDBACK', 'INCIDENT')",
            name="production_feedback_signal_type",
        ),
    )


class PlatformControl(Base):
    """Optimistically versioned global or per-agent execution suspension."""

    __tablename__ = "platform_controls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    control_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    scope: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    agent_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_versions.id", ondelete="RESTRICT"), index=True
    )
    suspended: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        CheckConstraint("scope IN ('GLOBAL', 'AGENT')", name="platform_controls_scope"),
        CheckConstraint("revision >= 1", name="platform_controls_revision"),
        CheckConstraint(
            "(scope = 'GLOBAL' AND agent_version_id IS NULL) OR "
            "(scope = 'AGENT' AND agent_version_id IS NOT NULL)",
            name="platform_controls_binding",
        ),
    )


class DurableActivity(Base):
    """Idempotency journal for durable outer-workflow activity execution."""

    __tablename__ = "durable_activities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    temporal_workflow_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    case_run_id: Mapped[str] = mapped_column(
        ForeignKey("case_runs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    activity_key: Mapped[str] = mapped_column(String(255), nullable=False)
    input_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result_sha256: Mapped[str | None] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "temporal_workflow_id", "activity_key", name="uq_durable_activities_identity"
        ),
        CheckConstraint(
            "status IN ('RUNNING', 'SUCCEEDED', 'FAILED')", name="durable_activities_status"
        ),
        CheckConstraint("length(input_sha256) = 64", name="durable_activities_input_hash"),
        CheckConstraint(
            "result_sha256 IS NULL OR length(result_sha256) = 64",
            name="durable_activities_result_hash",
        ),
        CheckConstraint("attempts >= 1", name="durable_activities_attempts"),
    )


class IntegrationOutbox(Base):
    """Case-scoped draft only; the initial platform has no external-send transition."""

    __tablename__ = "integration_outbox"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("agent_cases.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    run_id: Mapped[str | None] = mapped_column(String(36), index=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False, default="CREATE_DRAFT")
    destination: Mapped[str] = mapped_column(String(320), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="DRAFT", index=True)
    external_delivery_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(255))
    review_reason: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        CheckConstraint(
            "channel IN ('INTERNAL', 'EMAIL', 'SLACK', 'TEAMS', 'NOTION', 'TASK')",
            name="integration_outbox_channel",
        ),
        CheckConstraint("action = 'CREATE_DRAFT'", name="integration_outbox_action"),
        CheckConstraint(
            "status IN ('DRAFT', 'REVIEWED_FOR_MANUAL_USE', 'CANCELLED')",
            name="integration_outbox_status",
        ),
        CheckConstraint(
            "external_delivery_allowed = false", name="integration_outbox_no_delivery"
        ),
        CheckConstraint("length(content_sha256) = 64", name="integration_outbox_hash"),
        CheckConstraint(
            "(status = 'DRAFT' AND reviewed_by IS NULL AND reviewed_at IS NULL) OR "
            "(status <> 'DRAFT' AND reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="integration_outbox_review",
        ),
        ForeignKeyConstraint(
            ["run_id", "case_id"],
            ["case_runs.id", "case_runs.case_id"],
            name="fk_integration_outbox_run_case",
            ondelete="RESTRICT",
        ),
    )


class A2AExchange(Base):
    """Immutable answer-only exchange; it cannot delegate work or invoke tools."""

    __tablename__ = "a2a_exchanges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("agent_cases.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    task_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    intent: Mapped[str] = mapped_column(String(80), nullable=False)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    response_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    response_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="COMPLETED")
    requester_service: Mapped[str] = mapped_column(String(255), nullable=False)
    delegated_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        CheckConstraint(
            "intent IN ('CASE_STATUS', 'APPROVED_ARTIFACT_METADATA')",
            name="a2a_exchanges_intent",
        ),
        CheckConstraint("status = 'COMPLETED'", name="a2a_exchanges_status"),
        CheckConstraint("length(request_sha256) = 64", name="a2a_exchanges_request_hash"),
        CheckConstraint("length(response_sha256) = 64", name="a2a_exchanges_response_hash"),
    )
