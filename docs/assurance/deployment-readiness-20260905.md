# Deployment qualification — 2026-09-05

This audit supersedes earlier statements that the whole plan was production-ready
or that every remaining activity was only environment configuration.

## Completed engineering work

- Initialized a dedicated Git repository and checked that the requested GitHub
  destination is empty. No other project directory was changed.
- Fixed `.gitignore` so safe `.env.example` templates reach clean checkouts;
  runtime data, secrets, dependencies, dumps, and generated evidence remain ignored.
- Rebuilt the API with its reviewed contracts, workflow, registry and synthetic
  corpus. Dependencies install from `uv.lock` with `--frozen`.
- Replaced the Debian runtime after its scan reported unfixed OS vulnerabilities.
  The pinned Chainguard builder/runtime pair supplies Python 3.14.7; development
  remains compatible with Python 3.12. Runtime contains no build-stage tools.
  This follows the vendor's [multistage Python guidance](https://images.chainguard.dev/directory/image/python/overview).
- Pinned image bases, ran as numeric non-root users, and verified read-only API/web
  startup and HTTP health endpoints. The frontend runtime updates Alpine packages
  and removes npm, which the standalone server does not need.
- Scanned both final images with Trivy 0.74.0: zero HIGH/CRITICAL findings.
  Generated CycloneDX SBOMs and JSON scan evidence in ignored `.artifacts/`.
- Applied all M1–M8 PostgreSQL migrations and runtime-role grants against PG16 with
  pgvector. All five PostgreSQL guard tests passed. Updated the older artifact
  fixture to provide the M5 verification binding instead of weakening the guard.
- Dumped and restored the database into a newly created isolated database.
  Source/restored counts matched for cases, approvals, artifacts, verification,
  case events, and policy decisions. Local dump SHA-256:
  `bb606b9697895cdb9b326473da4f64693ee30fb4fa94dae254a868255a171ba3`.
- Hardened the reusable PowerShell restore drill to reject populated targets,
  stop on the first restore error, and compare source/restored counts. It no
  longer issues `pg_restore --clean`.
- Exercised a real Temporal server with a replacement worker consuming persisted
  history and a signal queued while no worker was running. This is a worker
  replacement test, not evidence of production cluster/mTLS disaster recovery.
- Fixed failed activity attempts to roll back partial business writes using a
  savepoint before committing the failure journal. Added a failure-after-flush test.
- Added CI container builds, image vulnerability gates, SBOM artifacts, real
  Temporal recovery checks, PostgreSQL restore artifacts, and CodeQL analysis.
- Staged source passed Gitleaks without publishing secrets or runtime data.

## Verification scope

- Native Python 3.12 API suite, including live PostgreSQL and Temporal:
  **407 passed** in 352.41 seconds, followed by passing focused release-gate tests.
- Final Python 3.14 container test stage, including live PostgreSQL and Temporal:
  **407 passed** in 331.11 seconds after the packaging and release-gate fixes.
- Frontend: **22 unit tests passed**, TypeScript, ESLint and production build passed.
- API packaged-runtime smoke: non-root, registry (5 agents/10 skills/16 tools),
  workflow, bundled corpus and private-gateway boundary passed.
- Read-only web runtime: health and public brand asset returned HTTP 200. Both
  web Dockerfiles now include public assets and the same runtime hardening.
- Contracts and Docker Compose render passed. Deployment preflight failed as
  expected on unresolved production placeholders and missing database egress.
- Hosted GitHub Actions/CodeQL, real corporate sign-in, live model qualification,
  approved-target connectivity and formal release validation have not run.
- The staged whitespace check reports pre-existing final blank lines and intended
  Markdown hard breaks. These were preserved rather than rewriting source fixtures.

No production deployment or GitHub push was performed. The user's push condition
(`once everything is ready`) remains unmet; the work is retained locally for review.

## Remaining production blockers

1. A hosting target, domain, database/storage endpoints, identity provider,
   Temporal mTLS, telemetry destination, workload identities and managed secrets
   have not been supplied. Kubernetes base files are templates; they need an
   environment overlay, restricted database/telemetry/identity egress, mounted
   credentials, and connectivity tests. `scripts/deployment-preflight.py` rejects
   the template as a live deployment.
2. The Evaluation Center runner reads `simulated_outcome`/`actual_outcome` from
   fixture input and accepts supplied model scores. It does not execute an
   independent end-to-end model evaluation. This is now labeled in trajectory and
   metrics, and cannot authorize production promotion in a production environment.
   A qualified execution/grading adapter and actual release evidence remain work.
3. Runtime dispatch/checkpointing is implemented, but several specialists are
   deterministic reference implementations. The claim of five independently
   model-driven production agents is not established by their registry manifests.
4. The AWS secret provider abstraction exists; mapping managed references into
   every runtime consumer and validating the workload identity is not demonstrated.
5. Formal organization-specific QA/CSV, privacy, security and release signoffs
   require designated human owners. No such approvals have been fabricated.
6. No configured signing identity is available locally. Do not describe a local
   commit or tag as signed, or a source upload as a signed container release.

The locally tested reference application can be used for staging qualification.
It must not be represented as a production-qualified pharmaceutical platform.
