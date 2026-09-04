-- Milestone 3 durable case orchestration and workflow-template registry.
-- Apply after 20260904_agent_os_control_plane.sql.

BEGIN;

CREATE TABLE IF NOT EXISTS public.workflow_template_versions (
  id varchar(36) PRIMARY KEY,
  workflow_key varchar(160) NOT NULL,
  version varchar(80) NOT NULL,
  display_name varchar(255) NOT NULL,
  manifest jsonb NOT NULL DEFAULT '{}'::jsonb,
  manifest_sha256 varchar(64) NOT NULL,
  release_status varchar(20) NOT NULL DEFAULT 'DRAFT',
  created_by varchar(255) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_workflow_template_versions_key_version
    UNIQUE (workflow_key, version),
  CONSTRAINT uq_workflow_template_versions_key_manifest_hash
    UNIQUE (workflow_key, manifest_sha256),
  CONSTRAINT ck_workflow_template_versions_manifest_hash_length
    CHECK (length(manifest_sha256) = 64),
  CONSTRAINT ck_workflow_template_versions_release_status CHECK (
    release_status IN (
      'DRAFT', 'DEVELOPMENT', 'TESTING', 'STAGING',
      'APPROVED', 'PRODUCTION', 'SUSPENDED', 'RETIRED'
    )
  ),
  CONSTRAINT ck_workflow_template_versions_manifest_object
    CHECK (jsonb_typeof(manifest) = 'object')
);

ALTER TABLE public.case_plans
  ADD COLUMN IF NOT EXISTS workflow_template_version_id varchar(36);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'fk_case_plans_workflow_template_version'
      AND conrelid = 'public.case_plans'::regclass
  ) THEN
    ALTER TABLE public.case_plans
      ADD CONSTRAINT fk_case_plans_workflow_template_version
      FOREIGN KEY (workflow_template_version_id)
      REFERENCES public.workflow_template_versions(id) ON DELETE RESTRICT;
  END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS ix_case_plans_workflow_template_version_id
  ON public.case_plans (workflow_template_version_id);
CREATE INDEX IF NOT EXISTS ix_workflow_template_versions_key_status
  ON public.workflow_template_versions (workflow_key, release_status);

CREATE TABLE IF NOT EXISTS public.run_events (
  id varchar(36) PRIMARY KEY,
  run_id varchar(36) NOT NULL,
  case_id varchar(36) NOT NULL,
  sequence integer NOT NULL,
  event_type varchar(80) NOT NULL,
  actor_type varchar(32) NOT NULL,
  actor_id varchar(255) NOT NULL,
  request_id varchar(80) NOT NULL,
  idempotency_key varchar(255) NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  previous_event_hash varchar(64),
  event_hash varchar(64) NOT NULL UNIQUE,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT fk_run_events_run_case FOREIGN KEY (run_id, case_id)
    REFERENCES public.case_runs(id, case_id) ON DELETE RESTRICT,
  CONSTRAINT uq_run_events_run_sequence UNIQUE (run_id, sequence),
  CONSTRAINT uq_run_events_run_idempotency UNIQUE (run_id, idempotency_key),
  CONSTRAINT ck_run_events_positive_sequence CHECK (sequence >= 1),
  CONSTRAINT ck_run_events_event_hash_length CHECK (length(event_hash) = 64),
  CONSTRAINT ck_run_events_previous_hash_length CHECK (
    previous_event_hash IS NULL OR length(previous_event_hash) = 64
  ),
  CONSTRAINT ck_run_events_payload_object CHECK (jsonb_typeof(payload) = 'object')
);

CREATE INDEX IF NOT EXISTS ix_run_events_run_occurred
  ON public.run_events (run_id, occurred_at);
CREATE INDEX IF NOT EXISTS ix_run_events_case_id ON public.run_events (case_id);
CREATE INDEX IF NOT EXISTS ix_run_events_event_type ON public.run_events (event_type);

CREATE TABLE IF NOT EXISTS public.agent_invocations (
  id varchar(36) PRIMARY KEY,
  run_id varchar(36) NOT NULL,
  case_id varchar(36) NOT NULL,
  plan_step_id varchar(36) NOT NULL
    REFERENCES public.case_plan_steps(id) ON DELETE RESTRICT,
  step_key varchar(160) NOT NULL,
  attempt integer NOT NULL DEFAULT 1,
  agent_version_id varchar(36)
    REFERENCES public.agent_versions(id) ON DELETE RESTRICT,
  status varchar(32) NOT NULL DEFAULT 'PENDING',
  input_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  input_sha256 varchar(64) NOT NULL,
  output_payload jsonb,
  output_sha256 varchar(64),
  output_schema_ref varchar(255) NOT NULL,
  limits jsonb NOT NULL DEFAULT '{}'::jsonb,
  usage jsonb NOT NULL DEFAULT '{}'::jsonb,
  error_code varchar(120),
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT fk_agent_invocations_run_case FOREIGN KEY (run_id, case_id)
    REFERENCES public.case_runs(id, case_id) ON DELETE RESTRICT,
  CONSTRAINT uq_agent_invocations_run_step_attempt
    UNIQUE (run_id, step_key, attempt),
  CONSTRAINT ck_agent_invocations_positive_attempt CHECK (attempt >= 1),
  CONSTRAINT ck_agent_invocations_input_hash_length CHECK (length(input_sha256) = 64),
  CONSTRAINT ck_agent_invocations_output_hash_length CHECK (
    output_sha256 IS NULL OR length(output_sha256) = 64
  ),
  CONSTRAINT ck_agent_invocations_status CHECK (
    status IN (
      'PENDING', 'RUNNING', 'WAITING_FOR_APPROVAL',
      'COMPLETED', 'BLOCKED', 'FAILED', 'CANCELLED'
    )
  ),
  CONSTRAINT ck_agent_invocations_input_object
    CHECK (jsonb_typeof(input_payload) = 'object'),
  CONSTRAINT ck_agent_invocations_output_object
    CHECK (output_payload IS NULL OR jsonb_typeof(output_payload) = 'object'),
  CONSTRAINT ck_agent_invocations_limits_object CHECK (jsonb_typeof(limits) = 'object'),
  CONSTRAINT ck_agent_invocations_usage_object CHECK (jsonb_typeof(usage) = 'object')
);

CREATE INDEX IF NOT EXISTS ix_agent_invocations_run_status
  ON public.agent_invocations (run_id, status);
CREATE INDEX IF NOT EXISTS ix_agent_invocations_case_id
  ON public.agent_invocations (case_id);
CREATE INDEX IF NOT EXISTS ix_agent_invocations_plan_step_id
  ON public.agent_invocations (plan_step_id);

ALTER TABLE public.approval_requests
  ADD COLUMN IF NOT EXISTS run_id varchar(36),
  ADD COLUMN IF NOT EXISTS plan_step_id varchar(36),
  ADD COLUMN IF NOT EXISTS step_key varchar(160);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'fk_approval_requests_run_case'
      AND conrelid = 'public.approval_requests'::regclass
  ) THEN
    ALTER TABLE public.approval_requests
      ADD CONSTRAINT fk_approval_requests_run_case
      FOREIGN KEY (run_id, case_id)
      REFERENCES public.case_runs(id, case_id) ON DELETE RESTRICT;
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'fk_approval_requests_plan_step_id'
      AND conrelid = 'public.approval_requests'::regclass
  ) THEN
    ALTER TABLE public.approval_requests
      ADD CONSTRAINT fk_approval_requests_plan_step_id
      FOREIGN KEY (plan_step_id)
      REFERENCES public.case_plan_steps(id) ON DELETE RESTRICT;
  END IF;
END;
$$;

ALTER TABLE public.approval_requests
  DROP CONSTRAINT IF EXISTS ck_approval_requests_type;
ALTER TABLE public.approval_requests
  ADD CONSTRAINT ck_approval_requests_type
  CHECK (approval_type IN ('PLAN_APPROVAL', 'STEP_APPROVAL', 'ARTIFACT_APPROVAL'));

ALTER TABLE public.approval_requests
  DROP CONSTRAINT IF EXISTS ck_approval_requests_step_target_type;
ALTER TABLE public.approval_requests
  ADD CONSTRAINT ck_approval_requests_step_target_type CHECK (
    (
      approval_type = 'STEP_APPROVAL'
      AND run_id IS NOT NULL AND plan_step_id IS NOT NULL AND step_key IS NOT NULL
    ) OR (
      approval_type <> 'STEP_APPROVAL'
      AND run_id IS NULL AND plan_step_id IS NULL AND step_key IS NULL
    )
  );

CREATE INDEX IF NOT EXISTS ix_approval_requests_run_id
  ON public.approval_requests (run_id);
CREATE INDEX IF NOT EXISTS ix_approval_requests_plan_step_id
  ON public.approval_requests (plan_step_id);

CREATE OR REPLACE FUNCTION public.pharma_agent_validate_run_event_chain()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  prior_sequence integer;
  prior_hash varchar(64);
BEGIN
  PERFORM 1 FROM public.case_runs WHERE id = NEW.run_id FOR UPDATE;
  SELECT sequence, event_hash INTO prior_sequence, prior_hash
  FROM public.run_events
  WHERE run_id = NEW.run_id
  ORDER BY sequence DESC
  LIMIT 1;

  IF prior_sequence IS NULL THEN
    IF NEW.sequence <> 1 OR NEW.previous_event_hash IS NOT NULL THEN
      RAISE EXCEPTION 'first run event must use sequence 1 and no previous hash'
        USING ERRCODE = '23514';
    END IF;
  ELSIF NEW.sequence <> prior_sequence + 1
        OR NEW.previous_event_hash IS DISTINCT FROM prior_hash THEN
    RAISE EXCEPTION 'run event does not extend the current hash chain'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.pharma_agent_protect_invocation_binding()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.run_id IS DISTINCT FROM OLD.run_id
     OR NEW.case_id IS DISTINCT FROM OLD.case_id
     OR NEW.plan_step_id IS DISTINCT FROM OLD.plan_step_id
     OR NEW.step_key IS DISTINCT FROM OLD.step_key
     OR NEW.attempt IS DISTINCT FROM OLD.attempt
     OR NEW.agent_version_id IS DISTINCT FROM OLD.agent_version_id
     OR NEW.input_payload IS DISTINCT FROM OLD.input_payload
     OR NEW.input_sha256 IS DISTINCT FROM OLD.input_sha256
     OR NEW.output_schema_ref IS DISTINCT FROM OLD.output_schema_ref
     OR NEW.limits IS DISTINCT FROM OLD.limits
     OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
    RAISE EXCEPTION 'agent invocation bindings are immutable'
      USING ERRCODE = '55000';
  END IF;
  IF OLD.status IN ('COMPLETED', 'BLOCKED', 'FAILED', 'CANCELLED')
     AND NEW IS DISTINCT FROM OLD THEN
    RAISE EXCEPTION 'terminal agent invocations are immutable'
      USING ERRCODE = '55000';
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
     OR NEW.run_id IS DISTINCT FROM OLD.run_id
     OR NEW.plan_step_id IS DISTINCT FROM OLD.plan_step_id
     OR NEW.step_key IS DISTINCT FROM OLD.step_key
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

DROP TRIGGER IF EXISTS trg_workflow_template_versions_protect_payload
  ON public.workflow_template_versions;
CREATE TRIGGER trg_workflow_template_versions_protect_payload
BEFORE UPDATE ON public.workflow_template_versions
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_protect_registry_payload();
DROP TRIGGER IF EXISTS trg_workflow_template_versions_prevent_delete
  ON public.workflow_template_versions;
CREATE TRIGGER trg_workflow_template_versions_prevent_delete
BEFORE DELETE ON public.workflow_template_versions
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_reject_immutable_change();

DROP TRIGGER IF EXISTS trg_run_events_validate_chain ON public.run_events;
CREATE TRIGGER trg_run_events_validate_chain
BEFORE INSERT ON public.run_events
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_validate_run_event_chain();
DROP TRIGGER IF EXISTS trg_run_events_append_only ON public.run_events;
CREATE TRIGGER trg_run_events_append_only
BEFORE UPDATE OR DELETE ON public.run_events
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_reject_immutable_change();

DROP TRIGGER IF EXISTS trg_agent_invocations_protect_binding
  ON public.agent_invocations;
CREATE TRIGGER trg_agent_invocations_protect_binding
BEFORE UPDATE ON public.agent_invocations
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_protect_invocation_binding();
DROP TRIGGER IF EXISTS trg_agent_invocations_prevent_delete
  ON public.agent_invocations;
CREATE TRIGGER trg_agent_invocations_prevent_delete
BEFORE DELETE ON public.agent_invocations
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_reject_immutable_change();

COMMIT;
