# Threat model

Status: implementation baseline. Review when identity, deployment topology, FDA acquisition, AI provider, notification integration, or corpus boundaries change.

## Scope and security objectives

The service processes public FDA evidence but also holds internal-confidential user questions, reviewer comments, access metadata, configuration, and potentially sensitive operational signals. Protect source integrity/provenance, authorization boundaries, user/query confidentiality, credentials, service availability, and forensic evidence.

Primary assets are corporate sessions and role mappings; FDA raw bytes and hashes; source/scope/version history; reviewer-approved derived content; RAG queries and retrieval traces; application/provider credentials; production code/configuration; audit, backup, and release evidence.

Trust boundaries are shown in [logical architecture](../architecture/logical-architecture.md). Network location alone grants no trust.

## Actors

- Authorized Viewer, Regulatory Analyst, Reviewer, System Administrator, and Security Auditor.
- Narrow non-interactive ingestion, worker, notification, and CI/CD service accounts.
- FDA source services, approved enterprise AI gateway, approved notification providers, Google OAuth/Workspace, Naver OAuth, and corporate SIEM.
- External attacker, compromised user, malicious insider, compromised dependency/provider, and malicious content embedded in an otherwise official source.

## Threat register

| ID | Threat / abuse case | Impact | Required mitigations | Verification |
|---|---|---|---|---|
| T01 | Account takeover, stolen session, or abusive public account | Unauthorized queries, cost consumption, review, export, or admin action | Verified Google/valid Naver OAuth identities, provider-scoped immutable subjects, viewer-only email accounts, secure server sessions, per-subject rate limits, 90-second API assertions, and offboarding | Auth/session negative tests; provider application evidence; rate-limit tests; SIEM drill |
| T02 | Horizontal/vertical privilege escalation | Cross-user data disclosure or unauthorized approval/configuration | Backend object authorization, explicit role matrix, separation of duties, corpus grants before retrieval | BOLA/IDOR and role-matrix tests |
| T03 | FDA URL manipulated for SSRF/DNS rebinding/redirect escape | Internal service access or data exfiltration | Fixed source discovery, HTTPS and FDA host allowlist, DNS/IP validation, redirect cap/revalidation, egress deny-by-default | SSRF, DNS rebinding, redirect fixtures; denied-egress test |
| T04 | Malicious or structurally changed FDA HTML/PDF | XSS, parser failure, resource exhaustion, corpus corruption | Treat as untrusted, byte/type/decompression limits, PDF magic validation, safe normalization/sanitization, no script execution, parser contract/fail closed | Parser robustness, oversized/polyglot and XSS fixtures |
| T05 | Product-scope confusion or parser regression | Biologics/device/food leakage into portal or RAG | Deterministic canonical Product parser, exact `Drugs` match, versioned decisions, negative fixtures, publish/index DB invariants | 100% precision/recall on approved scope fixtures |
| T06 | Prompt injection in source, attachment, or user query | Instruction hijack, fabricated citations, secret/corpus disclosure | Untrusted delimiters, no arbitrary model tools, bounded context, server-side prompts, output schema, grounding/citation and policy validation | Injection, jailbreak, exfiltration, executable-output evals |
| T07 | Retrieve then filter | Unauthorized context reaches model even if hidden from response | Authenticate and resolve corpus/document ACL before FTS/vector queries; fixed Drug filter in SQL | Cross-user/cross-corpus leakage tests; query-plan/code review |
| T08 | SQL injection or unsafe filter construction | Data theft/corruption | Strict input schemas, bounded fields, parameterized SQL, low-privilege DB roles | SAST, fuzzing, negative API tests |
| T09 | Stored/reflected XSS from FDA or AI content | Session theft or user compromise | Render safe Markdown/text only, sanitizer, output encoding, CSP, `nosniff`, frame restrictions | Browser/XSS tests and CSP scan |
| T10 | Secret leakage through repo/image/log/prompt/browser | Provider/database compromise | Secret manager/workload identity, environment separation, redaction, no browser storage, secret scan, rotation runbook | Repository/image scan; log/prompt sample; rotation drill |
| T11 | Tampered source or derived content | False regulatory intelligence | Immutable/versioned raw objects, SHA-256, append-only versions, deterministic anchors, controlled activation/review, audit trail | Integrity sampling, version/review audit UAT |
| T12 | Compromised dependency/build runner/image | Runtime compromise | Protected branches, SAST/SCA/secret/IaC/container scans, pinning, SBOM, minimal non-root images, signing/provenance | CI/release evidence; runtime policy scan |
| T13 | Destructive admin/ransomware | Evidence or service loss | JIT privileged access, immutable/versioned objects, PITR, backup identity separation, tested recovery | Restore drill; staged destructive-permission test |
| T14 | LLM/provider retention, training, or outage | Confidential query leakage or loss of derived service | Approved enterprise contract/settings, minimum prompt context, allowlisted endpoint, pinned model, timeout/circuit-breaker, source-only fallback | Vendor approval; egress test; outage integration test |
| T15 | Notification destination abuse | Internal information sent outside approved channels | Server-side destination allowlist, managed integration, minimum public-source content, dedupe, credential rotation | Destination negative test and delivery audit |
| T16 | Audit deletion, log injection, or uncorrelated events | Weak forensic reconstruction | Append-only audit access, structured/escaped logs, UTC/request/trace IDs, central SIEM, runtime cannot delete backups/audit | Privileged-action samples and incident drill |
| T17 | Resource exhaustion / abusive RAG or reprocess requests | Monitoring delay or service outage | Body/query/page limits, per-user/route rates, queue quotas/priorities, timeouts, worker/resource limits | Load and rate-limit tests |
| T18 | Scope/source changes during in-flight AI processing | Stale or unsupported output published | Bind every job to source version/hash; reject activation when current version changed | Race/idempotency integration test |

## Security invariants

1. Only a canonical FDA version with normalized Product class `Drugs` is admitted to normal display, summarization, chunks, or RAG.
2. Authorization and corpus grants execute before both lexical and semantic retrieval.
3. The model cannot browse, execute code, call arbitrary URLs, or access the database/filesystem.
4. Material AI statements require a verified excerpt within the named stored source anchor.
5. Normal runtime identities cannot overwrite raw evidence, prior source versions, reviews, or audit history.
6. Database, object storage, queue, and secret services are private; only constrained workers have controlled external egress.
7. No secret, bearer token, confidential full prompt, or unnecessary personal data enters general logs.
8. A backup is not accepted as a control until a restore has succeeded and evidence is retained.
9. Google/Naver provider access, refresh, and ID tokens never enter browser application state, FastAPI, or the service database; FastAPI accepts only the dedicated short-lived RS256 application assertion.

## Risk acceptance and review

Unaccepted critical vulnerabilities and failures of the blocking controls in `SECURITY_CONTROL_MATRIX.md` prevent production release. Each accepted residual risk needs an owner, expiry, compensating control, and change/risk record. Re-review at least annually and for any material architecture, provider, authentication, parser/scope, internal-corpus, or model-tool change.
