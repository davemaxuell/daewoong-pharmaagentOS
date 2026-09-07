# Launch preparation

Prepared 2026-09-07 from the authoritative
[implementation plan](../../PHARMA_AGENT_OS_IMPLEMENTATION_PLAN.md),
[handoff](../../PHARMA_AGENT_OS_IMPLEMENTATION_HANDOFF.md), and
[latest qualification evidence](../assurance/launch-readiness-20260906.md).
This is the execution sequence for that plan, not a replacement specification or
a production approval.

## Selected production target

The user selected **production on Vercel and Supabase** on 2026-09-07. Use the
[production configuration and activation runbook](../../infra/deployment/vercel/README.md).
Dedicated project identifiers and the production domain remain needed. Deliver
one complete regulatory-impact review workflow and qualify it with fictional
internal quality data before admitting production users or approved company data.

Pilot outputs remain decision support and require human review. Retain synthetic
data labels, source/version bindings, separate reviewer authority, and draft-only
integrations. Enabling access to the current interface alone does not establish
that its end-to-end agent workflow works.

## Engineering sequence

| Order | Work | Completion evidence |
| --- | --- | --- |
| 1 | Connect scheduled case steps to specialist execution | An approved case proceeds from dispatch through actual tool/agent execution to a persisted, schema-validated result without manually supplying success payloads |
| 2 | Complete one review package | Curated regulatory evidence and synthetic internal documents produce findings, impact hypotheses, an independent verification record, and an artifact that a separate reviewer can approve and export |
| 3 | Exercise execution failures | Lost worker, duplicate delivery, stale plan/source, exhausted budget, denied evidence, and suspended agent cannot bypass controls or duplicate committed work; failures have attributable terminal/recoverable states |
| 4 | Run evaluations against actual execution | Each trial executes its bound target and records observed outputs, tool outcomes, citations, time/cost, and independently derived grades; fixture-supplied success/model scores cannot satisfy live release gates |
| 5 | Prepare the selected environment | Exact domains, private services, database migrations/grants, immutable storage, authentication, secrets, telemetry, and durable worker configuration are rendered and checked for the selected host |
| 6 | Qualify the hosted pilot | Real allowed/denied accounts, separate analyst/reviewer access, one successful review, one denied-evidence case, one insufficient-evidence case, worker recovery, and rollback/restore are demonstrated on the target |
| 7 | Admit the pilot group | Record the tested version, named operator, admitted account subjects, data boundary, support route, stop conditions, and intended-use acceptance before inviting users |

Steps 1–4 can be implemented and exercised with isolated test dependencies in this
workspace. Live provider evaluation additionally needs the selected approved
model profiles and credentials in the deployment secret store. Steps 5–7 depend
on the selected target and account setup.

## Concrete code starting points

- `services/api/app/agent_platform/runtime/service.py::_dispatch_step` currently
  persists the invocation and marks it running or waiting for approval.
- `services/api/app/worker.py` handles `orchestrate_case_run` by advancing the
  orchestration state. This is not a complete specialist execution adapter.
- Reuse the existing regulatory runner, internal knowledge agents, verification
  services, MCP policy boundaries, durable journal, and `complete_step` result
  checks when implementing dispatch. Persist trusted execution context; do not
  let model output select authority, tools, or approval scope.
- `services/api/app/evaluation/service.py::DeterministicEvaluationRunner` reads
  supplied `simulated_outcome`/`actual_outcome` and `model_scores`. Keep this
  available for fixture tests while adding independently observed execution and
  grading. Preserve the production promotion block until qualifying evidence
  exists.

## Inputs needed from the service owner

| Decision | Required input |
| --- | --- |
| Audience | Production selected; identify the initial admitted accounts and data boundary |
| Hosting | Vercel/Supabase selected; dedicated project identifiers, domain, and operating budget |
| Accounts | Enabled identity provider(s), initial operator/analyst/reviewer accounts, and their immutable provider subjects |
| Models and data | Approved model profiles and whether data stays synthetic or includes approved internal documents |
| Operations | Named service owner, reviewer, support contact, and release/rollback decision owner |

Provide project names, domains, and preferences in the conversation. Configure
credentials through the target's secret store; do not paste them into this file
or chat. Complete provider login interactively when required.

The Vercel configuration now includes a bounded database-queue worker triggered
through Supabase Cron. Temporal and embedded polling are disabled for this
topology. Qualify the actual deployed worker before activating schedules.

## Pilot acceptance and stop conditions

The pilot is ready only when a real invited user can complete the declared flow
on the hosted version, with real authentication and no fabricated execution or
grading evidence. Retain the exact case/run/artifact IDs and corresponding
version hashes in the release record.

Stop admission or pause affected execution on an authorization leak, approval
bypass, missing source binding, duplicate committed effect, or loss of the audit
trail. Use the existing kill switches and deploy/rollback runbook; preserve
evidence and reconcile interrupted work before resuming.

A production release additionally requires the independently executed evaluation
gates, target security and recovery evidence, approved data/intended use, and the
designated human release decisions in the
[release evidence checklist](../assurance/release-evidence-checklist.md).

## Current status

- Local engineering baseline: verified on 2026-09-06; see the linked audit for
  exact tests, image scans, restore results, and qualification limits.
- Execution/evaluation adapters: outstanding application work. A prerequisite
  [completion-boundary fix](../assurance/completion-boundary-20260907.md) now checks
  structural contracts, finite usage, active attempt and current approval/release
  bindings. Evidence resolution and independently executed results remain required.
- Target: production on Vercel/Supabase selected; configuration prepared locally,
  dedicated project identifiers/domain still needed; no cloud resources provisioned.
- Target preparation verification: [489 passing API tests and live database
  boundary evidence](../assurance/vercel-supabase-preparation-20260907.md).
- Hosted pilot: not yet qualified.
- Production release: blocked; no approval inferred from local test results.
