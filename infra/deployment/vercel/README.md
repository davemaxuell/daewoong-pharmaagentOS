# Vercel Services + Supabase deployment

The root `vercel.json` deploys the Next.js portal and FastAPI application as one
Vercel Services project. The web service receives a private `API_BASE_URL`
binding to the API service. Only FastAPI health endpoints are public; browser API
requests continue to use the authenticated Next.js BFF routes.

## Supabase resources

Provision or connect one Supabase project through the Vercel Marketplace, then
create a private Storage bucket for immutable FDA evidence. Enable the `vector`
extension before bootstrapping the database.

The API uses native Postgres plus Supabase's server-side Storage API. A Supabase
publishable key is not used for privileged storage operations. The Marketplace
integration supplies `SUPABASE_URL` and the server-only `SUPABASE_SECRET_KEY`;
never expose the secret key through a `NEXT_PUBLIC_*` variable.

Use the Supabase transaction-pooler connection string for the Vercel FastAPI
service. Preserve the URL-encoded database password. The application normalizes
ordinary `postgres://` and `postgresql://` URLs to the asyncpg driver. For a
port-6543 transaction-pooler URL it also selects SQLAlchemy `NullPool` and
disables both SQLAlchemy and asyncpg prepared-statement caches.

The official Vercel Marketplace integration supplies this connection as
`POSTGRES_URL`, which the API accepts as a fallback for `DATABASE_URL`. If both
are present, `DATABASE_URL` takes precedence.

Create the private bucket before deployment:

```text
OBJECT_STORE_BACKEND=supabase
OBJECT_STORE_SUPABASE_BUCKET=fda-evidence
# Supplied by the Vercel Marketplace integration:
SUPABASE_URL=https://PROJECT_REF.supabase.co
SUPABASE_SECRET_KEY=<server-only secret key>
```

The object adapter uses content-addressed keys and conditional creation to
preserve application-level immutability. Supabase Storage does not provide native
S3 object versioning, so production operators must also prohibit destructive
bucket access and maintain a separately tested evidence backup.

## Required Vercel environment

Set these variables for Production and Preview as appropriate. Secret values
belong in Vercel Environment Variables and must not be committed.

```text
APP_ENV=production
AUTO_CREATE_SCHEMA=false
DEV_AUTH_ENABLED=false
EMBEDDED_WORKER_ENABLED=false
# Supplied as POSTGRES_URL by the Vercel Supabase integration. Otherwise set:
DATABASE_URL=<Supabase transaction-pooler URL>

OBJECT_STORE_BACKEND=supabase
OBJECT_STORE_SUPABASE_BUCKET=fda-evidence
# SUPABASE_URL and SUPABASE_SECRET_KEY are integration-managed.

ALLOWED_ORIGINS=https://YOUR_VERCEL_DOMAIN
# Vercel service bindings use deployment-specific internal hosts. Public API
# access remains limited to the top-level health rewrites and Vercel's edge.
ALLOWED_HOSTS=*
OIDC_ISSUER=daewoong-fda-web
OIDC_AUDIENCE=daewoong-fda-api
OIDC_ALGORITHMS=RS256
OIDC_PUBLIC_KEY=<matching RSA public key>

AUTH_URL=https://YOUR_VERCEL_DOMAIN
AUTH_TRUST_HOST=true
AUTH_SECRET=<Auth.js secret>
AUTH_GOOGLE_ID=<Google OAuth client ID>
AUTH_GOOGLE_SECRET=<Google OAuth client secret>
AUTH_NAVER_ID=<Naver OAuth client ID>
AUTH_NAVER_SECRET=<Naver OAuth client secret>
API_SESSION_PRIVATE_KEY=<PKCS#8 RSA private key>
API_SESSION_KEY_ID=web-session-v1
API_SESSION_ISSUER=daewoong-fda-web
API_SESSION_AUDIENCE=daewoong-fda-api

LLM_PROVIDER=gemini
GEMINI_API_KEY=<server-only Gemini key>
EMBEDDING_ENABLED=true
EMBEDDING_DIMENSIONS=1536
SMTP_ENABLED=false
```

The Vercel service binding supplies `API_BASE_URL`; do not set it manually in
Vercel.

## First database activation

Before the first application deployment, use the Supabase direct connection with
a migration-capable database user from a trusted machine:

```powershell
$env:DATABASE_URL = "postgresql+asyncpg://..."
$env:OBJECT_STORE_BACKEND = "supabase"
# Set SUPABASE_URL and SUPABASE_SECRET_KEY from the integration environment.
Set-Location services/api
python -m app.cli init-db
```

Keep `AUTO_CREATE_SCHEMA=false` in Vercel after the one-time bootstrap. This
repository's `contracts/schema.sql` is an architectural reference and must not be
used to initialize the runtime database.

## Deployment

Create or import the Vercel project from the repository root, choose the
**Services** framework preset, connect the existing Supabase project from the
Vercel Marketplace, add the remaining environment variables, and deploy:

```powershell
vercel link --repo
vercel build --prod
vercel deploy --prebuilt --prod
```

After deployment, register these OAuth callback URLs for every enabled provider:

```text
https://YOUR_VERCEL_DOMAIN/api/auth/callback/google
https://YOUR_VERCEL_DOMAIN/api/auth/callback/naver
```

Vercel Services hosts the HTTP API but not the continuously polling worker or the
six-hour FDA discovery scheduler. Those jobs still need a durable container/cron
runtime, or a separate bounded Vercel Workflow design, before live ingestion is
enabled.
