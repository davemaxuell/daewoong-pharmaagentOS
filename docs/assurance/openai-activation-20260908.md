# OpenAI provider activation — 2026-09-08

The owner supplied an OpenAI key and authorized replacing the generation provider.
The server now supports `LLM_PROVIDER=openai` through the Responses API. Gemini
remains available when explicitly configured. No browser credential was added.

## Implementation

- Provider-aware defaults select `gpt-5-mini` for chat profiles, analysis and
  translation, with no cross-provider document fallback models.
- Chat shares the existing language and citation validation. Stream text remains
  provisional until completion and validation; failed drafts emit reset events.
  Missing or inconsistent stream completion, refusals and incomplete responses
  fail closed. Reasoning and provider metadata are not emitted to users.
- Document generation shares existing source-token preservation, anchor-aware
  prompts and bounded translation validation. The OpenAI adapter converts the
  document schemas to strict JSON Schema and bounds transient retries.
- Requests use the fixed official HTTPS endpoint, server-side bearer credentials,
  `store=false`, configured timeouts/output limits and no redirects. Error text
  omits credentials and provider response bodies.
- Runtime configuration and the API contract recognize the OpenAI provider.

## Configuration evidence

Vercel project `pharmaagent-os` has `OPENAI_API_KEY` stored as a Secret for both
Production and Preview. `LLM_PROVIDER=openai`, all six chat/document model settings
use `gpt-5-mini`, and both document fallback lists are empty. Embeddings remain
disabled; the existing Gemini embedding implementation was not changed.

The local Vercel CLI's non-ASCII hostname header caused its ByteString exception.
A workspace-local Node preload substituted an ASCII hostname only for the CLI
process, restoring the existing login without changing credentials or the OS name.

The temporary key file was deleted after provisioning and live testing. An exact
secret scan found zero matches in tracked or unignored files. No secret is retained
in this evidence document, source, tests or handoff.

## Verification

- The supplied key returned HTTP 200 on a minimal Responses API request.
- Real provider calls passed cited English chat, scope classification, Korean
  translation and structured letter analysis using a short fictional training
  passage. This exercised the application adapter, not just authentication.
- The first translation run rejected an English-heavy parenthetical heading.
  Explicitly requesting Korean-only descriptive headings fixed the live check;
  validation thresholds were preserved.
- Existing AI, document-artifact and configuration regression tests: 110 passed.
- OpenAI transport, failure handling, configuration and runtime tests: 15 passed.
- Full backend regression run: 528 passed, 7 environment-gated skips in 391 seconds;
  the additional runtime-reporting test passed in the subsequent 15-test provider run.
- Ruff and the contract validator passed.

Local ignored evidence is under `.artifacts/openai-setup-20260908/`, including safe
connection, provider and provisioning results. The live tests used synthetic
supplied evidence; they are not FDA ingestion, clinical/regulatory qualification,
or production website end-to-end evidence.

## Remaining service dependency

The production database/object-store connection, application schema and FDA corpus
are still pending. The home page continues to save browser-local review requests.
Production environment inspection confirmed that database and Supabase connection
variables are absent; a public check returned HTTP 200 for `/` and 500 for `/health/live`.
Configuring a working LLM does not activate the complete case/agent workflow or
remove the existing live-workspace/data errors. No database project was changed
as part of this provider activation.

Implementation references: [Responses streaming](https://developers.openai.com/api/docs/guides/streaming-responses),
[structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs).
