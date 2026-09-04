# Security incident runbook

Use Daewoong's corporate incident process as authority. This application-specific checklist supplements it.

## Immediate response

1. Declare severity and incident ID; engage Information Security and the System Owner. Assign commander, technical lead, evidence lead, and communications owner.
2. Contain the narrowest affected account, session, integration, workload, route, model provider, or egress destination. Avoid deleting or rebuilding before evidence capture.
3. Preserve synchronized SIEM, gateway, IdP, application audit, database connection/audit, secret/KMS access, object-access, queue, deployment, and provider logs. Snapshot relevant configuration and artifact digests.
4. Establish impacted identities, data/corpus, operations, queries/exports, time window, source versions, build versions, and destinations.
5. For agent-runtime incidents, set `PUT /api/v1/control-tower/controls/global`
   to `suspended=true` with the incident reason. For a bounded agent defect, use
   `/controls/agents/{agent_version_id}`. Record the returned control revision;
   un-suspension requires that exact revision and System Owner or Platform
   Administrator authorization.

## Scenario actions

- **Account/session compromise:** disable identity/elevation, revoke sessions/tokens, review role/group changes and exports, require IdP remediation.
- **Credential exposure:** revoke/rotate affected and downstream credentials through the secret manager, invalidate cached sessions, verify no secret remains in history/image/logs; do not paste the value into the ticket.
- **Unauthorized export or RAG leakage:** disable affected route/corpus grant, preserve retrieval and export audit, identify recipients and content, start privacy/legal/QA notification assessment.
- **SSRF/source-fetch compromise:** stop acquisition worker egress, block indicator, preserve DNS/redirect/HTTP traces, verify object and internal-service access, test allowlist/DNS controls before restart.
- **Malicious dependency/image:** stop rollout, quarantine digest, revoke runner/workload credentials if needed, identify deployments/SBOM scope, rebuild from trusted pinned sources and verify provenance.
- **AI provider incident:** open circuit/block egress, rotate credential, identify request time range and data classes, follow vendor and internal notification requirements.
- **Agent/tool anomaly:** apply the global or exact-version kill switch, preserve
  the Temporal history and database activity journal, revoke the workload token,
  and retain MCP policy/tool observations before retrying or rolling back.
- **Destructive action/ransomware:** isolate writer identities, protect backups/object versions/audit, establish trusted recovery point, then follow restore runbook.

## Recovery and closure

1. Eradicate the cause, restore from trusted state if integrity is uncertain, and use new credentials/artifacts.
2. Validate SSO/authorization, Drug scope, evidence hashes, audit flow, egress controls, backup health, and affected user journeys before re-enable.
   Clear a kill switch only with its current optimistic revision so a concurrent
   incident command cannot be silently overwritten.
3. Monitor heightened indicators; document impact, decisions, notifications, recovery point, and evidence custody.
4. Add regression/security tests and corrective actions with owners/dates. Complete post-incident review and required QA/change/risk records.
