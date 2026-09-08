# FDA dataset copied to PharmaAgent OS — 2026-09-08

The owner approved copying the discovered dataset into `wdaflyddglimtijvgazl`.
The source project `uwgzvobkblrnmqwroegh` and the original `data.sql` were preserved.

## Completed copy

- Created all 57 application tables using the current ORM and established migration
  order. On Supabase, migration and runtime search paths include `extensions`,
  where the existing pgcrypto functions live.
- Imported all 21 public application tables in one transaction, preserving IDs,
  provenance, historical summaries/reviews and owner-scoped chat records. Every
  imported table count matched the dump. Supabase Auth/Storage system tables were
  not restored from SQL.
- Copied all 444 referenced raw files into the destination's private
  `pharma-evidence` bucket, preserving object keys. Each source download and each
  destination read matched the expected SHA-256. Total bytes: 20,454,044.
- Created distinct API and worker logins inheriting their existing runtime groups.
  Neither is a database owner, superuser, role creator or BYPASSRLS identity.
  Both transaction-pooler connections successfully read 884 letters.
- Applied the explicit RLS and Data API boundary to all 57 application tables.
  A real anonymous Data API read was denied (401), and a public object read was
  denied (400). The evidence bucket remains private.

| Data | Copied rows |
| --- | ---: |
| Warning letters | 884 |
| In-scope drug letters | 444 |
| Documents | 886 |
| Document versions | 884 |
| Searchable chunks | 4,298 |
| AI summaries | 16 |
| Translations | 3 |
| Findings | 53 |
| Chat threads / messages | 33 / 84 |

## Hosting configuration

Production Vercel configuration now points to the destination. Database URLs and
the Supabase server key are Vercel Secrets. Preview is not connected to production
data. OpenAI generation remains configured; ingestion workers, automatic delivery,
and specialist case execution were not enabled by copying the dataset.

Added an explicit `TELEMETRY_BACKEND=vercel_logs` mode for managed Vercel runtimes.
It records bounded route-template, status, duration and completion metadata to
Vercel runtime logs. It excludes request payloads, headers, URL parameters, query
strings and exception contents. Default OTLP behavior and non-Vercel production
requirements remain intact. This provides platform request logging, not a claim
of separately configured OTLP tracing or long-term audit retention.

Configuration/observability/deployment tests: 41 passed. Ruff and frontend lint
passed. GitHub quality/security workflows passed for application revision `5f10d96`.

Hosted readiness now returns HTTP 200 with both database and object store `ok`.
Vercel's private API hostname was observed in request logs and explicitly admitted:
`api.5152766237785039716d674a6c30346545716449486431477a686538.services.vercel-infra.com`.
Private letter-list, chat-list and saved-view requests returned 200. The library
page's earlier 3.5-second timeout expired before a successful 6.5-second hosted
response; the general read deadline is now 15 seconds.

Final hosted verification on revision `7956f26` passed:

- The live library displayed 440 active drug letters and opened the Safrel letter
  with its original text and findings. The other four in-scope records are already
  marked `retired_illustrative_fixture` in the source and remain excluded.
- The browser submitted a Korean question scoped to that letter. The stored
  assistant response completed with 838 characters and six citations; metadata
  confirmed OpenAI `gpt-5-mini`, `generation_used=true`, and no model fallback.
  The rendered answer and source panel were captured. This created verification
  chat records under isolated anonymous browser sessions after the baseline copy.
- GitHub quality and code-security workflows passed for the final code revision.
- `/health/live` and `/health/ready` returned 200; readiness confirmed both database
  and object-store access. A separate local ASGI read check also returned 200 for
  letter listing and detail using the real target runtime account.

The home review-request form still saves local drafts. Copying this dataset does
not implement the unfinished specialist execution adapters or enable scheduled
FDA ingestion, automatic notification delivery, or full case-agent execution.

## Evidence and handling

Ignored evidence under `.artifacts/database-import-20260908/` includes the database
copy counts, per-file hashes, runtime-account verification, boundary results and
Vercel provisioning results. The raw dump and cached source files remain local.
Temporary credential files were removed after hosted verification. An exact-value
scan found no copied API key, runtime password or database URL in tracked or
unignored files. Credentials remain in the approved hosted secret stores.

References: [Vercel runtime logs](https://vercel.com/docs/logs/runtime),
[structured application logging](https://vercel.com/kb/guide/add-structured-application-logs-to-vercel-functions).
