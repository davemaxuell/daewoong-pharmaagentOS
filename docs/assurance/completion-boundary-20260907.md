# Step completion boundary — 2026-09-07

Scope: local prerequisite for the specialist execution adapter. No cloud changes,
production activation, source publication, or release approval were performed.

## Finding and change

The previous `complete_step` accepted arbitrary output dictionaries and checked
only the run/step status and usage ceilings. A result could be accepted after
case-state changes, approval withdrawal or expiration, release withdrawal, or a
kill switch. Internal callers also bypassed HTTP usage parsing.

The shared completion service now refreshes and locks the run, invocation, and
case before checking the exact active invocation/attempt and plan binding. It
rechecks plan and required step approvals, workflow/agent/skill/tool release
availability, suspension controls, and the bound limits and output schema.
Usage validation runs for internal callers as well as HTTP callers and rejects
non-finite numbers, negative values, coerced counts, and unknown fields.

An explicit contract allowlist validates `RegulatoryFindingList@2.0.0` with the
existing regulatory contract and `VerificationReport@1.0.0` with the existing
verification response model. Unimplemented schema references return 409;
malformed output or usage returns 422 without echoing validation input.
Rejected completion does not persist output, completion events, or follow-up jobs.

## Verification

- Final full API suite: **508 passed, 7 explicitly gated integration skips** in
  **288.68 seconds**. Report: `.artifacts/completion-boundary-20260907/full-api-tests.xml`.
- Earlier focused case/runtime/completion suite: 32 passed, 1 gated Temporal skip.
  Its sandbox cache-write warning was resolved by running the final suite with
  approved filesystem access and all reports/caches inside this workspace.
- Ruff passed for the final changed runtime code and tests; contract validation
  and diff whitespace checks passed.
- New regressions cover malformed/unsupported contracts, invalid internal usage,
  stale case state, expired/revoked approval, mismatched invocation/attempt,
  global suspension, and withdrawn workflow releases. Rejection tests inspect
  persisted output, event counts, and queued work.

The existing completion state-machine tests now use explicit schema-valid test
fixtures in place of invalid success dictionaries. Those fixtures are not
executed specialist results or independently graded release evidence.

## Remaining work and limits

This change validates structure and current execution bindings. It does not
resolve output citations against retained sources, validate internal evidence
ACLs, prove a submitted verification report exists in storage, or independently
grade model output. The trusted HTTP result path still accepts caller-supplied
schema-valid records. These semantic and provenance checks must be connected to
actual specialist execution before production qualification.

Add exact completion contracts for knowledge, impact, deterministic services and
human artifact review while connecting their runners. A schema-valid `REVISE` or
`BLOCK` report must be routed by the future executor to correction/failure state;
structural acceptance alone does not imply a business PASS. Preserve the production
evaluation promotion guard and all outstanding hosted acceptance requirements.

Local reports belong in `.artifacts/completion-boundary-20260907/` (Git-ignored).
