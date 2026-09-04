# AI validation and RAG quality runbook

## Active local grounded-answer configuration

- Provider adapter: Google Gemini Developer API (local development only)
- User-facing model profiles: `auto`, `fast`, `balanced`, and `deep`
- Approved local profile mapping: `fast` → `gemini-3.1-flash-lite`,
  `balanced` → `gemini-3.5-flash`, `deep` → `gemini-3.7-flash`
- Approved thinking levels: `fast` → `minimal`, `balanced` → `low`, `deep` →
  `medium`; chat requests omit sampling parameters that current Gemini 3 models
  do not require
- Retrieval embedding: `gemini-embedding-2`, fixed at 1,536 dimensions
- Prompt version: `rag-grounded-v1`
- Secret source: server-side `GEMINI_API_KEY`; never browser/runtime response/audit data
- Failure behavior: reject uncited or out-of-range evidence markers and fall back to
  the next server-allowlisted profile model, then to retrieved official-source passages

Confirm the non-secret runtime state through the admin configuration endpoint. It
reports generation and embedding enablement, model, dimensions, and input-schema
version without returning provider credentials.
Changing the provider, model, prompt, language policy, or output validator requires
the model-change checks below. Rotate a key immediately after accidental disclosure;
do not rely on repository removal as revocation.

`auto` is a router decision, not an unbounded provider alias. Confirm that every
attempted/effective model ID belongs to the configured allowlist and that each
response and generation record contains the requested profile, routed profile,
attempted model ID, nullable effective model ID, `generation_used`, route reason,
and router version. Deterministic `none` and metadata-only responses record no model
attempt. A model-only `none` response may record an attempt but must record zero
retrieved chunks and never claim official-document evidence. Any rejected/provider-
failed output records an attempted model but must never claim its output was used.
Quota or transport failure may move from Deep to Balanced/Fast, or between Fast and
Balanced. Preserve the requested/routed profile, record the primary attempted model,
and report the actual validated model as the effective model.

## Unexpected retrieval route

1. Preserve the thread/message/generation IDs, explicit filters, inherited letter
   scope, requested retrieval mode, effective strategy, stable route reason, and
   selected source chunks. Do not log private model reasoning.
2. Confirm the route was planned before any corpus chunk query. `none` and metadata-
   only requests must not perform semantic corpus search.
3. For a dossier or explicit letter request, verify every cited chunk belongs to the
   selected current document version. For a comparison, verify the candidate set is
   limited to the explicitly resolved letters.
4. For a follow-up, inspect the server-owned thread scope and last citations. Do not
   reconstruct scope from untrusted browser history or concatenate the entire thread
   into a retrieval query.
5. Add the utterance to the planner matrix and retrieval-isolation regression suite
   before changing a route rule.
6. For a false scope refusal, distinguish a clearly unrelated request from ambiguous
   wording. Verify authorized company/MARCS resolution and current dossier/thread
   context before reviewing the semantic scope result. Scope classification judges
   meaning and recent conversation context rather than requiring literal regulatory
   keywords; provider failure or an ambiguous result must fail closed.

## Embedding backfill or model change

1. Keep one approved embedding model/dimension active across both queries and
   documents. Generation-model selection must not change the retrieval space.
2. Key each vector by chunk ID, provider, model, dimension, input-template schema,
   content SHA-256 and exact prepared-input SHA-256 (including title). Retry only
   missing or stale keys so a worker restart cannot duplicate records.
3. Backfill into a parallel pgvector set/index and measure retrieval against the
   lexical baseline before activation. Never mix vectors from different model spaces.
4. Confirm corpus, ACL, active-letter, and current-version filters are applied before
   approximate nearest-neighbor ranking.
5. Retain lexical retrieval as the fail-closed fallback if the embedding provider or
   vector index is unavailable; record the degraded mode in the generation audit.

For a new managed PostgreSQL database, run `fda-intel init-db` once with the
restricted migration/bootstrap identity. It creates the `vector` extension before
the ORM tables. Set `AUTO_CREATE_SCHEMA=false` on API and worker runtime identities
afterward; they do not need extension/schema-creation grants. Add the HNSW index
concurrently with the controlled migration only after the initial exact-search
backfill has been validated.

Enable embeddings only after the server secret is installed, then run
`fda-intel embed-current --limit 500` repeatedly (or omit `--limit`) until it reports
zero new rows. `--letter-id <uuid>` narrows an operational retry. Each completed
chunk is committed independently, so restarting the command skips its immutable
chunk/model/content key. Newly ingested current versions enqueue an idempotent
`embed` worker job only when both `EMBEDDING_ENABLED=true` and the server-side key
are present. Never pass the key as a CLI argument.

## AI extraction fails validation

1. Keep the official normalized source available; leave derived output `pending` or `needs_revision` and ineligible for active RAG synthesis.
2. Record source version/hash, anchors, model, prompt, schema, taxonomy, validator version, and failed rule. Do not store chain-of-thought.
3. Retry at most once with machine-readable validation feedback if policy allows.
4. Route unresolved output to side-by-side review. Reviewer edits/approval/rejection require a reason and append-only audit event.
5. Add a minimized case to the evaluation suite before changing prompt/model/validator behavior.

## Incorrect or unsupported RAG answer

1. Preserve query ID/hash, identity/role result, applied filters, corpus grants, retrieved chunk IDs/ranks, source versions, model/prompt/chunker versions, citations, and feedback in the controlled evaluation store.
2. Triage in order: authorization/scope, source parsing/anchors, retrieval, reranking, generation, citation/grounding, presentation.
3. If any unauthorized or out-of-scope chunk reached the model, stop affected RAG traffic and use the security-incident runbook.
4. Fix the narrowest layer and add a regression question. Never hide the issue by broad prompt wording.
5. Run retrieval, citation, insufficient-evidence, prompt-injection, and cross-corpus suites before activation.

## AI provider outage or material behavior change

1. Open the provider circuit after bounded failures; keep source browsing/search available and label AI features unavailable.
2. Do not silently switch to an unapproved endpoint/model. A fallback must already be approved, pinned, and evaluated.
3. Queue safe retryable jobs without duplicating summaries or notifications; protect current discovery capacity.
4. For model/provider/version changes, repeat schema, grounding, taxonomy, injection, leakage, and representative Drug benchmark gates under change control.
