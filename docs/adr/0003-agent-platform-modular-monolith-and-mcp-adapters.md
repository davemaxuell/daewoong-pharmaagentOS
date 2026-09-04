# ADR 0003: Keep the agent platform modular with MCP adapters until interfaces stabilize

- Status: accepted for implementation
- Date: 2026-09-04
- Owners: Architecture, Engineering, Platform, Security, QA

## Context

[ADR 0001](0001-modular-monolith-and-process-boundaries.md) established one
versioned Python codebase with separate API, scheduler, and worker process roles.
PharmaAgent OS adds cases, registries, policy, approvals, workflow state,
specialist agents, tool adapters, evaluations, and traces. Prematurely extracting
each MCP server or agent into a separately deployed service would add network
identity, authorization, release, failure, and observability boundaries before
the contracts and workload are measured.

MCP standardizes agent-to-tool messages, but it does not supply business
authorization, approval, source pinning, data ACLs, idempotency, or evidence
integrity. A network boundary alone would not provide those controls.

## Decision

Extend the existing modular monolith and retain the current API, scheduler, worker,
PostgreSQL, and object-store boundaries.

1. Add case/control-plane, runtime, policy, approval, artifact, evaluation, and
   observability modules to the existing Python service.
2. Keep regulatory and synthetic-knowledge domain logic behind ordinary typed
   application-service interfaces.
3. Place versioned MCP manifests and adapters over those interfaces. All adapter
   calls, including local calls, pass through the same registry, PreToolUse policy,
   PostToolUse validation, audit, limit, and suspension pipeline.
4. Keep MCP adapters in this repository for the MVP. They may run in-process for
   tests or as separately identified process roles when isolation is required,
   without becoming independent products or repositories.
5. Keep specialist agents inside one trusted, bounded runtime. Do not introduce
   A2A until agents have independent ownership and deployment needs.
6. Use the existing database-backed queue for bounded early work, add LangGraph as
   the inner graph after control-plane contracts are stable, and add Temporal as
   the outer durable workflow only after the extraction criteria below are met.
7. Store Git-authored definitions as immutable validated database deployment
   versions. Running code resolves pinned versions; it never loads mutable working
   files as production configuration.

The [agent-platform architecture](../architecture/agent-platform.md) defines the
runtime sequence and staged orchestration in detail.

## Boundary rules

- MCP is a transport/adapter boundary, not a permission boundary.
- The host derives user, case, plan, source pins, approvals, risk, and idempotency;
  the model cannot provide or override them.
- An adapter cannot expose arbitrary SQL, database, filesystem, shell, browser, or
  URL access.
- Local adapters cannot bypass gateway controls by importing a repository or
  database layer directly from agent code.
- API, scheduler, and worker identities and egress remain separate even when they
  share an image.
- Business history belongs in append-only product records, not only worker,
  LangGraph, MCP, or future Temporal logs.

## Extraction criteria

Extract an MCP adapter or workflow component into an independent deployable
service only when all of these are true:

1. Its versioned input/output/error contracts and compatibility policy are stable
   and covered by provider/consumer conformance tests.
2. Measured throughput, latency, availability, security isolation, data
   residency, or independent-team ownership requires a separate boundary.
3. End-user, runtime, agent, and tool identities can be propagated without a
   shared all-powerful token.
4. Deny-by-default authorization, ACL-before-retrieval, source pinning, approval,
   idempotency, rate limit, kill switch, and audit semantics remain equivalent.
5. Timeouts, retries, circuit breaking, reconciliation, rollout, rollback, and
   dependency failure modes have automated tests and named operators.
6. Secrets, egress, telemetry, backup/recovery, and incident response exist for
   the new boundary.
7. An architecture/security review records why the operational cost is justified.

Move the outer workflow to Temporal only when multi-day waits, deployment-spanning
resume, distributed queue isolation, or independent activity scaling is a
demonstrated requirement and all activities are idempotent or explicitly
reconcilable.

## Consequences

Positive:

- the team reuses the evidence, authorization, review, audit, and queue behavior
  already tested in the FDA platform;
- contracts can evolve atomically while the flagship workflow is measured;
- local and remote tool transports share one conformance and policy path;
- deployment remains small while runtime identities and process isolation remain
  explicit;
- later service extraction is driven by evidence and stable interfaces.

Costs and risks:

- module boundaries require review and tests because the language runtime does not
  enforce a network boundary;
- a shared database can tempt direct cross-module access;
- long-running human waits need explicit persisted states before Temporal;
- local MCP calls can be mistaken for trusted calls.

Mitigations are typed service interfaces, dependency rules, contract tests,
separate process identities, database privilege separation where practical, and
mandatory gateway/hook enforcement for every agent-visible tool.

## Rejected alternatives

- **One microservice per agent/tool now:** rejected because contracts, scaling, and
  ownership are not stable enough to justify the new failure and trust boundaries.
- **A single unrestricted agent with direct database access:** rejected because it
  defeats least privilege, source pinning, policy, and auditable tool selection.
- **Temporal from the first control-plane migration:** rejected because existing
  queue behavior is sufficient for bounded early work and activity contracts are
  not yet stable.
- **No MCP contract until later:** rejected because versioned narrow tool schemas
  are useful now even when their first adapter is local.

## Implementation amendment — Milestones 7 and 8

The staged extraction criteria were met for two narrowly bounded deployment roles:

- Temporal now wraps the database-authoritative LangGraph run loop. Activities use
  an exactly-once database journal, and the database queue remains the safe fallback.
- The three reviewed MCP bundles can run behind one private, service-authenticated
  gateway with dedicated workload identity and network policy.
- A2A is enabled only as an answer-only interoperability projection for case status
  and approved-artifact metadata. It does not delegate agents or tools and cannot
  write controlled records.

This amendment does not authorize a tool-per-microservice topology, arbitrary A2A
delegation, or direct writes to quality systems. The original authorization,
evidence, audit, idempotency, and extraction rules remain normative.
