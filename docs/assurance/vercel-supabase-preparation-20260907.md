# Vercel/Supabase production preparation — 2026-09-07

Production on Vercel/Supabase is the confirmed target. Local preparation is
verified; production activation remains blocked by target setup and incomplete
specialist execution/independent evaluation. No cloud resources were created,
linked, migrated, scheduled, deployed or promoted during this preparation.

## Implemented

- Three Vercel Services: portal, private API and authenticated bounded worker.
  Case/ingestion lanes use existing atomic claims, lease recovery and checkpoints.
  Cooperative slicing preserves failure retries and monotonic claim fencing.
- Explicit Vercel secret provider with deployment metadata checks. Validation
  errors omit input values. Platform injection is not attestation of secret
  visibility; services retain a shared project environment trust boundary.
- Reviewed contracts and the synthetic corpus are bundled into the Python service.
  Upload rules include required inputs and exclude local secrets.
- Supabase SQL removes browser-role access and enables backend RLS policies on
  all 57 application tables. Existing runtime grants and application ACLs remain.
- Supabase Cron/Vault SQL prepares two fixed worker triggers. Worker activation,
  initial account admission and model use remain disabled in the template.
- Production runbook, architecture decision and CI boundary regression updated.

## Evidence

Artifacts are retained inside `.artifacts/vercel-production-20260907/`.

| Check | Result |
| --- | --- |
| Full native API regression | **489 passed, 7 gated integration skips**, 336.74 seconds; `full-api-tests.xml` |
| Focused worker/configuration regression | **58 passed**; `worker-tests.xml` |
| Live PostgreSQL boundary and packaged-resource tests | **4 passed**; `boundary-tests.xml` |
| Ruff | API, all tests, deployment preflight and resource build script passed |
| Contracts | OpenAPI, schemas, fixtures, vocabulary, approval freshness and MCP checks passed |
| Vercel configuration | No instance-validation errors against the downloaded official schema using Draft7Validator |
| CI and diff | Workflow YAML parses; `git diff --check` passed |

The worker tests cover authentication, fixed trigger scope, separate queue lanes,
concurrent claims, checkpoint resume, timeout cancellation and retry allowances.
The live database test applied the boundary inside an isolated PostgreSQL 16
transaction: browser queries failed, runtime reads retained visibility, runtime
deletion stayed forbidden, and an unrelated table's grants remained unchanged.
All test DDL/roles were rolled back and the qualification container stopped.

The packaging test copies resources into an isolated service directory and loads
hash-validated agent/workflow contracts and the labeled synthetic corpus there.
The official Vercel schema contains nonstandard annotations that prevent strict
meta-schema checking; instance validation was performed separately. This is not
a hosted Vercel build proof. The Cron SQL has not been applied to Supabase.

No frontend code changed in this preparation. Earlier frontend, container scans,
Temporal and restore evidence remains in the [previous audit](launch-readiness-20260906.md).
Those image scans do not attest a new Vercel deployment or newly modified sources.

## Outstanding activation work

Confirm dedicated projects/domain; configure secrets, migration/runtime identities,
OAuth subjects and telemetry. Qualify exact private Host routing, pooler grants,
Storage restrictions, OAuth/revocation, Cron HTTP delivery, job recovery under
platform termination, evidence backup/restore and rollback on the target.
The Cron triggers drain jobs; automatic six-hour discovery still needs scheduling.

Connect dispatched specialists to real execution and independently observed
evaluation. Preserve production promotion guards until release gates and designated
human decisions are complete. The [production runbook](../../infra/deployment/vercel/README.md)
records activation order, constraints, pause procedures and official references.
