# Production on Vercel and Supabase

The service owner selected this production platform on 2026-09-07. The repository
now prepares three Vercel Services: the Next.js portal, private FastAPI API, and
an authenticated, bounded database-queue worker. Supabase supplies PostgreSQL,
private evidence Storage, Vault, and Cron. The first dedicated build is deployed
at https://pharmaagent-os.vercel.app; its frontend responds, while backend setup remains incomplete. See [hosting evidence](../../../docs/assurance/github-vercel-hosting-20260907.md).

The web receives `API_BASE_URL` through a private service binding. Public routing
exposes health checks and exactly two worker trigger paths; ordinary browser API
requests pass through the authenticated Next.js BFF. Worker triggers require the
server-only bearer secret and accept only an absent body or `{}`. Callers cannot
choose a job, source URL, model, or tool through this endpoint.

## Files and production decisions

- `production.env.example`: non-secret configuration; placeholders must be resolved.
- `supabase-data-api-boundary.sql`: explicit application-table grants and RLS boundary.
- `supabase-worker-cron.sql`: two named, every-minute triggers using Vault references.
- Root `vercel.json`: services, routing, 300-second function limits and resource builds.
- `scripts/prepare-vercel-resources.py`: bundles reviewed contracts and the explicitly
  synthetic internal corpus into the Python service; local secrets are excluded.
- [Architecture decision](../../../docs/adr/0004-vercel-supabase-production.md):
  platform secrets and bounded database workers, with qualification limits.

The selected Vercel team currently has no dedicated PharmaAgent OS project. Do not
link to the separate FDA application. Confirm dedicated Vercel/Supabase project
identifiers, exact domain, operating plan and service owner before cloud activation.

## Database and evidence setup

Use a dedicated Supabase project. Enable pgvector and create a **private**
`pharma-evidence` Storage bucket. With a migration identity on a direct/session
connection, follow the fresh-database prerequisites in `.github/workflows/ci.yml`
and apply the control-plane migration, ORM bootstrap (`python -m app.cli init-db`),
remaining migrations and runtime grants in the
[handoff's authoritative order](../../../PHARMA_AGENT_OS_IMPLEMENTATION_HANDOFF.md#database-migration-order).
`contracts/schema.sql` is a reference, not the runtime bootstrap. Keep production
`AUTO_CREATE_SCHEMA=false` and never use the database owner as a runtime login.
Run that one-off CLI from `services/api` with its migration-only environment
(`APP_ENV=staging`, `SECRET_PROVIDER=environment`, the migration `DATABASE_URL`,
and required Storage settings). Do not copy Vercel system metadata onto a local
machine to bypass the production provider check. These one-off process settings
must not replace the Vercel production environment.

Supabase may install pgcrypto in `extensions`. Include `public, extensions` in
the migration and runtime login search paths, and grant the runtime logins USAGE
on `extensions`; this keeps the migration's unqualified digest calls resolvable.

Apply `supabase-data-api-boundary.sql` after those migrations. It revokes browser
role access and enables RLS on all 57 current application tables. Runtime policies
permit the existing backend roles to exercise their existing grants; API code
continues to enforce user and evidence ACLs. The script neither changes Supabase
Auth/Storage schemas nor unrelated tables. New application tables must be added
to this boundary; a regression check compares the list to ORM metadata.

Provision distinct, non-owner, non-BYPASSRLS database logins that inherit
`fda_api_runtime` and `fda_worker_runtime`, respectively. Set `DATABASE_URL` and
`WORKER_DATABASE_URL` to their transaction-pooler URLs (port 6543, encoded passwords,
`sslmode=require`). The application disables local pooling and prepared-statement
caches for that port. Verify grants and pooler connectivity with each actual login;
merely granting a NOINHERIT group does not establish the login's inheritance settings.

Use `SUPABASE_SECRET_KEY` only on the server. The current Storage adapter uses
content-addressed, conditional writes. Supabase Storage is not WORM storage: qualify
evidence backup, restore, retention and administrative deletion controls separately
from database PITR. Never place this key in a `NEXT_PUBLIC_*` variable.

## Vercel configuration and secrets

Import the repository root as a Services project. The API and worker share source
code but use different entrypoints and database URLs. Build both with the supplied
resource-copy command; missing reviewed contracts must fail the build.

Populate the template for Production. Set credentials as Vercel **Secret** values:
Anonymous browser session secret (`PORTAL_SESSION_SECRET`), API session private key, both
runtime database URLs, Supabase secret key, worker trigger secret, model credentials
when qualified, and collector authentication where required. Configure the matching
OIDC public key and issuer/audience. Use separate Preview resources and secrets.
Do not manually set `API_BASE_URL`; the service binding supplies it at runtime.

`SECRET_PROVIDER=vercel` accepts platform-injected deployment secrets. Startup
requires Vercel system metadata; this check is not cryptographic attestation and
cannot prove that dashboard variables were marked Secret. Keep system variables
available. Project environment values are a shared trust boundary: separate
DATABASE_URL selection is not isolation from every secret held by another service
in this same project. If separate secret visibility is mandatory, qualify distinct
projects with authenticated connectivity before admitting data.

The portal has no account login or provider callbacks. Set `PORTAL_SESSION_SECRET`
to a generated secret of at least 32 characters in each hosted environment.
Anonymous browser identities receive only viewer authority through short-lived
RS256 `public_session` assertions. Do not grant reviewer/admin roles to public
visitors. Models and workers remain disabled until qualified.

Set `ALLOWED_HOSTS` to exact public, internal API and worker/probe hosts observed
in the target deployment. Binding reachability does not replace OIDC checks.
Hosted Host/proxy behavior must be tested; do not solve routing failures by enabling
wildcard host admission. Choose `TELEMETRY_BACKEND=vercel_logs` for bounded metadata
in managed Vercel runtime logs, or retain `otlp` with an actual HTTPS collector.
Vercel log mode requires platform metadata and the Vercel secret provider; it does
not claim external trace collection or long-term audit retention. Configure alarms
and retention separately for the intended operational requirements.

## Bounded workers and scheduling

`SERVERLESS_WORKER_ENABLED=false` rejects triggers until activation. When enabled,
Temporal and the embedded polling worker must be disabled. Each request recovers
expired job leases and processes at most eight jobs within a default 210-second
cooperative slice, leaving time before the configured 300-second function deadline.
Case and ingestion lanes claim only their own job types using the existing atomic
queue claim. A cooperative timeout preserves checkpoints and refunds that attempt's
failure budget while retaining monotonic claim fencing. Hard termination is recovered
through the existing five-minute lease and consumes the ordinary retry budget.

Enable Supabase pg_cron, pg_net and Vault. Add `pharma_worker_origin` (exact HTTPS
origin) and `pharma_worker_trigger_secret` (matching the Vercel secret) through the
Vault dashboard. After proving authenticated triggers on the actual deployment,
apply the Cron SQL. Its commands store references, not literal credentials.
These jobs **drain queued work**; they do not enqueue the six-hour FDA discovery
schedule. Add and qualify that schedule before claiming automatic corpus refresh.

Monitor HTTP outcomes in `net._http_response`, Cron history, pending-job age, stale
leases, dead letters, repeated time slices, and the business case state. A successful
Cron enqueue or HTTP 200 does not prove successful agent execution. Database claims
protect against overlapping requests, but the provider's actual duration, network
behavior and concurrency limits require a hosted recovery test. Vercel deployment
protection must permit the authorized scheduler's path; retain bearer authentication.

Pause by setting `SERVERLESS_WORKER_ENABLED=false` and unscheduling both named Cron
jobs. Use the existing platform kill switch for running case execution. Preserve
queue/checkpoint evidence while investigating; do not reset counters to hide failures.

## Release gate

Use a preview with isolated data to verify the deployed build, private service binding,
exact Host admission, both database identities, Storage permissions, anonymous session isolation,
worker interruption/recovery, telemetry, restore and rollback. Capture deployment,
case/run/artifact IDs and version hashes. Promote only the tested revision after
[release evidence](../../../docs/assurance/release-evidence-checklist.md) is complete.

The current case dispatch still records specialist invocations without executing
them. The evaluation runner still accepts fixture-supplied outcomes. Connecting
real specialist execution and independently observed evaluation is required before
a production case-review launch; keep existing production promotion guards intact.
No cloud project, migration, schedule, DNS change or production release has been
performed by this preparation.

## Platform references

Verified 2026-09-07: [Vercel Services configuration](https://vercel.com/docs/services/config-reference),
[service bindings](https://vercel.com/docs/services/bindings),
[Vercel Secret values](https://vercel.com/docs/environment-variables/sensitive-environment-variables),
[Supabase connections](https://supabase.com/docs/guides/database/connecting-to-postgres),
[RLS](https://supabase.com/docs/guides/database/postgres/row-level-security),
[Vault](https://supabase.com/docs/guides/database/vault), and
[pg_net](https://supabase.com/docs/guides/database/extensions/pg_net).
Services and pg_net currently carry beta qualifications in their documentation;
record acceptance of platform maturity and test the actual target behavior.
