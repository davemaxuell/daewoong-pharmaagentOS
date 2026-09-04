-- Milestone 1 Agent OS persistence foundation.
-- Apply with the migration identity before deploying case/control-plane APIs.
-- Canonical plans, source pins, policy decisions, artifact content/evidence, plan
-- steps, and case history are immutable; a new version or append-only event is
-- required for every controlled change.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.agent_versions (
  id varchar(36) PRIMARY KEY,
  agent_key varchar(160) NOT NULL,
  version varchar(80) NOT NULL,
  display_name varchar(255) NOT NULL,
  manifest jsonb NOT NULL DEFAULT '{}'::jsonb,
  manifest_sha256 varchar(64) NOT NULL,
  release_status varchar(20) NOT NULL DEFAULT 'DRAFT',
  created_by varchar(255) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_agent_versions_key_version UNIQUE (agent_key, version),
  CONSTRAINT uq_agent_versions_key_manifest_hash UNIQUE (agent_key, manifest_sha256),
  CONSTRAINT ck_agent_versions_manifest_hash_length CHECK (length(manifest_sha256) = 64),
  CONSTRAINT ck_agent_versions_release_status
    CHECK (release_status IN (
      'DRAFT', 'DEVELOPMENT', 'TESTING', 'STAGING',
      'APPROVED', 'PRODUCTION', 'SUSPENDED', 'RETIRED'
    )),
  CONSTRAINT ck_agent_versions_manifest_object CHECK (jsonb_typeof(manifest) = 'object')
);

CREATE TABLE IF NOT EXISTS public.skill_versions (
  id varchar(36) PRIMARY KEY,
  skill_key varchar(160) NOT NULL,
  version varchar(80) NOT NULL,
  display_name varchar(255) NOT NULL,
  manifest jsonb NOT NULL DEFAULT '{}'::jsonb,
  manifest_sha256 varchar(64) NOT NULL,
  release_status varchar(20) NOT NULL DEFAULT 'DRAFT',
  created_by varchar(255) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_skill_versions_key_version UNIQUE (skill_key, version),
  CONSTRAINT uq_skill_versions_key_manifest_hash UNIQUE (skill_key, manifest_sha256),
  CONSTRAINT ck_skill_versions_manifest_hash_length CHECK (length(manifest_sha256) = 64),
  CONSTRAINT ck_skill_versions_release_status
    CHECK (release_status IN (
      'DRAFT', 'DEVELOPMENT', 'TESTING', 'STAGING',
      'APPROVED', 'PRODUCTION', 'SUSPENDED', 'RETIRED'
    )),
  CONSTRAINT ck_skill_versions_manifest_object CHECK (jsonb_typeof(manifest) = 'object')
);

CREATE TABLE IF NOT EXISTS public.tool_versions (
  id varchar(36) PRIMARY KEY,
  tool_key varchar(160) NOT NULL,
  server_key varchar(160) NOT NULL,
  version varchar(80) NOT NULL,
  display_name varchar(255) NOT NULL,
  manifest jsonb NOT NULL DEFAULT '{}'::jsonb,
  manifest_sha256 varchar(64) NOT NULL,
  risk_class varchar(40) NOT NULL DEFAULT 'READ_ONLY_PUBLIC',
  side_effecting boolean NOT NULL DEFAULT false,
  release_status varchar(20) NOT NULL DEFAULT 'DRAFT',
  created_by varchar(255) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_tool_versions_key_version UNIQUE (tool_key, version),
  CONSTRAINT uq_tool_versions_key_manifest_hash UNIQUE (tool_key, manifest_sha256),
  CONSTRAINT ck_tool_versions_manifest_hash_length CHECK (length(manifest_sha256) = 64),
  CONSTRAINT ck_tool_versions_release_status
    CHECK (release_status IN (
      'DRAFT', 'DEVELOPMENT', 'TESTING', 'STAGING',
      'APPROVED', 'PRODUCTION', 'SUSPENDED', 'RETIRED'
    )),
  CONSTRAINT ck_tool_versions_manifest_object CHECK (jsonb_typeof(manifest) = 'object')
);

CREATE TABLE IF NOT EXISTS public.agent_cases (
  id varchar(36) PRIMARY KEY,
  title varchar(300) NOT NULL,
  objective text NOT NULL,
  status varchar(32) NOT NULL DEFAULT 'DRAFT',
  owner_subject varchar(255) NOT NULL,
  workflow_key varchar(160) NOT NULL,
  current_state_hash varchar(64) NOT NULL,
  idempotency_key varchar(255) NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_agent_cases_state_hash_length CHECK (length(current_state_hash) = 64),
  CONSTRAINT ck_agent_cases_status CHECK (
    status IN (
      'DRAFT', 'PLANNING', 'AWAITING_PLAN_APPROVAL', 'READY', 'RUNNING',
      'WAITING_FOR_INPUT', 'WAITING_FOR_REVIEW', 'NEEDS_REVISION', 'COMPLETED',
      'BLOCKED', 'FAILED', 'CANCELLED', 'STALE'
    )
  )
);

CREATE TABLE IF NOT EXISTS public.case_sources (
  id varchar(36) PRIMARY KEY,
  case_id varchar(36) NOT NULL REFERENCES public.agent_cases(id) ON DELETE RESTRICT,
  document_version_id varchar(36) NOT NULL
    REFERENCES public.document_versions(id) ON DELETE RESTRICT,
  source_role varchar(40) NOT NULL DEFAULT 'PRIMARY',
  source_sha256 varchar(64) NOT NULL,
  pinned_by varchar(255) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_case_sources_case_version_role
    UNIQUE (case_id, document_version_id, source_role),
  CONSTRAINT uq_case_sources_bound_identity
    UNIQUE (id, case_id, document_version_id, source_sha256),
  CONSTRAINT ck_case_sources_hash_length CHECK (length(source_sha256) = 64)
);

CREATE TABLE IF NOT EXISTS public.case_events (
  id varchar(36) PRIMARY KEY,
  case_id varchar(36) NOT NULL REFERENCES public.agent_cases(id) ON DELETE RESTRICT,
  sequence integer NOT NULL,
  event_type varchar(80) NOT NULL,
  actor_type varchar(32) NOT NULL,
  actor_id varchar(255) NOT NULL,
  request_id varchar(80) NOT NULL,
  idempotency_key varchar(255) NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  previous_event_hash varchar(64),
  event_hash varchar(64) NOT NULL UNIQUE,
  state_hash varchar(64) NOT NULL,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_case_events_case_sequence UNIQUE (case_id, sequence),
  CONSTRAINT uq_case_events_case_idempotency UNIQUE (case_id, idempotency_key),
  CONSTRAINT ck_case_events_positive_sequence CHECK (sequence >= 1),
  CONSTRAINT ck_case_events_event_hash_length CHECK (length(event_hash) = 64),
  CONSTRAINT ck_case_events_state_hash_length CHECK (length(state_hash) = 64),
  CONSTRAINT ck_case_events_previous_hash_length
    CHECK (previous_event_hash IS NULL OR length(previous_event_hash) = 64),
  CONSTRAINT ck_case_events_payload_object CHECK (jsonb_typeof(payload) = 'object')
);

CREATE TABLE IF NOT EXISTS public.case_plans (
  id varchar(36) PRIMARY KEY,
  case_id varchar(36) NOT NULL REFERENCES public.agent_cases(id) ON DELETE RESTRICT,
  version integer NOT NULL,
  objective text NOT NULL,
  plan_schema_version varchar(80) NOT NULL,
  plan_definition jsonb NOT NULL DEFAULT '{}'::jsonb,
  plan_sha256 varchar(64) NOT NULL,
  based_on_state_hash varchar(64) NOT NULL,
  created_by varchar(255) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_case_plans_case_version UNIQUE (case_id, version),
  CONSTRAINT uq_case_plans_case_hash UNIQUE (case_id, plan_sha256),
  CONSTRAINT uq_case_plans_bound_identity
    UNIQUE (id, case_id, version, plan_sha256, based_on_state_hash),
  CONSTRAINT ck_case_plans_positive_version CHECK (version >= 1),
  CONSTRAINT ck_case_plans_hash_length CHECK (length(plan_sha256) = 64),
  CONSTRAINT ck_case_plans_state_hash_length CHECK (length(based_on_state_hash) = 64),
  CONSTRAINT ck_case_plans_definition_object CHECK (jsonb_typeof(plan_definition) = 'object')
);

CREATE TABLE IF NOT EXISTS public.case_plan_steps (
  id varchar(36) PRIMARY KEY,
  plan_id varchar(36) NOT NULL REFERENCES public.case_plans(id) ON DELETE RESTRICT,
  position integer NOT NULL,
  step_key varchar(160) NOT NULL,
  title varchar(300) NOT NULL,
  instructions text NOT NULL,
  agent_version_id varchar(36) REFERENCES public.agent_versions(id) ON DELETE RESTRICT,
  depends_on jsonb NOT NULL DEFAULT '[]'::jsonb,
  skill_version_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  tool_version_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  output_schema_ref varchar(255) NOT NULL,
  risk_level varchar(40) NOT NULL,
  requires_approval boolean NOT NULL DEFAULT false,
  limits jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_case_plan_steps_plan_position UNIQUE (plan_id, position),
  CONSTRAINT uq_case_plan_steps_plan_key UNIQUE (plan_id, step_key),
  CONSTRAINT ck_case_plan_steps_positive_position CHECK (position >= 1),
  CONSTRAINT ck_case_plan_steps_depends_array CHECK (jsonb_typeof(depends_on) = 'array'),
  CONSTRAINT ck_case_plan_steps_skill_ids_array
    CHECK (jsonb_typeof(skill_version_ids) = 'array'),
  CONSTRAINT ck_case_plan_steps_tool_ids_array
    CHECK (jsonb_typeof(tool_version_ids) = 'array'),
  CONSTRAINT ck_case_plan_steps_limits_object CHECK (jsonb_typeof(limits) = 'object')
);

CREATE TABLE IF NOT EXISTS public.case_runs (
  id varchar(36) PRIMARY KEY,
  case_id varchar(36) NOT NULL REFERENCES public.agent_cases(id) ON DELETE RESTRICT,
  plan_id varchar(36) NOT NULL,
  plan_version integer NOT NULL,
  plan_sha256 varchar(64) NOT NULL,
  bound_state_hash varchar(64) NOT NULL,
  status varchar(32) NOT NULL DEFAULT 'PENDING',
  requested_by varchar(255) NOT NULL,
  idempotency_key varchar(255) NOT NULL UNIQUE,
  checkpoint jsonb NOT NULL DEFAULT '{}'::jsonb,
  error_code varchar(120),
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT fk_case_runs_bound_plan FOREIGN KEY (
    plan_id, case_id, plan_version, plan_sha256, bound_state_hash
  ) REFERENCES public.case_plans (
    id, case_id, version, plan_sha256, based_on_state_hash
  ) ON DELETE RESTRICT,
  CONSTRAINT ck_case_runs_positive_plan_version CHECK (plan_version >= 1),
  CONSTRAINT ck_case_runs_plan_hash_length CHECK (length(plan_sha256) = 64),
  CONSTRAINT ck_case_runs_state_hash_length CHECK (length(bound_state_hash) = 64),
  CONSTRAINT ck_case_runs_status CHECK (
    status IN (
      'PENDING', 'RUNNING', 'PAUSED', 'WAITING_FOR_APPROVAL',
      'COMPLETED', 'BLOCKED', 'FAILED', 'CANCELLED'
    )
  ),
  CONSTRAINT ck_case_runs_checkpoint_object CHECK (jsonb_typeof(checkpoint) = 'object'),
  CONSTRAINT uq_case_runs_id_case UNIQUE (id, case_id)
);

CREATE TABLE IF NOT EXISTS public.policy_decisions (
  id varchar(36) PRIMARY KEY,
  case_id varchar(36) REFERENCES public.agent_cases(id) ON DELETE RESTRICT,
  run_id varchar(36),
  bound_state_hash varchar(64),
  agent_version_id varchar(36)
    REFERENCES public.agent_versions(id) ON DELETE RESTRICT,
  tool_version_id varchar(36)
    REFERENCES public.tool_versions(id) ON DELETE RESTRICT,
  request_id varchar(80) NOT NULL,
  idempotency_key varchar(255) NOT NULL UNIQUE,
  principal_subject varchar(255) NOT NULL,
  action varchar(160) NOT NULL,
  effect varchar(24) NOT NULL,
  policy_key varchar(160) NOT NULL,
  policy_version varchar(80) NOT NULL,
  policy_sha256 varchar(64) NOT NULL,
  input_sha256 varchar(64) NOT NULL,
  decision_sha256 varchar(64) NOT NULL,
  reason_codes jsonb NOT NULL DEFAULT '[]'::jsonb,
  decision_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  evaluated_by varchar(255) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT fk_policy_decisions_run_case FOREIGN KEY (run_id, case_id)
    REFERENCES public.case_runs(id, case_id) ON DELETE RESTRICT,
  CONSTRAINT ck_policy_decisions_case_state_pair CHECK (
    (case_id IS NULL AND bound_state_hash IS NULL)
    OR (case_id IS NOT NULL AND bound_state_hash IS NOT NULL)
  ),
  CONSTRAINT ck_policy_decisions_run_requires_case
    CHECK (run_id IS NULL OR case_id IS NOT NULL),
  CONSTRAINT ck_policy_decisions_state_hash_length
    CHECK (bound_state_hash IS NULL OR length(bound_state_hash) = 64),
  CONSTRAINT ck_policy_decisions_policy_hash_length CHECK (length(policy_sha256) = 64),
  CONSTRAINT ck_policy_decisions_input_hash_length CHECK (length(input_sha256) = 64),
  CONSTRAINT ck_policy_decisions_decision_hash_length CHECK (length(decision_sha256) = 64),
  CONSTRAINT ck_policy_decisions_effect
    CHECK (effect IN ('ALLOW', 'DENY', 'REQUIRE_APPROVAL')),
  CONSTRAINT ck_policy_decisions_reason_codes_array
    CHECK (jsonb_typeof(reason_codes) = 'array'),
  CONSTRAINT ck_policy_decisions_metadata_object
    CHECK (jsonb_typeof(decision_metadata) = 'object')
);

CREATE TABLE IF NOT EXISTS public.tool_invocations (
  id varchar(36) PRIMARY KEY,
  case_id varchar(36) NOT NULL
    REFERENCES public.agent_cases(id) ON DELETE RESTRICT,
  run_id varchar(36) NOT NULL,
  agent_version_id varchar(36) NOT NULL
    REFERENCES public.agent_versions(id) ON DELETE RESTRICT,
  tool_version_id varchar(36) NOT NULL
    REFERENCES public.tool_versions(id) ON DELETE RESTRICT,
  policy_decision_id varchar(36) NOT NULL
    REFERENCES public.policy_decisions(id) ON DELETE RESTRICT,
  request_id varchar(80) NOT NULL UNIQUE,
  idempotency_key varchar(255) NOT NULL,
  principal_subject varchar(255) NOT NULL,
  runtime_service varchar(160) NOT NULL,
  agent_name varchar(160) NOT NULL,
  agent_version varchar(80) NOT NULL,
  tool_name varchar(160) NOT NULL,
  tool_version varchar(80) NOT NULL,
  arguments_sha256 varchar(64) NOT NULL,
  policy_effect varchar(24) NOT NULL,
  status varchar(20) NOT NULL,
  structured_result jsonb NOT NULL DEFAULT '{}'::jsonb,
  result_sha256 varchar(64) NOT NULL,
  provenance jsonb NOT NULL DEFAULT '[]'::jsonb,
  warnings jsonb NOT NULL DEFAULT '[]'::jsonb,
  latency_ms integer NOT NULL,
  started_at timestamptz NOT NULL,
  completed_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT fk_tool_invocations_run_case FOREIGN KEY (run_id, case_id)
    REFERENCES public.case_runs(id, case_id) ON DELETE RESTRICT,
  CONSTRAINT uq_tool_invocations_run_idempotency
    UNIQUE (run_id, idempotency_key),
  CONSTRAINT uq_tool_invocations_policy_decision UNIQUE (policy_decision_id),
  CONSTRAINT ck_tool_invocations_arguments_hash_length
    CHECK (length(arguments_sha256) = 64),
  CONSTRAINT ck_tool_invocations_result_hash_length CHECK (length(result_sha256) = 64),
  CONSTRAINT ck_tool_invocations_policy_effect
    CHECK (policy_effect IN ('ALLOW', 'DENY', 'REQUIRE_APPROVAL')),
  CONSTRAINT ck_tool_invocations_status
    CHECK (status IN ('SUCCEEDED', 'DENIED', 'FAILED')),
  CONSTRAINT ck_tool_invocations_policy_status CHECK (
    (policy_effect = 'ALLOW' AND status IN ('SUCCEEDED', 'FAILED'))
    OR (policy_effect <> 'ALLOW' AND status = 'DENIED')
  ),
  CONSTRAINT ck_tool_invocations_nonnegative_latency CHECK (latency_ms >= 0),
  CONSTRAINT ck_tool_invocations_timestamp_order CHECK (completed_at >= started_at),
  CONSTRAINT ck_tool_invocations_result_object
    CHECK (jsonb_typeof(structured_result) = 'object'),
  CONSTRAINT ck_tool_invocations_provenance_array
    CHECK (jsonb_typeof(provenance) = 'array'),
  CONSTRAINT ck_tool_invocations_warnings_array CHECK (jsonb_typeof(warnings) = 'array')
);

CREATE TABLE IF NOT EXISTS public.artifacts (
  id varchar(36) PRIMARY KEY,
  case_id varchar(36) NOT NULL REFERENCES public.agent_cases(id) ON DELETE RESTRICT,
  artifact_key varchar(160) NOT NULL,
  artifact_type varchar(120) NOT NULL,
  title varchar(300) NOT NULL,
  created_by varchar(255) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_artifacts_case_key UNIQUE (case_id, artifact_key),
  CONSTRAINT uq_artifacts_id_case UNIQUE (id, case_id)
);

CREATE TABLE IF NOT EXISTS public.artifact_versions (
  id varchar(36) PRIMARY KEY,
  artifact_id varchar(36) NOT NULL,
  case_id varchar(36) NOT NULL,
  version integer NOT NULL,
  plan_id varchar(36) NOT NULL,
  plan_version integer NOT NULL,
  plan_sha256 varchar(64) NOT NULL,
  bound_state_hash varchar(64) NOT NULL,
  run_id varchar(36),
  content_schema_version varchar(80) NOT NULL,
  content jsonb NOT NULL DEFAULT '{}'::jsonb,
  content_sha256 varchar(64) NOT NULL,
  evidence_manifest_sha256 varchar(64) NOT NULL,
  status varchar(20) NOT NULL DEFAULT 'DRAFT',
  created_by varchar(255) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT fk_artifact_versions_artifact_case FOREIGN KEY (artifact_id, case_id)
    REFERENCES public.artifacts(id, case_id) ON DELETE RESTRICT,
  CONSTRAINT fk_artifact_versions_bound_plan FOREIGN KEY (
    plan_id, case_id, plan_version, plan_sha256, bound_state_hash
  ) REFERENCES public.case_plans (
    id, case_id, version, plan_sha256, based_on_state_hash
  ) ON DELETE RESTRICT,
  CONSTRAINT fk_artifact_versions_run_case FOREIGN KEY (run_id, case_id)
    REFERENCES public.case_runs(id, case_id) ON DELETE RESTRICT,
  CONSTRAINT uq_artifact_versions_number UNIQUE (artifact_id, version),
  CONSTRAINT uq_artifact_versions_content_evidence
    UNIQUE (artifact_id, content_sha256, evidence_manifest_sha256),
  CONSTRAINT uq_artifact_versions_id_case UNIQUE (id, case_id),
  CONSTRAINT uq_artifact_versions_bound_identity
    UNIQUE (
      id, artifact_id, case_id, version, content_sha256, evidence_manifest_sha256
    ),
  CONSTRAINT ck_artifact_versions_positive_version CHECK (version >= 1),
  CONSTRAINT ck_artifact_versions_positive_plan_version CHECK (plan_version >= 1),
  CONSTRAINT ck_artifact_versions_plan_hash_length CHECK (length(plan_sha256) = 64),
  CONSTRAINT ck_artifact_versions_state_hash_length CHECK (length(bound_state_hash) = 64),
  CONSTRAINT ck_artifact_versions_content_hash_length CHECK (length(content_sha256) = 64),
  CONSTRAINT ck_artifact_versions_evidence_hash_length
    CHECK (length(evidence_manifest_sha256) = 64),
  CONSTRAINT ck_artifact_versions_status
    CHECK (status IN ('DRAFT', 'APPROVED', 'REJECTED')),
  CONSTRAINT ck_artifact_versions_content_object CHECK (jsonb_typeof(content) = 'object')
);

CREATE TABLE IF NOT EXISTS public.artifact_evidence (
  id varchar(36) PRIMARY KEY,
  artifact_version_id varchar(36) NOT NULL,
  case_id varchar(36) NOT NULL,
  case_source_id varchar(36) NOT NULL,
  document_version_id varchar(36) NOT NULL,
  source_sha256 varchar(64) NOT NULL,
  anchor varchar(500) NOT NULL,
  excerpt_sha256 varchar(64) NOT NULL,
  evidence_role varchar(40) NOT NULL DEFAULT 'SUPPORTING',
  created_by varchar(255) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT fk_artifact_evidence_version_case FOREIGN KEY (artifact_version_id, case_id)
    REFERENCES public.artifact_versions(id, case_id) ON DELETE RESTRICT,
  CONSTRAINT fk_artifact_evidence_case_source FOREIGN KEY (
    case_source_id, case_id, document_version_id, source_sha256
  ) REFERENCES public.case_sources (
    id, case_id, document_version_id, source_sha256
  ) ON DELETE RESTRICT,
  CONSTRAINT uq_artifact_evidence_membership
    UNIQUE (artifact_version_id, case_source_id, anchor, excerpt_sha256),
  CONSTRAINT ck_artifact_evidence_source_hash_length CHECK (length(source_sha256) = 64),
  CONSTRAINT ck_artifact_evidence_excerpt_hash_length CHECK (length(excerpt_sha256) = 64),
  CONSTRAINT ck_artifact_evidence_anchor_nonempty CHECK (length(btrim(anchor)) > 0)
);

CREATE TABLE IF NOT EXISTS public.approval_requests (
  id varchar(36) PRIMARY KEY,
  case_id varchar(36) NOT NULL REFERENCES public.agent_cases(id) ON DELETE RESTRICT,
  plan_id varchar(36) NOT NULL,
  plan_version integer NOT NULL,
  plan_sha256 varchar(64) NOT NULL,
  bound_state_hash varchar(64) NOT NULL,
  artifact_version_id varchar(36),
  artifact_id varchar(36),
  artifact_version integer,
  artifact_sha256 varchar(64),
  artifact_evidence_manifest_sha256 varchar(64),
  approval_type varchar(40) NOT NULL,
  status varchar(20) NOT NULL DEFAULT 'PENDING',
  requested_by varchar(255) NOT NULL,
  assigned_reviewer_id varchar(255),
  idempotency_key varchar(255) NOT NULL UNIQUE,
  decision_by varchar(255),
  decision_reason text,
  decided_at timestamptz,
  expires_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT fk_approval_requests_bound_plan FOREIGN KEY (
    plan_id, case_id, plan_version, plan_sha256, bound_state_hash
  ) REFERENCES public.case_plans (
    id, case_id, version, plan_sha256, based_on_state_hash
  ) ON DELETE RESTRICT,
  CONSTRAINT fk_approval_requests_artifact_target FOREIGN KEY (
    artifact_version_id, artifact_id, case_id, artifact_version, artifact_sha256,
    artifact_evidence_manifest_sha256
  ) REFERENCES public.artifact_versions (
    id, artifact_id, case_id, version, content_sha256, evidence_manifest_sha256
  ) ON DELETE RESTRICT,
  CONSTRAINT ck_approval_requests_positive_plan_version CHECK (plan_version >= 1),
  CONSTRAINT ck_approval_requests_plan_hash_length CHECK (length(plan_sha256) = 64),
  CONSTRAINT ck_approval_requests_state_hash_length CHECK (length(bound_state_hash) = 64),
  CONSTRAINT ck_approval_requests_artifact_target_complete CHECK (
    (
      artifact_version_id IS NULL AND artifact_id IS NULL
      AND artifact_version IS NULL AND artifact_sha256 IS NULL
      AND artifact_evidence_manifest_sha256 IS NULL
    ) OR (
      artifact_version_id IS NOT NULL AND artifact_id IS NOT NULL
      AND artifact_version IS NOT NULL AND artifact_sha256 IS NOT NULL
      AND artifact_evidence_manifest_sha256 IS NOT NULL
    )
  ),
  CONSTRAINT ck_approval_requests_artifact_target_type CHECK (
    (approval_type = 'ARTIFACT_APPROVAL' AND artifact_version_id IS NOT NULL)
    OR (approval_type <> 'ARTIFACT_APPROVAL' AND artifact_version_id IS NULL)
  ),
  CONSTRAINT ck_approval_requests_type
    CHECK (approval_type IN ('PLAN_APPROVAL', 'ARTIFACT_APPROVAL')),
  CONSTRAINT ck_approval_requests_positive_artifact_version
    CHECK (artifact_version IS NULL OR artifact_version >= 1),
  CONSTRAINT ck_approval_requests_artifact_hash_length
    CHECK (artifact_sha256 IS NULL OR length(artifact_sha256) = 64),
  CONSTRAINT ck_approval_requests_artifact_evidence_hash_length CHECK (
    artifact_evidence_manifest_sha256 IS NULL
    OR length(artifact_evidence_manifest_sha256) = 64
  ),
  CONSTRAINT ck_approval_requests_status
    CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'CANCELLED', 'EXPIRED')),
  CONSTRAINT ck_approval_requests_decision_metadata CHECK (
    status NOT IN ('APPROVED', 'REJECTED')
    OR (decision_by IS NOT NULL AND decided_at IS NOT NULL)
  ),
  CONSTRAINT ck_approval_requests_expiry_order CHECK (expires_at > created_at)
);

CREATE INDEX IF NOT EXISTS ix_agent_versions_agent_key
  ON public.agent_versions (agent_key);
CREATE INDEX IF NOT EXISTS ix_agent_versions_manifest_sha256
  ON public.agent_versions (manifest_sha256);
CREATE INDEX IF NOT EXISTS ix_agent_versions_release_status
  ON public.agent_versions (release_status);
CREATE INDEX IF NOT EXISTS ix_skill_versions_skill_key
  ON public.skill_versions (skill_key);
CREATE INDEX IF NOT EXISTS ix_skill_versions_manifest_sha256
  ON public.skill_versions (manifest_sha256);
CREATE INDEX IF NOT EXISTS ix_skill_versions_release_status
  ON public.skill_versions (release_status);
CREATE INDEX IF NOT EXISTS ix_tool_versions_tool_key
  ON public.tool_versions (tool_key);
CREATE INDEX IF NOT EXISTS ix_tool_versions_server_key
  ON public.tool_versions (server_key);
CREATE INDEX IF NOT EXISTS ix_tool_versions_manifest_sha256
  ON public.tool_versions (manifest_sha256);
CREATE INDEX IF NOT EXISTS ix_tool_versions_release_status
  ON public.tool_versions (release_status);
CREATE INDEX IF NOT EXISTS ix_agent_cases_owner_subject
  ON public.agent_cases (owner_subject);
CREATE INDEX IF NOT EXISTS ix_agent_cases_status
  ON public.agent_cases (status);
CREATE INDEX IF NOT EXISTS ix_agent_cases_owner_status
  ON public.agent_cases (owner_subject, status);
CREATE INDEX IF NOT EXISTS ix_case_sources_case_id
  ON public.case_sources (case_id);
CREATE INDEX IF NOT EXISTS ix_case_sources_document_version_id
  ON public.case_sources (document_version_id);
CREATE INDEX IF NOT EXISTS ix_case_events_case_occurred
  ON public.case_events (case_id, occurred_at);
CREATE INDEX IF NOT EXISTS ix_case_events_event_type
  ON public.case_events (event_type);
CREATE INDEX IF NOT EXISTS ix_case_events_request_id
  ON public.case_events (request_id);
CREATE INDEX IF NOT EXISTS ix_case_events_occurred_at
  ON public.case_events (occurred_at);
CREATE INDEX IF NOT EXISTS ix_case_plans_case_id
  ON public.case_plans (case_id);
CREATE INDEX IF NOT EXISTS ix_case_plan_steps_plan_id
  ON public.case_plan_steps (plan_id);
CREATE INDEX IF NOT EXISTS ix_case_plan_steps_agent_version_id
  ON public.case_plan_steps (agent_version_id);
CREATE INDEX IF NOT EXISTS ix_case_runs_case_status
  ON public.case_runs (case_id, status);
CREATE INDEX IF NOT EXISTS ix_case_runs_plan_id
  ON public.case_runs (plan_id);
CREATE INDEX IF NOT EXISTS ix_case_runs_status
  ON public.case_runs (status);
CREATE INDEX IF NOT EXISTS ix_policy_decisions_case_id
  ON public.policy_decisions (case_id);
CREATE INDEX IF NOT EXISTS ix_policy_decisions_run_id
  ON public.policy_decisions (run_id);
CREATE INDEX IF NOT EXISTS ix_policy_decisions_agent_version_id
  ON public.policy_decisions (agent_version_id);
CREATE INDEX IF NOT EXISTS ix_policy_decisions_tool_version_id
  ON public.policy_decisions (tool_version_id);
CREATE INDEX IF NOT EXISTS ix_policy_decisions_request_id
  ON public.policy_decisions (request_id);
CREATE INDEX IF NOT EXISTS ix_policy_decisions_principal_subject
  ON public.policy_decisions (principal_subject);
CREATE INDEX IF NOT EXISTS ix_policy_decisions_action
  ON public.policy_decisions (action);
CREATE INDEX IF NOT EXISTS ix_policy_decisions_effect
  ON public.policy_decisions (effect);
CREATE INDEX IF NOT EXISTS ix_policy_decisions_decision_sha256
  ON public.policy_decisions (decision_sha256);
CREATE INDEX IF NOT EXISTS ix_policy_decisions_case_created
  ON public.policy_decisions (case_id, created_at);
CREATE INDEX IF NOT EXISTS ix_policy_decisions_run_created
  ON public.policy_decisions (run_id, created_at);
CREATE INDEX IF NOT EXISTS ix_tool_invocations_case_id
  ON public.tool_invocations (case_id);
CREATE INDEX IF NOT EXISTS ix_tool_invocations_run_id
  ON public.tool_invocations (run_id);
CREATE INDEX IF NOT EXISTS ix_tool_invocations_agent_version_id
  ON public.tool_invocations (agent_version_id);
CREATE INDEX IF NOT EXISTS ix_tool_invocations_tool_version_id
  ON public.tool_invocations (tool_version_id);
CREATE INDEX IF NOT EXISTS ix_tool_invocations_policy_decision_id
  ON public.tool_invocations (policy_decision_id);
CREATE INDEX IF NOT EXISTS ix_tool_invocations_principal_subject
  ON public.tool_invocations (principal_subject);
CREATE INDEX IF NOT EXISTS ix_tool_invocations_tool_name
  ON public.tool_invocations (tool_name);
CREATE INDEX IF NOT EXISTS ix_tool_invocations_policy_effect
  ON public.tool_invocations (policy_effect);
CREATE INDEX IF NOT EXISTS ix_tool_invocations_status
  ON public.tool_invocations (status);
CREATE INDEX IF NOT EXISTS ix_tool_invocations_result_sha256
  ON public.tool_invocations (result_sha256);
CREATE INDEX IF NOT EXISTS ix_tool_invocations_case_created
  ON public.tool_invocations (case_id, created_at);
CREATE INDEX IF NOT EXISTS ix_tool_invocations_run_created
  ON public.tool_invocations (run_id, created_at);
CREATE INDEX IF NOT EXISTS ix_tool_invocations_tool_status
  ON public.tool_invocations (tool_name, status);
CREATE INDEX IF NOT EXISTS ix_artifacts_case_id
  ON public.artifacts (case_id);
CREATE INDEX IF NOT EXISTS ix_artifacts_artifact_type
  ON public.artifacts (artifact_type);
CREATE INDEX IF NOT EXISTS ix_artifact_versions_artifact_id
  ON public.artifact_versions (artifact_id);
CREATE INDEX IF NOT EXISTS ix_artifact_versions_case_id
  ON public.artifact_versions (case_id);
CREATE INDEX IF NOT EXISTS ix_artifact_versions_plan_id
  ON public.artifact_versions (plan_id);
CREATE INDEX IF NOT EXISTS ix_artifact_versions_run_id
  ON public.artifact_versions (run_id);
CREATE INDEX IF NOT EXISTS ix_artifact_versions_content_sha256
  ON public.artifact_versions (content_sha256);
CREATE INDEX IF NOT EXISTS ix_artifact_versions_status
  ON public.artifact_versions (status);
CREATE INDEX IF NOT EXISTS ix_artifact_versions_case_status
  ON public.artifact_versions (case_id, status);
CREATE INDEX IF NOT EXISTS ix_artifact_evidence_artifact_version_id
  ON public.artifact_evidence (artifact_version_id);
CREATE INDEX IF NOT EXISTS ix_artifact_evidence_case_id
  ON public.artifact_evidence (case_id);
CREATE INDEX IF NOT EXISTS ix_artifact_evidence_case_source_id
  ON public.artifact_evidence (case_source_id);
CREATE INDEX IF NOT EXISTS ix_artifact_evidence_document_version_id
  ON public.artifact_evidence (document_version_id);
CREATE INDEX IF NOT EXISTS ix_approval_requests_reviewer_status
  ON public.approval_requests (assigned_reviewer_id, status);
CREATE INDEX IF NOT EXISTS ix_approval_requests_case_id
  ON public.approval_requests (case_id);
CREATE INDEX IF NOT EXISTS ix_approval_requests_plan_id
  ON public.approval_requests (plan_id);
CREATE INDEX IF NOT EXISTS ix_approval_requests_approval_type
  ON public.approval_requests (approval_type);
CREATE INDEX IF NOT EXISTS ix_approval_requests_status
  ON public.approval_requests (status);
CREATE INDEX IF NOT EXISTS ix_approval_requests_assigned_reviewer_id
  ON public.approval_requests (assigned_reviewer_id);
CREATE INDEX IF NOT EXISTS ix_approval_requests_artifact_version_id
  ON public.approval_requests (artifact_version_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_approval_requests_pending_artifact
  ON public.approval_requests (artifact_version_id)
  WHERE artifact_version_id IS NOT NULL AND status = 'PENDING';

CREATE OR REPLACE FUNCTION public.pharma_agent_reject_immutable_change()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION '% rows are append-only/immutable; create a new version or event', TG_TABLE_NAME
    USING ERRCODE = '55000';
END;
$$;

CREATE OR REPLACE FUNCTION public.pharma_agent_validate_source_pin()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  retained_hash varchar(64);
BEGIN
  SELECT canonical_hash INTO retained_hash
  FROM public.document_versions
  WHERE id = NEW.document_version_id
  FOR SHARE;

  IF retained_hash IS NULL OR retained_hash IS DISTINCT FROM NEW.source_sha256 THEN
    RAISE EXCEPTION 'source pin hash does not match retained document version'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.pharma_agent_protect_pinned_document_version()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  -- A case source binds citations to the full retained evidence payload, not
  -- merely to canonical text. Discovery may still refresh last_seen_at, but a
  -- parser or operator must never replace anchors/provenance underneath a pin.
  IF EXISTS (
    SELECT 1
    FROM public.case_sources
    WHERE document_version_id = OLD.id
  ) AND (to_jsonb(NEW) - 'last_seen_at') IS DISTINCT FROM
        (to_jsonb(OLD) - 'last_seen_at') THEN
    RAISE EXCEPTION 'case-pinned document version evidence is immutable'
      USING ERRCODE = '55000';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.pharma_agent_validate_policy_binding()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.case_id IS NOT NULL AND NOT EXISTS (
    SELECT 1
    FROM public.agent_cases AS c
    WHERE c.id = NEW.case_id
      AND (
        c.current_state_hash = NEW.bound_state_hash
        OR EXISTS (
          SELECT 1 FROM public.case_events AS e
          WHERE e.case_id = c.id AND e.state_hash = NEW.bound_state_hash
        )
        OR EXISTS (
          SELECT 1 FROM public.case_plans AS p
          WHERE p.case_id = c.id AND p.based_on_state_hash = NEW.bound_state_hash
        )
      )
  ) THEN
    RAISE EXCEPTION 'policy decision state hash is not attributable to the case'
      USING ERRCODE = '23514';
  END IF;

  IF NEW.run_id IS NOT NULL AND NOT EXISTS (
    SELECT 1
    FROM public.case_runs AS r
    WHERE r.id = NEW.run_id
      AND r.case_id = NEW.case_id
      AND r.bound_state_hash = NEW.bound_state_hash
  ) THEN
    RAISE EXCEPTION 'policy decision run binding does not match case state'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.pharma_agent_validate_tool_invocation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  PERFORM 1
  FROM public.case_runs AS r
  JOIN public.agent_cases AS c ON c.id = r.case_id
  WHERE r.id = NEW.run_id
    AND r.case_id = NEW.case_id
    AND r.requested_by = NEW.principal_subject
    AND r.status = 'RUNNING'
    AND r.bound_state_hash = c.current_state_hash
  FOR SHARE OF r, c;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'tool invocation does not match its active run principal'
      USING ERRCODE = '23514';
  END IF;
  PERFORM 1
  FROM public.agent_versions AS a
  WHERE a.id = NEW.agent_version_id
    AND a.agent_key = NEW.agent_name
    AND a.version = NEW.agent_version
    AND a.release_status IN ('APPROVED', 'PRODUCTION')
  FOR SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'tool invocation agent identity does not match registry'
      USING ERRCODE = '23514';
  END IF;
  PERFORM 1
  FROM public.tool_versions AS t
  WHERE t.id = NEW.tool_version_id
    AND t.tool_key = NEW.tool_name
    AND t.version = NEW.tool_version
    AND t.release_status IN ('APPROVED', 'PRODUCTION')
  FOR SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'tool invocation tool identity does not match registry'
      USING ERRCODE = '23514';
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM public.policy_decisions AS p
    WHERE p.id = NEW.policy_decision_id
      AND p.case_id = NEW.case_id
      AND p.run_id = NEW.run_id
      AND p.agent_version_id = NEW.agent_version_id
      AND p.tool_version_id = NEW.tool_version_id
      AND p.effect = NEW.policy_effect
      AND p.principal_subject = NEW.principal_subject
      AND p.action = NEW.tool_name
      AND p.request_id = NEW.request_id
      AND p.input_sha256 = NEW.arguments_sha256
  ) THEN
    RAISE EXCEPTION 'tool invocation policy decision attribution is invalid'
      USING ERRCODE = '23514';
  END IF;
  IF NEW.structured_result->>'request_id' IS DISTINCT FROM NEW.request_id
     OR NEW.structured_result->>'tool_name' IS DISTINCT FROM NEW.tool_name
     OR NEW.structured_result->>'tool_version' IS DISTINCT FROM NEW.tool_version
     OR (
       NEW.status = 'SUCCEEDED'
       AND NEW.structured_result->>'status' IS DISTINCT FROM 'success'
     ) OR (
       NEW.status <> 'SUCCEEDED'
       AND NEW.structured_result->>'status' IS DISTINCT FROM 'error'
     ) THEN
    RAISE EXCEPTION 'tool invocation result identity does not match its envelope'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.pharma_agent_validate_event_chain()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  prior_sequence integer;
  prior_hash varchar(64);
BEGIN
  -- Serialize event appenders on the case row before checking the prior link.
  PERFORM 1 FROM public.agent_cases WHERE id = NEW.case_id FOR UPDATE;
  SELECT sequence, event_hash INTO prior_sequence, prior_hash
  FROM public.case_events
  WHERE case_id = NEW.case_id
  ORDER BY sequence DESC
  LIMIT 1;

  IF prior_sequence IS NULL THEN
    IF NEW.sequence <> 1 OR NEW.previous_event_hash IS NOT NULL THEN
      RAISE EXCEPTION 'first case event must use sequence 1 and no previous hash'
        USING ERRCODE = '23514';
    END IF;
  ELSIF NEW.sequence <> prior_sequence + 1 OR NEW.previous_event_hash IS DISTINCT FROM prior_hash THEN
    RAISE EXCEPTION 'case event does not extend the current hash chain'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.pharma_agent_protect_registry_payload()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF (to_jsonb(NEW) - 'release_status') IS DISTINCT FROM
     (to_jsonb(OLD) - 'release_status') THEN
    RAISE EXCEPTION 'registry version payloads are immutable'
      USING ERRCODE = '55000';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.pharma_agent_guard_plan_step_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM public.approval_requests WHERE plan_id = NEW.plan_id
  ) OR EXISTS (
    SELECT 1 FROM public.case_runs WHERE plan_id = NEW.plan_id
  ) THEN
    RAISE EXCEPTION 'plan steps cannot be appended after approval or execution binding'
      USING ERRCODE = '55000';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.pharma_agent_validate_artifact_version_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  prior_version integer;
BEGIN
  -- Serialize version allocation on the immutable artifact grouping.
  PERFORM 1 FROM public.artifacts WHERE id = NEW.artifact_id FOR UPDATE;
  SELECT max(version) INTO prior_version
  FROM public.artifact_versions
  WHERE artifact_id = NEW.artifact_id;

  IF NEW.status <> 'DRAFT' THEN
    RAISE EXCEPTION 'new artifact versions must begin in DRAFT'
      USING ERRCODE = '23514';
  END IF;
  IF (prior_version IS NULL AND NEW.version <> 1)
     OR (prior_version IS NOT NULL AND NEW.version <> prior_version + 1) THEN
    RAISE EXCEPTION 'artifact version must append the next version number'
      USING ERRCODE = '23514';
  END IF;
  IF NEW.run_id IS NOT NULL AND NOT EXISTS (
    SELECT 1
    FROM public.case_runs AS r
    WHERE r.id = NEW.run_id
      AND r.case_id = NEW.case_id
      AND r.plan_id = NEW.plan_id
      AND r.plan_version = NEW.plan_version
      AND r.plan_sha256 = NEW.plan_sha256
      AND r.bound_state_hash = NEW.bound_state_hash
  ) THEN
    RAISE EXCEPTION 'artifact run provenance does not match its plan binding'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.pharma_agent_protect_artifact_version()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF OLD.status IN ('APPROVED', 'REJECTED') AND NEW IS DISTINCT FROM OLD THEN
    RAISE EXCEPTION 'terminal artifact versions are immutable'
      USING ERRCODE = '55000';
  END IF;
  IF (to_jsonb(NEW) - 'status') IS DISTINCT FROM
     (to_jsonb(OLD) - 'status') THEN
    RAISE EXCEPTION 'artifact version content and provenance are immutable'
      USING ERRCODE = '55000';
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status THEN
    IF OLD.status <> 'DRAFT' OR NEW.status NOT IN ('APPROVED', 'REJECTED') THEN
      RAISE EXCEPTION 'invalid artifact version status transition'
        USING ERRCODE = '23514';
    END IF;
    IF NOT EXISTS (
      SELECT 1
      FROM public.approval_requests AS a
      WHERE a.artifact_version_id = NEW.id
        AND a.artifact_id = NEW.artifact_id
        AND a.case_id = NEW.case_id
        AND a.artifact_version = NEW.version
        AND a.artifact_sha256 = NEW.content_sha256
        AND a.artifact_evidence_manifest_sha256 = NEW.evidence_manifest_sha256
        AND a.approval_type = 'ARTIFACT_APPROVAL'
        AND a.status = NEW.status
    ) THEN
      RAISE EXCEPTION 'artifact status requires a matching terminal review decision'
        USING ERRCODE = '23514';
    END IF;
    IF NEW.status = 'APPROVED' AND NOT EXISTS (
      SELECT 1
      FROM public.agent_cases AS c
      WHERE c.id = NEW.case_id AND c.current_state_hash = NEW.bound_state_hash
    ) THEN
      RAISE EXCEPTION 'artifact approval publication references a stale case state'
        USING ERRCODE = '23514';
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.pharma_agent_guard_artifact_evidence_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  artifact_status varchar(20);
  retained_hash varchar(64);
  retained_excerpt text;
  retained_excerpt_sha256 varchar(64);
BEGIN
  -- Serialize evidence appenders against review binding. The approval trigger
  -- independently recomputes the canonical manifest before accepting review.
  SELECT status INTO artifact_status
  FROM public.artifact_versions
  WHERE id = NEW.artifact_version_id AND case_id = NEW.case_id
  FOR UPDATE;

  IF artifact_status IS DISTINCT FROM 'DRAFT' OR EXISTS (
    SELECT 1
    FROM public.approval_requests
    WHERE artifact_version_id = NEW.artifact_version_id
  ) THEN
    RAISE EXCEPTION 'artifact evidence cannot be appended after review binding'
      USING ERRCODE = '55000';
  END IF;

  SELECT canonical_hash INTO retained_hash
  FROM public.document_versions
  WHERE id = NEW.document_version_id;
  IF retained_hash IS NULL OR retained_hash IS DISTINCT FROM NEW.source_sha256 THEN
    RAISE EXCEPTION 'artifact evidence hash does not match retained document version'
      USING ERRCODE = '23514';
  END IF;
  SELECT anchor_value->>'text' INTO retained_excerpt
  FROM public.document_versions AS version,
       LATERAL json_array_elements(version.source_anchors) AS anchor_value
  WHERE version.id = NEW.document_version_id
    AND anchor_value->>'anchor' = NEW.anchor
  LIMIT 1;
  IF retained_excerpt IS NULL THEN
    RAISE EXCEPTION 'artifact evidence anchor is absent from retained document version'
      USING ERRCODE = '23514';
  END IF;
  retained_excerpt_sha256 := encode(
    digest(convert_to(retained_excerpt, 'UTF8'), 'sha256'),
    'hex'
  );
  IF retained_excerpt_sha256 IS DISTINCT FROM NEW.excerpt_sha256 THEN
    RAISE EXCEPTION 'artifact evidence excerpt hash does not match retained anchor text'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.pharma_agent_frame_manifest_field(field_value text)
RETURNS text
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
  SELECT octet_length(convert_to(field_value, 'UTF8'))::text || ':' || field_value;
$$;

CREATE OR REPLACE FUNCTION public.pharma_agent_artifact_evidence_manifest_sha256(
  target_artifact_version_id varchar(36)
)
RETURNS varchar(64)
LANGUAGE sql
STABLE
PARALLEL SAFE
AS $$
  SELECT encode(
    digest(
      convert_to(
        COALESCE(
          string_agg(
            public.pharma_agent_frame_manifest_field(e.case_source_id) ||
            public.pharma_agent_frame_manifest_field(e.document_version_id) ||
            public.pharma_agent_frame_manifest_field(e.source_sha256) ||
            public.pharma_agent_frame_manifest_field(e.anchor) ||
            public.pharma_agent_frame_manifest_field(e.excerpt_sha256) ||
            public.pharma_agent_frame_manifest_field(e.evidence_role),
            '' ORDER BY
              e.case_source_id COLLATE "C",
              e.document_version_id COLLATE "C",
              e.source_sha256 COLLATE "C",
              e.anchor COLLATE "C",
              e.excerpt_sha256 COLLATE "C",
              e.evidence_role COLLATE "C"
          ),
          ''
        ),
        'UTF8'
      ),
      'sha256'
    ),
    'hex'
  )
  FROM public.artifact_evidence AS e
  WHERE e.artifact_version_id = target_artifact_version_id;
$$;

CREATE OR REPLACE FUNCTION public.pharma_agent_protect_run_binding()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.case_id IS DISTINCT FROM OLD.case_id
     OR NEW.plan_id IS DISTINCT FROM OLD.plan_id
     OR NEW.plan_version IS DISTINCT FROM OLD.plan_version
     OR NEW.plan_sha256 IS DISTINCT FROM OLD.plan_sha256
     OR NEW.bound_state_hash IS DISTINCT FROM OLD.bound_state_hash
     OR NEW.requested_by IS DISTINCT FROM OLD.requested_by
     OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
     OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
    RAISE EXCEPTION 'run plan bindings are immutable'
      USING ERRCODE = '55000';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.pharma_agent_validate_run_state()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  live_state_hash varchar(64);
BEGIN
  SELECT current_state_hash INTO live_state_hash
  FROM public.agent_cases
  WHERE id = NEW.case_id;

  IF live_state_hash IS DISTINCT FROM NEW.bound_state_hash THEN
    RAISE EXCEPTION 'run references a stale case state'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.pharma_agent_protect_approval_binding()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF OLD.status <> 'PENDING' AND NEW IS DISTINCT FROM OLD THEN
    RAISE EXCEPTION 'terminal approval decisions are immutable'
      USING ERRCODE = '55000';
  END IF;
  IF NEW.case_id IS DISTINCT FROM OLD.case_id
     OR NEW.plan_id IS DISTINCT FROM OLD.plan_id
     OR NEW.plan_version IS DISTINCT FROM OLD.plan_version
     OR NEW.plan_sha256 IS DISTINCT FROM OLD.plan_sha256
     OR NEW.bound_state_hash IS DISTINCT FROM OLD.bound_state_hash
     OR NEW.artifact_version_id IS DISTINCT FROM OLD.artifact_version_id
     OR NEW.artifact_id IS DISTINCT FROM OLD.artifact_id
     OR NEW.artifact_version IS DISTINCT FROM OLD.artifact_version
     OR NEW.artifact_sha256 IS DISTINCT FROM OLD.artifact_sha256
     OR NEW.artifact_evidence_manifest_sha256 IS DISTINCT FROM
        OLD.artifact_evidence_manifest_sha256
     OR NEW.approval_type IS DISTINCT FROM OLD.approval_type
     OR NEW.requested_by IS DISTINCT FROM OLD.requested_by
     OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
     OR NEW.expires_at IS DISTINCT FROM OLD.expires_at
     OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
    RAISE EXCEPTION 'approval scope bindings are immutable'
      USING ERRCODE = '55000';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.pharma_agent_validate_approval_state()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  live_state_hash varchar(64);
  artifact_status varchar(20);
  live_evidence_manifest_sha256 varchar(64);
BEGIN
  IF TG_OP = 'INSERT' AND NEW.status <> 'PENDING' THEN
    RAISE EXCEPTION 'new approval requests must begin in PENDING'
      USING ERRCODE = '23514';
  END IF;
  IF TG_OP = 'INSERT' AND NEW.expires_at <= clock_timestamp() THEN
    RAISE EXCEPTION 'new approval requests require a future expiry'
      USING ERRCODE = '23514';
  END IF;

  IF TG_OP = 'UPDATE'
     AND OLD.status = 'PENDING'
     AND NEW.status IN ('APPROVED', 'REJECTED')
     AND clock_timestamp() >= NEW.expires_at THEN
    RAISE EXCEPTION 'expired approval requests cannot receive a review decision'
      USING ERRCODE = '23514';
  END IF;

  IF NEW.artifact_version_id IS NOT NULL THEN
    -- Serialize review binding against evidence appenders. Once this row exists,
    -- the evidence-insert guard freezes membership for the reviewed version.
    SELECT status INTO artifact_status
    FROM public.artifact_versions
    WHERE id = NEW.artifact_version_id AND case_id = NEW.case_id
    FOR UPDATE;
    IF artifact_status IS DISTINCT FROM 'DRAFT' THEN
      RAISE EXCEPTION 'artifact approval must target a DRAFT version'
        USING ERRCODE = '23514';
    END IF;
    IF NOT EXISTS (
      SELECT 1
      FROM public.artifact_evidence
      WHERE artifact_version_id = NEW.artifact_version_id
    ) THEN
      RAISE EXCEPTION 'artifact approval requires at least one evidence member'
        USING ERRCODE = '23514';
    END IF;
    live_evidence_manifest_sha256 :=
      public.pharma_agent_artifact_evidence_manifest_sha256(NEW.artifact_version_id);
    IF live_evidence_manifest_sha256 IS DISTINCT FROM
       NEW.artifact_evidence_manifest_sha256 THEN
      RAISE EXCEPTION 'artifact approval evidence manifest does not match membership'
        USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'INSERT' AND EXISTS (
      SELECT 1
      FROM public.approval_requests AS prior
      WHERE prior.artifact_version_id = NEW.artifact_version_id
        AND prior.status IN ('APPROVED', 'REJECTED')
    ) THEN
      RAISE EXCEPTION 'artifact version already has a terminal review decision'
        USING ERRCODE = '23514';
    END IF;
  END IF;

  IF TG_OP = 'INSERT' THEN
    SELECT current_state_hash INTO live_state_hash
    FROM public.agent_cases
    WHERE id = NEW.case_id;
  ELSIF NEW.status = 'APPROVED' AND OLD.status <> 'APPROVED' THEN
    SELECT current_state_hash INTO live_state_hash
    FROM public.agent_cases
    WHERE id = NEW.case_id;
  ELSE
    RETURN NEW;
  END IF;

  IF live_state_hash IS DISTINCT FROM NEW.bound_state_hash THEN
    RAISE EXCEPTION 'approval references a stale case state'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_case_sources_validate_pin ON public.case_sources;
CREATE TRIGGER trg_case_sources_validate_pin
BEFORE INSERT ON public.case_sources
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_validate_source_pin();
DROP TRIGGER IF EXISTS trg_case_sources_immutable ON public.case_sources;
CREATE TRIGGER trg_case_sources_immutable
BEFORE UPDATE OR DELETE ON public.case_sources
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_reject_immutable_change();
DROP TRIGGER IF EXISTS trg_document_versions_protect_case_pins
  ON public.document_versions;
CREATE TRIGGER trg_document_versions_protect_case_pins
BEFORE UPDATE ON public.document_versions
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_protect_pinned_document_version();

DROP TRIGGER IF EXISTS trg_case_events_validate_chain ON public.case_events;
CREATE TRIGGER trg_case_events_validate_chain
BEFORE INSERT ON public.case_events
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_validate_event_chain();
DROP TRIGGER IF EXISTS trg_case_events_append_only ON public.case_events;
CREATE TRIGGER trg_case_events_append_only
BEFORE UPDATE OR DELETE ON public.case_events
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_reject_immutable_change();

DROP TRIGGER IF EXISTS trg_case_plans_immutable ON public.case_plans;
CREATE TRIGGER trg_case_plans_immutable
BEFORE UPDATE OR DELETE ON public.case_plans
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_reject_immutable_change();
DROP TRIGGER IF EXISTS trg_case_plan_steps_immutable ON public.case_plan_steps;
CREATE TRIGGER trg_case_plan_steps_immutable
BEFORE UPDATE OR DELETE ON public.case_plan_steps
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_reject_immutable_change();
DROP TRIGGER IF EXISTS trg_case_plan_steps_guard_insert ON public.case_plan_steps;
CREATE TRIGGER trg_case_plan_steps_guard_insert
BEFORE INSERT ON public.case_plan_steps
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_guard_plan_step_insert();

DROP TRIGGER IF EXISTS trg_agent_versions_protect_payload ON public.agent_versions;
CREATE TRIGGER trg_agent_versions_protect_payload
BEFORE UPDATE ON public.agent_versions
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_protect_registry_payload();
DROP TRIGGER IF EXISTS trg_agent_versions_prevent_delete ON public.agent_versions;
CREATE TRIGGER trg_agent_versions_prevent_delete
BEFORE DELETE ON public.agent_versions
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_reject_immutable_change();
DROP TRIGGER IF EXISTS trg_skill_versions_protect_payload ON public.skill_versions;
CREATE TRIGGER trg_skill_versions_protect_payload
BEFORE UPDATE ON public.skill_versions
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_protect_registry_payload();
DROP TRIGGER IF EXISTS trg_skill_versions_prevent_delete ON public.skill_versions;
CREATE TRIGGER trg_skill_versions_prevent_delete
BEFORE DELETE ON public.skill_versions
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_reject_immutable_change();
DROP TRIGGER IF EXISTS trg_tool_versions_protect_payload ON public.tool_versions;
CREATE TRIGGER trg_tool_versions_protect_payload
BEFORE UPDATE ON public.tool_versions
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_protect_registry_payload();
DROP TRIGGER IF EXISTS trg_tool_versions_prevent_delete ON public.tool_versions;
CREATE TRIGGER trg_tool_versions_prevent_delete
BEFORE DELETE ON public.tool_versions
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_reject_immutable_change();

DROP TRIGGER IF EXISTS trg_case_runs_protect_binding ON public.case_runs;
CREATE TRIGGER trg_case_runs_protect_binding
BEFORE UPDATE ON public.case_runs
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_protect_run_binding();
DROP TRIGGER IF EXISTS trg_case_runs_validate_state ON public.case_runs;
CREATE TRIGGER trg_case_runs_validate_state
BEFORE INSERT ON public.case_runs
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_validate_run_state();

DROP TRIGGER IF EXISTS trg_policy_decisions_validate_binding ON public.policy_decisions;
CREATE TRIGGER trg_policy_decisions_validate_binding
BEFORE INSERT ON public.policy_decisions
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_validate_policy_binding();
DROP TRIGGER IF EXISTS trg_policy_decisions_append_only ON public.policy_decisions;
CREATE TRIGGER trg_policy_decisions_append_only
BEFORE UPDATE OR DELETE ON public.policy_decisions
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_reject_immutable_change();

DROP TRIGGER IF EXISTS trg_tool_invocations_validate ON public.tool_invocations;
CREATE TRIGGER trg_tool_invocations_validate
BEFORE INSERT ON public.tool_invocations
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_validate_tool_invocation();
DROP TRIGGER IF EXISTS trg_tool_invocations_append_only ON public.tool_invocations;
CREATE TRIGGER trg_tool_invocations_append_only
BEFORE UPDATE OR DELETE ON public.tool_invocations
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_reject_immutable_change();

DROP TRIGGER IF EXISTS trg_artifacts_immutable ON public.artifacts;
CREATE TRIGGER trg_artifacts_immutable
BEFORE UPDATE OR DELETE ON public.artifacts
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_reject_immutable_change();
DROP TRIGGER IF EXISTS trg_artifact_versions_validate_insert ON public.artifact_versions;
CREATE TRIGGER trg_artifact_versions_validate_insert
BEFORE INSERT ON public.artifact_versions
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_validate_artifact_version_insert();
DROP TRIGGER IF EXISTS trg_artifact_versions_protect ON public.artifact_versions;
CREATE TRIGGER trg_artifact_versions_protect
BEFORE UPDATE ON public.artifact_versions
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_protect_artifact_version();
DROP TRIGGER IF EXISTS trg_artifact_versions_prevent_delete ON public.artifact_versions;
CREATE TRIGGER trg_artifact_versions_prevent_delete
BEFORE DELETE ON public.artifact_versions
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_reject_immutable_change();
DROP TRIGGER IF EXISTS trg_artifact_evidence_validate_insert ON public.artifact_evidence;
CREATE TRIGGER trg_artifact_evidence_validate_insert
BEFORE INSERT ON public.artifact_evidence
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_guard_artifact_evidence_insert();
DROP TRIGGER IF EXISTS trg_artifact_evidence_immutable ON public.artifact_evidence;
CREATE TRIGGER trg_artifact_evidence_immutable
BEFORE UPDATE OR DELETE ON public.artifact_evidence
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_reject_immutable_change();

DROP TRIGGER IF EXISTS trg_approval_requests_protect_binding ON public.approval_requests;
CREATE TRIGGER trg_approval_requests_protect_binding
BEFORE UPDATE ON public.approval_requests
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_protect_approval_binding();
DROP TRIGGER IF EXISTS trg_approval_requests_prevent_delete ON public.approval_requests;
CREATE TRIGGER trg_approval_requests_prevent_delete
BEFORE DELETE ON public.approval_requests
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_reject_immutable_change();
DROP TRIGGER IF EXISTS trg_approval_requests_validate_state ON public.approval_requests;
CREATE TRIGGER trg_approval_requests_validate_state
BEFORE INSERT OR UPDATE ON public.approval_requests
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_validate_approval_state();

COMMIT;
