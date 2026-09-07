# GitHub publication and initial Vercel hosting — 2026-09-07

The user authorized GitHub publication and Vercel hosting. Source checkpoint
`8ade4a1a0d39fbbb892dfcbc00169d3464717290` was pushed to `main` at
https://github.com/davemaxuell/daewoong-pharmaagentOS.

A dedicated Vercel project, `pharmaagent-os`, was created under
`davemaxuell-1329s-projects` and connected to that repository. Project ID:
`prj_QRvb7xP9qmgJl04eEqdIHd1Gzhe8`. The separate FDA project was not modified.

## First deployment

- Public alias: https://pharmaagent-os.vercel.app
- Deployment: `dpl_GUENnRZaW4PNa2ffQKsi8V6h5Mo3`
- Inspection: https://vercel.com/davemaxuell-1329s-projects/pharmaagent-os/GUENnRZaW4PNa2ffQKsi8V6h5Mo3
- Vercel reported **Ready** after building Next.js, API and worker services.
- Vercel automatically assigned the first deployment to its **production target**.
  This platform label is not application production-readiness qualification.

| Public probe | Result |
| --- | --- |
| `/api/health` | 200, frontend health JSON |
| `/sign-in` | 200, login setup page |
| `/dashboard` | 307 to `/sign-in?callbackUrl=%2Fdashboard` |
| `/health/live` | 500, backend startup rejected missing production PostgreSQL URL |

Runtime logs confirm `Production DATABASE_URL requires PostgreSQL with a database name`.
The frontend is hosted; the backend and usable account login are not configured.

## Environment state and next steps

Production and Preview have restricted admission with an empty subject directory,
disabled developer authentication and schema auto-creation, disabled embedded,
serverless and Temporal workers, disabled model/embedding use, and disabled SMTP.
Separate Auth.js secrets were generated directly into Vercel Secret storage for
Production and Preview; they were not printed or committed. Project environment
changes apply on subsequent deployments.

The CLI generated ignored project-link metadata and an ignored `.env.local` with
its development OIDC token. Existing ignore rules preserve example environment files.

Still needed: dedicated Supabase project and isolated Preview resources,
migrated database with least-privilege API/worker connections, private Storage,
OAuth providers and immutable subjects, API assertion key pair, exact service
Hosts, telemetry, and hosted qualification. Configure secrets in Vercel, not Git/chat.

## GitHub checks

For `8ade4a1`, backend, frontend, PostgreSQL/Supabase boundary, Temporal recovery,
both container jobs, contracts, and deployment rendering passed. The secret scanner
flagged a test-only bearer string at `tests/test_serverless_worker.py:16`. The
follow-up adds an inline fixture exception and its exact historical fingerprint,
preserving the existing historical exception. Scanning remains enabled.

The preceding local API suite passed 508 tests with 7 gated integration skips.
Specialist execution and independently observed release evaluation remain unfinished.
