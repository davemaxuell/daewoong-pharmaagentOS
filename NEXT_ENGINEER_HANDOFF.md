# PharmaAgent OS — next engineer handoff

Prepared: **2026-09-09**
Requested outcome: **launch-ready production on Vercel and Supabase**  
Current status: **FDA library, grounded OpenAI chat and durable FDA Research Agent hosted; full internal case-agent qualification incomplete**

**Railway backend preparation (2026-09-09):** The user will deploy from GitHub.
Use [RAILWAY_SETUP.md](RAILWAY_SETUP.md) for two service settings and credential
templates, then the Vercel website cutover. Durable scheduled FDA ingestion,
restart recovery and live source pagination/detail checks are implemented.
The database/storage remain on the current Supabase project; no production
cutover or Railway deployment has been performed. Verification and publication
state: [Railway evidence](docs/assurance/railway-20260909.md).
Application revision `386d753` is pushed, all GitHub checks pass, and the existing
Vercel site/library remain healthy. Railway deployment and routing cutover are
still pending the user's action.

**Visual simplification (2026-09-09):** Home/Help now explain the workflow with three
labeled steps; research uses compact stage/action icons and expandable plans,
full activity history and review notes. Repeated explanatory paragraphs are shorter,
while findings, sources and exports remain complete. See
[visual UX evidence](docs/assurance/visual-ux-20260909.md) for checks and publication.
Application revision `2eec5f7` is hosted; the full UI release passed a real research
brief and 32 hosted Korean/English layout checks. Final CI links are in the evidence.

**FDA Research Agent (2026-09-08):** `/research` now implements goal-driven native
OpenAI tools, source/evidence checking, Supabase task/event persistence and visible
live progress. Stop/Resume preserve bounded checkpoints; completed briefs expose
citations and exports. This public-FDA workflow is separate from the still-disabled
internal case/ingestion lanes. Additive research tables and Vault/worker settings
are provisioned. See [release evidence](docs/assurance/research-agent-20260908.md)
for exact verification and deployment status. Release `e0f8c28` is deployed with
all GitHub checks passing (551 backend tests, 46 frontend tests and the separate
PostgreSQL/Temporal/security jobs). The real hosted Korean research and complete
Stop/Resume browser journey pass. The implementation handoff remains
authoritative. Do not stage the user's root package files or `supabase/`.

**Loading optimized (2026-09-08):** Application revision `489214b` is deployed and
passed all GitHub quality/security checks. Web/API functions now execute beside
the Sydney database. Sidebar reads run after rendering; the letter catalog uses
one bounded request for 440 records; duplicate detail/version reads are removed.
Measured initial chat/library/detail loads improved 24.0/23.5/10.6 seconds to
2.6/1.7/2.3 seconds. Repeat Home/chat/library visits were under one second. All
38 frontend tests and 26 hosted beginner UX checks passed; real cited AI, history
persistence and browser-session isolation were verified. See
[performance evidence](docs/assurance/performance-20260908.md), including cold-load
limits and complete timings. Preserve the user's untracked root package files and
`supabase/`, along with ignored data and artifacts.

**Beginner UX deployed (2026-09-08):** Application revision `d25d5cb` leads from Home
to live AI questions with editable examples and optional settings. Drafts remain
at `/requests` with their existing storage. The guide reflects current data/AI
availability. A hosted Korean document-specific AI answer completed with six
sources. Source-only fallbacks now explain the situation and hide long excerpts
until requested. All 29 frontend tests pass; see
[verification details](docs/assurance/beginner-ux-20260908.md).

**Hosted data verified (2026-09-08):** Revision `7956f26` and its GitHub quality/security
checks passed. Production readiness is healthy; the library displays 440 active
drug letters. Letter detail and a saved Korean OpenAI answer with six citations
were verified through the browser. The target is `wdaflyddglimtijvgazl`, with
private `pharma-evidence` Storage. Temporary credentials were removed. The workspace
Supabase CLI link now points to that target. See the copy evidence below.

**Dataset copy approved and completed (2026-09-08):** The owner selected copying
into `wdaflyddglimtijvgazl`. All 21 source application tables and 444 private raw
files are copied and verified; all 57 current tables and runtime roles are present.
Production Vercel database/Storage settings are provisioned. See
[copy evidence](docs/assurance/dataset-copy-20260908.md). This supersedes the pending
destination and empty-target notes below. Hosted verification is complete as recorded above.

**Dataset located (2026-09-08):** `data.sql` contains 884 letters, including 444
in-scope drug letters, and 4,298 searchable passages. Live counts match the now-linked
`uwgzvobkblrnmqwroegh` project (`supabase-daewoong`). The source data exists;
the hosted PharmaAgent OS connection is still pending. The user has been asked
whether to use that project or copy into `wdaflyddglimtijvgazl`. No import or cloud
configuration was performed. See [dataset evidence](docs/assurance/dataset-discovery-20260908.md).
Preserve the Git-ignored dump and the user's untracked package/Supabase setup files.

**OpenAI update (2026-09-08):** The server now supports OpenAI Responses, and
Production/Preview have a Secret key and `gpt-5-mini` generation settings. Real
adapter checks passed chat, scope classification, Korean translation and document
analysis using synthetic evidence. See [activation evidence](docs/assurance/openai-activation-20260908.md).
This does not resolve the missing database/storage/corpus setup or activate the
home page's full agent workflow. Keep the key out of browser code and source.

**Employee UX update (2026-09-08):** Home now guides staff through choosing a task,
writing a question, and saving/downloading a review request. Multiple browser
drafts, legacy migration, readable export, unsaved-work protection, plain-language
errors and a bilingual `/help` guide are implemented. Everyday navigation has six
destinations; specialist/operational tools expand separately. Build, lint, 26 tests
and production browser journeys passed. See the implementation record for full
evidence. Requests remain local drafts; live analysis and shared data are pending.

**Supabase access update:** The owner supplied project `wdaflyddglimtijvgazl`.
Authenticated CLI access works. It is named `Daewoong FDA`; metadata inspection
found no application tables and zero public tables. Database destination selection
is pending because the existing runbook specifies a dedicated PharmaAgent OS
project. No application schema or hosted configuration was changed. See
[access evidence](docs/assurance/supabase-access-20260907.md).

**Latest sizing update:** Text is approximately 18% larger across the portal,
with larger controls, a 280px sidebar, a 76px header and taller workflow steps.
The production build, lint, 22 tests, full browser interaction checks and six-route
responsive checks at five widths passed. See `DESIGN.md` for the sizing contract
and the implementation handoff for evidence. Backend configuration is still pending.

**Latest interface update:** At the user's request, the service now leads with an
agent workspace: a browser review brief, nine-step workflow inspector, five-agent
team explorer, case activity and human review. Research chat moved to `/ask` with
legacy query links preserved. The new design, route contract and test evidence
are documented at the top of `PHARMA_AGENT_OS_IMPLEMENTATION_HANDOFF.md`.
Do not restore the former chat-first home or introduce account login. Browser
drafts are local only; production agent execution and live data remain pending.

Publication update: checkpoint `8ade4a1` is on GitHub `main`. The dedicated Vercel
project `pharmaagent-os` serves https://pharmaagent-os.vercel.app. Supabase
setup remains needed; backend health returns 500 for missing database configuration.
See [hosting evidence](docs/assurance/github-vercel-hosting-20260907.md).
The working-tree and no-deployment notes below describe the earlier transfer state;
the GitHub commit now preserves that work.

Continuation on 2026-09-07 hardened the shared step-completion boundary before
specialist wiring. See [the evidence record](docs/assurance/completion-boundary-20260907.md).
The worker adapter and observed evaluation remain unfinished. Preserve the new
`runtime/validation.py` and `tests/test_completion_boundary.py` as well as the
modified runtime service/schemas, case tests, and implementation record.
Final continuation verification: **508 API tests passed, 7 gated integration
tests skipped**; Ruff, contract validation and diff whitespace checks passed.

**2026-09-07 public-access update:** The user removed all account-login requirements.
Google/Naver providers, the account menu, and Auth.js were removed. `/sign-in` now
redirects to the dashboard. `PORTAL_SESSION_SECRET` signs an automatic browser
cookie; backend assertions use anonymous subjects with viewer permission only.
Application commit `f1767f7` is deployed and live browser checks passed. Obsolete
Vercel login settings were removed. OAuth/admission setup in historical notes is
superseded. See
[public-access evidence](docs/assurance/public-access-20260907.md).

**Live-data follow-up (2026-09-07):** API server signing settings are now provisioned
in Vercel Production/Preview with separate RSA keys. Supabase connection, Storage,
production runtime settings and ingestion remain pending. See the implementation
record for the current incident diagnosis; the login-removal CI finished successfully.

## Start here

Work only inside `C:\Users\user\Desktop\PharmaAgentOS`. The directory
`C:\Users\user\Desktop\Daewoong FDA` and its deployed FDA application are a
separate project. Do not modify, link, or deploy this service over them.

This file is the transfer brief. Preserve the authoritative
[implementation plan](PHARMA_AGENT_OS_IMPLEMENTATION_PLAN.md) and update the
[implementation record](PHARMA_AGENT_OS_IMPLEMENTATION_HANDOFF.md) as work progresses.
The user has already selected **production, Vercel and Supabase**; do not reopen
that platform decision. Dedicated project identifiers and the final domain have
been requested but have not been supplied.

Read these next:

1. [Production deployment runbook](infra/deployment/vercel/README.md).
2. [Latest preparation evidence](docs/assurance/vercel-supabase-preparation-20260907.md).
3. [Execution and evaluation work remaining](docs/runbooks/launch-preparation.md).
4. [Vercel/Supabase architecture decision](docs/adr/0004-vercel-supabase-production.md).
5. [Release evidence checklist](docs/assurance/release-evidence-checklist.md).

## Preserve the working tree

The latest committed base at handoff is `2cb6da8` — `Fix production role separation
and workload startup wiring`. The launch-hardening and Vercel/Supabase preparation
changes are **uncommitted**, including important **untracked files**. A clone of
that commit alone will not contain this work. Do not reset or clean the working tree.

Run `git status --short` and review the complete diff before continuing. Preserve
both modified tracked files and new source/documentation files when transferring
the project. Do not transfer local `.env` files or credentials through Git/chat.
The `.artifacts/` evidence directory is ignored by Git; retain approved test reports
separately if handing over to a different machine. Virtual environments and local
container images are machine-local conveniences, not a reproducible source release.

No commit, source push, cloud provisioning, cloud migration, Cron activation, DNS
change or production deployment was performed during this launch preparation.

## What is implemented

The repository has milestone 0–8 reference implementations: case/run orchestration,
versioned agent/tool registries, evidence bindings, internal knowledge ACLs, impact
analysis, verification/artifacts, approvals, evaluation/control tower and durable
execution controls. Reference implementation coverage does **not** establish a
working production specialist-agent pipeline.

| Area | Current change and code location |
| --- | --- |
| Public access | Account login removed at user request; signed anonymous browser sessions in `visitor-session.ts`, `backend-auth.ts`, and `proxy.ts` give viewer access and isolate browser ownership |
| Production startup | `services/api/app/config.py` rejects unsafe database, Host, CORS, signing, telemetry, debug and SMTP settings; supports explicit Vercel-managed secret injection |
| Secrets | `services/api/app/security/secrets.py` adds a Vercel provider; metadata guards are not proof of dashboard secret visibility |
| Vercel services | Root `vercel.json` declares Next.js web, private FastAPI API and bounded FastAPI worker; web gets its API URL through a service binding |
| Worker | `services/api/app/serverless_worker.py`, `worker_entrypoint.py` and `worker.py` implement authenticated fixed-scope triggers, separate case/ingestion claims, bounded processing and cancellation recovery |
| Runtime resources | `scripts/prepare-vercel-resources.py`, `app/resource_paths.py` and registry/corpus loaders bundle reviewed contracts and labeled synthetic data into the service |
| Supabase | `infra/deployment/vercel/production.env.example`, `supabase-data-api-boundary.sql` and `supabase-worker-cron.sql` prepare configuration, browser-role denial/RLS and Vault-backed Cron triggers |
| CI/deployment checks | Frozen Python dependency installation, repaired restore canary, stronger deployment preflight, Docker test inputs and live Supabase-boundary regression |

## Worker and infrastructure details to retain

The worker exposes only POST `/internal/worker/cases` and
`/internal/worker/ingestion` through public routing. It requires a bearer secret,
rejects caller-selected job parameters, and accepts only an absent body or `{}`.
Each request processes at most eight jobs in a default 210-second cooperative
slice; Vercel functions are configured for 300 seconds. These are configuration
values, not proof of the target platform's observed behavior.

Cooperative cancellation saves/reuses checkpoints and extends the failure retry
allowance without decrementing the attempt counter. That monotonic counter fences
stale claims. Hard termination relies on the existing five-minute lease recovery.
Do not reset counters or weaken claim checks to make recovery tests pass.

`WORKER_DATABASE_URL` must be set separately from the API's `DATABASE_URL`.
Use the existing least-privilege API/worker roles, not the database owner.
Distinct selected database URLs do not isolate all secrets between services in
one Vercel project: the project environment is a shared trust boundary.

The Supabase boundary script covers all **57** current application tables. Browser
roles lose table access; runtime RLS policies permit existing backend grants.
User/evidence ACL enforcement still belongs in the API. The table-list regression
must be updated with schema additions. Supabase Storage uses conditional,
content-addressed writes; this is not native WORM storage or a verified evidence
backup. Administrative deletion controls and evidence restore remain to be qualified.

The Cron scripts **drain existing jobs**. They do not enqueue the six-hour FDA
discovery schedule. Temporal and embedded polling are disabled in the selected
template. The checked-in template also disables worker activation/model use and
admits no users until the immutable-subject directory is populated.

## Launch blockers and next work, in order

| Priority | Work | Completion evidence |
| --- | --- | --- |
| 1 | Connect dispatched case steps to actual specialist execution | An approved case executes its bound agents/tools and persists schema-validated results without manually injecting successful completion payloads |
| 2 | Replace fixture-based release evaluation with observed execution/grading | Trials execute their bound targets and record actual outputs, tool results, citations, budgets and independent grades; fixture success cannot authorize production |
| 3 | Configure dedicated Vercel/Supabase projects and domain | Correct project links, isolated Preview resources, credentials, exact Hosts, private binding, least-privilege database connections and isolated anonymous sessions work on the deployed revision |
| 4 | Qualify worker scheduling and recovery | Authorized Cron delivery, lane isolation, duplicate/overlapping delivery, cooperative timeout, hard termination, stale lease/dead-letter handling and six-hour source-job creation are demonstrated |
| 5 | Qualify one complete review flow and operations | Separate analyst/reviewer complete a real evidence-bound review/export; denied and insufficient evidence fail safely; telemetry, alarms, backup/restore and rollback are demonstrated |
| 6 | Record release decisions and admit users | Tested revision, case/run/artifact IDs, intended data/use, service owner, support route and required release decisions are recorded |

Concrete starting points for priorities 1–2:

- `services/api/app/agent_platform/runtime/service.py::_dispatch_step` currently
  persists an invocation and marks it running or waiting for approval.
- `services/api/app/worker.py` handles `orchestrate_case_run` by calling
  `advance_case_run`; that alone does not execute the specialist.
- `complete_step` now validates structural output contracts and current authority
  bindings. Only regulatory findings and the existing verification response shape
  are supported; unimplemented output references reject completion. Add each
  remaining exact contract with its execution adapter. Structural acceptance does
  not establish source resolution, independent grades, or a successful review.
- Reuse existing regulatory/internal-knowledge/impact/verification runners,
  durable journals, MCP authorization, source/version binding and `complete_step`
  validation. Trusted code must choose authority, tools and approval scope.
- `services/api/app/evaluation/service.py::DeterministicEvaluationRunner` reads
  supplied `simulated_outcome`/`actual_outcome` and model scores. It remains useful
  for fixture tests but is insufficient for independent release qualification.
- `services/api/app/evaluation/router.py` deliberately rejects fixture-based
  promotion to production. Preserve that guard until qualifying execution and
  grading evidence replaces the fixture path.

Exercise suspended agents, denied evidence, stale plans/sources, exhausted budgets,
duplicate delivery and worker loss alongside the successful flow. Do not treat
HTTP 200, a successful queue dequeue or a running invocation as case completion.

## Inputs still needed from the service owner

- Dedicated Vercel project/team, Supabase project and final production domain.
- Operating plan/budget and whether additional secret isolation is required.
- Enabled identity providers and immutable subjects for initial operator,
  analyst and separate reviewer accounts.
- Approved model profiles/provider and permitted production data boundary.
- Service owner, support contact and release/rollback decision owner.

Ask for identifiers and decisions only. Credentials belong in the deployment
secret store. The existing FDA project is not an implicit target.

## Database activation order

Use the [authoritative migration order](PHARMA_AGENT_OS_IMPLEMENTATION_HANDOFF.md#database-migration-order)
and the fresh-database sequence in `.github/workflows/ci.yml`. CI first prepares
migration prerequisites, applies the control-plane migration, completes the ORM
schema, then applies the remaining migrations and runtime grants. Do not initialize
the runtime from `contracts/schema.sql` or assume `init-db` installs immutable guards.

Apply `supabase-data-api-boundary.sql` only after all migrations/grants. Verify
actual login inheritance, table grants and RLS through both runtime identities.
Keep production `AUTO_CREATE_SCHEMA=false`. Apply Cron only after hosted trigger
authentication/recovery is qualified. Configure local migration-only settings as
documented; do not spoof Vercel system metadata on a local process.

## Verification already completed

These are historical results for the handoff working tree, not newly rerun tests
and not proof of cloud deployment:

| Evidence | Result |
| --- | --- |
| Latest full native API suite | **489 passed, 7 gated integration skips**, 336.74 seconds |
| Focused worker/config suite | **58 passed** |
| Separate live PostgreSQL boundary/resource suite | **4 passed**; test DDL/roles rolled back |
| Latest Ruff/contracts/config checks | Passed; CI YAML parses and diff whitespace check passed |
| Previous frontend qualification | **28 tests**, lint, TypeScript and production build passed |
| Previous packaged API qualification | **465 passed, 6 gated skips**; separate PostgreSQL/Temporal set **8 passed** |
| Previous recovery/security evidence | Isolated restore passed; both then-current runtime image scans had zero HIGH/CRITICAL findings |

Latest reports: `.artifacts/vercel-production-20260907/full-api-tests.xml`,
`worker-tests.xml`, `boundary-tests.xml`, and downloaded `vercel-schema.json`.
Older reports: `.artifacts/launch-20260906/`; see the
[earlier audit](docs/assurance/launch-readiness-20260906.md) for exact scope.
Previous image scans do not attest new runtime sources or a future Vercel build.

Vercel configuration instance validation passed. Strict meta-schema checking of
the downloaded platform schema encountered nonstandard annotations, and a real
Vercel build remains unverified. Private Host behavior, platform duration limits,
Cron HTTP delivery and production secrets have not been tested on a dedicated target.

## Reproduce checks locally

Use a fresh local shell without production credentials or live-integration opt-ins.
All generated files must stay within this workspace. The existing local environment
uses Python 3.12; CI uses Node 22. Install from the existing lockfiles.

```powershell
Set-Location 'C:\Users\user\Desktop\PharmaAgentOS\services\api'
uv sync --frozen --extra dev
New-Item -ItemType Directory -Force '../../.artifacts/engineer-handoff-check' | Out-Null
.venv/Scripts/ruff.exe check app tests ../../scripts/deployment-preflight.py ../../scripts/prepare-vercel-resources.py
.venv/Scripts/python.exe -m pytest --basetemp=../../.artifacts/engineer-handoff-check/tmp --junitxml=../../.artifacts/engineer-handoff-check/api-tests.xml --tb=short
.venv/Scripts/python.exe ../../contracts/validate_contracts.py
```

For web changes, run `npm ci`, `npm test`, `npm run lint`, `npm run typecheck` and
`npm run build` from `apps/web`. Follow `.github/workflows/ci.yml` for explicitly
isolated PostgreSQL/Temporal tests. `AGENT_OS_SUPABASE_TEST=1` requires a migrated,
seeded **test** database and uses transactional DDL; never point it at production.

The retained `pharma-launch-20260906-postgres` and
`pharma-launch-20260906-temporal` qualification containers are stopped. They are
local fixtures, not production services. Do not assume they exist on another machine.

## Deployment and stop conditions

Build and qualify an isolated Preview before production activation. Resolve the
exact binding/probe Host values without wildcard admission. Keep server assertions
RS256, preserve viewer-only public sessions, human/service role separation, immutable
source bindings, evidence ACLs, audit history and independent reviewer authority.

Monitor both Cron history and `net._http_response`, plus pending age, repeated time
slices, dead letters and business case state. A scheduler enqueue is not success.
Pause triggers using `SERVERLESS_WORKER_ENABLED=false` and unschedule
`pharma-case-worker` / `pharma-ingestion-worker`; use existing execution kill switches
for cases. Preserve checkpoints and audit evidence during investigation.

Stop admission on an authorization leak, approval bypass, missing evidence binding,
duplicate committed effect or lost audit trail. Do not declare launch readiness
until the blocker table above and release evidence are complete.
# Beginner AI UX update — 2026-09-08

Home now leads to live AI research; the local draft editor is at `/requests` with
the same stored drafts and a legacy saved-request bookmark redirect. Chat defaults
remain automatic, advanced settings collapse, and the Korean/English guide explains
source checking and current availability. Build, lint, all 26 frontend tests and
26 browser checks passed. See the authoritative implementation handoff and ignored
`.artifacts/beginner-ux-20260908/` evidence. The update is deployed; the fallback
follow-up adds three passing regression tests (29 frontend tests total).
