# FDA Drug Warning Letter Intelligence API

FastAPI implementation of the Drug-only, evidence-first service described in the
industrial handover. It runs locally with SQLite and uses the same SQLAlchemy 2
runtime models with PostgreSQL/`asyncpg`-compatible access in deployed
environments. The richer PostgreSQL contract in `contracts/schema.sql` still
requires migration alignment before production rollout.

## Local start

```powershell
cd services/api
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\python -m app.cli init-db
.venv\Scripts\python -m app.cli seed-demo
.venv\Scripts\uvicorn app.main:app --reload --port 8000
```

Local API requests use explicit development identity headers:

```text
X-Dev-User: local.user
X-Dev-Roles: viewer
```

Use `X-Dev-Roles: admin` for ingestion administration and `reviewer` for review
actions. Development-header authentication is refused when `APP_ENV=production`.
Production uses a Bearer JWT configured with `OIDC_ISSUER`, `OIDC_AUDIENCE`, and
either `OIDC_JWKS_URL` or `OIDC_PUBLIC_KEY`.

Production startup requires a PostgreSQL `DATABASE_URL`, `DEBUG=false`, explicit
`ALLOWED_HOSTS`, exact HTTPS CORS origins, and `OIDC_ALGORITHMS=RS256`. JWKS and
telemetry endpoints must use HTTPS without embedded credentials. Enabled SMTP
requires TLS. These checks complement the existing schema/authentication,
managed-secret-provider, and Temporal mTLS checks; they do not verify target
connectivity or qualify the live agents. See the
[launch readiness record](../../docs/assurance/launch-readiness-20260906.md).

Useful commands:

```powershell
python -m app.cli discover
python -m app.cli discover --source-url https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/compliance-actions-and-activities/warning-letters
python -m app.cli worker --once
pytest
```

`discover --source-url <FDA URL>` performs a bounded, allowlisted FDA fetch.
Running `discover` without a source uses the repository's deterministic fixture
corpus and never requires network access. Live acquisition evaluates and caches
FDA `robots.txt`, enforces its path policy and crawl delay, validates every redirect,
and fails closed when policy cannot be established.

The current FDA XLSX export contains listing metadata but omits canonical detail
links. The live adapter therefore reads the public server-side DataTables settings
published in the official page, requests at most 1,000 sorted rows per bounded JSON
page, preserves each raw response as discovery evidence, and stops after a complete
page falls outside the three-year cutoff. FDA currently publishes a 30-second crawl
delay, so the initial detail-document backfill is intentionally a long-running
worker job; do not bypass that source policy. Live runs persist a bounded SHA-256
checkpoint after every candidate. If the embedded worker restarts, it reconstructs
pre-checkpoint progress from retained document versions, skips completed URLs, and
retries only unfinished or failed candidates without resetting cumulative results.
Keep this local worker single-instance; horizontal production workers require an
atomic database claim/lease before they share the same queue.

Public probes are available at `/health/live` and `/health/ready`. Authenticated
service routes use the `/api/v1` prefix; interactive OpenAPI documentation is at
`/docs` outside production.

## Immutable object storage

Local development uses `OBJECT_STORE_BACKEND=local` and `OBJECT_STORE_PATH`.
Cloud API, worker and discovery processes must share one private S3-compatible
bucket by setting `OBJECT_STORE_BACKEND=s3` plus `OBJECT_STORE_S3_ENDPOINT`,
`OBJECT_STORE_S3_BUCKET`, `OBJECT_STORE_S3_ACCESS_KEY_ID`,
`OBJECT_STORE_S3_SECRET_ACCESS_KEY`, `OBJECT_STORE_S3_REGION`, and
`OBJECT_STORE_S3_URL_STYLE`. Railway Bucket credentials map directly from
`ENDPOINT`, `BUCKET`, `ACCESS_KEY_ID`, `SECRET_ACCESS_KEY`, and `REGION` using
service variable references. Use Railway's `BUCKET` value rather than the bucket's
display-name variable.

Raw FDA representations are stored below content-addressed SHA-256 keys. Existing
objects are verified before reuse and new uploads are verified after write. The
readiness probes also check bucket access, so invalid credentials do not produce a
healthy deployment.

## Rolling corpus and update email

Discovery and backfill runs admit listing candidates from the most recent three
calendar years (`CORPUS_BACKFILL_YEARS=3`). After every discovery-family run, a
retention sweep soft-retires letters whose issue date (or posted date fallback) is
at least five calendar years old (`CORPUS_ACTIVE_RETENTION_YEARS=5`). Retirement
sets the active browsing/RAG gates to false and records a `CORPUS_RETIRED` change
event; it does not delete raw objects, versions, chunks, scope decisions, or audit
history. Both cutoffs are calendar-year based and tested at the inclusive boundary.

New and updated in-scope letters create idempotent `notification_deliveries`
outbox rows. The test default target is `grisellacrystabel@gmail.com`; an administrator
can read or change it at `GET/PATCH /api/v1/admin/notification-settings`. SMTP is
fail-closed and disabled by default. Until `SMTP_ENABLED=true`, `SMTP_HOST`, and
`SMTP_FROM_EMAIL` are supplied server-side, attempted deliveries are recorded as
`suppressed` and no network connection is made. Credentials belong in `.env` for
local work or a deployment secret manager, never in Git.

Typical provider configuration:

```text
SMTP_ENABLED=true
SMTP_HOST=smtp.provider.example
SMTP_PORT=587
SMTP_USERNAME=<secret-managed username>
SMTP_PASSWORD=<secret-managed app password or token>
SMTP_FROM_EMAIL=fda-alerts@your-approved-domain.example
SMTP_STARTTLS=true
SMTP_USE_SSL=false
```

Use a provider/domain approved by Daewoong, with SPF, DKIM, and DMARC configured.
The email contains only event metadata and an official FDA link; FDA source text
remains authoritative.

## Gemini grounded answers

Grounded answer generation can use Google's stable Gemini 3.1 Flash-Lite model.
It is opt-in and server-side only: copy `.env.example` to `.env`, then set:

```text
LLM_PROVIDER=gemini
LLM_MODEL_ID=gemini-3.1-flash-lite
GEMINI_API_KEY=<rotated local-development key>
```

Restart the API after changing these values. The key is read as a secret and is
never returned to the portal, written to audit records, or included in prompts.
Authorization, the exact `Product: Drugs` scope gate, and evidence retrieval all
run before Gemini. Generated answers must cite markers from the retrieved source
set; invalid, uncited, unavailable, or blocked model output falls back to the
retrieved official-source passages.

Chat clients may use `POST /api/v1/rag/query/stream` with the same request body
as the stable JSON endpoint. It returns UTF-8 NDJSON events: retrieval, generation,
and validation phases; provisional `draft_delta` text; `draft_reset` on a rejected
attempt; and one `complete` event containing the normal `RagQueryResponse` after
the cancellation check and database commit. Clients must treat draft text as
disposable and only treat `complete.data` as authoritative. The original
`POST /api/v1/rag/query` JSON behavior remains available unchanged.

Korean whole-letter translation and structured findings/summary generation use
the separate `DOCUMENT_AI_*` and `DOCUMENT_TRANSLATION_*` profiles. The default
profile prefers Gemini 3.7 Flash with bounded 3.6/3.5 fallbacks, while chat stays
on the requested 3.1 Flash-Lite model. These document outputs are accepted only
after structure, source-anchor, protected-token, language, date, and safety
validation; accepted results are bound to the retained source hash and reused
from the database instead of consuming tokens on every view.

Direct Gemini Developer API use is suitable for this local integration only.
Production activation still requires Daewoong approval for provider terms,
retention/training controls, data residency, secret management, egress, quotas,
model change control, and the prompt-injection/RAG evaluation suite described in
the handover.
