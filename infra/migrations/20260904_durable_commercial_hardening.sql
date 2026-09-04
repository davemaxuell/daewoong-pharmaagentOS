-- Milestone 7 durable activity journal and global/per-agent runtime controls.
-- Apply after 20260904_evaluation_and_control_tower.sql.

BEGIN;

CREATE TABLE IF NOT EXISTS public.platform_controls (
  id varchar(36) PRIMARY KEY,
  control_key varchar(160) NOT NULL UNIQUE,
  scope varchar(20) NOT NULL,
  agent_version_id varchar(36) REFERENCES public.agent_versions(id) ON DELETE RESTRICT,
  suspended boolean NOT NULL DEFAULT false,
  reason text NOT NULL,
  revision integer NOT NULL DEFAULT 1,
  updated_by varchar(255) NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_platform_controls_scope CHECK (scope IN ('GLOBAL', 'AGENT')),
  CONSTRAINT ck_platform_controls_revision CHECK (revision >= 1),
  CONSTRAINT ck_platform_controls_binding CHECK (
    (scope = 'GLOBAL' AND agent_version_id IS NULL AND control_key = 'global') OR
    (scope = 'AGENT' AND agent_version_id IS NOT NULL AND control_key = 'agent:' || agent_version_id)
  )
);

CREATE TABLE IF NOT EXISTS public.durable_activities (
  id varchar(36) PRIMARY KEY,
  temporal_workflow_id varchar(255) NOT NULL,
  case_run_id varchar(36) NOT NULL REFERENCES public.case_runs(id) ON DELETE RESTRICT,
  activity_key varchar(255) NOT NULL,
  input_sha256 varchar(64) NOT NULL,
  status varchar(20) NOT NULL,
  result jsonb NOT NULL DEFAULT '{}'::jsonb,
  result_sha256 varchar(64),
  attempts integer NOT NULL DEFAULT 1,
  last_error text,
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  CONSTRAINT uq_durable_activities_identity UNIQUE (temporal_workflow_id, activity_key),
  CONSTRAINT ck_durable_activities_status CHECK (status IN ('RUNNING', 'SUCCEEDED', 'FAILED')),
  CONSTRAINT ck_durable_activities_input_hash CHECK (length(input_sha256) = 64),
  CONSTRAINT ck_durable_activities_result_hash CHECK (
    result_sha256 IS NULL OR length(result_sha256) = 64
  ),
  CONSTRAINT ck_durable_activities_attempts CHECK (attempts >= 1),
  CONSTRAINT ck_durable_activities_result CHECK (jsonb_typeof(result) = 'object')
);

CREATE INDEX IF NOT EXISTS ix_platform_controls_scope
  ON public.platform_controls(scope, suspended);
CREATE INDEX IF NOT EXISTS ix_platform_controls_agent
  ON public.platform_controls(agent_version_id) WHERE agent_version_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_durable_activities_workflow
  ON public.durable_activities(temporal_workflow_id, status);
CREATE INDEX IF NOT EXISTS ix_durable_activities_run
  ON public.durable_activities(case_run_id, started_at DESC);

CREATE OR REPLACE FUNCTION public.pharma_agent_validate_control_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'runtime controls are retained for audit';
  END IF;
  IF NEW.control_key <> OLD.control_key
     OR NEW.scope <> OLD.scope
     OR NEW.agent_version_id IS DISTINCT FROM OLD.agent_version_id
     OR NEW.revision <> OLD.revision + 1
     OR NEW.updated_at <= OLD.updated_at THEN
    RAISE EXCEPTION 'runtime control identity is immutable and revision must advance exactly once';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_platform_controls_guard ON public.platform_controls;
CREATE TRIGGER trg_platform_controls_guard
BEFORE UPDATE OR DELETE ON public.platform_controls
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_validate_control_update();

CREATE OR REPLACE FUNCTION public.pharma_agent_validate_activity_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'durable activities are append-retained';
  END IF;
  IF NEW.temporal_workflow_id <> OLD.temporal_workflow_id
     OR NEW.case_run_id <> OLD.case_run_id
     OR NEW.activity_key <> OLD.activity_key
     OR NEW.input_sha256 <> OLD.input_sha256
     OR NEW.started_at <> OLD.started_at
     OR NEW.attempts < OLD.attempts
     OR OLD.status = 'SUCCEEDED' THEN
    RAISE EXCEPTION 'durable activity identity or committed result is immutable';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_durable_activities_guard ON public.durable_activities;
CREATE TRIGGER trg_durable_activities_guard
BEFORE UPDATE OR DELETE ON public.durable_activities
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_validate_activity_update();

COMMIT;
