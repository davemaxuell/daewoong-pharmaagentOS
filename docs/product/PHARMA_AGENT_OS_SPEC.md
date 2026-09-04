# PharmaAgent OS product and MVP specification

- Status: implementation baseline
- Effective date: 2026-09-04
- Owners: Product/System Owner, Regulatory Intelligence, QA, Engineering, Security

## Authority and scope

This document is the repository-native product contract for PharmaAgent OS. The
terms **must**, **must not**, and **required** are release requirements. The
[agent intended-use statement](../assurance/agent-intended-use.md), [agent control
matrix](../assurance/agent-control-matrix.md), and existing deterministic Drug
corpus decision in [ADR 0002](../adr/0002-deterministic-drug-corpus-admission.md)
govern if another document is ambiguous.

PharmaAgent OS is a governed, case-based agent platform that converts external
pharmaceutical regulatory signals into evidence-backed internal review packages.
Its flagship workflow is:

> New or updated FDA Warning Letter → regulatory findings → potentially relevant
> internal assets → impact hypotheses → independent verification → human-approved
> decision-support report

It is not an autonomous compliance system. Official retained evidence is
authoritative; agent output is derived decision support.

## Product boundary

The existing FDA Drug Warning Letter Intelligence Platform remains the
**Regulatory Evidence capability**. Its deterministic Product: Drugs admission,
immutable document versions and hashes, source anchors, authorization-aware
retrieval, reviews, audit events, and background-job behavior must not be rebuilt
or bypassed.

PharmaAgent OS adds:

- a durable Case as the business, authorization, and audit boundary;
- exact source pins, typed and versioned plans, runs, and append-only case events;
- versioned agent, skill, workflow, model-policy, schema, and tool records;
- deny-by-default policy decisions and approvals bound to exact hashes;
- narrowly registered MCP tool adapters and lifecycle controls;
- specialist regulatory, knowledge, impact, and verification agents;
- evidence-backed impact hypotheses and immutable review artifacts;
- evaluation, trace, budget, suspension, and recovery controls.

Chat may exist inside a case, but chat history is not the system of record and is
never evidence by itself.

## First product MVP

For release planning, **MVP means Milestones 0 through 5**. Milestones 0 through 3
are enabling increments and must not be represented as the completed flagship
product.

### Included

- One workflow: FDA Warning Letter to Internal Impact Review.
- Manual creation or linking of a case from an admitted FDA Drug warning letter.
- An exact retained FDA document-version pin that never advances silently.
- A visible typed plan, plan revision, policy evaluation, and plan approval.
- A Case Orchestrator plus Regulatory Evidence, Internal Knowledge, Impact
  Analysis, and Verification agents with distinct tool allowlists.
- Read-only regulatory and internal-knowledge MCP adapters.
- A clearly marked synthetic internal pharmaceutical-quality corpus with
  revisions, anchors, relationships, and ACL fixtures.
- Case Workspace, Evidence Explorer, Impact review, and QA artifact review.
- Deterministic schema, identifier, hash, citation, and permission validation.
- No more than two automatic targeted correction loops.
- An immutable, versioned, non-GxP review report approved by a human QA Reviewer.
- Persisted events, invocations, policy decisions, approvals, versions, usage,
  validation results, and artifact provenance sufficient to reconstruct a run.
- Blocking regulatory, authorization, prompt-injection, and resilience
  evaluations, even though the full Evaluation Center UI is deferred.

### Excluded

- A declaration of GMP compliance, noncompliance, or a definitive internal gap.
- CAPA creation or approval, SOP revision, batch disposition, product
  release/rejection, regulatory submission, or equipment control.
- Any write to QMS, EDMS, MES, LIMS, or another controlled quality record.
- Use of real Daewoong internal quality documents in the portfolio MVP.
- External notifications, task creation, or other side effects.
- Automatic organization-wide memory or promotion of conversation text into
  approved knowledge.
- Arbitrary shell, SQL, browser, filesystem, database, or URL tools.
- A free-form agent swarm, recursive subagent creation, A2A interoperability, or a
  visual workflow builder.
- Temporal deployment, independent MCP microservices, and productized Control
  Tower/Evaluation Center views; these remain later hardening work.

Replacing synthetic content with company data, enabling a side effect, or making
an output a GxP record is a scope change and requires the reassessment defined in
the [agent intended-use statement](../assurance/agent-intended-use.md).

## Evidence trust model

| Level | Name | Meaning and permitted use |
| --- | --- | --- |
| A | Authoritative external evidence | Retained official FDA source version and anchor; may support regulatory facts |
| B | Controlled internal evidence | Authorized effective or retained internal document version and anchor; may support internal facts after ACL enforcement |
| C | User-provided context | Unverified context; must be labeled and cannot replace retained evidence |
| D | AI-derived content | Finding, summary, mapping, hypothesis, or recommendation; never primary evidence |
| E | Model working state | Ephemeral reasoning/context; never evidence and never shown or stored as chain-of-thought |

Every material claim must resolve to one or more accessible retained anchors. An
AI summary must not be used as the primary citation when its source exists.
Internal citations must include document ID, revision, effective date, and
section. A source update marks dependent cases and artifacts potentially stale
without changing their pins.

## Flagship workflow contract

| Stage | Required persisted output | Blocking control |
| --- | --- | --- |
| Admit signal | Source version and deterministic scope decision | Only canonical Product: Drugs evidence is admitted |
| Create case | Case, objective, owner, and exact CaseSource pin | Idempotency and no silent version switch |
| Plan | Immutable plan version and normalized plan hash | Strict schema, limits, prohibited-action check |
| Authorize | Policy decision and, when required, human approval | Approval bound to plan hash, versions, scope, and approver |
| Extract | Structured regulatory findings and source anchors | Read-only public tools; citation and schema validation |
| Retrieve | Authorized internal candidates with exact revisions | ACL before retrieval/model access; minimal blocked response |
| Analyze | Versioned impact hypotheses | Fact, hypothesis, assumption, unknown, and counterevidence separated |
| Verify | Independent verification report | Unsupported or overstated content blocks composition |
| Compose | Deterministically assembled draft revision | Validated structured records only |
| Review | Attributable QA decision and reason | Human ownership and stale-write conflict |
| Publish | Immutable approved report revision | Complete provenance and audit trail |

The workflow must fail safely:

- an updated source leaves the current run on its original pin and marks the case
  stale;
- insufficient evidence yields INCOMPLETE_EVIDENCE and open questions, not an
  invented relationship;
- denied access yields a minimal ACCESS_BLOCKED observation without protected
  titles or content;
- transient tool failures receive bounded retry, while uncertain side effects are
  never retried automatically;
- detected instructions in untrusted content are isolated, labeled, and recorded
  as a security event;
- exceeded budgets pause or stop the run with completed work preserved.

## Core product requirements

| ID | Requirement |
| --- | --- |
| PAOS-001 | Every execution belongs to one Case and one Run; a case may contain multiple runs |
| PAOS-002 | Every CaseSource pins an exact retained document version and source hash |
| PAOS-003 | Only an approved immutable plan hash may execute; changed inputs invalidate approval |
| PAOS-004 | The runtime calculates permissions from user, case, agent version, tool version, data scope, and action risk; model text cannot grant permission |
| PAOS-005 | Every agent and tool invocation records identity, versions, hashes, policy result, status, latency, usage, and error class |
| PAOS-006 | Regulatory findings and material report claims require resolvable retained evidence anchors |
| PAOS-007 | Internal ACL filtering occurs before ranking, prompt construction, or model access |
| PAOS-008 | Impact output distinguishes evidence, derived hypothesis, assumption, counterevidence, missing information, and confidence |
| PAOS-009 | Verification receives only the bounded evidence and candidate output needed to challenge the result and may block it |
| PAOS-010 | Corrections create new revisions and are bounded; history is not overwritten |
| PAOS-011 | Approved artifacts are immutable and reproducible from structured records and exact versions |
| PAOS-012 | Refresh, restart, retry, or worker failure cannot lose committed steps or duplicate an action |
| PAOS-013 | Limits exist for turns, tool calls, parallel agents, correction loops, runtime, tokens, and cost |
| PAOS-014 | Global, workflow, agent, and tool suspension is checked before start and resume |
| PAOS-015 | The platform never autonomously creates a CAPA or declares compliance status |

## Roles and human ownership

The minimum roles are Viewer, Regulatory Analyst, QA Reviewer, Domain SME,
Auditor, Agent Developer, Platform Administrator, and System Owner. Authorization
is enforced by the API/runtime, not by portal visibility.

Platform Administrators operate infrastructure and policy but cannot approve
regulatory content by default. Agent Developers cannot promote their own
production version. Only qualified human reviewers make internal relationship and
artifact decisions. Detailed authorities and separation rules are defined in the
[agent control matrix](../assurance/agent-control-matrix.md).

## MVP acceptance gate

The MVP is not releasable until all of the following are demonstrated:

1. Existing FDA platform tests and deterministic Drug-scope fixtures remain green.
2. A case pins and displays an exact source version and full append-only history.
3. A user can revise, approve, or reject a typed plan, and a stale approval cannot
   execute.
4. Specialist agents can access only their registered tools and authorized data.
5. Every regulatory finding and accepted relationship resolves to retained
   evidence; inaccessible content never reaches a model.
6. Seeded unsupported claims, prohibited conclusions, and known indirect prompt
   injections are blocked.
7. A final artifact requires QA review, is immutable after approval, and remains
   visibly labeled as decision support.
8. Restart and retry tests preserve state and create no duplicate action.
9. Critical authorization, approval-bypass, source-integrity, or injection
   failures are zero.
10. Synthetic records are unmistakably fictional and separated from company data.

## Related design records

- [Agent-platform architecture](../architecture/agent-platform.md)
- [Agent intended use](../assurance/agent-intended-use.md)
- [Agent control matrix](../assurance/agent-control-matrix.md)
- [Agent-platform threat-model delta](../threat-model/agent-platform-delta.md)
- [ADR 0003: modular monolith and MCP adapters](../adr/0003-agent-platform-modular-monolith-and-mcp-adapters.md)

