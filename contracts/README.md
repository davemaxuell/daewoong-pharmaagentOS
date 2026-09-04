# Contracts

These files are the versioned implementation boundary for the service:

- `schema.sql` is the normalized PostgreSQL 16 + pgvector architectural reference. It is not the runnable SQLAlchemy bootstrap schema and must not be applied to the API runtime database.
- `api_contract.yaml` is the OpenAPI 3.1 business/API contract.
- `summary_schema.json` is the strict AI extraction output contract.
- `taxonomy.yaml` is the controlled Drug finding vocabulary; `taxonomy_schema.json` validates its structure.
- `cases/` defines strict, append-safe Case, CaseSource, CaseEvent, CasePlan,
  PlanStep, durable CaseRun, and exact ApprovalBinding records. The fixtures include a
  schema-valid stale approval that the cross-contract validator must reject.
- `agents/` defines five versioned agents: the Case Orchestrator, Regulatory
  Evidence, Internal Knowledge, Impact Analysis, and independent Verification
  agents. Agent tools, skills, limits, lifecycle hooks, and release gates are
  data owned by the harness.
- `skills/` defines the ten approved reusable operating-instruction versions used
  by the initial platform and validates every entry against a closed schema.
- `workflows/` defines the typed regulatory-impact-review workflow. Version 1.0.0
  is approved and execution-enabled for plans whose exact agent/tool release
  bindings pass the runtime gate.
- `tools/` defines the versioned `regulatory-mcp`, `knowledge-mcp`, and
  `workflow-mcp` bundles. All 16 tools are deny-by-default, version-bound,
  runtime-attributed, bounded, and schema-validated. Workflow tools stop at
  internal drafts or ACL-filtered metadata; there is no external-send action.

The `cases/*.schema.json` resources are the canonical full-workflow records. The
Milestone 1 HTTP surface in `api_contract.yaml` is an intentionally narrower
creation/read projection over the first persistence slice; it is not represented
as conforming to fields it does not yet expose (tenant scope, workflow-definition
hashes, full budget/risk statements, and RFC 8785 plan serialization). Its stored
plans remain execution-ineligible until an approved agent/tool-pinned plan is
created and bound to a durable case run. The Milestone 3 HTTP projection is an
explicit adapter over the canonical CaseRun contract and its persisted checkpoint.

Run the contract checks from the repository root:

```powershell
python -m pip install -r contracts/requirements-validation.txt
python contracts/validate_contracts.py
npx --yes @redocly/cli lint contracts/api_contract.yaml
```

Validate `schema.sql` in a separate disposable pgvector database when Docker is
available. Bootstrap a fresh API database with `fda-intel init-db` under a dedicated
migration identity, then revoke DDL rights and run the API with
`AUTO_CREATE_SCHEMA=false`. Freeze that exact baseline and deliver later changes
through controlled, forward-compatible migrations; neither this reference file nor
the application runtime is a production migration runner.

Contract changes require coordinated versions and regression evidence. A category, scope rule, parser, model, prompt, schema, taxonomy, embedding, or chunker behavior change is a controlled release change.

Agent, workflow, and tool YAML resources carry a `definitionHash`. It is the
lowercase SHA-256 of UTF-8 JSON produced with sorted keys and compact
separators after removing `metadata.definitionHash`. The blocking validator
checks the digest, DAG/reference integrity, closed model-facing schemas,
deny-by-default tool policy, exact runtime attribution fields, source pins,
and approval freshness in addition to ordinary JSON Schema validation.
