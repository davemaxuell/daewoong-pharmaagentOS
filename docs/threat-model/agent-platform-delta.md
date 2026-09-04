# PharmaAgent OS threat-model delta

- Status: implementation baseline
- Effective date: 2026-09-04
- Owners: Security, Platform, Engineering, QA, System Owner

## Scope

This record extends the existing [FDA platform threat model](README.md). Existing
threats and invariants remain in force. This delta covers case orchestration,
model-driven agents, MCP adapters/servers, internal knowledge, approvals,
checkpoints, memory, and generated impact artifacts.

The security objectives are to keep agent authority no greater than the current
human and case grants; prevent untrusted content from changing instructions or
permissions; preserve evidence/version integrity; prevent cross-case or
unauthorized disclosure; make side effects approval-bound and idempotent; and
retain enough immutable telemetry to reconstruct observable behavior without
storing hidden chain-of-thought.

## Added assets and trust boundaries

Added assets include case objectives and membership, exact source pins, plans and
hashes, agent/skill/tool/workflow definitions, model policies, internal-document
ACLs, MCP manifests, tool inputs/outputs, policy decisions, approvals, checkpoints,
impact hypotheses, verification reports, artifacts, budgets, kill-switch state,
evaluation fixtures, and traces.

Added trust boundaries are:

1. user/portal → API case and control plane;
2. control plane → queue/orchestrator/agent runtime;
3. runtime → model provider;
4. runtime → MCP gateway → adapter or server;
5. adapter → regulatory or internal evidence store;
6. working/checkpoint state → approved knowledge and artifacts;
7. Git-authored definition → validated registry version → deployed runtime;
8. current run → human approval wait → resumed run.

Network location, a valid MCP response, a model recommendation, or prior approval
does not grant trust by itself.

## Delta threat register

| ID | Threat or abuse case | Impact | Required controls | Blocking verification |
| --- | --- | --- | --- | --- |
| A01 | Indirect prompt injection in FDA HTML/PDF, internal document, upload, tool description, or tool result | Agent follows data as instructions, changes plan, or exfiltrates data | Treat all retrieved content and MCP metadata as untrusted; remove active content; delimit and trust-label data; policy outside prompts; instruction detector and safe failure | Known injection corpus has zero policy/tool escape; malicious content cannot alter allowlist or approval |
| A02 | Agent/runtime acts as a confused deputy using the human's broader access | Unauthorized retrieval or action | Effective permission is the intersection of user, case, plan, agent, tool, record ACL, risk, approval, and limits; specialist-specific context and tools | Cross-role, cross-agent, and cross-case negative matrix |
| A03 | Model fabricates identity, approval, source pin, risk class, or idempotency metadata | Approval bypass, stale evidence, duplicate action | Host injects protected metadata outside model arguments; strict schemas reject reserved fields | Fuzzed arguments cannot override any host-derived field |
| A04 | Malicious or substituted MCP manifest/server expands tools or changes behavior | Supply-chain compromise or hidden authority | Allowlisted registry, immutable version/digest, signed/reviewed release, audience-scoped service identity, startup attestation, per-tool kill switch | Digest/version mismatch fails closed; unregistered discovery is invisible |
| A05 | MCP server returns malicious instructions, oversized output, active content, secrets, or invalid provenance | Prompt compromise, denial of service, leakage, fabricated evidence | PostToolUse schema/type/size bounds, sanitization, instruction and secret detection, trust labels, source resolution, output hash, quarantine | Malformed, oversized, injection, and fake-anchor fixtures are blocked |
| A06 | Broad tool arguments enable SSRF, SQL/path injection, arbitrary lookup, or record enumeration | Internal access, data theft, topology disclosure | Narrow identifiers, enums and bounded queries; domain service APIs; no arbitrary URL/SQL/path/shell/browser/database tools; egress allowlist | Schema fuzz, SSRF, path traversal, SQL injection, and enumeration tests |
| A07 | Retrieval filters after ranking or prompt construction | Protected internal content reaches model or trace | User/case/record ACL and data classification in the datastore query before FTS/vector ranking; minimal ACCESS_BLOCKED result | Canary records never appear in model request, response, cache, or trace |
| A08 | Cross-case context, checkpoint, cache, or stream reuse | Confidential data and permission leakage | Case/run-scoped keys and encryption context; ownership check on every load/stream; bounded typed context; no global prompt cache containing business data | Cross-user/case IDOR and cache-key collision tests |
| A09 | Working state, conversation, or malicious document poisons durable memory | False organizational facts persist or grant authority | No automatic organization-wide memory; working state separate from approved knowledge; provenance, TTL, inspect/revoke; human approval for durable facts; permissions never derive from memory | Seeded poison expires/revokes and cannot become evidence or authorization |
| A10 | AI summary or proposed relation is laundered into evidence/approved knowledge | Unsupported compliance conclusion | Trust levels A–E; source anchors required; proposed and approved relations separate; deterministic composer; human decision with reason | AI-on-AI citation and missing-anchor fixtures block artifact |
| A11 | Approval is replayed after plan/source/version/scope/payload change or by an unauthorized actor | Execution outside reviewed intent | Approval bound to exact hashes, versions, scope, limits, action, destination, approver role, and expiry; revalidate on start/resume; append-only decisions | Mutating each bound field yields conflict and approval-required |
| A12 | Compromised agent, skill, prompt, workflow, model policy, or evaluation definition reaches production | Systematic unsafe behavior | Git review, immutable digests, independent eval, Agent Developer/System Owner separation, release states, rollback target and suspension | Unauthorized/self-promotion fails; digest drift and failed critical eval block load |
| A13 | Recursive delegation, correction loops, parallelism, or provider/tool failure exhausts resources | Denial of service, runaway cost, stalled cases | No free-form subagent creation; per-run turns/tool/parallel/token/cost/time/correction limits; quotas, timeout, circuit breaker, global/component kill switches | Adversarial loop terminates predictably and records reason/usage |
| A14 | Retry, crash, duplicate signal, or uncertain completion repeats a side effect | Duplicate tasks/messages or corrupted state | Canonical fingerprint and idempotency key; intent/result records; atomic claims; reconciliation for uncertain non-idempotent work; R3 denied in MVP | Crash at each boundary creates no duplicate committed action |
| A15 | Secrets or confidential text leak through prompts, model provider, tool errors, artifacts, logs, or metrics | Credential/data compromise | Minimum context, approved provider/data class, scoped short credentials, redaction, structured errors, no full prompt/secret logs, egress deny-by-default | Canary-secret scans across provider fixture, API, trace, log, export, and error |
| A16 | Verification agent shares contaminated context or merely ratifies the producing agent | Unsupported result passes assurance | Independent model/profile where configured; fresh bounded evidence packet; no producer hidden state; deterministic graders retain veto; verifier cannot approve artifact | Seeded contradiction/unsupported claims are rejected across repeated trials |
| A17 | Attachment parser or calculation sandbox escape | Runtime compromise or internal network access | Ephemeral isolated container, no internal credentials, no unrestricted network, read-only input, CPU/RAM/time bounds, output validation, destroy after use | Malicious/polyglot, network, filesystem, resource, and persistence tests |
| A18 | Trace/audit tampering or chain-of-thought retention | Weak forensics or sensitive reasoning disclosure | Append-only events and hashes, separate audit privileges, central export, observable-action summaries only, no provider chain-of-thought request/storage | Privileged tamper test and storage inspection |
| A19 | Source changes while a plan runs, or obsolete internal revision is presented as effective | Stale or misleading report | Exact pins, effective/obsolete status, stale event, no silent switch, approval invalidation where scope changes | Race fixture retains old pin and blocks unreviewed new-version publication |
| A20 | Tool/service suspension or policy change is ignored by queued/resumed work | Known-vulnerable component continues operating | Check global/workflow/agent/tool release and suspension state before enqueue, claim, invoke, and resume | Kill-switch tests stop new and resumed calls while preserving state |

## Mandatory MCP and tool controls

Before tool use, the trusted host must authenticate the human and runtime, verify
case membership, resolve immutable agent/tool versions, validate the narrow input,
check the agent allowlist and user/data/record scope, classify risk, verify exact
approval and source pin, enforce suspension/budget/rate limits, and create the
idempotency key. The decision is persisted before dispatch.

After tool use, the host must validate schema and identifiers, bound output size,
detect confidential or instruction-like content, sanitize active content, assign
trust, attach exact source provenance, calculate a hash, persist the observation
and metrics, and return only the sanitized structured result.

MCP error responses must be structured and minimal. An authorization denial must
not disclose a protected title, identifier, count, path, schema variation, or
content. A tool server cannot request a broader token or delegate to an
unregistered server.

## Memory and context rules

- Working context and checkpoints are case/run scoped, revocable, and
  non-authoritative.
- Approved evidence remains in retained source records, not vector embeddings or
  summaries alone.
- Durable business facts need source provenance, a named human decision, version,
  effective status, and retention policy.
- Temporary memory has purpose, owner, creation time, expiry, and deletion/revoke
  behavior.
- Context compaction preserves identifiers, decisions, open questions, and source
  pins outside the prompt; it never turns a summary into evidence.
- Memory, retrieved text, and prior model output can never grant a role,
  permission, approval, or tool.

## Security invariants

1. Only deterministically admitted Product: Drugs source versions enter a normal
   agent workflow.
2. ACL enforcement occurs before retrieval, ranking, model access, caching, and
   tracing.
3. Only allowlisted tools of the approved immutable agent version are discoverable
   or callable.
4. Identity, case, approval, source pins, risk, and idempotency are host-derived.
5. Every material claim resolves to accessible retained evidence; model working
   state is never evidence.
6. R3 is denied in the MVP and R4 is always denied.
7. Changed bound input invalidates approval, and every resume re-evaluates policy.
8. Retries cannot duplicate actions or overwrite historical evidence.
9. Normal runtime identities cannot mutate prior versions, approvals, case events,
   or approved artifacts.
10. Critical authorization, approval-bypass, source-integrity, or known
    prompt-injection failures block release.

## Review and incident triggers

Re-review this delta for any new tool/server, real internal corpus, provider,
external integration, persistent memory, sandbox capability, A2A boundary,
Temporal migration, data classification, side effect, or regulated-use change.

Prompt-injection success, unauthorized model-context disclosure, approval bypass,
agent/tool manifest substitution, unexplained tool invocation, or duplicate
side effect is a security incident. Suspend the affected workflow/agent/tool,
preserve case and trace evidence, rotate implicated credentials, assess affected
cases and artifacts, and require a reviewed version plus blocking regression test
before reactivation.

## Related records

- [Agent-platform architecture](../architecture/agent-platform.md)
- [Agent control matrix](../assurance/agent-control-matrix.md)
- [Agent intended use](../assurance/agent-intended-use.md)
- [Product and MVP specification](../product/PHARMA_AGENT_OS_SPEC.md)

