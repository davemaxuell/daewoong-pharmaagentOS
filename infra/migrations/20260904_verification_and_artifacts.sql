-- Milestone 5 independent verification and immutable artifact provenance.
-- Apply after 20260904_internal_knowledge_and_impact.sql.

BEGIN;

CREATE TABLE IF NOT EXISTS public.verification_reports (
  id varchar(36) PRIMARY KEY,
  case_id varchar(36) NOT NULL REFERENCES public.agent_cases(id) ON DELETE RESTRICT,
  run_id varchar(36),
  plan_id varchar(36) NOT NULL,
  plan_version integer NOT NULL,
  plan_sha256 varchar(64) NOT NULL,
  bound_state_hash varchar(64) NOT NULL,
  input_sha256 varchar(64) NOT NULL,
  correction_iteration integer NOT NULL DEFAULT 0,
  status varchar(20) NOT NULL,
  checks jsonb NOT NULL DEFAULT '[]'::jsonb,
  issues jsonb NOT NULL DEFAULT '[]'::jsonb,
  verified_hypothesis_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  report_sha256 varchar(64) NOT NULL UNIQUE,
  verifier_name varchar(160) NOT NULL,
  verifier_version varchar(80) NOT NULL,
  created_by varchar(255) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT fk_verification_reports_run_case FOREIGN KEY (run_id, case_id)
    REFERENCES public.case_runs(id, case_id) ON DELETE RESTRICT,
  CONSTRAINT fk_verification_reports_plan_binding FOREIGN KEY (
    plan_id, case_id, plan_version, plan_sha256, bound_state_hash
  ) REFERENCES public.case_plans (
    id, case_id, version, plan_sha256, based_on_state_hash
  ) ON DELETE RESTRICT,
  CONSTRAINT uq_verification_reports_input_iteration
    UNIQUE (case_id, input_sha256, correction_iteration),
  CONSTRAINT ck_verification_reports_correction_limit
    CHECK (correction_iteration BETWEEN 0 AND 2),
  CONSTRAINT ck_verification_reports_status CHECK (status IN ('PASS', 'REVISE', 'BLOCK')),
  CONSTRAINT ck_verification_reports_plan_version CHECK (plan_version >= 1),
  CONSTRAINT ck_verification_reports_plan_hash CHECK (length(plan_sha256) = 64),
  CONSTRAINT ck_verification_reports_state_hash CHECK (length(bound_state_hash) = 64),
  CONSTRAINT ck_verification_reports_input_hash CHECK (length(input_sha256) = 64),
  CONSTRAINT ck_verification_reports_report_hash CHECK (length(report_sha256) = 64),
  CONSTRAINT ck_verification_reports_checks_array CHECK (jsonb_typeof(checks) = 'array'),
  CONSTRAINT ck_verification_reports_issues_array CHECK (jsonb_typeof(issues) = 'array'),
  CONSTRAINT ck_verification_reports_hypotheses_array
    CHECK (jsonb_typeof(verified_hypothesis_ids) = 'array')
);

CREATE INDEX IF NOT EXISTS ix_verification_reports_case_created
  ON public.verification_reports(case_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_verification_reports_input
  ON public.verification_reports(input_sha256);
CREATE INDEX IF NOT EXISTS ix_verification_reports_status
  ON public.verification_reports(status);

ALTER TABLE public.artifact_versions
  ADD COLUMN IF NOT EXISTS verification_report_id varchar(36);

DO $$ BEGIN
  ALTER TABLE public.artifact_versions
    ADD CONSTRAINT fk_artifact_versions_verification_report
    FOREIGN KEY (verification_report_id)
    REFERENCES public.verification_reports(id) ON DELETE RESTRICT;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS ix_artifact_versions_verification_report
  ON public.artifact_versions(verification_report_id);

CREATE OR REPLACE FUNCTION public.pharma_agent_validate_verified_artifact()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.verification_report_id IS NULL OR NOT EXISTS (
    SELECT 1
    FROM public.verification_reports AS v
    WHERE v.id = NEW.verification_report_id
      AND v.case_id = NEW.case_id
      AND v.plan_id = NEW.plan_id
      AND v.plan_version = NEW.plan_version
      AND v.plan_sha256 = NEW.plan_sha256
      AND v.bound_state_hash = NEW.bound_state_hash
      AND v.status = 'PASS'
  ) THEN
    RAISE EXCEPTION 'artifact requires an exact PASS verification binding'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_artifact_versions_require_verification
  ON public.artifact_versions;
CREATE TRIGGER trg_artifact_versions_require_verification
BEFORE INSERT ON public.artifact_versions
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_validate_verified_artifact();

DROP TRIGGER IF EXISTS trg_verification_reports_immutable
  ON public.verification_reports;
CREATE TRIGGER trg_verification_reports_immutable
BEFORE UPDATE OR DELETE ON public.verification_reports
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_reject_immutable_change();

COMMIT;
