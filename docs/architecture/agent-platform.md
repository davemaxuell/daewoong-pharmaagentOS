# PharmaAgent OS agent-platform architecture

- Status: implemented reference architecture (Milestones 0–8)
- Effective date: 2026-09-04
- Owners: Architecture, Engineering, Platform, Security, QA

## Scope

This design extends the existing [logical architecture](logical-architecture.md).
It does not replace the current API, scheduler, worker, database, object store,
deterministic FDA scope gate, or authorization boundary. The accepted deployment
decision remains [ADR 0001](../adr/0001-modular-monolith-and-process-boundaries.md);
the agent-specific extension is [ADR 0003](../adr/0003-agent-platform-modular-monolith-and-mcp-adapters.md).

## Logical planes

| Plane | Responsibilities | MVP realization |
| --- | --- | --- |
| Experience | Case Workspace, evidence, impact review, trace, QA review | Existing Next.js portal with additive case routes |
| Control | Registries, versions, policy, approvals, limits, model routing | FastAPI modules and immutable PostgreSQL records |
| Workflow | Case state, plan execution, pause/resume/cancel, retries | PostgreSQL ledger, bounded LangGraph graph, optional Temporal outer workflow |
| Agent runtime | Orchestrator and bounded specialist invocations | Separately identified API and Temporal worker workloads |
| Tool and data | MCP gateway/adapters, FDA evidence, synthetic knowledge, object storage | Three versioned private MCP servers over existing domain services |
| Assurance | Audit, trace, validation, evals, security events, usage | Append-only events, immutable trials/artifacts, OpenTelemetry, and Control Tower |

PostgreSQL is the authoritative store for business and workflow state. Versioned
object storage remains authoritative for raw source bytes. Git-controlled YAML and
Markdown are the authoring source for agent, workflow, skill, and tool definitions;
the runtime loads only validated, immutable deployment versions recorded in the
database.

## Baseline reuse map

Milestone 0 freezes the existing FDA application as the Regulatory Evidence
Service. Agent features extend these components; they do not fork their data or
replace their controls.

| Existing component | Reused capability | Agent-platform rule |
| --- | --- | --- |
| `WarningLetter`, `Document`, `DocumentVersion` | Official FDA identity, retained versions, hashes, and provenance | `CaseSource` references one exact `DocumentVersion`; source content is never copied into an agent-owned source table |
| `DocumentChunk` and parser source anchors | Bounded evidence retrieval and resolvable citations | Regulatory tools may return only case-pinned versions and retained anchors |
| `ScopeDecision` and deterministic scope fields | Product=Drugs admission control | Agent planning cannot broaden or override source scope |
| `Finding`, taxonomy, and review records | Controlled vocabulary and existing reviewed extraction history | New agent output uses a versioned result contract and remains distinct from reviewed production findings until accepted |
| `discovery.py`, `fda_client.py`, `ingestion.py`, `parsing.py` | Acquisition, normalization, hashing, and version creation | MCP adapters read retained results; they do not fetch arbitrary URLs or run a second ingestion path |
| `embedding_store.py` and `rag_planner.py` | Authorized retrieval over retained public evidence | Retrieval remains subordinate to deterministic filters and cannot establish authorization |
| `storage.py` | Versioned raw-source object storage | Agent records retain object/version provenance, never credentials or mutable aliases |
| `worker.py` and the database job lease | Initial queue, retry, recovery, and dead-letter mechanics | Milestones 1–2 use bounded jobs and persisted state; no human wait is held in worker memory |
| `audit.py` and request middleware | Attributable request and operation history | Agent/tool events add version, case, run, policy, hash, latency, and provenance metadata without storing hidden reasoning |
| Auth dependencies and server-side Drug filters | Human identity, roles, and row/scope enforcement | Model arguments never supply identity, role, membership, or source authorization |

The frozen baseline is the repository commit that predates the Agent OS patch
set. A release tag must be created only from a clean, reviewed tree so it cannot
misrepresent unrelated uncommitted work as the baseline.

## Case-first execution

~~~mermaid
flowchart LR
  U[Authorized user] --> W[Next.js Case Workspace]
  W --> A[FastAPI case and control plane]
  A --> P[Policy and approval service]
  A --> Q[Database-backed job queue]
  Q --> T[Temporal outer workflow]
  T --> R[Bounded LangGraph runtime]
  R --> G[Private MCP gateway and lifecycle hooks]
  G --> F[Regulatory adapter]
  G --> K[Synthetic knowledge adapter]
  G --> O[Draft-only integration outbox]
  F --> D[(PostgreSQL and retained FDA evidence)]
  K --> D
  R --> V[Deterministic validators and artifact composer]
  A --> E[(Case events, invocations, approvals, artifacts)]
~~~

Every run is subordinate to one case, one immutable plan version, and explicit
source pins. The runtime receives a minimal context packet rather than an entire
conversation. Case state, approval state, source pins, evidence, and completed
steps live outside prompts.

## Execution and control sequence

1. The API authenticates the human, resolves case membership and current role
   grants, and loads exact source pins.
2. The control plane resolves immutable workflow, agent, skill, tool, schema,
   prompt, and model-policy versions.
3. Deterministic policy classifies data and action risk, checks suspension and
   budgets, and determines required approval.
4. The approved plan is enqueued with its hash and a canonical idempotency key.
5. Before each agent or tool call, the host recalculates authorization; no
   identity, permission, approval, or idempotency field is accepted from model
   output.
6. The MCP gateway exposes only the current agent's allowlisted tool manifests.
7. Tool output is schema-validated, size-bounded, sanitized, trust-labeled,
   source-attributed, hashed, and persisted before it enters model context.
8. Deterministic validators gate each specialist result. Invalid output can
   receive a bounded targeted retry; it cannot advance silently.
9. The artifact composer uses validated structured records, never free-form hidden
   model state.
10. A qualified human reviews the artifact, and publication creates an immutable
    revision plus an append-only event.

The complete hook contract is:

| Hook | Required host behavior |
| --- | --- |
| SessionStart | Load identity, case, ACL, pins, approved versions, policy, and budgets |
| PrePlan / PostPlan | Classify intended use and risk; validate schema, limits, prohibited actions, and approval need |
| PreAgentInvoke | Check version status and minimize the specialist context |
| PreToolUse | Authenticate, authorize, validate arguments, verify pin/approval, enforce limits, and issue idempotency key |
| PostToolUse | Validate/sanitize, attach provenance and trust, hash, persist, meter, and return a structured observation |
| PreHandoff | Pass only typed records and necessary evidence |
| PostAgentResult | Validate schema, citations, boundary language, and revision |
| BeforeArtifact | Require evidence for every material claim |
| ApprovalRequested / Resume | Persist state; bind and then revalidate approval, versions, freshness, policy, and budgets |
| Stop / OnFailure | Persist outcome and usage; classify retry versus escalation; prevent duplicate effects |

## Staged durability decision

The orchestration path is deliberately **database queue → LangGraph → Temporal**.
Each stage retains PostgreSQL case records and append-only events as the product
system of record.

### Stage A — existing database-backed queue

Use for Milestones 1 and 2:

- execute deterministic case operations and bounded single-agent regulatory jobs;
- store a step intent before enqueue and an idempotent completion after success;
- represent waits as persisted case states, not a worker blocked on a human;
- resume through a new authorized job after revalidating state;
- retain existing lease, claim, recovery, retry, and dead-letter behavior.

This stage must not simulate a durable multi-day in-memory workflow.

Exit to Stage B only when the case, plan, event, invocation, approval, and
checkpoint contracts are migration-tested and the Regulatory Evidence Agent meets
its release gate.

### Stage B — LangGraph inside the existing worker

Introduce in Milestone 3 for:

- explicit typed agent state and deterministic/model-driven nodes;
- conditional routing and bounded specialist invocation;
- checkpoints, human interrupts, pause/resume/cancel, and event streaming;
- bounded correction loops and preserved completed-step results.

The graph executes only an approved plan hash. Checkpoints contain identifiers and
typed state, not credentials or unbounded prompt transcripts. On resume the host
rechecks source freshness, versions, approval validity, policy, suspension, and
budgets.

Exit to Stage C only when graph/workflow contracts are stable, crash/resume tests
are reliable, multi-day waits or independent scaling are demonstrated needs, and
all activities have deterministic idempotency/reconciliation semantics.

### Stage C — Temporal as the outer workflow (implemented)

Introduced in Milestone 7. Temporal owns durable timers, approval signals,
schedules, retry/backoff, queue isolation, deployment-spanning waits, and activity
recovery. LangGraph remains the bounded inner specialist graph.

~~~text
Temporal workflow
├── generate and authorize plan activity
├── wait for plan-approval signal
├── execute bounded LangGraph activity
├── wait for artifact-review signal
└── publish immutable artifact activity
~~~

Temporal history is orchestration evidence, not the product audit record.
Business transitions must still create case events transactionally. Workflow code
must be deterministic, and non-idempotent or uncertain actions require explicit
reconciliation rather than automatic retry.

## MCP and controlled interoperability boundary

MCP is agent-to-tool communication, not an authorization system. In the implemented reference deployment:

- adapters and domain services remain in this repository;
- adapters may run in-process for tests or in the private MCP workload, but every call passes
  through the same host policy and hook pipeline;
- tools are narrow, read-only, versioned, schema-constrained, and allowlisted per
  immutable agent version;
- host-derived identity, case, source pin, approval, risk, and idempotency metadata
  are injected outside model-controlled arguments;
- adapters use domain service interfaces and never grant arbitrary database,
  filesystem, browser, URL, SQL, or shell access;
- tool discovery is filtered before the model sees it;
- structured denial and failure observations reveal no unauthorized resource
  names or content.

Milestone 8 adds one answer-only A2A endpoint for case status and approved-artifact
metadata. It authenticates a short-lived audience-bound service identity, rechecks
the delegated user's case access, performs no tool delegation, and cannot create or
modify controlled records. Email, collaboration, Notion, and task integrations stop
at immutable drafts; no delivery credential or send transition exists.

## Durability and failure invariants

- Commit intent before dispatch and commit result before marking a step complete.
- Use one canonical request fingerprint and idempotency key per logical operation.
- Never hold a database transaction open across a model, tool, or human wait.
- A retry may reuse a committed read result but cannot overwrite history.
- A changed source never alters an in-flight pin; it emits a stale event.
- A changed plan, source set, agent/tool version, scope, policy, or expired
  approval blocks resume until re-evaluated.
- Cancellation is cooperative and persisted; completed evidence remains visible.
- A transient read may retry within policy. An uncertain side effect pauses for
  reconciliation.
- Provider chain-of-thought is never requested, persisted, or exposed; the trace
  contains observable inputs, outputs, actions, validations, and decisions.

## Deployment and extraction rule

The API, scheduler, Temporal worker, backup job, and private MCP service retain
distinct runtime identities and egress
despite sharing code. An MCP adapter or workflow component may become an
independent service only when its interface has a versioned conformance suite,
authorization and identity are preserved over the new boundary, and measured
security, ownership, availability, or scaling needs outweigh the operational
cost. The extraction criteria are normative in
[ADR 0003](../adr/0003-agent-platform-modular-monolith-and-mcp-adapters.md).

## Related controls

- [Product and MVP specification](../product/PHARMA_AGENT_OS_SPEC.md)
- [Agent control matrix](../assurance/agent-control-matrix.md)
- [Agent-platform threat-model delta](../threat-model/agent-platform-delta.md)
