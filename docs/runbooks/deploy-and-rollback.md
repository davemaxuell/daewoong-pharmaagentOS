# Deploy and rollback runbook

The platform-neutral configuration and hardened Kubernetes example are in [`infra/deployment`](../../infra/deployment/README.md). The release evidence checklist is in [`docs/assurance`](../assurance/release-evidence-checklist.md).

## Before deployment

1. Confirm approved change, immutable version/digest, reviewed migrations and rollback/forward-fix plan.
2. Retain tests for parser/scope, authz, schema/OpenAPI, RAG/grounding/leakage, and staging smoke/UAT as applicable.
3. Confirm SAST/SCA/secret/container/IaC results, SBOM, provenance/signature where used, and zero unaccepted critical findings.
4. Record active application, parser, scope rule, model, prompt, schema, taxonomy, embedding, and chunker versions.
5. Verify recent backup and successful restore-test evidence; announce window and owner.

## Deploy

1. Apply backward-compatible migrations using the migration identity. Application runtimes must not own the schema.
2. Roll out stateless API/web instances with readiness gates, then workers; maintain scheduler leader election.
   Deploy the private MCP gateway and Temporal workers with separate workload
   identities. Confirm Temporal mTLS, namespace, task queue, and durable activity
   journal before enabling `TEMPORAL_ENABLED` on the API.
3. Run post-deploy checks: liveness/readiness, SSO/roles, one in-scope and negative-scope fixture, browse/detail, audit/SIEM correlation, queue claim, object integrity sample, RAG citation and insufficient-evidence behavior, egress denial.
4. Observe errors, latency, queue age, Product extraction, validation failures, auth denials, and egress alerts through the defined soak period.

## Rollback / forward fix

1. Stop the rollout and disable affected routes/workers if integrity, authorization, scope, or migration safety is uncertain.
2. Prefer rolling application artifacts back while leaving backward-compatible schema in place. Never use destructive database reset/checkout commands.
   The prior production target recorded on the approved evaluation release is the
   rollback candidate; direct registry promotion cannot bypass that release gate.
3. If data changed, identify writes by deployment/request/job IDs. Restore only through the approved recovery plan; preserve versions/audit.
4. Re-run the post-deploy checks on the restored artifact. Reconcile queued/idempotent jobs and suppress duplicate notifications.
5. Record outcome, affected data/jobs/users, active versions, and corrective action before closing the change.
