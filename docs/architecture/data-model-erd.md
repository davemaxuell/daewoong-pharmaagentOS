# Core data model

The SQL source of truth is [`contracts/schema.sql`](../../contracts/schema.sql). This view emphasizes provenance, immutable versions, review, and pre-retrieval authorization.

```mermaid
erDiagram
  INGESTION_RUNS ||--o{ DISCOVERY_SNAPSHOTS : records
  INGESTION_RUNS ||--o{ PROCESSING_JOBS : owns
  INGESTION_RUNS o|--o{ CHANGE_EVENTS : detects

  WARNING_LETTERS ||--o{ DOCUMENTS : contains
  WARNING_LETTERS ||--o{ SCOPE_DECISIONS : has
  WARNING_LETTERS ||--o{ CHANGE_EVENTS : emits
  DOCUMENTS o|--o{ DOCUMENTS : parent_of
  DOCUMENTS ||--o{ DOCUMENT_VERSIONS : versions
  DOCUMENT_VERSIONS ||--o{ SCOPE_DECISIONS : supports
  DOCUMENT_VERSIONS ||--o{ SOURCE_ANCHORS : segments

  DOCUMENT_VERSIONS ||--o{ AI_SUMMARIES : derives
  AI_SUMMARIES ||--o{ VIOLATIONS : contains
  VIOLATIONS ||--o{ VIOLATION_EVIDENCE : grounded_by
  SOURCE_ANCHORS ||--o{ VIOLATION_EVIDENCE : cited_by
  AI_SUMMARIES ||--o{ REVIEWS : reviewed_through
  USERS ||--o{ REVIEWS : performs

  CORPORA ||--o{ CORPUS_GRANTS : authorized_by
  CORPORA ||--o{ DOCUMENT_CHUNKS : contains
  WARNING_LETTERS ||--o{ DOCUMENT_CHUNKS : scopes
  DOCUMENT_VERSIONS ||--o{ DOCUMENT_CHUNKS : chunked_as
  SOURCE_ANCHORS ||--o{ DOCUMENT_CHUNKS : locates
  USERS ||--o{ RAG_QUERIES : asks
  CORPORA ||--o{ RAG_QUERIES : searched

  USERS ||--o{ ROLE_BINDINGS : receives
  USERS ||--o{ SUBSCRIPTIONS : owns
  SUBSCRIPTIONS ||--o{ NOTIFICATION_DELIVERIES : receives
  CHANGE_EVENTS ||--o{ NOTIFICATION_DELIVERIES : triggers
```

## Invariants

- `warning_letters` is the stable lifecycle identity; warning, response, and closeout records are separate `documents`.
- `document_versions`, `scope_decisions`, AI outputs, evidence, reviews, lifecycle events, and audit events are append-only records.
- A current user-visible letter must be `IN_SCOPE_DRUGS`, contain exact normalized class `Drugs`, and have `current_in_scope=true`.
- A retrievable chunk must also be active in an authorized corpus. The scope-safe SQL view is a base; effective `corpus_grants` are joined before either lexical or vector search.
- Raw object keys are private references. Integrity is checked with retained SHA-256 values; browsers receive authorized time-limited downloads or official FDA links.

