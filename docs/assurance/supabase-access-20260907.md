# Supabase access verification — 2026-09-07

The owner supplied `https://wdaflyddglimtijvgazl.supabase.co` and a publishable
API key. The key is not reproduced here and is not a backend database credential.

The authenticated Supabase CLI successfully listed the project and queried its
schema through `db query --linked --project-ref wdaflyddglimtijvgazl`.
The project is named **Daewoong FDA**, reports `ACTIVE_HEALTHY`, and is located in
`ap-southeast-2`. Metadata inspection returned no application tables in
`pg_stat_user_tables` after excluding Supabase-managed schemas. A second query
confirmed `current_database() = postgres`, `current_user = postgres`, and zero
tables in the `public` schema. This verifies management/query access; it does not
establish that an FDA dataset has been loaded.

No application migration, data import, runtime grant, bucket creation, or Vercel
environment change was applied in this verification. The project's name conflicts
with the deployment handoff's assumption of a separate FDA service and a dedicated
PharmaAgent OS database. The owner was asked whether to use this database for both
services or read FDA data while keeping PharmaAgent OS tables in a separate project.
That destination choice remains pending. Do not substitute the supplied publishable
key for `SUPABASE_SECRET_KEY`, `DATABASE_URL`, or `WORKER_DATABASE_URL`.

The deployment and frontend remain at commit `c03b966`; live backend setup remains
incomplete. Once the database destination is resolved, follow the authoritative
migration order and verify actual runtime-role connectivity before deployment.
