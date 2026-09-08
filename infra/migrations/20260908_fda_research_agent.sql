-- Session-owned public-FDA research drafts. Run as the migration owner.
BEGIN;
CREATE TABLE IF NOT EXISTS public.research_runs (
  id varchar(36) PRIMARY KEY,
  owner_id varchar(255) NOT NULL,
  client_request_id varchar(36) NOT NULL,
  objective text NOT NULL,
  language varchar(2) NOT NULL CHECK (language IN ('en', 'ko')),
  status varchar(32) NOT NULL DEFAULT 'queued' CHECK
    (status IN ('queued','running','completed','stopped','failed','limit_reached','insufficient_evidence')),
  stage varchar(32) NOT NULL DEFAULT 'planning',
  revision integer NOT NULL DEFAULT 0,
  checkpoint json NOT NULL DEFAULT '{}',
  result json,
  model_calls integer NOT NULL DEFAULT 0,
  total_tokens integer NOT NULL DEFAULT 0,
  resumes integer NOT NULL DEFAULT 0,
  lease_id varchar(36),
  lease_expires_at timestamptz,
  error_code varchar(80),
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_research_owner_request UNIQUE (owner_id, client_request_id),
  CHECK (model_calls >= 0 AND total_tokens >= 0)
);
CREATE INDEX IF NOT EXISTS ix_research_runs_owner_id ON public.research_runs(owner_id);
CREATE INDEX IF NOT EXISTS ix_research_runs_status ON public.research_runs(status);
CREATE INDEX IF NOT EXISTS ix_research_queue ON public.research_runs(status, lease_expires_at, created_at);
CREATE TABLE IF NOT EXISTS public.research_events (
  id varchar(36) PRIMARY KEY,
  run_id varchar(36) NOT NULL REFERENCES public.research_runs(id) ON DELETE CASCADE,
  sequence integer NOT NULL,
  kind varchar(50) NOT NULL,
  stage varchar(32) NOT NULL,
  data json NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_research_event_sequence UNIQUE (run_id, sequence)
);
CREATE INDEX IF NOT EXISTS ix_research_events_run_id ON public.research_events(run_id);
ALTER TABLE public.research_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.research_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.research_runs, public.research_events FROM PUBLIC;
DO $boundary$
DECLARE role_name text;
BEGIN
  FOREACH role_name IN ARRAY ARRAY['anon', 'authenticated', 'fda_readonly_runtime'] LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
      EXECUTE format('REVOKE ALL ON public.research_runs, public.research_events FROM %I', role_name);
    END IF;
  END LOOP;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='fda_api_runtime')
    AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname='fda_worker_runtime') THEN
    GRANT SELECT, INSERT, UPDATE ON public.research_runs TO fda_api_runtime, fda_worker_runtime;
    GRANT SELECT, INSERT ON public.research_events TO fda_api_runtime, fda_worker_runtime;
    DROP POLICY IF EXISTS pharma_research_runtime ON public.research_runs;
    DROP POLICY IF EXISTS pharma_research_runtime ON public.research_events;
    CREATE POLICY pharma_research_runtime ON public.research_runs
      TO fda_api_runtime, fda_worker_runtime USING (true) WITH CHECK (true);
    CREATE POLICY pharma_research_runtime ON public.research_events
      TO fda_api_runtime, fda_worker_runtime USING (true) WITH CHECK (true);
  END IF;
END $boundary$;
COMMIT;
