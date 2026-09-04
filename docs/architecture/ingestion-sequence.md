# Ingestion and publication sequence

```mermaid
sequenceDiagram
  autonumber
  participant S as Scheduler
  participant Q as Durable queue
  participant W as Ingestion worker
  participant F as FDA
  participant O as Object storage
  participant D as PostgreSQL
  participant A as Approved AI gateway
  participant R as Reviewer
  participant N as Notification worker

  S->>Q: enqueue discovery idempotency key
  Q->>W: claim discovery job
  W->>F: fetch robots/listing/XLSX through rate limiter
  F-->>W: listing bytes + HTTP provenance
  W->>O: put immutable discovery snapshot
  W->>D: record snapshot, diff current listing

  loop each new or materially changed candidate
    W->>F: fetch canonical detail (allowlisted host)
    F-->>W: untrusted source bytes + metadata
    W->>W: parse Product deterministically
    W->>D: append scope decision

    alt exact normalized Product contains Drugs
      W->>O: put immutable raw HTML/PDF
      W->>W: normalize body, anchors, hashes
      W->>D: append document version and lifecycle event
      W->>A: send bounded source segments only
      A-->>W: strict JSON extraction
      W->>W: schema, grounding, citation, consistency checks
      alt validation and publication policy pass
        W->>D: append summary/findings and activate approved output
        W->>D: create authorized Drug chunks and indexes
        W->>Q: enqueue deduplicated notification
        Q->>N: deliver approved public-source content
      else review required
        W->>D: save pending/failed validation result
        R->>D: approve, revise, or reject with reason
        D-->>Q: enqueue indexing/notification after approval
      end
    else Product parsed without Drugs
      W->>D: record OUT_OF_SCOPE minimal evidence
      Note over W,D: no body summary, embedding, normal portal, or RAG admission
    else Product missing or contradictory
      W->>D: record AMBIGUOUS exception
      W->>Q: bounded retry / admin review
    end
  end
```

## Idempotency boundaries

| Stage | Key |
|---|---|
| Discovery | `source_url + export_sha256` |
| Scope | `canonical_url + source_version_id + scope_rule_version` |
| Fetch | `canonical_url + expected_source_state_hash` |
| Parse | `document_version_id + parser_version` |
| Summarize | `document_version_id + model_id + prompt_version + schema_version` |
| Embed | `document_version_id + embedding_model_id + chunker_version` |
| Notify | `change_event_id + subscription_id` |

Only a changed normalized document-body hash creates a new source version. ETag changes alone update retrieval provenance.

