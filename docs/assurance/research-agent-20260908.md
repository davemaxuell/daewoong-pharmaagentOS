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
- 45 focused backend checks pass, covering research ownership/idempotency,
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

Hosted OpenAI execution and final CI/deployment evidence are recorded below after
the release has been verified.

## Remaining limits

This agent uses retained FDA documents, not fresh FDA website ingestion. It does
not analyze internal SOPs, determine Daewoong compliance, create CAPAs, approve
decisions, send messages, or write controlled systems. AI evidence checking can
still be wrong; the employee must review original passages. No account login is
required. Saved work is accessible only through its signed browser session;
clearing cookies, changing browsers or session expiry loses that access. Export
important briefs. Stop prevents further state changes but cannot retract an
already dispatched provider request or its charge.
