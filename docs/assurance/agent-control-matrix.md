# PharmaAgent OS agent control matrix

- Status: implementation baseline
- Effective date: 2026-09-04
- Owners: System Owner, QA, Security, Platform

## Enforcement rule

Authorization is deny-by-default and server-side. A model can request a capability
but cannot grant identity, scope, approval, budget, risk class, idempotency, or
tool access. Frontend visibility and prompt instructions are not controls.

The runtime calculates effective permission as the intersection of:

~~~text
active user grant
∩ case membership and scope
∩ approved plan
∩ immutable agent-version allowlist
∩ active tool/version policy
∩ data classification and record ACL
∩ action-risk policy
∩ unexpired approval
∩ runtime limits and suspension state
~~~

Any missing or contradictory input denies the operation and creates an
attributable policy decision.

## Action risk classes

| Class | Example | Required control | MVP disposition |
| --- | --- | --- | --- |
| R0 | Read pinned public FDA metadata or evidence | Authenticated case context, admitted Drug source, agent/tool allowlist, source pin | Automatically allowed after deterministic checks |
| R1 | Read an authorized internal document | Approved plan, user ACL before retrieval, case/data scope, knowledge-agent allowlist | Allowed for the synthetic corpus only |
| R2 | Generate a non-GxP draft or impact hypothesis | Approved plan, validated evidence, intended-use guard, immutable draft revision, QA artifact review before approval | Allowed |
| R3 | Create a task or send an internal notification | Separate explicit action approval, destination allowlist, minimum data, idempotency, delivery audit | Out of MVP; deny |
| R4 | Modify QMS/EDMS/MES/LIMS content, controlled documents, CAPA, batch disposition, submission, or equipment | Prohibited; no runtime approval path | Always deny |

Splitting an action into smaller calls does not lower its class. Exporting a draft
does not authorize its use as a controlled record. R4 cannot be enabled by a
Platform Administrator, prompt, plan, or emergency override; it requires an
approved intended-use and architecture scope change.

## Human and service authority

Legend: **Initiate** requests work; **Decide** makes the named content decision;
**Operate** manages technical configuration; **Inspect** is read-only. Blank means
no authority.

| Capability | Viewer | Regulatory Analyst | Domain SME | QA Reviewer | Auditor | Agent Developer | Platform Administrator | System Owner |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Read approved regulatory artifact | Inspect | Inspect | Inspect | Inspect | Inspect |  | Operate metadata only | Inspect |
| Create case / propose plan |  | Initiate | Initiate within assigned case | Initiate |  |  |  | Initiate |
| Approve R0/R1 case plan |  | Decide within grant | Decide within assigned domain | Decide |  |  |  | Decide |
| Decide internal relationship |  | Propose | Decide | Decide |  |  |  | Decide |
| Approve final artifact |  |  | Recommend | Decide |  |  |  | Decide if qualified/designated |
| Inspect complete audit/version history |  | Inspect own/assigned | Inspect assigned | Inspect | Inspect | Development only | Operate without content approval | Inspect |
| Author agent/skill/tool/workflow definition |  |  |  |  |  | Initiate | Operate infrastructure |  |
| Promote production agent version |  |  |  | Quality evidence review | Inspect evidence | Propose only | Deploy approved version only | Decide |
| Change runtime policy or suspend component |  |  |  |  |  |  | Propose | Operate | Decide policy/risk acceptance |
| Approve R3 side effect |  | Designated business owner only | Designated owner only | Decide content if designated |  |  | Cannot self-approve | Decide |
| Authorize R4 action |  |  |  |  |  |  |  |  |

Corporate identity and training records determine which named people receive each
role. A service account, model, agent, worker, or integration can never be a human
approver.

## Required separation of duties

1. **Content versus platform:** Platform Administrators can deploy, suspend, and
   operate approved components but cannot approve regulatory findings,
   relationships, or artifacts by virtue of that role.
2. **Development versus release:** Agent Developers may publish to development or
   staging and propose a version. They cannot promote their own production
   version. The System Owner decides promotion after independent evaluation and
   required QA/Security evidence.
3. **Generation versus approval:** An agent or runtime that generated an artifact
   cannot approve it. Final approval requires an authenticated qualified human QA
   Reviewer or designated qualified System Owner.
4. **Access versus content:** Approval of a plan never expands a user's record ACL.
   A reviewer sees only evidence already authorized to that reviewer.
5. **Policy versus exception:** A Platform Administrator cannot create an
   exception and approve the affected content/action alone. Any permitted
   temporary exception needs System Owner and Security/QA risk acceptance with an
   expiry. R4 has no exception path.
6. **Synthetic versus real data:** Approval of the MVP workflow authorizes only
   the labeled synthetic internal corpus, not real company records.

## Approval types and binding

| Approval | Minimum authorized decider | What it permits | Required binding |
| --- | --- | --- | --- |
| Plan approval | Regulatory Analyst, Domain SME, QA Reviewer, or System Owner within assigned scope | Execution of the named read/derive steps | Case, plan ID/version/hash, source pins/hashes, internal scope, agent/tool versions, limits, risk classes |
| Relationship decision | Domain SME or QA Reviewer | Accept/reject/return one proposed internal mapping | Hypothesis revision, exact external/internal evidence pins, decision, reason |
| Artifact approval | QA Reviewer or qualified designated System Owner | Publication of one non-GxP immutable revision | Artifact ID/revision/hash, case/run, evidence manifest, validation report, intended-use version |
| R3 action approval | Designated business owner plus content approver required by data policy | One named destination/action | Exact payload hash, destination, actor, expiry, idempotency key |
| Production version approval | System Owner after required QA/Security evidence | Deployment of one immutable agent/skill/tool/workflow bundle | Definition digests, model policy, eval run, known risks, rollback target |
| Risk acceptance | System Owner and required QA/Security owner | Time-bounded residual risk only | Risk, scope, compensating control, owner, expiry, review date |

An approval is append-only and records approve/reject/request-revision,
authenticated actor, role at decision time, UTC timestamp, reason, and all binding
fields. Rejection and manual modification always require a reason.

## Stale-approval rules

Approval is invalidated before start or resume when any bound value changes,
including:

- plan content or normalized plan hash;
- source version, hash, or source set;
- internal document scope or record ACL;
- workflow, agent, skill, tool, prompt, schema, model-policy, or policy version;
- requested action, payload, destination, or risk class;
- limits or budget where the new value is less restrictive;
- approver authority, case membership, component release status, or approval
  expiry.

The API must return a conflict/approval-required state and append an event. It must
not silently copy an old approval to the changed object.

## Tool-call decision order

Before a tool is visible or invoked, the host must:

1. authenticate the end user and runtime service;
2. verify case membership and active run;
3. resolve approved immutable agent and tool versions;
4. validate model-supplied arguments against the narrow schema;
5. verify agent allowlist, user scope, data classification, and record ACL;
6. classify action risk and verify the exact approval;
7. verify source pins, suspension state, budget, quota, and rate limit;
8. inject host-derived identity/context and generate the idempotency key;
9. allow or deny and persist the policy decision.

After a call, the host validates and bounds the result, detects confidential or
instruction-like content, assigns trust and provenance, redacts secrets, hashes
and persists the observation, records usage/error metrics, and only then returns
it to the agent.

## Blocking verification

Release tests must prove:

- a Regulatory Evidence Agent cannot discover or call knowledge/workflow tools;
- a Knowledge Agent cannot bypass record ACLs or reveal blocked titles;
- a changed plan/source/version cannot reuse approval;
- a Platform Administrator and Agent Developer cannot approve prohibited content
  or self-promote;
- every R3 call is denied in the MVP and every R4 call is denied in all states;
- disabled agents, tools, workflows, or global runtime cannot start or resume;
- denial, approval, retry, cancellation, and reviewer decisions remain
  reconstructable from immutable records.

## Related records

- [Agent intended use](agent-intended-use.md)
- [Agent-platform architecture](../architecture/agent-platform.md)
- [Agent-platform threat-model delta](../threat-model/agent-platform-delta.md)

