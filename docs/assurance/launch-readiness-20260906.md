# Launch readiness — 2026-09-06

**Decision: production launch remains blocked.** The locally verified application
is a candidate for controlled staging qualification. No production deployment,
source push, release signature, live provider login, or organization approval was
performed during this review.

This review follows the authoritative implementation plan and handoff and updates
the [previous qualification record](deployment-readiness-20260905.md). No target
environment or launch audience was confirmed during this review.

## Issues fixed

- Added `AUTH_ADMISSION_MODE=restricted` for private pilots and internal service
  access. Only explicitly assigned immutable Google/Naver subjects can sign in.
  Removing a subject rejects its existing session at the proxy and server identity
  boundary and prevents new API assertions. Existing assertions expire within
  90 seconds. Public viewer admission remains available through `public`, the
  compatibility default. The Kubernetes and deployment templates select restricted
  admission; their empty directory deliberately admits nobody.
- Production settings now reject SQLite/missing PostgreSQL database names, debug
  mode, wildcard/empty Host admission, insecure or malformed CORS origins,
  non-RS256 algorithm lists, HTTP or credential-bearing JWKS/telemetry URLs,
  and enabled plaintext SMTP. Existing authentication, migration, storage TLS,
  secret-provider, and Temporal mTLS checks remain in force.
- Deployment preflight now rejects empty/malformed/non-workload inputs, missing
  or unrestricted PostgreSQL egress, unpinned init-container images, and unsafe
  effective settings after ConfigMap references and inline overrides. It handles
  UTF-8 BOM files and reports invalid YAML without printing parser input values.
  This is a static check; server-side schema validation, policy coverage, secrets,
  and actual connectivity still require the target environment.
- CI Python jobs now install from `uv.lock` using frozen resolution. The isolated
  restore drill reproduced a missing `updated_at` value in CI's raw SQL canary
  insert; the workflow now supplies it. New preflight tests and their script are
  included in the API container test stage through the explicit build allowlist.
- Corrected deployment instructions that claimed obsolete email allowlists or
  email-based admin roles worked. Corrected Railway's API build context and
  documented complete Agent OS migrations/grants for managed deployments.
  The incomplete Vercel topology is explicitly documented as staging material.

## Verification evidence

Evidence files are retained in the ignored workspace directory
`.artifacts/launch-20260906/`. Synthetic credentials were used for isolated tests;
no external messages or model requests were sent.

| Check | Result |
| --- | --- |
| Baseline native API suite | 427 passed, 6 explicitly gated integration skips |
| Final configuration/auth/deployment regression set | 76 passed |
| PostgreSQL/Temporal focused suite | 8 passed: 5 live PostgreSQL checks, 1 live Temporal recovery check, 2 runtime regressions; no skips |
| Final packaged API suite (Python 3.14, networking disabled) | 465 passed, 6 explicitly gated live-integration skips in 792.52 seconds |
| Frontend unit tests | 28 passed across 6 files |
| ESLint, TypeScript, production Next.js build | Passed |
| Ruff, contracts, Kubernetes render, Compose render | Passed |
| Base-template deployment preflight | Blocked as expected: placeholder images/domains, no database egress, empty private admission directory |
| Read-only non-root API image smoke | Passed: registry 5/10/16, workflow, corpus, private gateway |
| Read-only non-root web image HTTP smoke | Passed: health, sign-in, static asset, 5 protected redirects, signed-out POST denial |
| Refreshed Trivy 0.74.0 runtime scans | Zero HIGH/CRITICAL findings in both images; CycloneDX SBOMs retained |
| Changed-source Gitleaks v8.30.1 scan | Passed; no leaks found |
| Isolated PostgreSQL logical restore | Passed: 9 table counts matched and canary survived |

All M1–M8 SQL migrations and runtime-role grants were applied with
`ON_ERROR_STOP=1` to a newly created local PostgreSQL 16/pgvector database.
The Temporal check used a real local server and replaced the worker after a
signal was queued. The restore used a new empty target and no destructive clean
option. Its dump SHA-256 is
`36ff1294f3fe9d6da304275ef91d9345cd46c22e241443acf8f306d2d2ced198`.
This is local recovery evidence; production RPO/RTO and cluster/mTLS recovery
remain unqualified. Some restored tables were empty, as recorded in `restore.json`.
The packaged suite used workspace-mounted temporary databases. Its six gated
checks were exercised separately in the PostgreSQL/Temporal run above. All four
temporary qualification services were stopped after use; the test container
removed itself on completion. Evidence and local images are retained.

Locally built image identifiers (not published registry releases or signatures):

- API: `sha256:47bcb2da38b29eee06865bc7eda471334482f147d853a64b2720489e186aec98`
- Web: `sha256:240c3c16648db298b54237a206065b30db02fc3326e8064f466306e8f620e5ff`

## Outstanding launch gates

| Gate | Required completion |
| --- | --- |
| Target and audience | Confirm private pilot, internal production, or public production; select the approved host/domain and responsible operator |
| Infrastructure | Supply the environment overlay, immutable release images, PostgreSQL/storage, TLS, Temporal, restricted egress, telemetry, workload identity, and managed-secret consumer wiring; verify their connectivity |
| Real authentication | Configure provider applications, callback URLs, signing keys, and actual admitted subjects; test allowed/denied accounts and role separation on the target |
| Production agents | Complete and qualify specialist execution adapters; registry manifests alone do not establish independently executed production agents |
| Release evaluation | Implement independently executed and graded live evaluations; the current fixture runner cannot authorize production promotion |
| Operational and human release | Run hosted CI/CodeQL, target restore/rollback and UAT, then retain designated security/privacy/QA/CSV approvals and release signing evidence |

Use the [release evidence checklist](release-evidence-checklist.md) to retain exact
version-bound results. Passing local tests and scans does not close these gates.
