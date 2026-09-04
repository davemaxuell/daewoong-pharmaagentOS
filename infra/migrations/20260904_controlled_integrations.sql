-- Milestone 8 draft/read-only connectors and immutable answer-only A2A exchanges.
-- Apply after 20260904_durable_commercial_hardening.sql.

BEGIN;

CREATE TABLE IF NOT EXISTS public.integration_outbox (
  id varchar(36) PRIMARY KEY,
  case_id varchar(36) NOT NULL REFERENCES public.agent_cases(id) ON DELETE RESTRICT,
  run_id varchar(36),
  channel varchar(32) NOT NULL,
  action varchar(40) NOT NULL DEFAULT 'CREATE_DRAFT',
  destination varchar(320) NOT NULL,
  content jsonb NOT NULL DEFAULT '{}'::jsonb,
  content_sha256 varchar(64) NOT NULL,
  status varchar(40) NOT NULL DEFAULT 'DRAFT',
  external_delivery_allowed boolean NOT NULL DEFAULT false,
  requested_by varchar(255) NOT NULL,
  reviewed_by varchar(255),
  review_reason text,
  reviewed_at timestamptz,
  idempotency_key varchar(255) NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_integration_outbox_channel CHECK (
    channel IN ('INTERNAL', 'EMAIL', 'SLACK', 'TEAMS', 'NOTION', 'TASK')
  ),
  CONSTRAINT ck_integration_outbox_action CHECK (action = 'CREATE_DRAFT'),
  CONSTRAINT ck_integration_outbox_status CHECK (
    status IN ('DRAFT', 'REVIEWED_FOR_MANUAL_USE', 'CANCELLED')
  ),
  CONSTRAINT ck_integration_outbox_no_delivery CHECK (external_delivery_allowed = false),
  CONSTRAINT ck_integration_outbox_hash CHECK (length(content_sha256) = 64),
  CONSTRAINT ck_integration_outbox_content CHECK (jsonb_typeof(content) = 'object'),
  CONSTRAINT ck_integration_outbox_review CHECK (
    (status = 'DRAFT' AND reviewed_by IS NULL AND reviewed_at IS NULL) OR
    (status <> 'DRAFT' AND reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)
  ),
  CONSTRAINT fk_integration_outbox_run_case FOREIGN KEY (run_id, case_id)
    REFERENCES public.case_runs(id, case_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS public.a2a_exchanges (
  id varchar(36) PRIMARY KEY,
  case_id varchar(36) NOT NULL REFERENCES public.agent_cases(id) ON DELETE RESTRICT,
  task_key varchar(255) NOT NULL UNIQUE,
  intent varchar(80) NOT NULL,
  request_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  request_sha256 varchar(64) NOT NULL,
  response_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  response_sha256 varchar(64) NOT NULL,
  status varchar(20) NOT NULL DEFAULT 'COMPLETED',
  requester_service varchar(255) NOT NULL,
  delegated_subject varchar(255) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_a2a_exchanges_intent CHECK (
    intent IN ('CASE_STATUS', 'APPROVED_ARTIFACT_METADATA')
  ),
  CONSTRAINT ck_a2a_exchanges_status CHECK (status = 'COMPLETED'),
  CONSTRAINT ck_a2a_exchanges_request_hash CHECK (length(request_sha256) = 64),
  CONSTRAINT ck_a2a_exchanges_response_hash CHECK (length(response_sha256) = 64),
  CONSTRAINT ck_a2a_exchanges_request CHECK (jsonb_typeof(request_payload) = 'object'),
  CONSTRAINT ck_a2a_exchanges_response CHECK (jsonb_typeof(response_payload) = 'object')
);

CREATE INDEX IF NOT EXISTS ix_integration_outbox_case
  ON public.integration_outbox(case_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_integration_outbox_status
  ON public.integration_outbox(status, channel);
CREATE INDEX IF NOT EXISTS ix_a2a_exchanges_case
  ON public.a2a_exchanges(case_id, created_at DESC);

CREATE OR REPLACE FUNCTION public.pharma_agent_validate_integration_draft_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'integration drafts are retained for audit';
  END IF;
  IF OLD.status <> 'DRAFT'
     OR NEW.status NOT IN ('REVIEWED_FOR_MANUAL_USE', 'CANCELLED')
     OR NEW.id <> OLD.id
     OR NEW.case_id <> OLD.case_id
     OR NEW.run_id IS DISTINCT FROM OLD.run_id
     OR NEW.channel <> OLD.channel
     OR NEW.action <> OLD.action
     OR NEW.destination <> OLD.destination
     OR NEW.content <> OLD.content
     OR NEW.content_sha256 <> OLD.content_sha256
     OR NEW.external_delivery_allowed
     OR NEW.requested_by <> OLD.requested_by
     OR NEW.idempotency_key <> OLD.idempotency_key
     OR NEW.created_at <> OLD.created_at
     OR NEW.reviewed_by IS NULL
     OR NEW.reviewed_at IS NULL THEN
    RAISE EXCEPTION 'integration draft content is immutable and only one review transition is allowed';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_integration_outbox_guard ON public.integration_outbox;
CREATE TRIGGER trg_integration_outbox_guard
BEFORE UPDATE OR DELETE ON public.integration_outbox
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_validate_integration_draft_update();

DROP TRIGGER IF EXISTS trg_a2a_exchanges_immutable ON public.a2a_exchanges;
CREATE TRIGGER trg_a2a_exchanges_immutable
BEFORE UPDATE OR DELETE ON public.a2a_exchanges
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_reject_immutable_change();

COMMIT;
