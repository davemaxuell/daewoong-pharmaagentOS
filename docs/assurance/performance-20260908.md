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
| Home | 4.116 | 3.479 |
| New AI chat | 23.986 | 2.433 |
| FDA library | 23.535 | 2.818 |
| Letter detail | 10.645 | 8.667 |
| Trends | 22.875 | 1.777 |
| Saved sources | 22.976 | 0.902 |
| Control tower | 13.310 | 1.214 |

Repeated navigation at the end of the same run: Home 3.855 → 0.458 seconds;
chat 24.495 → 1.267 seconds; library 24.576 → 1.153 seconds. First Home navigation
occurred immediately after deployment and includes initial runtime/browser costs.

These initial results are for `d7a08a6`, deployment
`dpl_HESwkALUCxPETqAiMvLVDua9TL72`. Vercel reports the API and web functions in
`syd1`; production response headers changed from `iad1` to `syd1`. All GitHub
quality/security jobs passed: [run 34229848288](https://github.com/davemaxuell/daewoong-pharmaagentOS/actions/runs/34229848288).
The subsequent detail-read optimization will be measured after publication.

Hosted functional smoke: 440 visible letters, working detail, a real AI answer
(no source-only fallback) with six citations in 14.552 seconds, history persistence
after reload and isolation from a separate browser session. Sidebar responses are
private/no-store. Database and object storage readiness passed. No browser errors.

Raw timings and browser evidence remain in ignored `.artifacts/performance-20260908/`;
no session cookies or secrets are included in the committed report.
