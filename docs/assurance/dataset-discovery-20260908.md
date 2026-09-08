# Supplied FDA dataset — 2026-09-08

The owner supplied `data.sql` in the PharmaAgent OS workspace. It is a
31,194,535-byte PostgreSQL data-only export, despite the accompanying "Dumped
schema" message. It contains COPY data and no CREATE TABLE/SCHEMA/EXTENSION
statements. The original file is preserved and `/data.sql` is now Git-ignored.
It also contains prior chat records and subscriptions; do not publish the dump.

## Confirmed location and inventory

The workspace's linked Supabase project is now `uwgzvobkblrnmqwroegh`, named
`supabase-daewoong`. Read-only queries against that project returned the same
counts as the supplied export:

| Records | Count |
| --- | ---: |
| Warning letters | 884 |
| Document versions | 884 |
| Searchable document chunks | 4,298 |
| Storage object metadata | 444 |

The dump also contains 886 document records, 16 AI summaries, 3 translations,
53 violations/findings, 33 chat threads and 84 chat messages. Letter scope is
444 `IN_SCOPE_DRUGS`, 419 `OUT_OF_SCOPE`, and 21 `AMBIGUOUS`. Preserve the scope
filters; the total 884 is not the count of eligible drug letters.

Earlier empty-database observations concerned `wdaflyddglimtijvgazl` and
`yuzksuqknxuyjutqwyqr`, not this newly identified populated source project.

## Compatibility and remaining work

- All 21 exported application tables have the same column names as the current
  ORM definitions. COPY row widths passed inspection, and declared foreign-key
  references between exported tables had no missing targets. This is static
  inspection, not a restore or deployed integration test.
- The current service defines 57 application tables. The 36 Agent OS tables are
  absent from the export and still require the established migration sequence.
- All 444 unique non-null raw-object keys have matching metadata in the
  `fda-evidence` bucket. SQL contains metadata rather than object bytes. A move
  to another project requires separate file transfer and hash verification.
  File downloadability and hashes have not yet been tested.
- Select the target before running migrations or changing hosted credentials:
  use the existing `uwgzvobkblrnmqwroegh` project, or copy the FDA dataset into
  the previously supplied `wdaflyddglimtijvgazl` project. The question is pending.
  Do not treat the local link as authorization to modify another running service.
- Once selected, apply the appropriate schema additions, provision distinct
  API/worker runtime logins and Storage access, and configure the PharmaAgent OS
  Vercel project. Validate actual reads, citation retrieval, object integrity and
  AI calls through the hosted app before declaring the data connection complete.

No dump SQL, remote migration, cloud data import or Vercel configuration change
was performed during this inspection. Existing user-created root package files
and `supabase/config.toml` were left intact.

Ignored machine-readable inspection evidence is in
`.artifacts/database-import-20260908/`: `dump-inventory.json`,
`compatibility.json`, `source-metadata.json`, and `source-counts.json`.
