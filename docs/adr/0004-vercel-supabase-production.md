# 0004: Prepare production for Vercel and Supabase

Date: 2026-09-07. Status: selected platform; implementation under qualification.

The service owner selected production on Vercel/Supabase. Preserve the source
implementation plan and its release controls while adapting the infrastructure.

Use Vercel Services for web, private API, and bounded worker HTTP requests.
Supabase provides PostgreSQL/pgvector, private evidence Storage, and Cron/Vault
triggers. Reuse the existing database queue and recovery protocol. Temporal remains
an optional alternative requiring a separately hosted worker and mTLS; it is disabled
in this deployment template. Continuously polling workers cannot be assumed to run
inside a request-scoped function.

Accept deployment-scoped Vercel Secret injection through an explicit provider,
alongside the existing AWS provider. Platform metadata catches accidental selection;
it does not attest dashboard secret visibility or workload identity. Qualify secret
scope, rotation, access and redaction on the target. Services in one project share
a trust boundary; distinct runtime database URLs do not isolate all environment
secrets from the other services.

Preserve atomic job claiming and monotonically increasing attempt fencing. Refund
cooperative time slices through the retry allowance, not a decrement of the claim
counter. Recover hard termination through the existing lease. Scheduled requests
drain existing jobs; automatic source-job creation requires separate qualification.

Block direct Supabase browser-role access to application tables. RLS policies allow
the existing backend group roles to exercise only their grants; application ACLs
remain mandatory. Storage immutability is application-enforced and requires separately
qualified administrative controls and backup; it is not a WORM guarantee.

This decision does not waive independent specialist execution/evaluation, intended
use, release ownership, security, restore, or hosted recovery evidence. Vercel
Services and pg_net maturity, function limits, exact private Host behavior, secret
isolation and workload duration must be assessed on the actual dedicated projects.
See the [production runbook](../../infra/deployment/vercel/README.md) for configuration,
remaining activation inputs, verification, and official platform references.
