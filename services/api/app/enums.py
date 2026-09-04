from enum import StrEnum


class ScopeStatus(StrEnum):
    UNVERIFIED = "UNVERIFIED"
    IN_SCOPE_DRUGS = "IN_SCOPE_DRUGS"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    AMBIGUOUS = "AMBIGUOUS"
    SCOPE_CHANGED = "SCOPE_CHANGED"


class ChangeEventType(StrEnum):
    NEW = "NEW"
    UPDATED = "UPDATED"
    RESPONSE_ADDED = "RESPONSE_ADDED"
    CLOSEOUT_ADDED = "CLOSEOUT_ADDED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    RESTORED = "RESTORED"
    PARSE_FAILED = "PARSE_FAILED"
    SCOPE_CHANGED = "SCOPE_CHANGED"
    CORPUS_RETIRED = "CORPUS_RETIRED"


class DocumentType(StrEnum):
    WARNING_LETTER = "warning_letter"
    RESPONSE = "response"
    CLOSEOUT = "closeout"


class ReviewState(StrEnum):
    PENDING = "pending"
    AUTO_APPROVED = "auto_approved"
    APPROVED = "approved"
    NEEDS_REVISION = "needs_revision"
    REJECTED = "rejected"


class ReviewDecision(StrEnum):
    APPROVE = "approve"
    NEEDS_REVISION = "needs_revision"
    REJECT = "reject"


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class Role(StrEnum):
    VIEWER = "viewer"
    ANALYST = "analyst"
    REVIEWER = "reviewer"
    ADMIN = "admin"
    AUDITOR = "auditor"
    SERVICE = "service"
