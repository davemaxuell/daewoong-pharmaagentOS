# Deployment baseline

This directory contains a platform-neutral configuration shape and an example hardened Kubernetes base. It is a starting template, not authorization to deploy to production. Final ingress/WAF, workload identity, secret manager, private managed data services, egress enforcement, certificates, SIEM, backup/PITR, and HA settings depend on Daewoong's approved platform.

## Container builds

Build the API from the repository root (including contracts and corpus) and the standalone Next.js portal from its application context:

```powershell
docker build --file services/api/Dockerfile --tag fda-api:local .
docker build --tag fda-web:local apps/web
```

Release builds must use immutable tags/digests, generate an SBOM, pass SAST/SCA/secret/container/IaC scans, and be signed/attested where supported. The checked-in Kubernetes image names are deliberately non-routable placeholders; replace them in an environment overlay with approved immutable digests.

## Workload-specific runtime wiring

All Python processes retain the same strict production settings validation.
Provision these references through the approved secret-management channel before
starting the workloads; the repository contains no secret values:

- `fda-worker-runtime` and `pharma-orchestrator-runtime` each need
  `api-session-public-key` in addition to their existing keys. This is the public
  verification key, never the portal's private signing key.
- `fda-api-runtime` and `fda-worker-runtime` each need `object-store-endpoint`
  (HTTPS), `object-store-bucket`, `object-store-region`, `object-store-access-key-id`
  and `object-store-secret-access-key`. Use the same governed evidence bucket with
  separately scoped credentials. The base explicitly selects S3 storage so these
  read-only containers cannot silently fall back to local container storage.
- The API and orchestrator mount `pharma-temporal-mtls` with `ca.crt`, `tls.crt`
  and `tls.key`. Approved environment overlays should provide workload-specific
  client identities/certificates as required by the Temporal authorization policy.
- The MCP gateway and orchestrator disable model generation and embeddings because
  their current process implementations do not call those providers. The ingestion
  worker retains its model/embedding settings. Only the API and orchestrator enable
  Temporal; the ingestion worker and MCP gateway do not dispatch Temporal work.

API health probes connect directly to the Pod but send `Host: fda-api`. Retain that
internal name in `ALLOWED_HOSTS`; do not weaken Host validation with `*`.
Regression tests validate these settings with synthetic secret values and exercise
all three API probes through the real middleware. They do not prove that secrets,
network routes, storage or certificates exist in the target cluster.

These references do not complete the separate managed-secret-provider integration
or replace the environment overlay, least-privilege grants and connectivity checks.

## Managed PostgreSQL and embedding bootstrap

Provision an empty PostgreSQL 16 database with pgvector available. Do not apply
`contracts/schema.sql` to the API database; that file is the normalized analytical
reference, while the runnable API uses the exact SQLAlchemy schema in `public`.
For the first deployment only, use a dedicated migration identity:

```powershell
$env:DATABASE_URL = "postgresql+asyncpg://MIGRATION_USER:URL_ENCODED_SECRET@HOST/DATABASE?ssl=require"
$env:OBJECT_STORE_PATH = "C:\writable-migration-staging"
fda-intel init-db
$migrationFiles = @(
    '20260904_agent_os_control_plane.sql',
    '20260904_agent_os_orchestration.sql',
    '20260904_internal_knowledge_and_impact.sql',
    '20260904_verification_and_artifacts.sql',
    '20260904_evaluation_and_control_tower.sql',
    '20260904_durable_commercial_hardening.sql',
    '20260904_controlled_integrations.sql'
)
foreach ($migrationFile in $migrationFiles) {
    psql "postgresql://MIGRATION_USER@HOST/DATABASE?sslmode=require" --set ON_ERROR_STOP=1 -f "infra/migrations/$migrationFile"
    if ($LASTEXITCODE -ne 0) { throw "Migration failed: $migrationFile" }
}
psql "postgresql://MIGRATION_USER@HOST/DATABASE?sslmode=require" --set ON_ERROR_STOP=1 -f infra/policies/postgres-runtime-roles.sql
if ($LASTEXITCODE -ne 0) { throw 'Runtime grants failed' }
```

Then bind the NOLOGIN roles to short-lived workload identities, revoke DDL from
the API/worker identities, and deploy with `AUTO_CREATE_SCHEMA=false`. Backfill
only missing current-corpus embeddings; the command commits each completed chunk
and is safe to resume:

For an existing database, apply the reviewed forward migrations with the migration
identity before deploying the corresponding application version:

- `infra/migrations/20260831_chat_thread_focus.sql` for durable selected-document chat scope;
- `infra/migrations/20260831_saved_views_persistence.sql` for owner-scoped saved-view CRUD;
- `infra/migrations/20260831_embedding_space_provenance.sql` for embedding-space identity.

The embedding migration marks older rows as `legacy-unknown-v0`; those rows are
intentionally excluded until the active chunker/template space is re-embedded.

```powershell
fda-intel embed-current --limit 100
```

After provenance backfill and retrieval validation, apply
`infra/migrations/20260831_chunk_embeddings_hnsw.sql` outside a transaction. A
future retained-schema change requires a reviewed forward migration; `create_all`
is only the empty-database baseline and cannot upgrade existing columns.

## Kubernetes example

Render the base without contacting a cluster:

```powershell
kubectl kustomize infra/deployment/kubernetes/base
```

`kubectl kustomize` is an offline render check. Schema-aware `kubectl apply --dry-run=server` requires an approved staging cluster/context and should be part of environment validation.

Run `python scripts/deployment-preflight.py <rendered-overlay.yaml>` against the
chosen environment render before applying it. The base intentionally fails this
check because its image digests, domains and external database egress are placeholders.
Passing this static check is not production approval; see the
[current qualification record](../../docs/assurance/deployment-readiness-20260905.md).

Before applying an environment overlay:

> The checked-in runtime uses PostgreSQL `processing_jobs` as its durable queue and
> supports either local filesystem or S3-compatible immutable FDA object storage.
> Production should set `OBJECT_STORE_BACKEND=s3` and inject the same private,
> environment-scoped bucket credentials into API, worker and discovery workloads.
> Filesystem mode remains for local development or an explicitly approved shared,
> encrypted, versioned volume. The readiness probe verifies configured storage.

1. Provision `fda-api-runtime`, `fda-web-runtime`, and `fda-worker-runtime` through the approved secret manager/CSI integration. Do not commit Secret manifests. The web secret contains the Auth.js secret, enabled Google/Naver OAuth client credentials, and API-session private key; the API receives only the matching public key.
2. Add environment-specific network policy for the corporate ingress, private PostgreSQL/queue/object endpoints, approved FDA hosts through the egress proxy, Gemini/AI gateway, notifications, DNS, and SIEM. Google login needs controlled HTTPS egress to its authorization/token/user-info endpoints. Naver login needs controlled HTTPS egress to `nid.naver.com` and `openapi.naver.com`. The base defaults to deny and intentionally cannot reach external dependencies.
3. Replace placeholder images and `*.example.invalid` values; register `/api/auth/callback/google` and/or `/api/auth/callback/naver` exactly for enabled providers, enable the account/domain allowlist, and assign reviewer/admin roles only through server-side exact-email lists. Google Workspace-domain entries require a matching verified `hd` claim. Naver requires a returned `@naver.com` profile email; prefer exact Naver email admission because adding `naver.com` to the domain allowlist authorizes every Naver Mail account.
4. Enable PostgreSQL 16 with `pgvector`, run the controlled initial bootstrap or approved forward migrations with a separate migration identity, apply `postgres-runtime-roles.sql`, then deploy API/web before workers. Keep `EMBEDDING_DIMENSIONS=1536` unless a controlled full-corpus re-embedding migration is approved.
5. Configure managed PostgreSQL HA/PITR, object versioning/encryption, persistent queue, restore tests, centralized telemetry, WAF/TLS, and at least two API/web replicas.
6. Configure the platform scheduler with `concurrencyPolicy: Forbid` to run one bounded
   `fda-intel discover --source-url <approved FDA listing URL>` cycle on the approved
   cadence (the recommended starting point is every six hours). The durable worker
   completes queued embedding and notification work; do not run overlapping scrapes.
7. Run the release gates in the deployment runbook and retain evidence.

The base deliberately omits an Ingress because public/private gateway resources, annotations, certificates, and WAF integration are platform-specific. It also does not deploy PostgreSQL, Redis, MinIO, a secret store, or an egress proxy; those must be approved managed/private dependencies in production.
