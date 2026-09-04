# Agentic RAG and persistent chat

## Objective

The assistant plans the smallest evidence operation that can answer the current
request. It does not search the entire FDA corpus on every turn. The planner emits
only a stable strategy and reason code; private model reasoning is neither exposed
nor stored.

## Routing matrix

| User case | Retrieval strategy | Evidence boundary | Default model profile |
| --- | --- | --- | --- |
| Greeting, capability/help, account or model-setting question | `none` | No FDA retrieval; deterministic service guidance | No model or `fast` |
| General, stable FDA Drug warning-letter explanation that does not require a document | `none` | Model-only conversation; no document query and no claim of official evidence | `fast` |
| Source URL, issuer, country, posted/issue date, count or latest-letter request | `metadata` | Authorized structured letter rows; no semantic corpus scan | No model or `fast` |
| Ask launched from one dossier, explicit letter ID/MARCS/company, or follow-up on that letter | `letter` | Current authorized chunks for that letter only | `fast` |
| Explicit comparison of two or more letters | `multi_letter` | Current authorized chunks for only the resolved letters | `balanced` |
| Broad patterns, recurring findings, trends, or discovery across manufacturers | `corpus` | Hybrid lexical/vector search over the authorized current corpus | `balanced` |
| Compare an internal pipeline/workflow with a selected warning letter | `letter` or `multi_letter` with comparison guard | FDA claims come only from selected source chunks; user-supplied workflow facts remain unverified context | `deep` |
| Translate, summarize, or inspect findings for a selected letter | `letter` plus persisted artifact reuse | Cached artifacts guide anchors but are never cited as FDA evidence | `fast` or document-artifact profile |
| Unrelated medical, legal, or general-knowledge request | `none` | Scope-boundary response; no model-memory answer | No model |

Explicit user filters and dossier locks override automatic scope resolution. An
explicit **All letters** selection intentionally suspends the dossier filter for that
request; the client must omit the locked letter ID rather than sending contradictory
scope instructions. A
thread may inherit its last resolved letter IDs for a referential follow-up such
as “그 서한에서 FDA가 또 무엇을 요구했나요?”. A clear new topic or explicit
different letter resets that inherited scope. Historical user messages are not
blindly concatenated into every retrieval query.

The domain gate first stops greetings and clearly unrelated requests without a
chunk query. For wording that is merely ambiguous, it then resolves company and
MARCS references against authorized current FDA Drug sources. A recognized corpus
company, an explicit current-request dossier, or a natural referential follow-up
establishes application context even when the user does not repeat words such as
“FDA,” “pharma,” or “warning letter.” If deterministic context is still
inconclusive, an allowlisted fast model performs a constrained semantic scope
classification; unavailable, invalid, or ambiguous classification fails closed.
Explicit non-domain intent such as stock-price, corporate-profile, travel, cooking,
personalized medical, or legal requests remains inadmissible even with a selected
letter. Landing-page suggestions are self-contained FDA Drug warning-letter
questions validated against the same planner in both supported languages.

Selecting a retrieved source for inspection does not silently change scope. The
explicit **Use as main document** action submits the persisted assistant-message ID
and cited chunk ID to a dedicated endpoint. The API verifies that the completed
answer belongs to the caller's thread, that the chunk was actually cited, and that
the current FDA Drug document/version and ACL remain admissible. It then stores the
server-derived letter, document, exact version, source chunk and source message as
the thread focus. Subsequent letter retrieval is constrained to that exact version
until the user clears the focus, chooses another cited document, or switches to an
unscoped corpus/conversation mode.

## Trust and authorization order

1. Validate the Google- or Naver-backed application session at the web boundary.
2. Send a short-lived, server-signed application assertion to the API. Provider
   tokens never reach browser JavaScript or the API database.
3. Derive ownership from the verified principal; never accept `owner_id` from a
   client.
4. Resolve thread ownership and corpus grants. Cross-user thread identifiers are
   concealed with `404` responses.
5. Apply active corpus, current document version, ACL, letter and metadata filters
   before ranking.
6. Treat the question, conversation, source HTML and cached AI artifacts as
   untrusted data. Only retained FDA source chunks can support cited FDA claims.
7. Buffer and validate citation markers/language before marking an assistant
   message complete.

## Persistence and recovery

An ID is allocated before a generation begins. The user message and a pending
assistant placeholder are committed atomically with an idempotent client message
ID and canonical request fingerprint. The assistant then transitions to completed
or failed; the same key can resume failed or stale work but cannot be reused with
different input. User and pending assistant records retain the normalized request
snapshot (filters, language, source limit, retrieval mode and model profile), so a
reload can retry with the identical fingerprint. The completed message stores the answer, citations,
requested/effective retrieval mode, requested/effective model profile, attempted
and effective model IDs, whether generated output was actually used,
prompt/router versions, evidence sufficiency and latency. Provider chain-of-thought
is never persisted.

This makes `/chat/threads/{thread_id}` reloadable across devices and prevents a refresh or
duplicate submission from paying for a second generation. Pending/error states
remain auditable and can be safely reconciled.

The existing JSON query contract remains available for non-streaming clients. The
additive NDJSON stream reports retrieval, generation, and validation phases and may
emit provider text as a clearly provisional draft. A rejected attempt sends a reset
before retry. The only authoritative answer is the final `complete` event, emitted
after whole-answer validation and the database commit; draft deltas are never
persisted and never activate citations. Disconnect or cancellation leaves no
partial answer and cannot overwrite a superseded attempt.

Conversation history is searched server-side within the verified owner boundary.
The optional normalized query matches titles or persisted message content, treats
SQL wildcard characters literally, and preserves the default exclusion of archived
threads. No cross-account search index or provider credential is stored.

## Embeddings and cloud storage

Normalized documents, chunks, chat records and versioned chunk embeddings belong
in managed PostgreSQL. Raw immutable FDA responses remain in versioned encrypted
object storage and are referenced by hash/key; they should not be copied into the
chat prompt unless admitted, parsed and chunked.

The approved retrieval embedding is independent of the user-selected generation
model. A vector row is immutable across chunk ID, provider, embedding model,
dimension, input-template schema, source content SHA-256 and the exact prepared
input SHA-256 (including normalized document title). Retrieval admits only rows
whose chunker version and complete vector-space provenance match the running
planner. Queued jobs retain that same specification so a rolling model change is
honored and an unsupported provider/template change fails closed instead of mixing
spaces. Changing any vector-space coordinate requires a parallel re-embedding.
PostgreSQL uses pgvector with a fixed 1,536-dimensional HNSW index. SQLite stores
vectors as JSON and performs bounded cosine ranking for development/tests; lexical
retrieval remains the production and local fail-safe whenever semantic ranking is
unavailable.

## Model profiles

The client selects a stable profile rather than an arbitrary provider model ID:

- `auto`: the planner chooses from observable request complexity.
- `fast`: low-latency single-letter and straightforward grounded answers.
- `balanced`: multi-letter and broad corpus synthesis.
- `deep`: complex internal-comparison support with the same no-compliance-
  conclusion guard.

Administrators control the allowlisted model mapping. Every response records the
requested and routed profiles, the attempted model (if any), the effective model
only when validated generated output is present, and `generation_used`. A
deterministic or metadata-only response reports no model use; a rejected/provider-
failed generation reports an attempted model but no effective one. Manual selection
never changes corpus authorization, evidence requirements, or the embedding model.
