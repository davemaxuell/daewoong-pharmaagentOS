# PharmaAgent OS

An agent workspace for regulatory review: prepare an objective, inspect specialist
responsibilities and evidence, and follow governed case work through human review.
The interface now leads with agents and workflows; FDA search and research chat
remain supporting tools. Public browsing requires no account. Live data and
specialist execution still depend on the pending backend setup and qualification.

An evidence-first internal service for monitoring U.S. FDA warning letters whose
canonical FDA metadata contains the exact product class `Drugs`. The platform
keeps official source evidence authoritative, versions every source and derived
artifact, and prevents unverified or non-Drug records from entering search or RAG.

This repository implements the production handover in
`FDA_Drug_Warning_Letter_Intelligence_Platform_Industrial_Handover_v2.md`.
The consolidated product experience and release acceptance contract lives in
`docs/product/UX_SPEC.md`; it is the source of truth for current interface behavior.
The complete feature, interface, backend-pipeline, operations, and current-state
handoff is maintained in [`HANDOFF.md`](HANDOFF.md).

The additive PharmaAgent OS implementation baseline is defined by
[`docs/product/PHARMA_AGENT_OS_SPEC.md`](docs/product/PHARMA_AGENT_OS_SPEC.md),
with its intended-use boundary and staged architecture under `docs/assurance/`
and `docs/architecture/agent-platform.md`. The complete implementation inventory,
verification evidence, migration order, and operations handoff are in
[`PHARMA_AGENT_OS_IMPLEMENTATION_HANDOFF.md`](PHARMA_AGENT_OS_IMPLEMENTATION_HANDOFF.md).

Deployment status and the remaining launch blockers are recorded in
the [2026-09-06 readiness audit](docs/assurance/launch-readiness-20260906.md).
Passing local tests does not constitute production release approval.

## What is implemented

- FastAPI service with deterministic Product scope decisions, immutable source
  versions, lifecycle events, evidence anchors, review state, audit events, and
  authorization-aware retrieval.
- FDA acquisition controls including host and IP validation, redirect limits,
  response bounds, `robots.txt`, crawl-delay enforcement, and FDA's server-side
  DataTables JSON/HTML listing discovery. Discovery/backfill uses a configurable
  three-year window, while an
  auditable five-year soft-retirement gate keeps aged letters out of active search
  and RAG without deleting retained source evidence.
- Automatic, idempotent NEW/UPDATED email outbox delivery with an admin-editable
  target. SMTP is disabled locally until an approved provider is explicitly
  configured, so tests and fixture ingestion cannot send real mail.
- Next.js portal with a source-grounded warning-letter chat as the main dashboard,
  plus a paginated Drug Letter Explorer, evidence detail, trends, saved views,
  review, and operations administration. Each detail view can persist a validated
  Korean full-letter translation, structured findings, and a practical summary
  against the exact retained FDA source version, then open a letter-constrained
  chat with those saved artifacts available as non-authoritative context. The
  entire application chrome and workflow UI can be switched between English and
  Korean; official FDA source text remains authoritative.
- Account-free public browsing with isolated anonymous browser sessions and
  owner-scoped persistent chat history. Public visitors have viewer permissions;
  privileged review and administration remain protected.
- Agentic retrieval routing that skips document search for greetings/help, uses
  structured metadata for dates/links/counts, locks dossier questions and
  follow-ups to selected-letter chunks, and reserves corpus search for broad
  discovery. Users can select Fast/Balanced/Deep or let Auto choose an approved
  model profile for the request.
- Versioned chunk embeddings suitable for managed PostgreSQL + pgvector, with
  lexical fallback and a resumable existing-corpus embedding backfill.
- Daewoong Pharmaceutical visual identity using the current official logo,
  orange/gray palette, and locally hosted Pretendard variable font. The font
  license is retained beside the asset in `apps/web/app/fonts`.
- PostgreSQL/pgvector reference schema, strict AI summary JSON Schema, versioned
  pharmaceutical taxonomy, and OpenAPI 3.1 contract.
- PharmaAgent OS Milestones 0–8: governed cases and plans; 5 versioned agents,
  10 skills, and 16 deny-by-default tools across 3 private MCP bundles; bounded
  LangGraph execution inside an optional Temporal outer workflow; ACL-first
  synthetic internal knowledge and impact hypotheses; independent verification,
  immutable QA-reviewed artifacts, and export; multi-trial evaluation and release
  gates; Control Tower telemetry and kill switches; and draft/read-only Email,
  Slack/Teams, Notion/task, document-metadata, and answer-only A2A integration.
- Local infrastructure definitions, security policies, threat model, runbooks,
  and CI quality/security gates.

## Repository map

```text
apps/web/             Next.js internal portal
services/api/         FastAPI API, ingestion, retrieval, worker, and tests
contracts/            SQL, OpenAPI, AI output schema, and taxonomy
fixtures/              Clearly labeled fictional development/evaluation data
infra/                Local and production-oriented infrastructure templates
docs/                 Architecture, threat model, and runbooks
tests/fixtures/        Shared source fixtures and negative scope examples
```

## Local development

### 1. Optional local data services

The API defaults to SQLite and local immutable objects, so these services are not
required for the first run. To exercise the deployment-shaped dependencies:

```powershell
Copy-Item infra/local/.env.example infra/local/.env
# Replace the local-only password placeholders before starting the stack.
docker compose --env-file infra/local/.env -f infra/local/compose.yaml up -d --wait
```

This starts loopback-only PostgreSQL/pgvector, authenticated Redis, and versioned
MinIO. See `infra/local/README.md` for lifecycle and data-removal cautions.

### 2. API

```powershell
cd services/api
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m app.cli init-db
python -m app.cli seed-demo
uvicorn app.main:app --reload --port 8000
```

Development API calls use explicit identity headers:

```text
X-Dev-User: local.user
X-Dev-Roles: viewer
```

Use `reviewer` or `admin` only for the matching local workflow. Development
header authentication cannot start in production mode.

Optional grounded AI answers use an allowlisted Gemini profile. Keep the credential only
in `services/api/.env` (which is ignored), set `LLM_PROVIDER=gemini`,
`GEMINI_API_KEY`, and the `CHAT_*_MODEL_ID` values from `.env.example`, then restart the API.
`auto` routes low-latency single-letter work to Fast, broad/multi-letter work to
Balanced, and internal workflow comparison support to Deep. Enable semantic
retrieval separately with `EMBEDDING_ENABLED=true`; its model and 1,536-dimensional
vector space are independent of the selected chat model.
Persisted document translation and analysis use their separately configured
`DOCUMENT_*` model profile with strict structured-output and source-integrity
validation. See `services/api/README.md` for the grounding and
production-approval boundary.

### 3. Portal

In a second terminal:

```powershell
cd apps/web
Copy-Item .env.example .env.local
npm install
npm run dev
```

Open `http://localhost:3000`. If the API is unavailable, the portal visibly
switches to its isolated preview dataset; it never presents preview data as live.
The main chat fails closed and displays a connection error instead of substituting
a canned answer when grounded retrieval is unavailable.
Use the `EN` / `한국어` control in the portal header to change the interface
language. The preference is retained in the browser.

The portal opens directly without login or provider accounts. Configure
`PORTAL_SESSION_SECRET` for anonymous browser isolation and the API-session RSA
settings in `apps/web/.env.example` for the private backend connection. Public
visitors receive viewer authority; approval and administration remain controlled.
See `docs/runbooks/authentication.md` for setup and verification.

After installing the API and portal dependencies, Windows users can start both
services as persistent hidden local processes from the repository root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-local.ps1
```

The launcher creates and seeds its isolated local database on first use. Stop only
the processes recorded by that launcher with `scripts\stop-local.ps1`.

### 4. Quality checks

```powershell
cd services/api
.\.venv\Scripts\ruff.exe check app tests
.\.venv\Scripts\pytest.exe

cd ../../apps/web
npm run lint
npm run typecheck
npm test
npm run build
```

Contract and deployment validation commands are documented alongside the files
under `contracts/` and `infra/`. The current non-secret Railway staging map is in
[`infra/deployment/railway/README.md`](infra/deployment/railway/README.md).

To exercise deployment-spanning agent runs, start the optional Compose
`agent-platform` profile and run `pharma-temporal-worker` from the API virtual
environment. The database ledger remains authoritative and the database queue is
the safe fallback when Temporal is disabled.

## Safety boundaries

- Corpus admission is deterministic. AI never decides Product scope.
- `UNVERIFIED`, `AMBIGUOUS`, and `OUT_OF_SCOPE` content cannot enter user search
  or retrieval.
- FDA HTML and attachments are untrusted input and are never rendered raw.
- Authorization and corpus filters are applied before lexical/vector retrieval.
- Generated answers must cite stored official-source anchors and report when
  evidence is insufficient.
- The service is regulatory intelligence and human decision support. It does not
  initiate CAPA, declare an internal compliance gap, or replace controlled quality
  records.

## Production handoff

The included deployment material is a baseline, not approval to bypass Daewoong
controls. Before backend production activation, configure the server assertion boundary and
replace local storage and example endpoints with approved private managed services, KMS/secrets,
SIEM, enterprise AI gateway, backup/restore, and notification integrations. All
release-blocking controls in `SECURITY_CONTROL_MATRIX.md` still require recorded
verification evidence.

The same SQLAlchemy runtime can use SQLite locally or a managed PostgreSQL
`DATABASE_URL`; PostgreSQL stores approved chunk vectors with pgvector. Raw source
objects use the local filesystem during development and the implemented private
S3-compatible immutable adapter in cloud environments. Production rollout still
requires controlled database migrations/bootstrap, managed bucket provisioning,
plus an exercised data migration and restore procedure.
