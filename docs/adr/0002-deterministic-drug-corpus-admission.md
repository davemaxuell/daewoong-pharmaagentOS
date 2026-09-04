# ADR 0002: Deterministic Drug corpus admission

- Status: accepted and release-blocking
- Date: 2026-08-29
- Owners: Regulatory Intelligence, Backend/Data, QA, Security

## Decision

Only canonical FDA detail metadata containing the exact normalized Product class `Drugs` may enter normal display, summarization, chunking, notification, or RAG. Listing columns, company/subject terms, issuing office, body language, taxonomy labels, and model output may prioritize work but cannot admit a record.

Parsed Product metadata without `Drugs` is `OUT_OF_SCOPE`. Missing, empty, malformed, or contradictory top-level Product metadata is `AMBIGUOUS` and withheld. Every decision records the source version, raw and normalized values, source anchor, rule version, timestamp, and method. AI never makes or overrides this decision.

## Consequences

Parser/scope changes require version increments, positive and negative fixture regression, historical reconciliation, and controlled release evidence. An out-of-scope record reaching the portal or RAG is both a data-quality and security incident. Manual exceptions are attributable/versioned and cannot rewrite original parser evidence.

