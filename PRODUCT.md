# PharmaAgent OS

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Pharmaceutical regulatory and quality teams assessing FDA Drug warning letters.
This audience is inferred from the authoritative implementation plan; the user
has requested a complete interface redesign emphasizing the agentic service.

## Product Purpose

Turn a regulatory question and retained source evidence into an inspectable
agent plan, evidence trail, and review package for a human decision.

## Operating Context

FDA source discovery, case preparation, specialist steps, evidence verification,
human approvals, and execution oversight. Korean and English are supported.

## Capabilities and Constraints

The user explicitly removed all account login. Public visitors remain viewers.
Existing API authorization, source-version ownership, and review gates remain.
The API/database and ingestion are not live; specialist execution and independent
evaluation qualification are incomplete. The interface must never invent runs,
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

- Lead with the regulatory objective and the work required to address it.
- Make agent responsibility, source evidence, and human decisions inspectable.
- Distinguish planned, running, completed, unavailable, and restricted states.
- Preserve FDA search and chat as supporting research tools.
