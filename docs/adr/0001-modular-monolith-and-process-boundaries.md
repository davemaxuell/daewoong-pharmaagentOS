# ADR 0001: Modular monolith with isolated process roles

- Status: accepted for the starter implementation
- Date: 2026-08-29
- Owners: Product/System Owner, Engineering, Platform, Security

## Context

The service needs deterministic FDA discovery/parsing, an authenticated API, a portal, durable background processing, AI extraction, retrieval, and notifications. Splitting every stage into a network service would increase deployment, authorization, and observability complexity before workload measurements justify it.

## Decision

Use one versioned Python codebase with separately deployed API, scheduler, and worker process roles, plus one Next.js portal. PostgreSQL is the authoritative transactional store and contains FTS/pgvector metadata in the same authorization boundary. Raw evidence uses private versioned S3-compatible storage. Background work uses an approved durable queue; Redis is only the local development implementation.

Keep runtime identities and network access distinct even when process roles share an image:

- API: authenticated business endpoints, backend authorization, audit; no FDA acquisition or arbitrary egress.
- Scheduler: leader-elected creation of bounded/idempotent jobs; no user-facing ingress.
- Worker: constrained FDA/AI/notification egress and only the data privileges required for its job class.
- Web: server-rendered portal calling the internal API; no direct database/object/queue access.

## Consequences

Deployment remains small while code boundaries, queue contracts, audit events, and identities allow later extraction of a measured bottleneck. Production must not collapse the separate workload identities or widen worker egress merely because code is shared. A service split requires an architecture/security review and evidence that the added boundary solves an observed problem.

