# Ingestion, parser, and Product-scope runbook

The [Railway backend profile](../../RAILWAY_SETUP.md) runs
`python -m app.background_worker` with a durable daily discovery schedule and
incremental refresh. Its shipped `app.fda_probe` command checks actual FDA access
without database writes. Keep other ingestion consumers disabled when using this
profile; research uses its own leased queue.

## Discovery failure

1. Confirm the last successful run, queue age, source status, and whether the failure is isolated or system-wide.
2. Check FDA availability and current `robots.txt`; do not bypass crawl policy or the configured delay.
3. Inspect export-link discovery, HTTP status/redirects, content type, row count, and column fingerprint. Use the HTML listing fallback only when supported.
4. Retry transient 429/5xx responses through bounded backoff and `Retry-After`. Do not launch parallel manual fetches.
5. Preserve the failed run/snapshot metadata. One failed run never deletes, closes, or marks existing records obsolete.
6. Escalate after the configured consecutive-failure threshold. Close only after a successful full listing reconciliation and queue recovery.

## Parser or canonical-body failure

1. Retain raw bytes, retrieval provenance, hashes, failing parser version, and job/run IDs; mark `PARSE_FAILED`.
2. Confirm URL/host/content-type/size controls passed. Quarantine suspicious HTML/PDF for Security review.
3. Compare against supported fixtures and minimize a public-source regression fixture without altering the retained raw source.
4. Change the narrowest deterministic parser rule, increment the parser version, and run all parser/scope fixtures.
5. Reprocess the affected immutable source version using an idempotency key. Confirm normalized body, anchors, Product metadata, and body hash before resolving.

## Product metadata is missing or contradictory

1. Set/retain `AMBIGUOUS`; withhold body, summary, embedding, publication, and notification.
2. Retry canonical acquisition and deterministic parsing. Do not infer Product from company, office, subject, citations, or AI.
3. If unresolved, route to an administrator/reviewer exception with source anchor and parser diagnostics.
4. A manual exception must be attributable, reasoned, and versioned; never rewrite the original parser decision.

## Out-of-scope record leaked

1. Open a security/data-quality incident. Deactivate the record in the active Drug retrieval view/index; retain raw evidence and audit history.
2. Record source versions, incorrect scope rule/parser version, first/last exposure, users, notifications, answers, and exports potentially affected.
3. Search the corpus for the same failure mode. Disable publication/indexing if the failure is systemic.
4. Correct deterministic Product parsing and increment the scope-rule/parser version.
5. Run positive Drug and negative Biologics/device/food/missing-Product fixtures plus historical reconciliation.
6. Revoke affected derived chunks/summaries from active retrieval, notify internal owners as required, and retain closure/evaluation evidence.

## Source removed, redirected, or restored

1. Preserve prior versions and URLs. Record status and full validated FDA-only redirect chain.
2. Require repeatable confirmation before `SOURCE_UNAVAILABLE`; do not create it for one transient failure.
3. Emit `RESTORED` when the source returns. Never silently replace historical URLs or retrieval dates.
4. Revalidate Product and canonical content on any new destination before publication.
