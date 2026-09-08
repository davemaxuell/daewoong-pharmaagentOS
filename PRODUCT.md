# PharmaAgent OS

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Daewoong employees preparing questions about FDA findings, including staff who
do not know agent terminology or regulatory software. Quality and regulatory
specialists retain the formal review role. The user explicitly requested an
interface that anyone in the company can understand and use.

## Product Purpose

Turn a regulatory question and retained source evidence into an inspectable
agent plan, evidence trail, and review package for a human decision.

## Operating Context

FDA source discovery, case preparation, specialist steps, evidence verification,
human approvals, and execution oversight. Korean and English are supported.

## Capabilities and Constraints

The user explicitly removed all account login. Public visitors remain viewers.
Existing API authorization, source-version ownership, and review gates remain.
The hosted database, FDA source library and cited AI answers are connected.
The FDA Research Agent accepts an employee goal, chooses bounded search/read tools,
checks cited findings and saves a review brief. Its plan, tool events and evidence
are visible during execution. Tasks persist on the service with browser-session
ownership, stop/resume controls and bounded background execution.
Automatic FDA ingestion, specialist execution and independent evaluation
qualification are incomplete. The interface must never invent runs,
FDA records, completion statistics, or successful agent execution. A locally
prepared objective is a draft, not an executed or server-saved case.

## Brand Commitments

PharmaAgent OS is the product name. Retain the existing Daewoong identity asset
as organizational attribution. This preservation is inferred from the repository.

## Evidence on Hand

PHARMA_AGENT_OS_IMPLEMENTATION_PLAN.md is the source plan;
PHARMA_AGENT_OS_IMPLEMENTATION_HANDOFF.md is the current implementation record.
Existing case, evidence, governance, chat, and evaluation routes provide the
functional baseline. Agent definitions exist under contracts/agents.

## Product Principles

- Lead with an employee task and an editable question, with examples.
- Keep specialist configuration and operational tools secondary.
- Explain which actions work now, where work is saved, and what happens next.
- Make agent responsibility, source evidence, and human decisions inspectable.
- Distinguish planned, running, completed, unavailable, and restricted states.
- Lead beginners to FDA agent research; keep quick chat accessible and local draft preparation secondary.
