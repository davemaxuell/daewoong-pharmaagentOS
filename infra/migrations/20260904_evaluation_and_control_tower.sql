-- Milestone 6 outcome evaluation, release gates, and feedback linkage.
-- Apply after 20260904_verification_and_artifacts.sql.

BEGIN;

CREATE TABLE IF NOT EXISTS public.evaluation_suites (
  id varchar(36) PRIMARY KEY,
  suite_key varchar(160) NOT NULL,
  version varchar(80) NOT NULL,
  name varchar(255) NOT NULL,
  description text NOT NULL,
  target_kind varchar(40) NOT NULL,
  gates jsonb NOT NULL DEFAULT '[]'::jsonb,
  suite_sha256 varchar(64) NOT NULL UNIQUE,
  created_by varchar(255) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_evaluation_suites_key_version UNIQUE (suite_key, version),
  CONSTRAINT ck_evaluation_suites_target_kind CHECK (target_kind IN ('AGENT_VERSION', 'WORKFLOW_VERSION')),
  CONSTRAINT ck_evaluation_suites_hash CHECK (length(suite_sha256) = 64),
  CONSTRAINT ck_evaluation_suites_gates CHECK (jsonb_typeof(gates) = 'array')
);

CREATE TABLE IF NOT EXISTS public.evaluation_cases (
  id varchar(36) PRIMARY KEY,
  suite_id varchar(36) NOT NULL REFERENCES public.evaluation_suites(id) ON DELETE RESTRICT,
  case_key varchar(160) NOT NULL,
  title varchar(300) NOT NULL,
  category varchar(80) NOT NULL,
  input jsonb NOT NULL DEFAULT '{}'::jsonb,
  expected_outcome jsonb NOT NULL DEFAULT '{}'::jsonb,
  critical boolean NOT NULL DEFAULT false,
  synthetic boolean NOT NULL DEFAULT true,
  case_sha256 varchar(64) NOT NULL,
  created_by varchar(255) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_evaluation_cases_suite_key UNIQUE (suite_id, case_key),
  CONSTRAINT ck_evaluation_cases_hash CHECK (length(case_sha256) = 64),
  CONSTRAINT ck_evaluation_cases_category CHECK (category IN ('REGULATORY', 'INTERNAL_RETRIEVAL', 'END_TO_END', 'SECURITY', 'RESILIENCE')),
  CONSTRAINT ck_evaluation_cases_synthetic CHECK (synthetic),
  CONSTRAINT ck_evaluation_cases_input CHECK (jsonb_typeof(input) = 'object'),
  CONSTRAINT ck_evaluation_cases_expected CHECK (jsonb_typeof(expected_outcome) = 'object')
);

CREATE TABLE IF NOT EXISTS public.evaluation_runs (
  id varchar(36) PRIMARY KEY,
  suite_id varchar(36) NOT NULL REFERENCES public.evaluation_suites(id) ON DELETE RESTRICT,
  target_kind varchar(40) NOT NULL,
  target_version_id varchar(36) NOT NULL,
  target_sha256 varchar(64) NOT NULL,
  baseline_version_id varchar(36),
  trial_count integer NOT NULL,
  status varchar(20) NOT NULL,
  metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
  total_trials integer NOT NULL DEFAULT 0,
  passed_trials integer NOT NULL DEFAULT 0,
  critical_failures integer NOT NULL DEFAULT 0,
  total_cost_usd double precision NOT NULL DEFAULT 0,
  total_latency_ms integer NOT NULL DEFAULT 0,
  requested_by varchar(255) NOT NULL,
  idempotency_key varchar(255) NOT NULL UNIQUE,
  started_at timestamptz NOT NULL,
  completed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_evaluation_runs_target_kind CHECK (target_kind IN ('AGENT_VERSION', 'WORKFLOW_VERSION')),
  CONSTRAINT ck_evaluation_runs_trials CHECK (trial_count BETWEEN 3 AND 20),
  CONSTRAINT ck_evaluation_runs_status CHECK (status IN ('PENDING', 'RUNNING', 'PASSED', 'FAILED')),
  CONSTRAINT ck_evaluation_runs_target_hash CHECK (length(target_sha256) = 64),
  CONSTRAINT ck_evaluation_runs_counts CHECK (total_trials >= 0 AND passed_trials >= 0 AND passed_trials <= total_trials),
  CONSTRAINT ck_evaluation_runs_critical CHECK (critical_failures >= 0),
  CONSTRAINT ck_evaluation_runs_usage CHECK (total_cost_usd >= 0 AND total_latency_ms >= 0),
  CONSTRAINT ck_evaluation_runs_metrics CHECK (jsonb_typeof(metrics) = 'object')
);

CREATE TABLE IF NOT EXISTS public.evaluation_trials (
  id varchar(36) PRIMARY KEY,
  evaluation_run_id varchar(36) NOT NULL REFERENCES public.evaluation_runs(id) ON DELETE RESTRICT,
  evaluation_case_id varchar(36) NOT NULL REFERENCES public.evaluation_cases(id) ON DELETE RESTRICT,
  trial_number integer NOT NULL,
  status varchar(20) NOT NULL,
  trajectory jsonb NOT NULL DEFAULT '[]'::jsonb,
  final_state jsonb NOT NULL DEFAULT '{}'::jsonb,
  output_sha256 varchar(64) NOT NULL,
  token_count integer NOT NULL DEFAULT 0,
  cost_usd double precision NOT NULL DEFAULT 0,
  latency_ms integer NOT NULL DEFAULT 0,
  error_code varchar(120),
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_evaluation_trials_identity UNIQUE (evaluation_run_id, evaluation_case_id, trial_number),
  CONSTRAINT ck_evaluation_trials_number CHECK (trial_number >= 1),
  CONSTRAINT ck_evaluation_trials_status CHECK (status IN ('PASSED', 'FAILED')),
  CONSTRAINT ck_evaluation_trials_hash CHECK (length(output_sha256) = 64),
  CONSTRAINT ck_evaluation_trials_usage CHECK (token_count >= 0 AND cost_usd >= 0 AND latency_ms >= 0),
  CONSTRAINT ck_evaluation_trials_trajectory CHECK (jsonb_typeof(trajectory) = 'array'),
  CONSTRAINT ck_evaluation_trials_state CHECK (jsonb_typeof(final_state) = 'object')
);

CREATE TABLE IF NOT EXISTS public.evaluation_grades (
  id varchar(36) PRIMARY KEY,
  evaluation_trial_id varchar(36) NOT NULL REFERENCES public.evaluation_trials(id) ON DELETE RESTRICT,
  grader_type varchar(24) NOT NULL,
  metric varchar(80) NOT NULL,
  score double precision NOT NULL,
  passed boolean NOT NULL,
  critical boolean NOT NULL DEFAULT false,
  rationale text NOT NULL,
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  graded_by varchar(255) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_evaluation_grades_metric UNIQUE (evaluation_trial_id, grader_type, metric),
  CONSTRAINT ck_evaluation_grades_type CHECK (grader_type IN ('DETERMINISTIC', 'MODEL', 'HUMAN')),
  CONSTRAINT ck_evaluation_grades_score CHECK (score BETWEEN 0 AND 1),
  CONSTRAINT ck_evaluation_grades_evidence CHECK (jsonb_typeof(evidence) = 'object')
);

CREATE TABLE IF NOT EXISTS public.release_approvals (
  id varchar(36) PRIMARY KEY,
  evaluation_run_id varchar(36) NOT NULL UNIQUE REFERENCES public.evaluation_runs(id) ON DELETE RESTRICT,
  target_kind varchar(40) NOT NULL,
  target_version_id varchar(36) NOT NULL,
  target_sha256 varchar(64) NOT NULL,
  target_status varchar(20) NOT NULL,
  decision varchar(20) NOT NULL,
  rollback_target_id varchar(36),
  decided_by varchar(255) NOT NULL,
  reason text NOT NULL,
  decided_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_release_approvals_target_kind CHECK (target_kind IN ('AGENT_VERSION', 'WORKFLOW_VERSION')),
  CONSTRAINT ck_release_approvals_target_status CHECK (target_status IN ('STAGING', 'PRODUCTION')),
  CONSTRAINT ck_release_approvals_decision CHECK (decision IN ('APPROVED', 'REJECTED')),
  CONSTRAINT ck_release_approvals_target_hash CHECK (length(target_sha256) = 64)
);

CREATE TABLE IF NOT EXISTS public.production_feedback (
  id varchar(36) PRIMARY KEY,
  case_id varchar(36) REFERENCES public.agent_cases(id) ON DELETE RESTRICT,
  run_id varchar(36),
  artifact_version_id varchar(36),
  agent_version_id varchar(36),
  signal_type varchar(80) NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  payload_sha256 varchar(64) NOT NULL,
  submitted_by varchar(255) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_production_feedback_hash CHECK (length(payload_sha256) = 64),
  CONSTRAINT ck_production_feedback_link CHECK (num_nonnulls(case_id, run_id, artifact_version_id, agent_version_id) >= 1),
  CONSTRAINT ck_production_feedback_type CHECK (signal_type IN ('APPROVAL', 'REJECTION', 'EDIT', 'INTERRUPTION', 'UNRESOLVED_QUESTION', 'TOOL_FAILURE', 'NEGATIVE_FEEDBACK', 'INCIDENT')),
  CONSTRAINT ck_production_feedback_payload CHECK (jsonb_typeof(payload) = 'object')
);

CREATE INDEX IF NOT EXISTS ix_evaluation_cases_suite ON public.evaluation_cases(suite_id);
CREATE INDEX IF NOT EXISTS ix_evaluation_runs_suite_status ON public.evaluation_runs(suite_id, status);
CREATE INDEX IF NOT EXISTS ix_evaluation_runs_target ON public.evaluation_runs(target_kind, target_version_id);
CREATE INDEX IF NOT EXISTS ix_evaluation_trials_run ON public.evaluation_trials(evaluation_run_id);
CREATE INDEX IF NOT EXISTS ix_evaluation_grades_trial ON public.evaluation_grades(evaluation_trial_id);
CREATE INDEX IF NOT EXISTS ix_release_approvals_target ON public.release_approvals(target_kind, target_version_id);
CREATE INDEX IF NOT EXISTS ix_production_feedback_case ON public.production_feedback(case_id, created_at DESC);

DROP TRIGGER IF EXISTS trg_evaluation_suites_immutable ON public.evaluation_suites;
CREATE TRIGGER trg_evaluation_suites_immutable BEFORE UPDATE OR DELETE ON public.evaluation_suites
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_reject_immutable_change();
DROP TRIGGER IF EXISTS trg_evaluation_cases_immutable ON public.evaluation_cases;
CREATE TRIGGER trg_evaluation_cases_immutable BEFORE UPDATE OR DELETE ON public.evaluation_cases
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_reject_immutable_change();
DROP TRIGGER IF EXISTS trg_evaluation_trials_immutable ON public.evaluation_trials;
CREATE TRIGGER trg_evaluation_trials_immutable BEFORE UPDATE OR DELETE ON public.evaluation_trials
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_reject_immutable_change();
DROP TRIGGER IF EXISTS trg_evaluation_grades_immutable ON public.evaluation_grades;
CREATE TRIGGER trg_evaluation_grades_immutable BEFORE UPDATE OR DELETE ON public.evaluation_grades
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_reject_immutable_change();
DROP TRIGGER IF EXISTS trg_release_approvals_immutable ON public.release_approvals;
CREATE TRIGGER trg_release_approvals_immutable BEFORE UPDATE OR DELETE ON public.release_approvals
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_reject_immutable_change();
DROP TRIGGER IF EXISTS trg_production_feedback_immutable ON public.production_feedback;
CREATE TRIGGER trg_production_feedback_immutable BEFORE UPDATE OR DELETE ON public.production_feedback
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_reject_immutable_change();

COMMIT;
