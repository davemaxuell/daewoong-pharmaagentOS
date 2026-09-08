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
- Root Vercel configuration selects `syd1`, alongside the Supabase database in
  Sydney. See [Vercel region configuration](https://vercel.com/docs/functions/configuring-functions/region)
  and [region mapping](https://vercel.com/docs/regions).

No cross-user data cache, database credentials, model settings, evidence checks,
ingestion schedule or worker activation changed.

## Local verification

- Frontend: 35 tests passed; ESLint and production build/TypeScript passed.
- API: 55 focused tests passed (core API, catalog and deployment configuration).
- OpenAPI/JSON Schema contract validation passed.
- Delayed-sidebar browser: Home visible in 688 ms while the sidebar request was
  held for three seconds. Normal loading had no false error; failure/retry loaded
  history without a page reload. No browser JavaScript errors.
- Design detector: no findings in changed UI components.

## Hosted measurements

Baseline captured on Edge from this workspace against the production alias.
The same browser context navigated 16 routes; Home, chat and library were repeated
at the end. Ready time means the first main heading or chat textarea became
visible, not AI generation completion. These are individual observations, not a
statistical latency guarantee.

| Route | Before (seconds) | After (seconds) |
| --- | ---: | ---: |
| Home | 4.116 | Pending deployment |
| New AI chat | 23.986 | Pending deployment |
| FDA library | 23.535 | Pending deployment |
| Letter detail | 10.645 | Pending deployment |
| Trends | 22.875 | Pending deployment |
| Saved sources | 22.976 | Pending deployment |
| Control tower | 13.310 | Pending deployment |

Production baseline function headers showed `iad1`. Deployment region and final
measurements will be verified after publication. Raw timings and browser evidence
remain in ignored `.artifacts/performance-20260908/`; no session cookies or secrets
are included in the committed report.
