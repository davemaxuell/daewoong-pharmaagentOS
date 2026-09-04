# Backup and restore runbook

## Preconditions

- Production uses PostgreSQL PITR and versioned raw object storage with backup permissions separated from runtime identities.
- Record approved RPO/RTO, retention, restore target, responsible operators, and recovery point before starting.
- Scheduled tests restore into an isolated non-production environment with production notifications and crawlers disabled.

## Restore sequence

1. Open a recovery/change record and preserve the failure timeline. Verify backup catalog integrity and choose a recovery point at or before the incident.
2. Establish isolated identity, network, DNS, certificates, secret references, and logging. Never reuse a suspected credential.
3. Restore PostgreSQL to a new instance/namespace; do not overwrite the source environment during a test.
4. Restore or mount versioned raw objects read-only. Verify sampled database object keys, sizes, and SHA-256 values.
5. Restore queue configuration but initially suppress deliveries and external side effects. Recreate jobs from authoritative database state where possible.
6. Validate schema migrations, row counts, referential integrity, current Drug-scope invariants, append-only history, and latest accepted recovery timestamp.
7. Rebuild derived FTS/vector indexes from authorized current source versions. AI summaries are retained/rebuilt only according to approved version metadata.
8. Exercise liveness/readiness, authenticated browse/detail, scope-negative query, authorized RAG, audit emission, and a dry-run discovery.
9. Enable workers in stages, reconcile listing/source versions, then enable notifications after dedupe checks.

## Acceptance evidence

Record actual RPO/RTO, backup identifiers, database/object versions, integrity sample, tests/results, discrepancies, operator/reviewer approvals, and follow-up actions. A copied backup without a successful tested restore is not accepted recovery evidence.

## PharmaAgent OS restore exercise

Use `scripts/verify-pharma-backup-restore.ps1` with two short-lived database URLs
provided through the approved secret channel. The script refuses identical source
and target URLs, requires explicit acknowledgement that the target is isolated,
creates a SHA-256 manifest, restores with ownership stripped, and captures counts
for cases, runs, approvals, artifacts, hash-chained events, and durable activities.

After the scripted checks, verify one paused run can resume, one pending approval
survived unchanged, the latest run-event chain recomputes, and sampled retained
source/object hashes match. Keep the dump identifier, manifest, count output,
operator, reviewer, measured RPO/RTO, and change/incident record together as the
restore evidence package. Delete the isolated restored environment only under the
approved recovery-test change after evidence retention is confirmed.
