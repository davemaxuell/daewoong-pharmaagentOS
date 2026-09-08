# PharmaAgent OS implementation handoff

**Handoff date:** 2026-09-08

**Next engineer:** Start with [the transfer brief](NEXT_ENGINEER_HANDOFF.md) for
the publication state, production blockers, verification and ordered
next steps. This file remains the authoritative implementation record.

**Authoritative workspace:** `C:\Users\user\Desktop\PharmaAgentOS`  
**Source plan:** `PHARMA_AGENT_OS_IMPLEMENTATION_PLAN.md`  
**Implementation state:** Milestones 0–8 have reference implementations; production qualification is incomplete.

**2026-09-08 loading performance:** Sidebar history/notifications now load after
the page renders, with private authenticated responses and retry without a page
reload. Late history reads preserve locally created, edited and archived chats.
A bounded SQL-paginated metadata catalog replaces five sequential collection
requests for the current 440 visible letters. Document/history links avoid bulk
prefetching. Letter detail shares its request between metadata and rendering and
uses the version/hash already returned with its content. Vercel is confirmed in
Sydney alongside the database. Local build, lint, 38 frontend tests, 55 focused
API checks, two OpenAPI checks and contract validation passed.
A delayed-sidebar browser check rendered Home in 688 ms while the sidebar remained
pending for three seconds; loading, failure/retry and history hydration passed.
Revision `d7a08a6` passed all GitHub quality/security checks and hosted smoke: 440
letters, a real AI answer with six citations, saved history after reload, session
isolation and healthy database/storage. Initial repeat navigation improved Home
3.855 → 0.458 s, chat 24.495 → 1.267 s and library 24.576 → 1.153 s. The detail-read
follow-up awaits final hosted measurement. Before/after evidence is recorded in
[performance evidence](docs/assurance/performance-20260908.md).

**2026-09-08 beginner AI experience:** Home now leads to the working AI through
one primary action and three editable example tasks. Chat uses automatic defaults,
a visible question label and text send/stop buttons; model, scope and filters are
optional. Progress/errors and the help guide use plain Korean/English. The guide
accurately distinguishes saved FDA data and cited AI answers from future ingestion
and specialist/internal-document execution.

The complete existing draft workflow moved to `/requests`, retaining storage keys
and redirecting old `/dashboard#saved-requests` bookmarks. Navigation has five
everyday destinations, with drafts also linked directly from Home. Specialist and
operational routes retain their access guards. Production build/TypeScript, lint,
26 frontend tests and 26 browser checks passed, covering both languages at
320/390/768/1440px, example prefill without auto-send, advanced controls, keyboard
focus and draft recovery. No JavaScript errors or horizontal overflow. The design
detector found only existing rules in legacy global CSS, none in new UI code.
Evidence: `.artifacts/beginner-ux-20260908/`. Revision `81f3e9b` deployed and passed
GitHub quality/security and all 26 hosted browser checks. A generic Korean example
returned six sources through the source-only fallback, not an AI explanation.
The follow-up UX explains that state and keeps long raw excerpts closed until
requested. Three regression checks bring the passing frontend total to 29.
Final application revision `d25d5cb` is deployed. A hosted Korean document-specific
question completed with a `gpt-5-mini` explanation and six cited sources; no browser
errors. Database and Storage readiness remain healthy. See
[beginner UX evidence](docs/assurance/beginner-ux-20260908.md).

**2026-09-08 hosted data and AI verified:** Production revision `7956f26` passed
GitHub quality/security checks. Both public health endpoints return 200; database
and Storage checks are healthy. A live browser displayed 440 active drug letters,
opened the source detail and completed a Korean OpenAI answer with six citations.
Four additional drug-scope rows are retired illustrative fixtures and stay hidden.
The explicit private Vercel API hostname is admitted, and general backend reads
now allow 15 seconds instead of 3.5 seconds. Temporary provisioning credentials
were removed; the copied data and original source export remain preserved.
This supersedes earlier missing-database notices. Full specialist execution,
scheduled ingestion and the home page's local-draft workflow remain separate work.

**2026-09-08 dataset copy completed:** The owner approved destination
`wdaflyddglimtijvgazl`. All source application records were copied transactionally;
884 letters and 4,298 chunks match the dump. All 444 raw source files passed
source/destination SHA-256 verification. The destination now has all 57 current
tables, the full migration sequence, RLS boundary and separate runtime logins.
Production Vercel credentials/settings are provisioned. An explicit managed
Vercel request-logging mode supports this hosting configuration without a dummy
OTLP endpoint. See [copy evidence](docs/assurance/dataset-copy-20260908.md).
Hosted end-to-end verification is complete as recorded above.

**2026-09-08 populated dataset located:** The owner supplied `data.sql`, a data-only
export with 884 letters (444 in-scope drug letters), 4,298 passages and 444 Storage
object metadata rows. Read-only queries against the now-linked Supabase project
`uwgzvobkblrnmqwroegh` (`supabase-daewoong`) matched those counts. Earlier empty
results concerned two different projects. Existing exported table columns match;
36 Agent OS tables are absent. Database destination selection is pending before
cloud changes. See [dataset evidence](docs/assurance/dataset-discovery-20260908.md).
The dump is preserved and Git-ignored; it includes historical chat records.

**2026-09-08 OpenAI activation:** Added a server-only Responses provider with
shared citation/language checks, structured analysis and Korean translation.
The supplied key passed real adapter calls using synthetic evidence. Production
and Preview now hold `OPENAI_API_KEY` as a Vercel Secret and select `gpt-5-mini`
for generation, with empty document fallback lists. Embeddings remain disabled.
The temporary key file was removed; no repository secret matches were found.
See [activation evidence](docs/assurance/openai-activation-20260908.md) for test
scope. Database, storage, corpus and full agent-workflow activation remain pending;
the home request form still saves local drafts.

**2026-09-08 employee usability redesign:** Replaced the workflow-first home with
a guided review request: select one of three plain-language tasks, write an
editable question using an optional example, add an optional FDA HTTPS link,
and save or download the request. Up to 30 browser drafts can be reopened,
updated and deleted with confirmation. The earlier single-draft format migrates
without losing content. Readable text export is primary; labeled JSON remains
available in technical details. Browser storage failures retain editor contents
and permit download; corrupt archives are not overwritten. Unsaved edits are
guarded on page exit, internal navigation and request switching.

Everyday navigation now exposes six employee tasks, including saved requests and
a new bilingual `/help` guide. Specialists, review records, approvals, trends,
evaluation and operations remain accessible in an expandable section. Three
outcome-oriented stages explain the agents; the actual nine-step definition is
available on demand. Errors explain recovery in plain language. Mobile layouts
put saved work ahead of the agent explanation. The enlarged type scale remains.

The interface explicitly identifies saved requests as local, unsubmitted and not
analyzed. No database migration, live FDA ingestion, automated specialist execution,
shared company storage or new access privilege is represented as complete.

Verification: production build/TypeScript, lint and 26 frontend tests passed.
Production-mode Edge checks passed task validation, FDA-link rejection, multiple
draft save/restore/delete, readable export, advanced navigation, nine supporting
routes, Korean/English reflow at 320/390/768/1024/1440px, and mobile Escape/focus.
Separate browser checks passed legacy migration, guarded unsaved clearing, and
download after a storage write failure. No browser JavaScript errors; UI detector
returned no findings. Local evidence: `.artifacts/employee-ux-20260908/` (ignored).

**2026-09-07 Supabase access verified:** The owner supplied project
`wdaflyddglimtijvgazl`. Authenticated CLI project listing and schema queries work.
The project is named `Daewoong FDA`; no application tables were found and the
public schema contains zero tables. A publishable key does not provide backend
runtime credentials. The destination choice (shared database or separate
PharmaAgent OS project) was requested before migrations; no application schema,
data, grants, buckets or Vercel configuration were changed. See
[access verification](docs/assurance/supabase-access-20260907.md).

**2026-09-07 larger interface:** Increased the shared typography scale by roughly
18%, using rem units and a 13px floor for small metadata. Primary body text is
17–19px and workspace headings are 33–40px. Enlarged navigation to 280px, the
header to 76px, primary actions to 46–50px and workflow rows to at least 60px.
The brief editor, navigation icons and template controls also have more room.
Narrow headers, evidence cards and Trends controls reflow at mobile sizes.
Corrected the shared sidebar offset to match the wider navigation.

Verification: production build/TypeScript, lint and all 22 frontend tests passed.
Headless Edge passed the existing complete interaction check (draft lifecycle,
agent search/selection, nine routes, both languages, mobile navigation/focus,
no login and admin denial) without JavaScript errors. Six routes were checked at
320, 390, 768, 1024 and 1440px with no page-level horizontal overflow. Screenshots
and size measurements are in ignored `.artifacts/interface-size-20260907/`;
the typography detector returned no findings. Backend setup remains pending.

**2026-09-07 agent-focused interface redesign:** The service owner requested a
complete interface change emphasizing agentic work. `/dashboard` now presents a
review brief, the actual nine-step workflow definition, selectable specialist
responsibilities and human checkpoints, and accessible case activity. `/agents`
adds searchable descriptions of the five versioned agent definitions. No running
agents, case records, or completion counts are fabricated when the API is absent.
Browser drafts can be saved, restored, deleted and exported as explicitly
unexecuted JSON. These drafts do not create governed cases or submit execution.

The shared navy/light/cobalt theme, PharmaAgent OS identity and grouped navigation
apply across the portal. Cases, approvals, evaluation and operations have shared
bilingual unavailable states with useful routes back to brief preparation.
`/ask` now owns research chat; legacy dashboard query links retain their source
and conversation context. Chat creation/archive invalidate the new route as well.
Account-free viewer authorization and all backend execution/review guards remain.
Korean defaults, English switching, mobile navigation and keyboard focus remain.
Global CSS zoom is removed. Product truth, design rules and UX supersession are
recorded in `PRODUCT.md`, `DESIGN.md`, and `docs/product/UX_SPEC.md`.

Verification: 22 frontend tests passed; lint and production build/TypeScript passed.
Headless Edge checked draft persistence/isolation/export/deletion, workflow and
agent selection, agent search, nine supporting routes, preserved legacy links,
single-main landmarks, desktop/mobile overflow, mobile navigation/Escape focus,
both languages, no login, and denied admin access. No browser JavaScript errors.
Screenshots and JSON evidence are under ignored
`.artifacts/agent-redesign-20260907/`. The UI detector returned no findings.
Live data, specialist execution and independent evaluation qualification remain
pending; this interface work does not resolve the Supabase/backend blockers.

**2026-09-07 live FDA data incident:** The deployed frontend health returned 200,
but API health returned 500. Vercel web logs also reported missing
`API_SESSION_ISSUER`. Added API session issuer/audience/key ID, matching OIDC
issuer/audience/RS256 configuration, and `SECRET_PROVIDER=vercel` to Production
and Preview. Generated separate 3072-bit RSA keypairs for each environment;
private keys were sent directly to Vercel Secrets, never written to source or logs.
The next deployment applies these settings. Supabase project access, runtime
database URLs, private Storage and remaining production runtime configuration
are still absent. No FDA ingestion or successful live query has been established.
The service owner was asked for the dedicated Supabase project URL; credentials
must be configured through the provider or local ignored environment, not chat.
Login removal remains intact. The full application CI run for `f1767f7` completed
successfully (quality-and-security run `34078404837`).

**2026-09-07 account-free portal:** At the user's request, Google/Naver login,
Auth.js callbacks, and the account/sign-out interface were removed. All visitors
open the dashboard directly; old sign-in links redirect there. An automatic,
signed HttpOnly browser cookie preserves separate chat/saved-view ownership.
Public API assertions carry anonymous UUID subjects and viewer authority; the API
rejects elevated public-session roles, including group-derived permissions.
`PORTAL_SESSION_SECRET` replaces the OAuth settings for the web frontend.
Previous private-account admission requirements below are historical and superseded.
Application commit `f1767f7` is deployed; live desktop/mobile checks confirm direct
dashboard access without login. Obsolete Vercel login settings were removed.
See [public-access evidence](docs/assurance/public-access-20260907.md).

**2026-09-07 GitHub/Vercel publication:** The user authorized publication and
hosting. Checkpoint `8ade4a1` is on GitHub `main`; the dedicated `pharmaagent-os`
Vercel project is connected and its frontend is hosted at
https://pharmaagent-os.vercel.app. The sign-in page and frontend health return 200;
the backend returns 500 because its required production PostgreSQL URL is missing.
Supabase setup, specialist execution, and release qualification remain
outstanding. See [hosting evidence](docs/assurance/github-vercel-hosting-20260907.md).
This supersedes earlier statements that no source push or cloud deployment occurred.

**2026-09-07 continuation — completion boundary:** Before connecting specialist
execution, inspection found that `complete_step` did not validate its declared
output schema or recheck completion-time bindings. The shared service now locks
and refreshes run/invocation/case records, checks active invocation identity and
attempt, plan/state/schema/budget bindings, current approvals, release availability,
and suspension controls. Usage rejects non-finite, negative, coerced, and unknown
values. Exact output contracts currently supported are `RegulatoryFindingList@2.0.0`
and `VerificationReport@1.0.0` (using the existing verification response model).
Other output references fail closed until their adapters and contracts are implemented.
This is structural validation, not proof of retained evidence, independent
verification, or actual specialist execution. The HTTP result path remains a
trusted-caller submission path; fixture outputs cannot qualify production.
See [completion boundary evidence](docs/assurance/completion-boundary-20260907.md).
Final verification: **508 API tests passed, 7 gated integration tests skipped**
in 288.68 seconds. Ruff, contract validation and diff whitespace checks passed.

**Latest audit:** [Launch readiness review](docs/assurance/launch-readiness-20260906.md)
records private-account admission, stricter production startup checks, deployment
preflight/CI repairs, and fresh PostgreSQL/Temporal/restore/container evidence.
Production launch remains blocked by target integration, independently executed
agent/evaluation qualification, and designated release approvals.

**2026-09-06 remediation:** Private deployment templates now use
`AUTH_ADMISSION_MODE=restricted`; populate the immutable-subject role directory
before admitting users. Production rejects SQLite fallback, wildcard Hosts,
unsafe CORS/JWKS/telemetry settings, debug mode, non-RS256 authentication and
plaintext SMTP. CI uses the frozen Python lock and supplies the restore canary's
required timestamp. The latest audit records the full verification scope.
Final verification: **465 packaged API tests passed** with 6 explicitly gated
live-integration skips; the separate PostgreSQL/Temporal set passed all 8 tests.
The web passed 28 tests, lint, TypeScript and production build. Isolated restore,
read-only runtime smoke, contracts and source-secret scans passed; both refreshed
runtime image scans reported zero HIGH/CRITICAL findings. These results establish
local engineering evidence, not target-environment qualification.

**2026-09-07 launch preparation:** The
[launch preparation runbook](docs/runbooks/launch-preparation.md) specifies a
proposed private-pilot sequence, the remaining execution/evaluation adapter work,
hosted acceptance checks, and the owner inputs needed to select the deployment.
The user subsequently selected production on Vercel/Supabase. The
[production runbook](infra/deployment/vercel/README.md) and
[architecture decision](docs/adr/0004-vercel-supabase-production.md) record the
prepared three-service topology, platform secret provider, bounded queue worker,
Supabase Cron/Vault triggers, RLS boundary, and runtime resource packaging.
Dedicated projects/domain and hosted qualification remain outstanding. This does
not complete specialist execution or independent evaluation, and no production
approval or cloud mutation is implied.
Verification: **489 API tests passed, 7 gated integration tests skipped**; the
separate live PostgreSQL boundary/resource set passed all 4 tests. Ruff, contracts,
CI YAML parsing and configuration instance validation passed. See the
[Vercel/Supabase preparation evidence](docs/assurance/vercel-supabase-preparation-20260907.md)
for exact scope and target qualification limits.

**Production-check remediation:** Service/human role separation is now enforced
after group mapping. The Kubernetes base includes missing public-key references,
process-specific model/Temporal settings, API certificate mounts, remote-storage
references and health-probe Host headers. These are local code/template fixes, not
target-cluster qualification; see the latest audit for their verification scope.
Follow-up verification: 39 focused tests passed; the full offline container suite
passed 427 tests with 6 explicitly gated live-integration skips.

All PharmaAgent OS work is contained in this workspace. The earlier FDA project is
separate and must not be used as a working directory for future changes. Git metadata,
local secrets, dependency caches, databases, and build output from that project were
not imported. A dedicated Git repository was initialized during deployment
preparation. GitHub publication and production release are distinct operations.

## Delivered outcome

The existing FDA Product=Drugs evidence platform now includes a case-first agent
operating system with:

- immutable source pins, typed plans, hash-chained case/run events, durable checkpoints,
  human interrupts, and stale-write protection;
- five versioned agents, ten reusable skills, one approved workflow, and sixteen
  deny-by-default tools across three private MCP bundles;
- ACL-before-retrieval synthetic internal knowledge, version history, relationship
  evidence, impact hypotheses, and deterministic review priority;
- independent verification, bounded correction, immutable artifact revisions,
  QA approval, and evidence-bound export;
- multi-trial evaluation, deterministic/model/human grade records, release blocking,
  rollback targets, production feedback, and an Agent Control Tower;
- optional Temporal durability around the bounded LangGraph workflow, exactly-once
  activity journaling, database-queue fallback, kill switches, quotas, workload
  identities, secrets-provider abstraction, OpenTelemetry, backups, and runbooks;
- draft/read-only Email, Slack/Teams, Notion/task, and document-metadata integration,
  plus answer-only A2A interoperability. No agent connector can send or publish.

The product remains decision support. It cannot autonomously create a CAPA, determine
compliance, reject a batch, revise an SOP, or write a controlled quality-system record.

## Milestone status

| Milestone | Status | Principal implementation |
| --- | --- | --- |
| M0 — baseline and boundaries | Complete | Product spec, intended use, control matrix, architecture/ADR, threat model, synthetic-data labeling, release checklist |
| M1 — case/control plane | Complete | Case/source/event/plan/approval/registry/artifact models, REST APIs, Case Workspace, canonical hashes, PostgreSQL guards |
| M2 — Regulatory MCP/agent | Complete | Five R0 tools, two-phase authorization, source-pin validation, sanitation, evidence/citation validator, bounded Regulatory Evidence Agent |
| M3 — orchestration/Plan Mode | Reference implementation | Approved workflow registry, typed LangGraph state, durable run/checkpoint/event APIs, pause/resume/cancel, step approvals, timeline UI; production specialist execution wiring remains |
| M4 — internal knowledge/impact | Reference implementation | Fictional revisioned corpus, ACL filtering, hybrid retrieval, relationship graph, Knowledge MCP, deterministic specialists, Impact Studio; live model/data qualification remains |
| M5 — verification/review | Reference implementation | Separate deterministic verification checks, two-correction ceiling, immutable reports/artifacts/export, QA UI; independent production model qualification remains |
| M6 — evaluation/control tower | Reference implementation | Fixture outcome grading, release gate demonstrations, feedback, metrics dashboards; independent production execution/grading adapter still required |
| M7 — commercial hardening | Partially qualified | Temporal outer workflow and activity replay guards, service identities, private MCP gateway, policy templates, secret-provider abstraction, telemetry, quotas, kill switches, backup drill; managed-secret wiring and target infrastructure qualification remain |
| M8 — controlled integrations | Complete | Immutable no-send outbox, manual review, prohibited-directive guard, ACL metadata adapter, draft-only Workflow MCP, answer-only A2A, Handoffs UI |

## Versioned runtime inventory

### Agents

| Agent | Version | Reviewed definition SHA-256 |
| --- | --- | --- |
| Case Orchestrator | 1.0.0 | `4d1df30f66219c09cbce680ef23ed439b763f65a12620f1435b5e8db1c0beb42` |
| Regulatory Evidence Agent | 1.3.0 | `5b19303a147b12c07533523127a58577ff7fe5d27a19413443d7f32a5d775daa` |
| Internal Knowledge Agent | 1.1.0 | `f1a6ff4ffed4033dd6928c974b606b1dffff7996a9f2529423fc46c6b9c335c5` |
| Impact Analysis Agent | 1.0.2 | `df2372f12bb1bac165608c7722e38e3d6954dae962365ef66cbdaebab1d591f5` |
| Verification Agent | 1.2.1 | `bb4437ef676bbe079046d83a576ef9ff893e42d3e5380be31654ddc538ebd6fa` |

The `regulatory-impact-review@1.0.0` workflow hash is
`6f535115bbfe1cb2e9fe29ee80b3c8b15c4409157829e1ae836fcb3adc36ce67`.

### MCP bundles

| Bundle | Version | Tools | Reviewed definition SHA-256 |
| --- | --- | ---: | --- |
| regulatory-mcp | 1.0.0 | 5 | `478dbf57c2b85c75e77616ce723e2b5fd771250516c91e69d26aabcec19b4952` |
| knowledge-mcp | 1.0.0 | 6 | `324b65c53afbdcaa6e9af759a467fb86eccef99de97a9703419d34d460d3e2b1` |
| workflow-mcp | 1.0.0 | 5 | `a0896543a821f9ee474e9ede7219cd689af09e141186908d0cf1ec5f4ea2f67c` |

The ten approved skills are defined in
`contracts/skills/initial-skills.v1.0.0.yaml`. Registry seeding is idempotent and
rejects content drift for an existing semantic version.

## Code map

### Product, contracts, and assurance

- `docs/product/PHARMA_AGENT_OS_SPEC.md` — normative product boundary and workflow.
- `docs/architecture/agent-platform.md` and `docs/adr/0003-agent-platform-modular-monolith-and-mcp-adapters.md` — implemented architecture and extraction decision.
- `docs/assurance/agent-intended-use.md`, `agent-control-matrix.md`, and
  `release-evidence-checklist.md` — human authority and release controls.
- `docs/threat-model/agent-platform-delta.md` — prompt injection, confused deputy,
  tool abuse, data leakage, memory poisoning, and durability threats.
- `contracts/agents`, `contracts/skills`, `contracts/tools`, `contracts/workflows`,
  and `contracts/cases` — strict schemas, reviewed manifests, examples, and hashes.
- `contracts/validate_contracts.py` — closed-schema, hash, DAG, version-reference,
  approval-freshness, tool-policy, and OpenAPI validation.

### API and runtime

- `services/api/app/models.py` — control plane, execution, evidence, evaluation,
  hardening, integration, and A2A persistence models.
- `services/api/app/cases` — case/plan/approval APIs, source pins, canonical state,
  idempotency, and append-only case events.
- `services/api/app/agent_platform/runtime` — LangGraph workflow, durable run
  transitions, worker queue integration, limits, interrupts, and event history.
- `services/api/app/agent_platform/temporal` — outer workflow, signals, mTLS client,
  worker, and idempotent activity journal.
- `services/api/app/agent_platform/mcp/regulatory`, `knowledge`, and `workflow` —
  typed gateways, policy enforcement, ACL/source binding, budgets, result validation,
  provenance, and idempotency.
- `services/api/app/agent_platform/mcp/server.py` — private service-authenticated MCP
  process; documentation and OpenAPI endpoints are disabled.
- `services/api/app/internal_knowledge` — synthetic corpus seed, hybrid retrieval,
  relationship graph, impact agent, and review APIs.
- `services/api/app/verification` — independent verification, correction limit,
  artifact composition/review/export, and immutable evidence membership.
- `services/api/app/evaluation` — suites, cases, trials, graders, release decisions,
  feedback, trace inspection, and Control Tower aggregates spanning inventory,
  queues/retries, model/tool errors, approvals, citation and routing quality,
  suspensions, cost, percentile latency, and review turnaround.
- `services/api/app/approvals` — consolidated case-authorized Approval Center read model.
- `services/api/app/integrations` — no-send drafts, manual review, read-only document
  metadata, and answer-only A2A.
- `services/api/app/security/secrets.py` and `app/observability.py` — local/AWS secret
  provider boundary and metadata-only OTLP tracing.

### Web application

- `apps/web/app/(portal)/cases` and `components/agent-platform/case-workspace.tsx` —
  Overview, Plan, Execution, Impact, QA Review, Handoffs, Evidence, and History views.
- `apps/web/app/(portal)/approvals` — consolidated approval queue with case links.
- `apps/web/app/(portal)/evaluations` — version-bound suite/run/release UI.
- `apps/web/app/(portal)/control-tower` — health, quality, security, cost/value,
  immutable inventory, and global/exact-agent suspension UI.
- `apps/web/lib/case-api-client.ts`, `case-types.ts`, and
  `governance-api-client.ts` — server-only bearer calls and strict response parsing.

### Infrastructure and operations

- `infra/deployment/kubernetes/base` — API/web/worker plus two-replica Temporal worker,
  two-replica private MCP gateway, dedicated service accounts, PDBs, NetworkPolicies,
  OTEL/Temporal settings, and backup CronJob.
- `infra/local/compose.yaml` — optional local Temporal/UI `agent-platform` profile.
- `infra/policies/postgres-runtime-roles.sql` — separate API, worker, readonly,
  orchestrator, and MCP NOLOGIN roles with least-privilege grants.
- `scripts/verify-pharma-backup-restore.ps1` — explicit isolated-target PostgreSQL
  dump, SHA-256 evidence, restore, and control-plane row-count verification.
- `docs/runbooks` — deploy/rollback, backup/restore, security incident, auth,
  ingestion, and AI/retrieval quality procedures.
- `.github/workflows/ci.yml` — Python, PostgreSQL trigger/grant, all forward migrations,
  isolated backup restore with canary, frontend, contract, deployment-render, and
  secret-scan jobs.

## Database migration order

Run migrations only as the controlled migration owner. Runtime identities must not
have DDL privileges.

1. `20260904_agent_os_control_plane.sql`
2. bootstrap the current SQLAlchemy schema with `fda-intel init-db` for a fresh database
3. `20260904_agent_os_orchestration.sql`
4. `20260904_internal_knowledge_and_impact.sql`
5. `20260904_verification_and_artifacts.sql`
6. `20260904_evaluation_and_control_tower.sql`
7. `20260904_durable_commercial_hardening.sql`
8. `20260904_controlled_integrations.sql`
9. apply `infra/policies/postgres-runtime-roles.sql`

The SQL adds database-enforced immutability, exact case/run/plan/artifact bindings,
one-way review transitions, append-only evaluation/A2A records, and delete guards.
CI runs every script with `psql --set ON_ERROR_STOP=1` against PG16 + pgvector.

## Security and integrity invariants

- Identity, case, run, agent, approval, scope, and idempotency context is supplied by
  the trusted host, not model output.
- Production human assertions are short-lived and audience-bound. Service assertions
  use `token_use=service_access`, a `svc:` subject, only the `service` role, and a
  maximum five-minute lifetime.
- Retrieval filters access before ranking or model context. Denied resources do not
  leak titles, metadata, or existence.
- Every tool is deny-by-default, exact-version allowlisted, schema/size/time bounded,
  reauthorized around execution, and attributed to user/case/run/agent.
- A global or exact-agent suspension gates starts, resumes, workers, and MCP calls.
  Updates use optimistic revisions and attributable reasons.
- Tool/activity retries replay only an exact committed input hash. Conflicting reuse
  fails closed and no side effect is duplicated.
- Approved artifacts are immutable. Review is bound to content and evidence-manifest
  hashes; stale writes return conflicts.
- Agent integration records always contain `external_delivery_allowed=false`. The
  platform has no delivery transition or connector credential in this workflow.
- A2A returns case status or approved-artifact metadata only. It cannot invoke tools,
  delegate agents, or perform a controlled write.
- Traces store observable metadata, versions, hashes, metrics, and decisions—not hidden
  chain-of-thought, credentials, or unrestricted source bodies.

## Local operation

### API

```powershell
cd "C:\Users\user\Desktop\PharmaAgentOS\services\api"
uv sync --all-extras --dev
.\.venv\Scripts\python.exe -m app.cli init-db
.\.venv\Scripts\python.exe -m app.cli seed-demo
.\.venv\Scripts\uvicorn.exe app.main:app --reload --port 8000
```

### Portal

```powershell
cd "C:\Users\user\Desktop\PharmaAgentOS\apps\web"
Copy-Item .env.example .env.local
npm install
npm run dev
```

### Optional Temporal and private MCP processes

```powershell
cd "C:\Users\user\Desktop\PharmaAgentOS"
docker compose --env-file infra/local/.env -f infra/local/compose.yaml --profile agent-platform up -d --wait

$env:TEMPORAL_ENABLED = "true"
$env:TEMPORAL_ADDRESS = "127.0.0.1:7233"
services\api\.venv\Scripts\pharma-temporal-worker.exe

services\api\.venv\Scripts\uvicorn.exe app.agent_platform.mcp.server:private_mcp_app --app-dir services/api --host 127.0.0.1 --port 8001
```

Production requires managed PostgreSQL/pgvector, private versioned object storage,
an approved identity provider, workload identity/AWS Secrets Manager or equivalent,
Temporal mTLS, a private OTEL collector, and reviewed egress routes.

## Verification evidence from this workspace

Latest qualification on 2026-09-05:

- Native API suite with live PostgreSQL and Temporal enabled: **407 passed** in
  352.41 seconds. No integration tests were skipped in this run.
- The subsequent fixture-release guard change passed its focused regression tests.
- Final packaged-runtime evidence and remaining blockers are recorded in the
  [deployment readiness audit](docs/assurance/deployment-readiness-20260905.md).

Earlier baseline checks on 2026-09-04/05 (retained as historical evidence):

- Full API test suite: **400 passed, 5 skipped** in 325.96 seconds.
- The five skips are the explicitly gated live-PostgreSQL tests.
- Post-finalization Control Tower, Approval Center, private MCP, OpenAPI, case-runtime,
  and backup/restore regression set: **18 passed**.
- Regulatory MCP/agent/evaluation focused suite: **71 passed**.
- Final hardening/integration/OpenAPI/restore focused suite: **4 passed**.
- Ruff: `ruff check app tests` — **passed**.
- Web unit tests: **22 passed** across 5 test files.
- Web ESLint with zero warnings: **passed**.
- Web TypeScript check: **passed**.
- Next.js 16 production build: **passed**, including `/approvals`, `/cases`,
  `/cases/[caseId]`, `/evaluations`, and `/control-tower`.
- Contract validator: **passed** — OpenAPI, JSON Schemas, examples, taxonomy,
  12 Agent OS schemas, 6 positive case fixtures, approval freshness, 5 agents,
  10 skills, and 16 deny-by-default tools.
- Kubernetes `kubectl kustomize`: **passed**.
- Docker Compose configuration render: **passed**.
- Local SQLite backup/restore integrity test: **passed**, including control-plane
  schema and a restored canary.

The original test run skipped PostgreSQL because Docker was stopped. The later
deployment audit started Docker, applied all migrations and grants, passed the five
PostgreSQL tests, restored an isolated dump, and exercised live Temporal worker
replacement. See the latest audit for scope and evidence; production mTLS/cluster
disaster recovery remains unqualified.

## Environment-dependent activation still required

The remaining work includes both environment activation and application integration:

1. Review the dedicated Git repository and configure the approved release signing identity.
2. Run the CI PostgreSQL job and retain migration, trigger, grant, and restore evidence.
3. Connect approved corporate IdP/JWKS, workload identities, secret manager, OTEL/SIEM,
   Temporal mTLS, object storage, and egress gateway services.
4. Replace or supplement the compact fictional corpus with a qualified synthetic or
   approved internal dataset. No real Daewoong quality-system data is included.
5. Execute formal security, privacy, QA/CSV, disaster-recovery, and release approvals.
6. Implement independently executed release-grade probabilistic evaluations and
   specialist execution adapters, then approve exact versions before production promotion.

Draft-only connectors deliberately require a human to copy or deliver reviewed
content. Adding automatic Email/Slack/Teams/Notion/task delivery or any controlled
quality-system write would be a new scope requiring explicit action approvals,
reconciliation semantics, threat review, and separate validation.
