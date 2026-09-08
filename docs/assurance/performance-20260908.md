# Loading performance — 2026-09-08

## Changes

- Portal layout reads only the local signed identity. History and the newest
  notification load after hydration through a viewer-guarded, private/no-store
  route. Slow sidebar reads no longer hold up unrelated page content.
- History loading, retry and merging preserve browser-session privacy and local
  changes made while a request is pending. Initial loading does not show an error.
- `/api/v1/letters/catalog` returns existing list metadata for at most 1,000 current
  in-scope letters per request, paginating in SQL before enrichment. The current
  440-letter collection needs one request instead of five. Cursor validation,
  ordering, filtering boundaries and the 10,000-record client ceiling remain.
- Individual document and saved-chat links do not prefetch every linked page.
- Letter-detail metadata and page rendering share one request-scoped React read.
  The detail's current version/hash are used directly, eliminating an additional
  version-history request that could select an unrelated response/closeout version.
- Root Vercel configuration selects `syd1`, alongside the Supabase database in
  Sydney. See [Vercel region configuration](https://vercel.com/docs/functions/configuring-functions/region)
  and [region mapping](https://vercel.com/docs/regions).

No cross-user data cache, database credentials, model settings, evidence checks,
ingestion schedule or worker activation changed.

## Local verification

- Frontend: 38 tests passed; ESLint and production build/TypeScript passed.
- API: 55 focused tests passed (core API, catalog and deployment configuration).
- OpenAPI/JSON Schema contract validation passed.
- Delayed-sidebar browser: Home visible in 688 ms while the sidebar request was
  held for three seconds. Normal loading had no false error; failure/retry loaded
  history without a page reload. No browser JavaScript errors.
- Design detector: no findings in changed UI components.
- Beginner experience: all 26 local browser checks passed across Korean/English
  and 320/390/768/1440px, including draft persistence and keyboard interactions.

## Hosted measurements

Baseline captured on Edge from this workspace against the production alias.
The same browser context navigated 16 routes; Home, chat and library were repeated
at the end. Ready time means the first main heading or chat textarea became
visible, not AI generation completion. These are individual observations, not a
statistical latency guarantee.

| Route | Before (seconds) | After (seconds) |
| --- | ---: | ---: |
| Home | 4.116 | 3.644 |
| New AI chat | 23.986 | 2.592 |
| FDA library | 23.535 | 1.661 |
| Letter detail | 10.645 | 2.336 |
| Help | 4.000 | 0.967 |
| Trends | 22.875 | 0.845 |
| Saved sources | 22.976 | 0.748 |
| Review drafts | 3.853 | 0.757 |
| Specialists | 3.897 | 0.704 |
| Cases | 3.859 | 0.710 |
| Approvals | 4.380 | 0.966 |
| Evaluations | 3.895 | 0.809 |
| Control tower | 13.310 | 0.735 |

Repeated navigation at the end of the same run: Home 3.855 → 0.600 seconds;
chat 24.495 → 0.711 seconds; library 24.576 → 0.848 seconds. First Home navigation
occurred immediately after deployment with a fresh browser context; it includes
initial browser/asset loading and may include runtime cold-start costs. All 16
navigations returned 200 with no browser JavaScript errors.

Final results are for application revision `489214b`, deployment
`dpl_AsEM9y81Ac7xVmcd4Y2x9H1c4ZEJ`. Vercel reports the API and web functions in
`syd1`; production response headers changed from `iad1` to `syd1`. All GitHub
quality/security jobs passed: [run 34230400069](https://github.com/davemaxuell/daewoong-pharmaagentOS/actions/runs/34230400069).
CodeQL also passed: [run 34230400072](https://github.com/davemaxuell/daewoong-pharmaagentOS/actions/runs/34230400072).
The backend suite passed 535 tests with seven environment-gated skips; separate
PostgreSQL jobs passed the five schema and two RLS tests. Temporal recovery,
container scans, secret scan, frontend, contracts and deployment rendering passed.

The first performance release, `d7a08a6`, also passed CI and all 26 hosted beginner
UX checks. Its detail load was 8.667 seconds; eliminating duplicate detail/version
reads reduced that to the final 2.336-second observation.

Hosted functional smoke: 440 visible letters, working detail, a real AI answer
(no source-only fallback) with six citations in 14.552 seconds, history persistence
after reload and isolation from a separate browser session. Sidebar responses are
private/no-store. Database and object storage readiness passed. No browser errors.

Raw timings and browser evidence remain in ignored `.artifacts/performance-20260908/`;
no session cookies or secrets are included in the committed report.

## Limits

These changes reduce page and database-read latency. The observed AI answer time
is a separate functional check, not a before/after generation benchmark. Model
latency, cold starts, network conditions and larger future corpora remain variable.
No repeated benchmarking or broader architectural changes are needed to qualify
this bounded loading optimization; revisit catalog pagination if the corpus grows.
