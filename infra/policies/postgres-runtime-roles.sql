-- Apply to the SQLAlchemy runtime schema in `public` after `fda-intel init-db`,
-- using the schema owner/migration identity. These are NOLOGIN group roles;
-- bind short-lived workload identities separately.

BEGIN;

DO $$ BEGIN
  CREATE ROLE fda_api_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE ROLE fda_worker_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE ROLE fda_readonly_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE ROLE pharma_orchestrator_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE ROLE pharma_mcp_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO
  fda_api_runtime, fda_worker_runtime, fda_readonly_runtime,
  pharma_orchestrator_runtime, pharma_mcp_runtime;

GRANT SELECT ON ALL TABLES IN SCHEMA public TO
  fda_api_runtime, fda_worker_runtime, fda_readonly_runtime;

-- Agent-control-plane records contain case-scoped objectives, approvals,
-- evidence bindings, and exact tool observations. They are resolved through
-- the API's object-level authorization, never through the generic readonly
-- database identity.
REVOKE SELECT ON
  public.agent_versions,
  public.skill_versions,
  public.tool_versions,
  public.workflow_template_versions,
  public.agent_cases,
  public.case_sources,
  public.case_events,
  public.case_plans,
  public.case_plan_steps,
  public.case_runs,
  public.run_events,
  public.agent_invocations,
  public.policy_decisions,
  public.tool_invocations,
  public.artifacts,
  public.artifact_versions,
  public.artifact_evidence,
  public.approval_requests,
  public.internal_assets,
  public.internal_asset_versions,
  public.internal_asset_acl,
  public.asset_relations,
  public.relation_evidence,
  public.impact_hypotheses,
  public.verification_reports,
  public.evaluation_suites,
  public.evaluation_cases,
  public.evaluation_runs,
  public.evaluation_trials,
  public.evaluation_grades,
  public.release_approvals,
  public.production_feedback,
  public.platform_controls,
  public.durable_activities,
  public.integration_outbox,
  public.a2a_exchanges
FROM fda_readonly_runtime;

REVOKE SELECT ON public.research_runs, public.research_events FROM fda_readonly_runtime;
GRANT SELECT, INSERT, UPDATE ON public.research_runs TO fda_api_runtime, fda_worker_runtime;
GRANT SELECT, INSERT ON public.research_events TO fda_api_runtime, fda_worker_runtime;

GRANT INSERT ON
  public.ai_summaries,
  public.document_translations,
  public.violations,
  public.reviews,
  public.ingestion_runs,
  public.processing_jobs,
  public.subscriptions,
  public.audit_events,
  public.rag_queries,
  public.chat_threads,
  public.chat_messages,
  public.chat_thread_focus,
  public.workflow_template_versions,
  public.agent_cases,
  public.case_sources,
  public.case_events,
  public.case_plans,
  public.case_plan_steps,
  public.case_runs,
  public.run_events,
  public.agent_invocations,
  public.approval_requests,
  public.policy_decisions,
  public.tool_invocations,
  public.artifacts,
  public.artifact_versions,
  public.artifact_evidence,
  public.impact_hypotheses,
  public.verification_reports,
  public.evaluation_suites,
  public.evaluation_cases,
  public.evaluation_runs,
  public.evaluation_trials,
  public.evaluation_grades,
  public.release_approvals,
  public.production_feedback,
  public.platform_controls,
  public.integration_outbox,
  public.a2a_exchanges
TO fda_api_runtime;

GRANT UPDATE ON
  public.evaluation_runs,
  public.agent_versions,
  public.platform_controls,
  public.integration_outbox
TO fda_api_runtime;

GRANT UPDATE ON
  public.ai_summaries,
  public.subscriptions,
  public.ingestion_runs,
  public.processing_jobs,
  public.chat_threads,
  public.chat_messages,
  public.chat_thread_focus,
  public.workflow_template_versions,
  public.agent_cases,
  public.case_runs,
  public.agent_invocations,
  public.approval_requests,
  public.artifact_versions
TO fda_api_runtime;

-- A background agent host uses the same guarded tables when execution is
-- deployed outside the API process. Database triggers still require exact
-- active-run, registry, policy, and result bindings for every observation.
GRANT INSERT ON
  public.run_events,
  public.agent_invocations,
  public.approval_requests,
  public.policy_decisions,
  public.tool_invocations,
  public.impact_hypotheses,
  public.verification_reports,
  public.durable_activities
TO fda_worker_runtime;

GRANT UPDATE ON public.case_runs TO fda_worker_runtime;
GRANT UPDATE ON public.durable_activities TO fda_worker_runtime;

GRANT SELECT ON
  public.agent_versions,
  public.skill_versions,
  public.tool_versions,
  public.workflow_template_versions,
  public.agent_cases,
  public.case_sources,
  public.case_plans,
  public.case_plan_steps,
  public.case_runs,
  public.run_events,
  public.agent_invocations,
  public.approval_requests,
  public.platform_controls,
  public.durable_activities
TO pharma_orchestrator_runtime;

GRANT INSERT ON public.run_events, public.agent_invocations, public.approval_requests,
  public.durable_activities
TO pharma_orchestrator_runtime;
GRANT UPDATE ON public.agent_cases, public.case_runs, public.agent_invocations,
  public.approval_requests, public.durable_activities
TO pharma_orchestrator_runtime;

GRANT SELECT ON
  public.agent_versions,
  public.tool_versions,
  public.agent_cases,
  public.case_sources,
  public.case_plans,
  public.case_plan_steps,
  public.case_runs,
  public.agent_invocations,
  public.approval_requests,
  public.platform_controls,
  public.document_versions,
  public.document_chunks,
  public.internal_assets,
  public.internal_asset_versions,
  public.internal_asset_acl,
  public.asset_relations,
  public.relation_evidence,
  public.policy_decisions,
  public.tool_invocations,
  public.integration_outbox
TO pharma_mcp_runtime;

GRANT INSERT ON public.policy_decisions, public.tool_invocations,
  public.integration_outbox, public.audit_events
TO pharma_mcp_runtime;
GRANT UPDATE ON public.case_runs TO pharma_mcp_runtime;

GRANT UPDATE ON
  public.agent_cases,
  public.agent_invocations,
  public.approval_requests,
  public.impact_hypotheses
TO fda_worker_runtime;

-- Corpus ingestion uses the worker identity. The API may only read ACL-filtered
-- projections and review existing hypotheses; it cannot alter source revisions.
GRANT INSERT ON
  public.internal_assets,
  public.internal_asset_versions,
  public.internal_asset_acl,
  public.asset_relations,
  public.relation_evidence
TO fda_worker_runtime;

GRANT UPDATE ON public.internal_assets, public.asset_relations
TO fda_worker_runtime;

-- Clearing or replacing a selected document removes only this owner-scoped
-- provenance row; content, source, and chat records remain immutable here.
GRANT DELETE ON public.chat_thread_focus TO fda_api_runtime;

GRANT INSERT, UPDATE ON
  public.warning_letters,
  public.documents,
  public.document_versions,
  public.scope_decisions,
  public.change_events,
  public.ai_summaries,
  public.document_translations,
  public.violations,
  public.document_chunks,
  public.chunk_embeddings,
  public.ingestion_runs,
  public.processing_jobs,
  public.subscriptions,
  public.notification_deliveries,
  public.audit_events,
  public.discovery_snapshots
TO fda_worker_runtime;

GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO
  fda_api_runtime, fda_worker_runtime, pharma_orchestrator_runtime, pharma_mcp_runtime;

-- Run these as the migration owner so future objects never become public.
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM PUBLIC;

COMMIT;
