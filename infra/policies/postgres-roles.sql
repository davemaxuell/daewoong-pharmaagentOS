-- Apply after contracts/schema.sql as the schema owner/migration identity.
-- These NOLOGIN roles contain privileges only. Bind approved short-lived workload
-- identities separately; do not add passwords to this file.

BEGIN;

DO $$ BEGIN
  CREATE ROLE fda_api_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE ROLE fda_ingestion_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE ROLE fda_worker_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE ROLE fda_readonly_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

REVOKE ALL ON SCHEMA fda_intel FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA fda_intel TO
  fda_api_runtime, fda_ingestion_runtime, fda_worker_runtime, fda_readonly_runtime;

GRANT SELECT ON
  fda_intel.current_drug_letters,
  fda_intel.authorized_drug_chunks,
  fda_intel.warning_letters,
  fda_intel.documents,
  fda_intel.document_versions,
  fda_intel.source_anchors,
  fda_intel.ai_summaries,
  fda_intel.document_translations,
  fda_intel.violations,
  fda_intel.violation_evidence,
  fda_intel.change_events,
  fda_intel.corpora,
  fda_intel.corpus_grants,
  fda_intel.ingestion_runs,
  fda_intel.processing_jobs,
  fda_intel.reviews
TO fda_api_runtime;
GRANT INSERT ON
  fda_intel.audit_events,
  fda_intel.rag_queries,
  fda_intel.ai_summaries,
  fda_intel.document_translations,
  fda_intel.violations,
  fda_intel.ingestion_runs,
  fda_intel.processing_jobs,
  fda_intel.reviews
TO fda_api_runtime;
GRANT UPDATE (status, started_at, completed_at, error_code, error_detail)
  ON fda_intel.ingestion_runs TO fda_api_runtime;

GRANT SELECT, INSERT ON
  fda_intel.discovery_snapshots,
  fda_intel.document_versions,
  fda_intel.scope_decisions,
  fda_intel.source_anchors,
  fda_intel.change_events,
  fda_intel.audit_events
TO fda_ingestion_runtime;
GRANT SELECT, INSERT, UPDATE ON
  fda_intel.ingestion_runs,
  fda_intel.processing_jobs,
  fda_intel.warning_letters,
  fda_intel.documents
TO fda_ingestion_runtime;

GRANT SELECT ON
  fda_intel.warning_letters,
  fda_intel.documents,
  fda_intel.document_versions,
  fda_intel.scope_decisions,
  fda_intel.source_anchors,
  fda_intel.ai_summaries,
  fda_intel.document_translations,
  fda_intel.violations,
  fda_intel.violation_evidence,
  fda_intel.corpora,
  fda_intel.corpus_grants,
  fda_intel.document_chunks,
  fda_intel.change_events,
  fda_intel.processing_jobs,
  fda_intel.subscriptions,
  fda_intel.notification_deliveries
TO fda_worker_runtime;
GRANT INSERT ON
  fda_intel.ai_summaries,
  fda_intel.document_translations,
  fda_intel.violations,
  fda_intel.violation_evidence,
  fda_intel.document_chunks,
  fda_intel.change_events,
  fda_intel.notification_deliveries,
  fda_intel.audit_events
TO fda_worker_runtime;
GRANT UPDATE ON
  fda_intel.ai_summaries,
  fda_intel.processing_jobs,
  fda_intel.notification_deliveries
TO fda_worker_runtime;

GRANT SELECT ON
  fda_intel.current_drug_letters,
  fda_intel.warning_letters,
  fda_intel.documents,
  fda_intel.document_versions,
  fda_intel.change_events
TO fda_readonly_runtime;

COMMIT;
