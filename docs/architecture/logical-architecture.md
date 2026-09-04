# Logical architecture

This is the starter deployment boundary for the internal FDA Drug Warning Letter Intelligence service. Production substitutions must preserve the same trust boundaries.

```mermaid
flowchart LR
  user["Daewoong user<br/>managed device"] --> idp["Corporate IdP<br/>SSO + MFA"]
  idp --> gateway["Private ingress<br/>WAF / reverse proxy"]

  subgraph app["Private application zone"]
    web["Next.js web"]
    api["FastAPI API<br/>authn + authz + audit"]
    scheduler["Scheduler<br/>leader-elected"]
    worker["Constrained workers<br/>ingest / AI / index / notify"]
    queue["Durable queue"]
    web --> api
    scheduler --> queue
    queue --> worker
    api --> queue
  end

  gateway --> web
  gateway --> api

  subgraph data["Private data zone"]
    postgres[("PostgreSQL<br/>FTS + pgvector")]
    objects[("Versioned object storage<br/>raw FDA evidence")]
    secrets["Secret manager + KMS"]
  end

  api --> postgres
  worker --> postgres
  worker --> objects
  api --> secrets
  worker --> secrets

  subgraph egress["Controlled egress zone"]
    proxy["Egress proxy / NAT<br/>destination allowlist"]
  end

  worker --> proxy
  proxy --> fda["Approved fda.gov hosts"]
  proxy --> ai["Approved enterprise AI gateway"]
  proxy --> notify["Approved email / Slack integration"]

  gateway --> siem["Central telemetry / SIEM"]
  api --> siem
  worker --> siem
  idp --> siem
```

## Boundary rules

- Only ingress may reach web/API; PostgreSQL, queue, objects, and secrets have no public endpoint.
- Backend authorization is independent of frontend navigation. Corpus grants and `Product: Drugs` are applied before FTS/vector retrieval.
- FDA bytes and attachments are untrusted input. Raw HTML is never rendered directly.
- Workers can reach only approved FDA, AI, and notification destinations. They cannot reach sensitive manufacturing/QC networks.
- The model has no shell, browser, arbitrary URL, filesystem, or database tool.
- Raw sources and normalized source versions are authoritative; summaries and embeddings are versioned derivatives.

## Availability baseline

- At least two stateless API/web replicas in production.
- Managed PostgreSQL HA/PITR, versioned object storage, and a persistent queue.
- Health probes, rolling deployment, bounded graceful shutdown, and scheduler leader election.
- FTS/vector data is rebuildable from retained source versions. Proposed service goals are 99.5% monthly availability, RPO at most 15 minutes, and RTO at most four hours, subject to enterprise approval.

