# PharmaAgent OS intended use and regulated-use boundary

- Status: implementation baseline pending formal QA and System Owner approval
- Effective date: 2026-09-04
- Owners: System Owner, Regulatory Intelligence, QA, Security

## Relationship to the existing intended use

This statement extends the FDA platform
[intended-use baseline](intended-use.md) to agent-planned workflows, internal
knowledge retrieval, impact hypotheses, and review artifacts. It does not approve
production or regulated use. The more restrictive statement applies if the two
records differ.

## Intended use

PharmaAgent OS is an internal regulatory-intelligence and human
decision-support aid for authorized personnel. It may:

- organize a review around an admitted public FDA Drug warning letter;
- pin, retrieve, and cite exact retained official source evidence;
- extract structured regulatory findings for human inspection;
- search only internal documents that the current user and case are authorized to
  access;
- propose potentially relevant internal assets and review questions;
- express evidence-backed impact hypotheses, assumptions, counterevidence,
  uncertainty, and missing information;
- independently verify citation support and overstatement;
- prepare a clearly labeled draft impact-review package for qualified human
  review.

The portfolio MVP uses fictional synthetic internal quality documents only. The
official FDA source and, when later approved, the effective controlled internal
document remain authoritative.

## Intended users and decisions

Regulatory Analysts initiate and investigate cases. Domain SMEs assess proposed
relationships. QA Reviewers own artifact decisions. Auditors inspect retained
evidence and history. Agent Developers and Platform Administrators operate
technical components but do not acquire content-approval authority from those
roles. The System Owner approves the intended use and production agent releases.

Humans remain responsible for:

- confirming source interpretation and internal applicability;
- obtaining missing context outside the agent workflow;
- accepting, rejecting, or revising proposed relationships with reasons;
- deciding whether a formal quality-system process is required;
- approving any artifact and controlling any later use of it.

## Prohibited use

The platform and its agents must not autonomously:

- declare Daewoong, a site, process, system, record, or product compliant or
  noncompliant;
- assert a confirmed GMP gap from an external observation;
- initiate, create, approve, close, or determine the necessity of a CAPA,
  deviation, change control, investigation, or audit response;
- create or revise an SOP, policy, validation record, training assignment, or
  other controlled record;
- release or reject product or make a batch-disposition decision;
- control or instruct manufacturing, laboratory, or computerized equipment;
- submit, send, or publish content to a regulator or external party;
- write to QMS, EDMS, MES, LIMS, or another validated/controlled system;
- replace qualified human review or present model confidence as compliance
  certainty.

Users must not use an exported report to bypass the same restrictions.

## Output status and required presentation

All findings, summaries, mappings, priorities, hypotheses, and recommendations are
derived aids. The interface and exported artifact must:

- display **Decision support — human review required**;
- distinguish source fact, internal fact, hypothesis, assumption, counterevidence,
  unknown, and human decision;
- show exact accessible source/version anchors for every material claim;
- identify synthetic internal content as **FICTIONAL TEST DATA — NOT A COMPANY
  RECORD**;
- show stale, incomplete-evidence, access-blocked, and unverified-context states;
- use **Review Priority**, never Compliance Risk Score;
- avoid language that implies validation, QA approval, or regulatory acceptance
  before the corresponding attributable human decision.

Model working state and hidden reasoning are not evidence and must not be exposed
or retained. A confidence value describes model uncertainty only and cannot
replace evidence strength or human judgment.

## GxP and records boundary

Under the MVP intended use, case records and reports are non-GxP
regulatory-intelligence artifacts. They are not:

- the official FDA record;
- a controlled quality-system record;
- required evidence of a regulated activity;
- an electronic signature;
- an automated compliance decision;
- a direct control input to a regulated process.

Formal reassessment and documented approval are required before any output becomes
or feeds one of those categories. Reassessment must determine applicable
validation, electronic-record/signature, data-integrity, audit-trail, retention,
change-control, supplier, access-review, backup/restore, business-continuity, and
periodic-review controls under Daewoong procedures.

## Scope-change triggers

Stop release or operation and reassess intended use when any of the following is
proposed:

- replacing the synthetic corpus with actual company or partner records;
- connecting a controlled or validated system;
- enabling a task, notification, write, submission, or equipment action;
- using output as required quality evidence or a release/compliance decision;
- changing the user population, legal entity, geography, data classification, or
  retention purpose;
- introducing automatic durable memory or organization-wide learned facts;
- permitting autonomous plan approval, artifact approval, or unbounded agents;
- materially changing providers, agent capabilities, tool scopes, or workflow
  topology.

## Conditions for authorized use

Use is permitted only when:

1. identity, role, case membership, and data ACLs are enforced server-side;
2. exact source versions, agent/tool versions, plans, policy decisions, and
   approvals are retained;
3. the [agent control matrix](agent-control-matrix.md) is implemented and tested;
4. every material claim can be inspected against retained evidence;
5. prompt-injection, authorization, stale-approval, and prohibited-conclusion
   tests pass with no critical failure;
6. qualified human reviewers are trained on the limitations and own final
   decisions;
7. residual risks, owners, compensating controls, and expiry dates are approved.

Production release additionally requires formal signature/approval of this
statement by the named System Owner and QA owner.

## Related records

- [Product and MVP specification](../product/PHARMA_AGENT_OS_SPEC.md)
- [Agent control matrix](agent-control-matrix.md)
- [Agent-platform threat-model delta](../threat-model/agent-platform-delta.md)

