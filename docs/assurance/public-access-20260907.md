# Account-free portal — 2026-09-07

The service owner requested removal of all account login. The frontend now opens
the dashboard directly. Google/Naver integrations, Auth.js and account/sign-out
controls have been removed, along with their dependencies and environment setup.
Old `/sign-in` links redirect to `/dashboard`; `/api/auth/providers` returns 404.

An automatic signed browser cookie carries an anonymous UUID subject and lasts
30 days. Production uses a Secure, HttpOnly, SameSite=Lax, host-only cookie.
Separate Preview/Production `PORTAL_SESSION_SECRET` values were provisioned as
Vercel Secrets without writing their values to source or evidence files.

The API connection retains RS256 assertions. Public assertions expire after 90
seconds and have only viewer authority. The API rejects malformed anonymous
subjects, elevated public roles and group-derived public privileges. Existing
ownership checks use the anonymous subject; clearing the browser cookie loses
access to that browser's prior private history. No cross-device account exists.

## Verification before publication

- Frontend: 20 tests passed across six files; lint, TypeScript and production
  build passed. The final UI detector returned no findings.
- API authentication regression: 30 tests passed, including public viewer access,
  denied elevated roles and denied group-based escalation. Ruff passed.
- Headless Edge against the local production build: dashboard 200 without login,
  legacy sign-in redirect, removed provider endpoint, distinct visitor cookies,
  returning-cookie continuity, and denied admin/review rendering passed.
  Next.js streamed denied pages carry its not-found boundary after a 200 response;
  no privileged content is rendered.
- Desktop (1280 x 900) and mobile (390 x 844) screenshots inspected. Account UI is
  absent, mobile has no horizontal overflow, and no browser JavaScript errors occurred.
- Local evidence is retained under ignored `.artifacts/public-access-20260907/`.

## Deployment and remaining work

Application commit `f1767f7` was pushed to GitHub `main` and deployed successfully
as Vercel deployment `dpl_6iBCzj3odCd1pUeHiMTXBpeYeecr`. The public alias
https://pharmaagent-os.vercel.app points to this account-free build.

The same headless desktop/mobile checks passed against the public alias: direct
dashboard 200, no account controls, legacy sign-in redirect, provider endpoint 404,
distinct/continuous browser cookies, protected admin/review rendering, no overflow
or browser JavaScript errors. Frontend health returned 200; backend health still
returned 500 because production database setup is outstanding.

Obsolete `AUTH_SECRET`, `AUTH_ADMISSION_MODE`, `AUTH_SUBJECT_ROLE_ASSIGNMENTS_JSON`
and `AUTH_TRUST_HOST` variables were removed from Vercel Preview and Production.
The current implementation record supersedes historical OAuth/admission setup
requirements.

Supabase/database and server API signing configuration remain outstanding. Browser
identity checks do not establish live database persistence or successful AI queries.
The existing specialist execution and production qualification blockers remain.

GitHub checks for `f1767f7`: frontend, contracts, PostgreSQL schema/restore,
Temporal recovery, both container checks, deployment rendering and secret scanning
passed. Both CodeQL language jobs passed. The full backend regression job was
still running when this evidence was recorded; the focused authentication suite
above passed locally. CI run: https://github.com/davemaxuell/daewoong-pharmaagentOS/actions/runs/34078404837.
