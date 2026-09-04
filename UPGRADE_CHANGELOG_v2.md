# Upgrade Changelog — FDA Drug Warning Letter Intelligence Platform v2.0

## Scope changes

- Production corpus narrowed from all FDA Warning Letters to canonical FDA pages whose Product metadata explicitly contains `Drugs`.
- Added deterministic scope states: `UNVERIFIED`, `IN_SCOPE_DRUGS`, `OUT_OF_SCOPE`, `AMBIGUOUS`, `SCOPE_CHANGED`.
- Removed cross-product parser/taxonomy assumptions from the production design.
- Replaced the prior R3 Medical Companies example (`Product: Biologics`) with Tianjin Kilo (`Product: Drugs`) and retained R3 only as a negative test fixture.
- Added drug-focused taxonomy and subtype facets for finished pharmaceuticals, OTC, API, sterile/non-sterile, contract activities, registration/listing, and other drug contexts.

## Security architecture upgrades

- Added enterprise trust-zone architecture and zero-trust principles.
- Added corporate SSO/MFA, least privilege, separation of duties, JIT/PAM guidance, and service-account boundaries.
- Added private network/data-service requirements, controlled ingress, FDA/LLM egress allowlists, and scraper network isolation.
- Added KMS/secret-manager requirements, environment separation, encryption, and key/credential rotation.
- Added API/browser security controls, safe FDA content rendering, SSRF/XSS/CSRF/CORS/rate-limit protections, and export controls.
- Added LLM/RAG prompt-injection, data-exfiltration, tool-isolation, grounding, ACL-before-retrieval, model/provider governance, and cross-corpus leakage controls.
- Added secure SDLC: SAST, SCA, secret scanning, IaC/container scans, SBOM, signed artifacts/provenance, runtime hardening, and controlled model/prompt changes.
- Added SIEM/audit requirements, vulnerability management, penetration testing, backup/DR/ransomware resilience, incident response, and security release gates.

## Industrial operations upgrades

- Added proposed availability/RPO/RTO targets.
- Added security/data-quality observability metrics and alerts.
- Added production runtime hardening and change-control requirements.
- Expanded integration, regression, adversarial, authorization, and RAG security tests.
- Added production Definition of Done and handover evidence requirements.
- Added separate security control matrix with implementation, verification evidence, and ownership.
