-- Apply as the dedicated PharmaAgent OS migration owner after all migrations/grants.
-- This changes only the explicit application tables; never use a shared project
-- as a substitute for reviewing this boundary. Supabase auth/storage stay untouched.
BEGIN;

DO $boundary$
DECLARE
  table_name text;
  app_tables text[] := ARRAY[
    'a2a_exchanges', 'agent_cases', 'agent_invocations', 'agent_versions',
    'ai_summaries', 'approval_requests', 'artifact_evidence', 'artifact_versions',
    'artifacts', 'asset_relations', 'audit_events', 'case_events', 'case_plan_steps',
    'case_plans', 'case_runs', 'case_sources', 'change_events', 'chat_messages',
    'chat_thread_focus', 'chat_threads', 'chunk_embeddings', 'discovery_snapshots',
    'document_chunks', 'document_translations', 'document_versions', 'documents',
    'durable_activities', 'evaluation_cases', 'evaluation_grades', 'evaluation_runs',
    'evaluation_suites', 'evaluation_trials', 'impact_hypotheses', 'ingestion_runs',
    'integration_outbox', 'internal_asset_acl', 'internal_asset_versions',
    'internal_assets', 'notification_deliveries', 'platform_controls',
    'policy_decisions', 'processing_jobs', 'production_feedback', 'rag_queries',
    'relation_evidence', 'release_approvals', 'research_runs', 'research_events', 'reviews', 'run_events',
    'scope_decisions', 'skill_versions', 'subscriptions', 'tool_invocations',
    'tool_versions', 'verification_reports', 'violations', 'warning_letters',
    'workflow_template_versions'
  ];
BEGIN
  FOREACH table_name IN ARRAY app_tables LOOP
    IF to_regclass(format('public.%I', table_name)) IS NULL THEN
      RAISE EXCEPTION 'Missing application table %. Complete migrations first.', table_name;
    END IF;
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM PUBLIC, anon, authenticated', table_name);
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('DROP POLICY IF EXISTS pharma_server_runtime ON public.%I', table_name);
    EXECUTE format(
      'CREATE POLICY pharma_server_runtime ON public.%I FOR ALL TO '
      'fda_api_runtime, fda_worker_runtime, fda_readonly_runtime, '
      'pharma_orchestrator_runtime, pharma_mcp_runtime USING (true) WITH CHECK (true)',
      table_name
    );
  END LOOP;
END
$boundary$;

-- Applies to future tables created by this migration identity. New tables must
-- also be added to the explicit list and receive the runtime policy before use.
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anon, authenticated;
COMMIT;
