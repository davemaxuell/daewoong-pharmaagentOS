# Railway staging deployment

This runbook maps the repository to the `Daewoong-Bio-FDA` Railway project. It
contains no secret values and does not authorize production promotion.

## Current checkpoint

- Project ID: `38f6a1df-799c-4937-bfbe-909f4f65989c`
- Staging environment ID: `1e8d8d9a-0c8d-4de0-9de8-eed96e39c90f`
- Local Railway CLI target: `staging`
- Default compute region: Singapore (`asia-southeast1-eqsg3a`)
- Bucket region: Singapore (`sin`)
- Billing: not enabled; no service, database, bucket or deployment has been created

Railway's free trial can deploy code and data services, but it is not durable
production infrastructure. Enable an approved paid plan before relying on the
database or bucket, and configure a workspace usage alert/budget.

## Service map

Create empty services first, configure them, and only then connect the GitHub
source. This prevents an incomplete automatic deployment.

| Railway resource | Root directory | Start command | Exposure / probe |
| --- | --- | --- | --- |
| `web` | `/apps/web` | Dockerfile `CMD` | Public; `/api/health` |
| `api` | `/` | Dockerfile `CMD` | Private only; `/health/ready` |
| `worker` | `/` | `fda-intel worker --poll-seconds 2` | Private; no HTTP probe |
| `cron` | `/` | `fda-intel discover --source-url https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/compliance-actions-and-activities/warning-letters` | Private; `0 */6 * * *` UTC |
| `pgvector` | Railway pgvector PostgreSQL template | Template managed | Private only |
| `fda-objects` | Railway Bucket | N/A | Private; region `sin` |

API, worker, and cron require the repository-root build context and
`services/api/Dockerfile`; set `RAILWAY_DOCKERFILE_PATH=services/api/Dockerfile`.
The web uses `apps/web/Dockerfile` from its application context. The API image honors Railway's
runtime `PORT`; the web standalone server does the same. Set the API and web
restart policy to `ON_FAILURE`, the worker to `ALWAYS`, and cron to `NEVER`.
Railway skips a cron occurrence while the previous execution remains active.

## Private service wiring

Only `web` receives a public Railway domain. Keep `api`, `worker`, `cron`, the
database and bucket off public networking. Set the web service's backend URL with
Railway references:

```text
API_BASE_URL=http://${{api.RAILWAY_PRIVATE_DOMAIN}}:${{api.PORT}}
```

For `api`, `worker`, and `cron`, map the database and bucket by reference. The
database adapter accepts Railway's ordinary `postgres://` or `postgresql://`
`DATABASE_URL` and selects `asyncpg` internally.

```text
DATABASE_URL=${{pgvector.DATABASE_URL}}
OBJECT_STORE_BACKEND=s3
OBJECT_STORE_S3_ENDPOINT=${{fda-objects.ENDPOINT}}
OBJECT_STORE_S3_BUCKET=${{fda-objects.BUCKET}}
OBJECT_STORE_S3_ACCESS_KEY_ID=${{fda-objects.ACCESS_KEY_ID}}
OBJECT_STORE_S3_SECRET_ACCESS_KEY=${{fda-objects.SECRET_ACCESS_KEY}}
OBJECT_STORE_S3_REGION=${{fda-objects.REGION}}
OBJECT_STORE_S3_URL_STYLE=virtual
```

`BUCKET` is the globally unique S3 API name. Do not substitute
`RAILWAY_BUCKET_NAME`, which is only the display name.

## Non-secret API baseline

Apply these to API and worker unless the row above limits them to another process:

```text
APP_ENV=staging
AUTO_CREATE_SCHEMA=false
DEV_AUTH_ENABLED=false
EMBEDDED_WORKER_ENABLED=false
FDA_ALLOWED_HOSTS=www.fda.gov,fda.gov
FDA_REQUEST_DELAY_SECONDS=30
FDA_ROBOTS_FAIL_CLOSED=true
CORPUS_BACKFILL_YEARS=3
CORPUS_ACTIVE_RETENTION_YEARS=5
LLM_PROVIDER=gemini
EMBEDDING_ENABLED=true
EMBEDDING_DIMENSIONS=1536
NOTIFICATION_DEFAULT_RECIPIENT=grisellacrystabel@gmail.com
SMTP_ENABLED=false
OIDC_ISSUER=daewoong-fda-web
OIDC_AUDIENCE=daewoong-fda-api
OIDC_ALGORITHMS=RS256
OIDC_ROLE_CLAIM=roles
```

Set `ALLOWED_HOSTS` to the API private domain and `ALLOWED_ORIGINS` to the exact
web HTTPS origin after Railway generates the web domain. The API requires the
matching application-session public key. Keep `AUTO_CREATE_SCHEMA=false` during
normal operation.

## Non-secret web baseline

```text
AUTH_REQUIRED=true
AUTH_TRUST_HOST=true
AUTH_ADMISSION_MODE=restricted
AUTH_SUBJECT_ROLE_ASSIGNMENTS_JSON={}
API_SESSION_ISSUER=daewoong-fda-web
API_SESSION_AUDIENCE=daewoong-fda-api
API_SESSION_KEY_ID=web-session-v1
```

After generating the public web domain, set `AUTH_URL` to its exact HTTPS origin
and register exact Google/Naver callback URLs. Populate the private role directory
with approved immutable `google:<sub>` and `naver:<id>` account IDs before login;
an empty restricted directory denies everyone. Email lists grant neither access
nor roles. Naver profiles may return any consented email domain.

## Secrets entered directly in Railway

Never paste these into chat, `.env.example`, Git, build logs, or this runbook:

- a newly rotated Gemini API key;
- `AUTH_SECRET`;
- Google and Naver OAuth client secrets;
- the web service's PKCS#8 RSA application-session private key;
- the matching public key for API validation;
- a dedicated Gmail App Password or an approved transactional-email credential.

The previously shared Gemini keys and mailbox password must be considered exposed
and rotated. Keep `SMTP_ENABLED=false` until a controlled delivery test is ready.

## First staging activation order

1. Enable billing and a budget/usage alert.
2. Create the pgvector template and `fda-objects` bucket in Singapore.
3. Create and configure `api`; execute the complete controlled schema bootstrap,
   M1–M8 migrations, and runtime grants in the authoritative
   [handoff](../../../PHARMA_AGENT_OS_IMPLEMENTATION_HANDOFF.md#database-migration-order)
   with the migration identity, then retain `AUTO_CREATE_SCHEMA=false`.
4. Create `worker` and `cron` from the same API image and references.
5. Create `web`, generate its public domain, then finalize hosts, origins and OAuth
   callbacks before enabling login.
6. Deploy API and web, confirm both readiness probes, then start one worker.
7. Run one bounded discovery manually, validate counts/object integrity/email
   suppression, and only then enable the six-hour cron.
8. Enable SMTP last and send one controlled alert to
   `grisellacrystabel@gmail.com`.

Do not enable production until staging authentication, ingestion, RAG citations,
translation/summary reuse, retention, notification deduplication, and restore
tests have recorded acceptable results.
