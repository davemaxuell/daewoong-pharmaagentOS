# Runbook index

| Runbook | Use when | Primary owner |
|---|---|---|
| [Google and Naver authentication](authentication.md) | Provider setup, callback, account-policy, key rotation, or login failure | Platform + Information Security |
| [Ingestion and scope](ingestion-and-scope.md) | Discovery, fetch, parser, lifecycle, or Product-scope failure | Backend/data on-call |
| [AI and RAG quality](ai-and-rag-quality.md) | Validation failures, incorrect answers, citation or leakage concerns | AI/ML + Regulatory/QA |
| [Security incident](security-incident.md) | Account, secret, dependency, export, SSRF, provider, or destructive event | Information Security + System Owner |
| [Backup and restore](backup-and-restore.md) | Scheduled recovery test or production recovery | Platform + System Owner |
| [Deploy and rollback](deploy-and-rollback.md) | Controlled staging/production release | Platform + change owner |

For every incident: use UTC timestamps; assign incident/change ID, commander, and communications owner; preserve evidence before remediation; never paste credentials or full confidential prompts into tickets or general logs; record decisions, validation, and closure evidence.
