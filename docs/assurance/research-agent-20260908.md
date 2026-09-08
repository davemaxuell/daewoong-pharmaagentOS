# FDA Research Agent implementation and qualification

The user approved a goal-driven FDA research agent with visible live execution.
This is a bounded public-evidence slice of the source implementation plan; it does
not qualify the full internal impact, specialist, approval or controlled-write workflow.

## Implemented behavior

- `/research` accepts an editable Korean/English goal. One OpenAI research agent
  chooses native tools to plan, search, read and submit a cited draft. Search can
  adapt to results; an unsuccessful evidence check feeds corrections back into
  the same loop. This is actual tool execution, not a simulated progress animation.
- A separate structured OpenAI call checks the proposed findings against the
  supplied passages. Code also verifies every citation, current Drug scope,
  public-viewer ACL, source version and passage hash before/after checking.
  AI checking is not regulatory approval. Outputs contain attributed findings,
  citations, review questions and limits for human review.
- Supabase stores owner-scoped `research_runs` and `research_events`. An API
  admission transaction saves the task before Next.js schedules a worker trigger.
  Background execution checkpoints after each action. Incremental browser reads
  run every two seconds while visible, ten seconds when hidden, and back off on
  failure. Page rendering itself does not wait for research or task-history reads.
- PostgreSQL `FOR UPDATE SKIP LOCKED` claims work; lease identifiers fence every
  update. Stop revokes the lease so a late response cannot overwrite it. Resume
  uses the retained checkpoint and budget. Expired leases are recoverable.
- Limits: 12 total model calls, 90,000 reserved tokens, four searches, 12 retained
  passages, two semantic checks, three resumes, two active and ten daily tasks per
  browser owner, and 100 new tasks globally per day. Model use is reserved before
  each request so a terminated worker cannot repeatedly spend unrecorded calls.
- Only the research worker lane is enabled. Existing ingestion/case lanes retain
  their separate disabled flag. The trigger accepts an authenticated empty body;
  callers cannot select a run, owner, tool, URL or SQL statement.
- Home and everyday navigation lead to research. The work view shows actual plan,
  searches, source excerpts, evidence checks and saved status; Stop, Resume,
  View brief, citation disclosure and copy/download are available in both languages.

## Local evidence

- 46 frontend tests pass. Production build, TypeScript and ESLint pass.
- Focused backend checks pass, covering research ownership/idempotency,
  citations, correction loops, budget exhaustion, model outage/resume, stopped and
  expired worker leases, source ACL/hash changes, quotas, strict provider requests,
  worker trigger authentication and deployment boundaries.
- Full-stack Edge tests use an explicitly scripted model and seeded FDA fixtures
  locally. They demonstrate visible incremental events, saved reload, cross-browser
  denial, source disclosure, text download, Stop fencing and Resume completing
  after navigation away. Korean/English and widths 320, 390, 768 and 1440 have no
  horizontal overflow or browser exceptions. These fixtures are not production AI
  qualification.
- Impeccable detector returned no findings. Independent UI finish review requested
  a prominent View brief action, a source disclosure chevron and accurate zero-
  result labels; all are addressed. UTC timestamps and stage continuity were also fixed.
- Added a PostgreSQL CI test for concurrent duplicate admission, single worker
  ownership and Stop fencing; SQLite does not prove those locking properties.
- OpenAPI and the existing cross-contract validation pass.
- The initial complete local regression run passed 549 tests with eight expected
  environment-dependent skips. Later focused regressions cover Korean plan
  enforcement and readable Unicode in the independent evidence-check request.
  Final CI adds those two regression cases to the full suite.

## Operations and cloud boundary

The target is `wdaflyddglimtijvgazl`; research migration is additive and preserves
the existing FDA corpus and private Storage. Both new tables have RLS and deny
browser Data API roles and the general read-only runtime role. Only API/worker
roles have the required research grants. API results exclude private model
conversation, encrypted reasoning, lease identifiers and owner identifiers.

`RESEARCH_AGENT_ENABLED=true`, a server-only `WORKER_TRIGGER_SECRET`, and the web
`RESEARCH_WORKER_URL` service binding enable execution. API/worker allowed hosts
include the private service hostnames. Web/API/worker remain in Sydney.

`infra/deployment/vercel/supabase-research-cron.sql` schedules one recovery trigger
per minute only when queued or expired work exists. The origin and trigger secret
are read from Supabase Vault. Apply after the research worker deployment is ready.
To disable new execution, set `RESEARCH_AGENT_ENABLED=false` and redeploy; Stop
and saved-task reads remain available. Do not enable the general worker flag to
activate research.

The research recovery schedule is now active. The Vault-authenticated `pg_net`
probe returned HTTP 200 without timing out; idle scheduled executions succeed
without sending HTTP requests. Hosted readiness is 200, an unauthenticated
research trigger is 401, and case/ingestion triggers remain disabled with 503.

## Hosted qualification

The service is deployed at https://pharmaagent-os.vercel.app/research. Actual
OpenAI calls used the retained Supabase FDA corpus; no scripted model is deployed.
The migration preserves 884 warning letters and private evidence Storage.

- The first Korean comparison completed with two sources, five findings and seven
  model calls. Its evidence checker requested a revision before the second check
  passed. Real saved plan/search/read/draft/check events were visible during the run.
- A separate English task was stopped after model execution began. Its late result
  could not change the stopped state. After Resume was acknowledged, all browser
  pages were closed; the worker completed its brief and the saved result reopened
  successfully. This run used eight total model calls across the interruption.
- A further Korean check withheld its final brief when two evidence reviews failed.
  This demonstrated the fail-closed outcome and exposed escaped Unicode in the
  checker input. The request now carries readable Korean, feedback is bounded to
  500 characters per issue, and Korean plans must pass a language check before
  being shown. The corrected hosted comparison completed in approximately 23
  seconds, with a Korean plan and successful evidence check.
- Final complete hosted journey: task accepted in 1.99 seconds, Korean brief ready
  at 23.1 seconds, six model calls, 16,336 tokens, two cited sources and two findings.
  The second task also completed after Stop/Resume and closing the page, using
  seven calls across the interruption. The complete browser report has no errors.
- Saved reopening, other-browser 404 denial, citation disclosure, keyboard focus
  on View brief, text download, Korean/English navigation, and responsive widths
  320/390/768/1440 passed on the hosted interface without browser exceptions.

Local evidence is retained under `.artifacts/research-agent-20260908/`: browser
reports/screenshots, downloaded briefs, database event/source-pin evidence and
worker boundary results. No production secrets or private model conversations are
included in the checked-in report.

Application revision `e0f8c28` is deployed on Vercel in Sydney. All jobs in
[quality and security](https://github.com/davemaxuell/daewoong-pharmaagentOS/actions/runs/34240612186)
and [code security](https://github.com/davemaxuell/daewoong-pharmaagentOS/actions/runs/34240612178)
passed: 551 backend tests with eight expected environment skips, 46 frontend tests,
PostgreSQL schema/locking/RLS checks (5 + 1 + 2), three Temporal recovery checks,
container tests/scans, contracts, deployment rendering and secret scanning.
The separate PostgreSQL and Temporal jobs exercise the environment-dependent
paths skipped by the general suite. Production browser qualification and the
Vault-authenticated recovery probe are also complete.

## Remaining limits

This agent uses retained FDA documents, not fresh FDA website ingestion. It does
not analyze internal SOPs, determine Daewoong compliance, create CAPAs, approve
decisions, send messages, or write controlled systems. AI evidence checking can
still be wrong; the employee must review original passages. No account login is
required. Saved work is accessible only through its signed browser session;
clearing cookies, changing browsers or session expiry loses that access. Export
important briefs. Stop prevents further state changes but cannot retract an
already dispatched provider request or its charge.
