# FDA Drug Warning Letter Intelligence Platform — Security Control Matrix

**Target organization:** Daewoong Pharmaceutical
**Status:** Proposed production baseline; reconcile with Daewoong Information Security, QA, Privacy, Records Management, and infrastructure standards before go-live.
**Scope:** Internal FDA `Product: Drugs` Warning Letter monitoring, AI summarization, PostgreSQL/pgvector RAG, portal, review, and notifications.

| ID | Domain | Required control | Implementation expectation | Verification evidence | Proposed owner |
|---|---|---|---|---|---|
| IAM-01 | Identity | Restricted federated login | Auth.js Google/Naver OAuth with provider-scoped immutable subjects, accepted provider email, server allowlist, and no local password/public self-registration. Google domains require the matching Workspace `hd` claim; Naver accepts only a returned `@naver.com` address. | Staging/production auth tests and Google/Naver application records | IAM / Platform |
| IAM-02 | Identity | MFA | Enforced by each approved identity provider's account policy; privileged accounts require the strongest factor available and explicit corporate approval | Provider/MFA policy evidence | IAM / Security |
| IAM-03 | Authorization | Least privilege | Viewer, Analyst, Reviewer, Admin, Auditor, Service Account permissions explicitly mapped | Role matrix + automated authz tests | Product / Backend / Security |
| IAM-04 | Authorization | Separation of duties | System admin cannot silently approve regulatory content; reviewer approval separated where required | UAT + audit samples | QA/Regulatory / Security |
| IAM-05 | Privileged access | Time-bound admin | JIT/PAM elevation where corporate platform supports it | PAM/JIT records | Security / IAM |
| IAM-06 | Lifecycle | Rapid deprovisioning | Identity-provider suspension plus server allowlist/role removal revoke access; Naver access must not depend on unmanaged domain-wide admission for privileged roles | Offboarding test | IAM |
| NET-01 | Network | Private data services | PostgreSQL, object store, queue, secret manager not public | Network scan / cloud posture evidence | Platform / Security |
| NET-02 | Ingress | Controlled ingress | Corporate reverse proxy/WAF/private gateway only | Architecture + firewall/WAF config | Platform |
| NET-03 | Egress | Destination allowlist | Worker egress limited to approved FDA, LLM, notification endpoints | Egress policy + denied-destination test | Platform / Security |
| NET-04 | SSRF | FDA fetch isolation | URL scheme/host/DNS/IP/redirect validation; no arbitrary user-supplied fetch | Security tests | Backend / Security |
| NET-05 | Segmentation | Scraper isolation | Ingestion worker cannot reach sensitive internal manufacturing/QC networks | Network policy test | Platform / Security |
| CRY-01 | Encryption | TLS | TLS for user ingress, DB, object/queue/AI connections according to corporate minimum | Scanner/config evidence | Platform |
| CRY-02 | At-rest encryption | Managed encryption | DB, backups, objects, queue where supported use managed KMS | Cloud configuration evidence | Platform |
| SEC-01 | Secrets | Central secret manager | No production secrets in repository, images, browser storage, or general config | Secret scan + deployment config | Platform / Security |
| SEC-02 | Secrets | Rotation | Rotation policy for provider/API/DB/integration credentials; immediate rotation on incident | Rotation records/runbook | System Owner / Security |
| SEC-03 | Workload identity | Short-lived identity | Prefer workload federation/managed identity over static keys | Deployment identity evidence | Platform |
| APP-01 | Input validation | Strict schema validation | Pydantic/server-side validation, bounded size, unknown-field policy | Unit/security tests | Backend |
| APP-02 | SQL safety | Parameterized queries | No string-built SQL with user input | SAST/code review | Backend |
| APP-03 | XSS | Safe source rendering | Normalize FDA content to safe Markdown/text; sanitize output; CSP | XSS tests / CSP scan | Frontend / Backend |
| APP-04 | CSRF/CORS | Browser request protection | CSRF where cookie auth; restrictive CORS | Automated security tests | Frontend / Backend |
| APP-05 | Sessions | Secure sessions | Secure/HttpOnly/SameSite cookies or equivalent server session; no unsafe localStorage tokens | Browser security tests | Frontend / IAM |
| APP-06 | Errors | Information minimization | No stack traces, SQL, secret names, internal topology in client errors | Negative tests | Backend |
| APP-07 | Rate limiting | Abuse protection | RAG, export, login-adjacent, reprocess/admin operations rate limited | Load/abuse tests | Backend / Platform |
| SCOPE-01 | Corpus scope | Deterministic Drug gate | Only canonical FDA Product metadata containing exact `Drugs` enters corpus | Positive/negative scope fixtures | Backend / Regulatory |
| SCOPE-02 | Fail closed | Ambiguous metadata withheld | Missing/malformed Product metadata -> AMBIGUOUS, not published/indexed | Parser tests | Backend |
| DATA-01 | Source integrity | Immutable/versioned source | Raw FDA bytes stored with SHA-256 and retrieval provenance | Integrity sampling | Backend / Platform |
| DATA-02 | Data minimization | Minimize personal fields | Avoid unnecessary indexing of recipient email/address | Schema review | Product / Privacy |
| DATA-03 | Query confidentiality | RAG query handling | Treat user queries/reviewer notes as internal-confidential; no full prompt in general logs | Logging review | AI/ML / Security |
| DATA-04 | ACL | Authorization before retrieval | Corpus/document ACL filters applied before FTS/vector results reach model | Cross-user leakage tests | Backend / AI/ML |
| AI-01 | Prompt injection | Untrusted source boundary | FDA/attachments treated as data; explicit delimiters; model cannot follow source instructions | Adversarial evals | AI/ML |
| AI-02 | Tool isolation | No arbitrary tools | RAG/summarizer has no shell, browser, DB, arbitrary URL tool | Architecture/code review | AI/ML / Security |
| AI-03 | Grounding | Evidence validation | Material claims require stored source anchors; citations checked after generation | Evaluation report | AI/ML / Regulatory |
| AI-04 | Provider | Approved enterprise endpoint | Provider retention/training/residency terms reviewed | Vendor/security approval | Security / Legal / AI/ML |
| AI-05 | Model governance | Version registry | Model/prompt/schema/taxonomy/chunker versions recorded and controlled | Release metadata | AI/ML / QA |
| AI-06 | Data exfiltration | Prompt minimization | Public summarization receives only needed FDA content; no unrelated Daewoong context | Prompt review | AI/ML / Security |
| SDLC-01 | Source control | Protected branches | PR review, CODEOWNERS, restricted release branches | Repository settings | Engineering |
| SDLC-02 | Code security | Automated scans | SAST, secret scan, SCA/dependency scan, container/IaC scan | CI evidence | Engineering / Security |
| SDLC-03 | Supply chain | SBOM | Machine-readable SBOM for release/container artifacts | Release artifact | Engineering / Security |
| SDLC-04 | Artifact integrity | Signed/provenanced build | Sign images/releases and retain build provenance where platform supports it | Registry/attestation evidence | Platform |
| SDLC-05 | Runtime hardening | Minimal containers | Non-root, drop capabilities, no privileged mode, read-only FS where practical | Container policy scan | Platform |
| LOG-01 | Audit | Privileged audit trail | Admin/reviewer/config/model actions record actor, object, before/after, reason, request ID | Audit query/UAT | Backend / QA |
| LOG-02 | SIEM | Centralized security telemetry | Auth, WAF, admin, secrets, egress, deployment, backup alerts reach SIEM | SIEM dashboard/test alert | Security / Platform |
| LOG-03 | Log hygiene | Secret/confidential redaction | Bearer tokens, raw secrets, full confidential prompts excluded | Log sampling | Engineering / Security |
| VULN-01 | Vulnerability | No critical at go-live | No unaccepted critical production vulnerability | Scan report / risk acceptance | Security / System Owner |
| VULN-02 | Pen test | Pre-production security test | Application/API/auth/RAG attack surface tested per corporate policy | Pen-test report | Security |
| VULN-03 | Patch | Remediation process | Findings assigned owner/deadline; recurring review | Vulnerability tracker | System Owner / Security |
| BCP-01 | Backup | PITR/versioned backups | PostgreSQL PITR + versioned raw object store | Backup configuration | Platform |
| BCP-02 | Restore | Tested recovery | Restore into non-production on defined schedule | Restore test report | Platform / System Owner |
| BCP-03 | Ransomware | Separated backup permissions | Runtime identity cannot destroy all backups/source history | IAM review / destructive test in staging | Platform / Security |
| IR-01 | Incident | Security runbooks | Account compromise, credential exposure, leakage, malicious dependency, provider incident, destructive admin | Approved runbooks | Security / System Owner |
| IR-02 | Evidence | Preserve forensic trace | Audit/SIEM/build/config evidence available with synchronized timestamps | Incident drill | Security / Platform |
| GOV-01 | GxP | Intended-use assessment | Regulatory intelligence / decision-support boundary documented; re-assess on quality-record use | QA/system assessment | QA / System Owner |
| GOV-02 | Change control | Controlled behavior changes | Parser/scope/auth/model/prompt/schema/taxonomy/retrieval changes go through release/change process | Change tickets/release notes | Engineering / QA |
| GOV-03 | Access review | Periodic access certification | Privileged/role access reviewed periodically | Review evidence | System Owner / IAM |
| GOV-04 | Vendor | Third-party review | LLM/cloud/notification providers reviewed under corporate supplier/security process | Vendor approval | Procurement / Security / Legal |

## Go-live blocking controls

At minimum, the following should be considered release-blocking: `IAM-01`, `IAM-02`, `IAM-03`, `NET-01`, `NET-03`, `SEC-01`, `APP-02`, `SCOPE-01`, `SCOPE-02`, `DATA-04`, `AI-01`, `AI-03`, `SDLC-02`, `LOG-01`, `LOG-02`, `VULN-01`, `BCP-02`, and `GOV-01`.

## Evidence package to retain per production release

- release version / Git commit;
- approved change record;
- automated test report;
- Drug scope regression report;
- RAG/AI evaluation report for behavior-changing releases;
- SAST/SCA/secret/container/IaC results;
- SBOM;
- signed artifact/provenance evidence where used;
- database migration and rollback plan;
- active model/prompt/schema/taxonomy/chunker versions;
- security exception/risk acceptance records;
- staging smoke/UAT evidence;
- production post-deployment health check.
