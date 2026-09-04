# Release evidence checklist

Record links or immutable identifiers; do not paste secrets, tokens, confidential full prompts, or unnecessary personal data into the evidence package.

- [ ] Release version, source commit, immutable image digests, signatures/attestations
- [ ] Approved change record, owners, window, migration and rollback/forward-fix plan
- [ ] Active parser, scope rule, model, prompt, schema, taxonomy, embedding, and chunker versions
- [ ] Unit, parser, Drug-scope, contract, integration, authz, security, and selected E2E results
- [ ] Positive Drug and negative Biologics/device/food/missing/conflicting Product fixture results
- [ ] AI schema/grounding/citation/injection and RAG retrieval/leakage/insufficient-evidence reports when affected
- [ ] SAST, SCA, secret, container, and IaC scan reports; SBOM; no unaccepted critical finding
- [ ] Staging SSO/MFA/role-matrix and separation-of-duties evidence
- [ ] Network/WAF/private-data/egress-denial and SIEM test evidence
- [ ] Backup state and latest successful isolated restore-test report with measured RPO/RTO
- [ ] Regulatory/QA UAT and approved intended-use assessment
- [ ] Production post-deployment probes, Drug-scope smoke, audit correlation, queue claim, evidence integrity sample, and RAG citation/insufficient-evidence checks
- [ ] Residual risk acceptances with owner, compensating control, expiry, and review date

