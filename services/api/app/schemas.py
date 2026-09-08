from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.enums import ReviewDecision


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class HealthResponse(StrictModel):
    status: Literal["ok", "degraded"]
    service: str
    version: str
    checks: dict[str, str] | None = None


class LetterListItem(StrictModel):
    id: UUID
    company_name: str
    country: str | None
    subject: str | None
    canonical_url: str
    marcs_cms_number: str | None
    posted_date: date | None
    issue_date: date | None
    issuing_offices: list[str]
    scope_status: str
    normalized_product_classes: list[str] = Field(default_factory=lambda: ["Drugs"])
    current_in_scope: Literal[True] = True
    scope_label: Literal["FDA Product: Drugs"] = "FDA Product: Drugs"
    drug_subtypes: list[str]
    lifecycle_status: str
    has_response: bool = False
    has_closeout: bool = False
    review_state: str | None = None
    categories: list[str] = Field(default_factory=list)
    first_seen_at: datetime
    last_seen_at: datetime
    updated_at: datetime


class CursorPage(StrictModel):
    items: list[LetterListItem]
    next_cursor: str | None
    has_more: bool
    enforced_scope: Literal["FDA Product: Drugs"] = "FDA Product: Drugs"


class VersionResponse(StrictModel):
    id: UUID
    document_id: UUID
    document_type: str
    version_number: int
    canonical_hash: str
    raw_sha256: str
    scope_status: str
    parser_version: str
    retrieved_at: datetime
    last_seen_at: datetime
    source_url: str
    anchors: list[dict[str, Any]] = Field(default_factory=list)


class DocumentResponse(StrictModel):
    id: UUID
    document_type: str
    title: str | None
    canonical_url: str
    issue_date: date | None
    source_available: bool
    current_version_id: UUID | None


class SummaryResponse(StrictModel):
    id: UUID
    document_version_id: UUID
    parent_summary_id: UUID | None
    revision: int
    executive_summary: str
    language: str
    review_state: str
    validation_report: dict[str, Any]
    taxonomy_version: str
    created_at: datetime


class FindingResponse(StrictModel):
    id: UUID
    label: str
    categories: list[str]
    process_lenses: list[str]
    finding: str
    regulatory_references: list[str]
    evidence: list[dict[str, str]]
    fda_requested_actions: list[str]
    comparison_points: list[str]
    attention_level: str | None
    confidence: float | None
    review_state: str


class LetterAiArtifactResponse(StrictModel):
    id: UUID
    document_version_id: UUID
    artifact_type: Literal["translation", "findings", "summary"]
    language: Literal["en", "ko"]
    content: dict[str, Any]
    provider: str
    model_id: str
    prompt_version: str
    source_hash: str
    created_at: datetime


class ChangeResponse(StrictModel):
    id: UUID
    warning_letter_id: UUID
    company_name: str
    event_type: str
    before_state: dict[str, Any] | None
    after_state: dict[str, Any] | None
    source_version_id: UUID | None
    detected_at: datetime
    published_at: datetime | None


class ChangePage(StrictModel):
    items: list[ChangeResponse]
    next_cursor: str | None
    has_more: bool


class LetterDetail(StrictModel):
    id: UUID
    company_name: str
    country: str | None
    subject: str | None
    canonical_url: str
    marcs_cms_number: str | None
    fda_reference_number: str | None
    posted_date: date | None
    issue_date: date | None
    issuing_offices: list[str]
    fda_product_raw: list[str]
    normalized_product_classes: list[str]
    scope_status: str
    scope_label: Literal["FDA Product: Drugs"] = "FDA Product: Drugs"
    drug_subtypes: list[str]
    lifecycle_status: str
    documents: list[DocumentResponse]
    current_version: VersionResponse | None
    normalized_markdown: str | None
    summary: SummaryResponse | None
    findings: list[FindingResponse]
    ai_artifacts: list[LetterAiArtifactResponse] = Field(default_factory=list)
    lifecycle: list[ChangeResponse]
    interpretation_notice: str = (
        "Decision support only. FDA source evidence is authoritative; internal comparison "
        "questions are not compliance conclusions."
    )


class DashboardCounts(StrictModel):
    total_drug_letters: int
    new_letters: int
    updated_letters: int
    responses_added: int
    closeouts_added: int
    pending_reviews: int
    scope_exceptions: int


class DashboardResponse(StrictModel):
    scope_label: Literal["FDA Product: Drugs"] = "FDA Product: Drugs"
    counts: DashboardCounts
    last_successful_discovery: datetime | None
    recent_events: list[ChangeResponse]
    category_distribution: list[dict[str, Any]]
    issuing_office_distribution: list[dict[str, Any]]


class RagFilters(StrictModel):
    letter_id: UUID | None = None
    company: str | None = Field(default=None, max_length=300)
    issuing_office: str | None = Field(default=None, max_length=200)
    category: str | None = Field(default=None, max_length=300)
    regulation: str | None = Field(default=None, max_length=200)
    drug_subtype: str | None = Field(default=None, max_length=150)
    issue_date_from: date | None = None
    issue_date_to: date | None = None
    letter_ids: list[UUID] = Field(default_factory=list, max_length=100)
    companies: list[str] = Field(default_factory=list, max_length=50)
    issuing_offices: list[str] = Field(default_factory=list, max_length=20)
    categories: list[str] = Field(default_factory=list, max_length=30)
    regulatory_references: list[str] = Field(default_factory=list, max_length=30)
    drug_subtypes: list[str] = Field(default_factory=list, max_length=20)
    posted_from: date | None = None
    posted_to: date | None = None
    include_responses: bool = True
    include_closeouts: bool = True

    @model_validator(mode="before")
    @classmethod
    def accept_portal_filter_names(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        aliases = {
            "letterId": "letter_id",
            "dateFrom": "issue_date_from",
            "dateTo": "issue_date_to",
            "subtype": "drug_subtype",
        }
        for external, internal in aliases.items():
            if external in normalized and internal not in normalized:
                normalized[internal] = normalized.pop(external)
        return normalized


class RagConversationMessage(StrictModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2_000)

    @field_validator("content")
    @classmethod
    def meaningful_content(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("conversation message is empty")
        return value


class RagQueryRequest(StrictModel):
    question: str = Field(min_length=3, max_length=2_000)
    language: Literal["auto", "en", "ko"] = "auto"
    filters: RagFilters = Field(default_factory=RagFilters)
    conversation_history: list[RagConversationMessage] = Field(
        default_factory=list,
        max_length=8,
    )
    max_sources: int = Field(default=5, ge=1, le=10)
    product_scope: Literal["Drugs"] | None = None
    thread_id: UUID | None = None
    client_message_id: str | None = Field(default=None, min_length=1, max_length=100)
    retrieval_mode: Literal["auto", "none", "metadata", "letter", "corpus"] = "auto"
    model_profile: Literal["auto", "fast", "balanced", "deep"] = "auto"

    @field_validator("question")
    @classmethod
    def meaningful_question(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 3:
            raise ValueError("question is too short")
        return value

    @model_validator(mode="after")
    def idempotency_requires_thread(self) -> RagQueryRequest:
        if self.client_message_id and not self.thread_id:
            raise ValueError("client_message_id requires thread_id")
        return self


class CitationResponse(StrictModel):
    chunk_id: UUID
    warning_letter_id: UUID
    company_name: str
    title: str | None
    document_type: str
    issue_date: date | None
    posted_date: date | None
    source_anchor: str
    excerpt: str
    source_url: str
    score: float
    document_version_id: UUID | None = None
    source_version: str | None = None
    source_hash: str | None = None


class RagQueryResponse(StrictModel):
    query_id: UUID
    answer: str
    interpretation_label: Literal["source_facts", "ai_synthesis", "internal_comparison"]
    scope_label: Literal["FDA Product: Drugs"] = "FDA Product: Drugs"
    filters_applied: dict[str, Any]
    evidence_sufficiency: Literal["sufficient", "partial", "insufficient"]
    citations: list[CitationResponse]
    notice: str
    thread_id: UUID | None = None
    user_message_id: UUID | None = None
    assistant_message_id: UUID | None = None
    retrieval_strategy: Literal["none", "metadata", "letter", "multi_letter", "corpus"]
    route_reason: str
    requested_model_profile: Literal["auto", "fast", "balanced", "deep"]
    effective_model_profile: Literal["fast", "balanced", "deep"]
    generation_used: bool
    attempted_model_id: str | None = None
    effective_model_id: str | None = None
    focused_document_version_id: UUID | None = None
    generated_at: datetime


class ChatThreadCreate(StrictModel):
    title: str = Field(default="새 대화", min_length=1, max_length=200)
    model_preference: Literal["auto", "fast", "balanced", "deep"] = "auto"
    retrieval_preference: Literal["auto", "none", "metadata", "letter", "corpus"] = "auto"
    active_letter_ids: list[UUID] = Field(default_factory=list, max_length=20)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("title is empty")
        return value


class ChatThreadPatch(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    model_preference: Literal["auto", "fast", "balanced", "deep"] | None = None
    retrieval_preference: Literal["auto", "none", "metadata", "letter", "corpus"] | None = None
    active_letter_ids: list[UUID] | None = Field(default=None, max_length=20)
    archived: bool | None = None

    @field_validator("title")
    @classmethod
    def normalize_optional_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = " ".join(value.split())
        if not value:
            raise ValueError("title is empty")
        return value

    @model_validator(mode="after")
    def require_change(self) -> ChatThreadPatch:
        if not self.model_fields_set:
            raise ValueError("at least one thread field is required")
        return self


class ChatMessageResponse(StrictModel):
    id: UUID
    sequence: int
    role: Literal["user", "assistant"]
    content: str
    status: Literal["pending", "completed", "failed", "cancelled"]
    client_message_id: str | None
    rag_query_id: UUID | None
    citations: list[CitationResponse]
    route_metadata: dict[str, Any]
    model_metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ChatDocumentFocusSelect(StrictModel):
    assistant_message_id: UUID
    chunk_id: UUID


class ChatDocumentFocusResponse(StrictModel):
    warning_letter_id: UUID
    document_id: UUID
    document_version_id: UUID
    source_chunk_id: UUID
    source_message_id: UUID
    selected_at: datetime


class ChatThreadSummary(StrictModel):
    id: UUID
    title: str
    model_preference: Literal["auto", "fast", "balanced", "deep"]
    retrieval_preference: Literal["auto", "none", "metadata", "letter", "corpus"]
    active_letter_ids: list[UUID]
    focus: ChatDocumentFocusResponse | None = None
    archived_at: datetime | None
    last_message_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ChatThreadDetail(ChatThreadSummary):
    messages: list[ChatMessageResponse]


class ChatThreadPage(StrictModel):
    items: list[ChatThreadSummary]
    page: int
    limit: int
    total: int
    has_more: bool


class ReviewPatchRequest(StrictModel):
    decision: ReviewDecision = Field(validation_alias=AliasChoices("decision", "state"))
    reason: str = Field(min_length=3, max_length=2_000)
    edited_executive_summary: str | None = Field(default=None, min_length=10, max_length=20_000)
    edited_structured_output: dict[str, Any] | None = None
    edited_output: dict[str, Any] | None = None
    expected_summary_version: str | None = Field(default=None, max_length=200)
    change_ticket: str | None = Field(default=None, max_length=200)

    @field_validator("decision", mode="before")
    @classmethod
    def accept_contract_decisions(cls, value: object) -> object:
        return {"approved": "approve", "rejected": "reject"}.get(str(value), value)

    @field_validator("edited_executive_summary")
    @classmethod
    def normalize_edited_summary(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if len(normalized) < 10:
            raise ValueError("edited output must contain at least 10 non-whitespace characters")
        return normalized


class ReviewActionResponse(StrictModel):
    review_id: UUID
    source_summary_id: UUID
    resulting_summary_id: UUID
    source_document_version_id: UUID
    resulting_revision: int
    review_state: str
    reviewed_by: str
    reviewed_at: datetime
    content_changed: bool
    request_id: str


class ReviewQueueItem(StrictModel):
    summary: SummaryResponse
    company_name: str
    warning_letter_id: UUID
    source_url: str
    failed_checks: list[str]
    marcs_cms_number: str | None
    related_open_items: int = Field(ge=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    high_attention: bool


class ReviewQueuePage(StrictModel):
    items: list[ReviewQueueItem]
    next_cursor: str | None
    previous_cursor: str | None
    has_more: bool
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


class StartIngestionRequest(StrictModel):
    run_type: Literal[
        "discovery",
        "reconcile",
        "lifecycle_sweep",
        "backfill",
        "lifecycle",
        "integrity_sample",
    ] = "discovery"
    source: str = Field(default="FDA warning-letter listing", min_length=3, max_length=2_048)
    reason: str | None = Field(default=None, min_length=3, max_length=1_000)
    change_ticket: str | None = Field(default=None, max_length=200)
    options: dict[str, Any] = Field(default_factory=dict)


class IngestionRunResponse(StrictModel):
    id: UUID
    run_type: str
    source: str
    status: str
    requested_by: str
    parser_version: str
    scope_rule_version: str
    started_at: datetime | None
    completed_at: datetime | None
    metrics: dict[str, Any]
    error_code: str | None
    created_at: datetime


class IngestionRunPage(StrictModel):
    items: list[IngestionRunResponse]
    next_cursor: str | None
    has_more: bool


class RuntimeConfigurationResponse(StrictModel):
    application_version: str
    parser_version: str
    scope_rule_version: str
    taxonomy_version: str
    chunker_version: str
    ai_provider: Literal["none", "gemini", "openai"]
    ai_model_id: str
    ai_prompt_version: str
    ai_configured: bool
    embedding_enabled: bool
    embedding_provider: Literal["google-gemini"]
    embedding_model_id: str
    embedding_dimensions: int
    embedding_input_schema_version: str
    corpus_backfill_years: int
    corpus_active_retention_years: int
    smtp_delivery_enabled: bool
    smtp_configured: bool


class NotificationSettingsResponse(StrictModel):
    subscription_id: UUID
    target_email: str
    enabled: bool
    event_types: list[Literal["NEW", "UPDATED"]]
    smtp_delivery_enabled: bool
    smtp_configured: bool
    queued_deliveries: int
    failed_deliveries: int
    last_delivered_at: datetime | None
    updated_at: datetime


class NotificationSettingsPatch(StrictModel):
    target_email: str | None = Field(default=None, min_length=3, max_length=320)
    enabled: bool | None = None

    @field_validator("target_email")
    @classmethod
    def valid_target_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        from app.notifications import normalize_email

        try:
            return normalize_email(value)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

    @model_validator(mode="after")
    def at_least_one_change(self) -> NotificationSettingsPatch:
        if self.target_email is None and self.enabled is None:
            raise ValueError("target_email or enabled is required")
        return self


class VersionPage(StrictModel):
    items: list[VersionResponse]
    next_cursor: str | None
    has_more: bool


class ReprocessRequest(StrictModel):
    stages: list[
        Literal[
            "scope",
            "parse",
            "summarize",
            "validate",
            "chunk",
            "index",
            "embed",
            "publish",
            "notify",
        ]
    ] = Field(default_factory=lambda: ["parse", "chunk", "index"], min_length=1)
    reason: str = Field(min_length=3, max_length=1_000)
    source_version_id: UUID | None = None
    change_ticket: str | None = Field(default=None, max_length=200)

    @field_validator("stages")
    @classmethod
    def unique_stages(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("stages must be unique")
        return value


class JobResponse(StrictModel):
    id: UUID
    job_type: str
    status: str
    idempotency_key: str
    warning_letter_id: UUID | None
    document_version_id: UUID | None
    created_at: datetime


class JobAccepted(StrictModel):
    job_id: UUID
    status: Literal["queued"] = "queued"


class SavedViewCriteria(StrictModel):
    """The only Drug-letter filters that may be persisted or restored by the portal."""

    query: str | None = Field(default=None, max_length=300)
    drug_subtype: str | None = Field(default=None, max_length=200)
    category: str | None = Field(default=None, max_length=300)
    country: str | None = Field(default=None, max_length=120)
    lifecycle_state: Literal[
        "ACTIVE",
        "NEW",
        "UPDATED",
        "RESPONSE_ADDED",
        "CLOSEOUT_ADDED",
        "RESTORED",
    ] | None = None
    review_state: Literal[
        "auto_approved",
        "approved",
        "needs_revision",
        "rejected",
    ] | None = None
    linked_document: Literal["response", "closeout", "open"] | None = None
    posted_from: date | None = None
    posted_to: date | None = None

    @field_validator("query", "drug_subtype", "category", "country")
    @classmethod
    def normalize_saved_view_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None

    @model_validator(mode="after")
    def valid_posted_range(self) -> SavedViewCriteria:
        if self.posted_from and self.posted_to and self.posted_from > self.posted_to:
            raise ValueError("posted_from must be on or before posted_to")
        return self


SavedViewCadence = Literal["off", "immediate", "daily", "weekly"]
SavedViewAlertState = Literal[
    "off",
    "ready",
    "delivery_unavailable",
    "digest_scheduler_unavailable",
]


class SavedViewCreateRequest(StrictModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=1_000)
    criteria: SavedViewCriteria = Field(default_factory=SavedViewCriteria)
    cadence: SavedViewCadence = "off"

    @field_validator("name")
    @classmethod
    def normalize_saved_view_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("saved-view name is empty")
        return normalized

    @field_validator("description")
    @classmethod
    def normalize_saved_view_description(cls, value: str) -> str:
        return " ".join(value.split())


class SavedViewUpdateRequest(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1_000)
    criteria: SavedViewCriteria | None = None
    cadence: SavedViewCadence | None = None

    @field_validator("name")
    @classmethod
    def normalize_optional_saved_view_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("saved-view name is empty")
        return normalized

    @field_validator("description")
    @classmethod
    def normalize_optional_saved_view_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return " ".join(value.split())


class SavedViewResponse(StrictModel):
    id: UUID
    name: str
    description: str
    criteria: SavedViewCriteria
    frequency: Literal["immediate", "daily", "weekly"]
    channel: str
    active: bool
    alert_state: SavedViewAlertState
    result_count: int = Field(ge=0)
    last_matched: date | None
    owner_id: str
    open_url: str
    created_at: datetime
    updated_at: datetime


class SavedViewPage(StrictModel):
    items: list[SavedViewResponse]
    next_cursor: str | None
    has_more: bool
