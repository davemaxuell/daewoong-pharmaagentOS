-- FDA Drug Warning Letter Intelligence Platform
-- Reference schema for PostgreSQL 16+ with pgvector.
-- Apply through a controlled migration role. Application runtimes must not own objects.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS fda_intel;
SET search_path TO fda_intel, public;

DO $$ BEGIN
  CREATE TYPE scope_status AS ENUM (
    'UNVERIFIED', 'IN_SCOPE_DRUGS', 'OUT_OF_SCOPE', 'AMBIGUOUS', 'SCOPE_CHANGED'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE document_type AS ENUM (
    'warning_letter', 'response', 'closeout', 'attachment'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE review_state AS ENUM (
    'pending', 'auto_approved', 'approved', 'needs_revision', 'rejected'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE event_type AS ENUM (
    'NEW', 'UPDATED', 'RESPONSE_ADDED', 'CLOSEOUT_ADDED',
    'SOURCE_UNAVAILABLE', 'RESTORED', 'PARSE_FAILED', 'SCOPE_CHANGED',
    'CORPUS_RETIRED'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE job_status AS ENUM (
    'queued', 'running', 'succeeded', 'failed', 'dead_letter', 'cancelled'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE actor_type AS ENUM ('user', 'service_account', 'system');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  oidc_subject text NOT NULL,
  issuer text NOT NULL,
  corporate_user_id text,
  display_name text,
  email text,
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz,
  UNIQUE (issuer, oidc_subject)
);

CREATE TABLE IF NOT EXISTS role_bindings (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES users(id) ON DELETE CASCADE,
  oidc_group text,
  role_name text NOT NULL CHECK (
    role_name IN ('viewer', 'regulatory_analyst', 'reviewer', 'system_administrator', 'security_auditor')
  ),
  effective_from timestamptz NOT NULL DEFAULT now(),
  effective_until timestamptz,
  granted_by text NOT NULL,
  change_ticket text,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (user_id IS NOT NULL OR oidc_group IS NOT NULL),
  CHECK (effective_until IS NULL OR effective_until > effective_from)
);

CREATE INDEX IF NOT EXISTS role_bindings_user_idx ON role_bindings (user_id, effective_from);
CREATE INDEX IF NOT EXISTS role_bindings_group_idx ON role_bindings (oidc_group, effective_from);

CREATE TABLE IF NOT EXISTS service_accounts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL UNIQUE,
  workload_identity text NOT NULL UNIQUE,
  purpose text NOT NULL,
  owner text NOT NULL,
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
  credential_reference text,
  rotation_due_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (credential_reference IS NULL OR credential_reference !~* '(password|secret|token)\s*=')
);

CREATE TABLE IF NOT EXISTS ingestion_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_type text NOT NULL CHECK (run_type IN ('discovery', 'backfill', 'lifecycle', 'reprocess', 'integrity_sample')),
  status job_status NOT NULL DEFAULT 'queued',
  requested_by_actor_type actor_type NOT NULL DEFAULT 'system',
  requested_by text NOT NULL,
  idempotency_key text NOT NULL UNIQUE,
  checkpoint jsonb NOT NULL DEFAULT '{}'::jsonb,
  counters jsonb NOT NULL DEFAULT '{}'::jsonb,
  parser_version text,
  source_client_version text,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  error_code text,
  error_detail text,
  CHECK (jsonb_typeof(checkpoint) = 'object'),
  CHECK (jsonb_typeof(counters) = 'object')
);

CREATE TABLE IF NOT EXISTS discovery_snapshots (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ingestion_run_id uuid NOT NULL REFERENCES ingestion_runs(id),
  source_url text NOT NULL CHECK (source_url ~ '^https://([a-z0-9-]+\.)*fda\.gov/'),
  final_url text NOT NULL CHECK (final_url ~ '^https://([a-z0-9-]+\.)*fda\.gov/'),
  redirect_chain jsonb NOT NULL DEFAULT '[]'::jsonb,
  retrieved_at timestamptz NOT NULL,
  etag text,
  last_modified text,
  sha256 char(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  raw_object_key text NOT NULL,
  detected_columns text[] NOT NULL,
  schema_fingerprint char(64) NOT NULL CHECK (schema_fingerprint ~ '^[0-9a-f]{64}$'),
  row_count integer NOT NULL CHECK (row_count >= 0),
  parser_version text NOT NULL,
  source_client_version text NOT NULL,
  http_anomalies jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_url, sha256)
);

CREATE TABLE IF NOT EXISTS warning_letters (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  canonical_url text NOT NULL UNIQUE CHECK (canonical_url ~ '^https://([a-z0-9-]+\.)*fda\.gov/'),
  marcs_cms_number text,
  fda_reference_number text,
  company_name text NOT NULL,
  country text,
  subject text,
  issuing_offices text[] NOT NULL DEFAULT '{}',
  issue_date date,
  posted_date date,
  fda_product_raw jsonb NOT NULL DEFAULT '[]'::jsonb,
  normalized_product_classes text[] NOT NULL DEFAULT '{}',
  scope_status scope_status NOT NULL DEFAULT 'UNVERIFIED',
  scope_rule_version text,
  scope_source_anchor text,
  scope_decided_at timestamptz,
  current_in_scope boolean NOT NULL DEFAULT false,
  lifecycle_status text NOT NULL DEFAULT 'active' CHECK (lifecycle_status IN ('active', 'unavailable', 'closed', 'retired_by_retention')),
  current_version_id uuid,
  first_in_scope_version_id uuid,
  first_seen_at timestamptz NOT NULL,
  last_seen_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (last_seen_at >= first_seen_at),
  CHECK (current_in_scope = false OR scope_status = 'IN_SCOPE_DRUGS'),
  CHECK (jsonb_typeof(fda_product_raw) = 'array')
);

CREATE UNIQUE INDEX IF NOT EXISTS warning_letters_marcs_uq
  ON warning_letters (marcs_cms_number) WHERE marcs_cms_number IS NOT NULL;
CREATE INDEX IF NOT EXISTS warning_letters_posted_idx ON warning_letters (posted_date DESC, id);
CREATE INDEX IF NOT EXISTS warning_letters_company_idx ON warning_letters (lower(company_name));
CREATE INDEX IF NOT EXISTS warning_letters_scope_idx ON warning_letters (scope_status, current_in_scope);

CREATE TABLE IF NOT EXISTS documents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  warning_letter_id uuid NOT NULL REFERENCES warning_letters(id),
  parent_document_id uuid REFERENCES documents(id),
  document_type document_type NOT NULL,
  canonical_url text NOT NULL CHECK (canonical_url ~ '^https://([a-z0-9-]+\.)*fda\.gov/'),
  title text,
  issue_date date,
  current_version_id uuid,
  first_seen_at timestamptz NOT NULL,
  last_seen_at timestamptz NOT NULL,
  source_available boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (warning_letter_id, canonical_url),
  CHECK (last_seen_at >= first_seen_at),
  CHECK (parent_document_id IS NULL OR document_type <> 'warning_letter')
);

CREATE INDEX IF NOT EXISTS documents_warning_letter_idx ON documents (warning_letter_id, document_type);

CREATE TABLE IF NOT EXISTS document_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(id),
  version_number integer NOT NULL CHECK (version_number > 0),
  retrieved_at timestamptz NOT NULL,
  final_url text NOT NULL CHECK (final_url ~ '^https://([a-z0-9-]+\.)*fda\.gov/'),
  redirect_chain jsonb NOT NULL DEFAULT '[]'::jsonb,
  http_status smallint NOT NULL CHECK (http_status BETWEEN 100 AND 599),
  etag text,
  last_modified text,
  content_type text NOT NULL,
  raw_object_key text NOT NULL,
  raw_sha256 char(64) NOT NULL CHECK (raw_sha256 ~ '^[0-9a-f]{64}$'),
  canonical_body_sha256 char(64) NOT NULL CHECK (canonical_body_sha256 ~ '^[0-9a-f]{64}$'),
  normalized_markdown text NOT NULL,
  normalized_text text NOT NULL,
  parser_version text NOT NULL,
  extraction_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  fda_product_raw jsonb NOT NULL DEFAULT '[]'::jsonb,
  normalized_product_classes text[] NOT NULL DEFAULT '{}',
  scope_status scope_status NOT NULL,
  scope_rule_version text NOT NULL,
  scope_source_anchor text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (document_id, version_number),
  UNIQUE (document_id, canonical_body_sha256),
  CHECK (jsonb_typeof(redirect_chain) = 'array'),
  CHECK (jsonb_typeof(extraction_metadata) = 'object'),
  CHECK (jsonb_typeof(fda_product_raw) = 'array'),
  CHECK (scope_status <> 'IN_SCOPE_DRUGS' OR normalized_product_classes @> ARRAY['Drugs']::text[])
);

CREATE INDEX IF NOT EXISTS document_versions_document_idx
  ON document_versions (document_id, version_number DESC);
CREATE INDEX IF NOT EXISTS document_versions_scope_idx
  ON document_versions (scope_status, created_at DESC);

DO $$ BEGIN
  ALTER TABLE warning_letters
    ADD CONSTRAINT warning_letters_current_version_fk
    FOREIGN KEY (current_version_id) REFERENCES document_versions(id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  ALTER TABLE warning_letters
    ADD CONSTRAINT warning_letters_first_in_scope_version_fk
    FOREIGN KEY (first_in_scope_version_id) REFERENCES document_versions(id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  ALTER TABLE documents
    ADD CONSTRAINT documents_current_version_fk
    FOREIGN KEY (current_version_id) REFERENCES document_versions(id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS scope_decisions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  warning_letter_id uuid NOT NULL REFERENCES warning_letters(id),
  source_version_id uuid NOT NULL REFERENCES document_versions(id),
  canonical_url text NOT NULL,
  fda_product_raw jsonb NOT NULL,
  normalized_product_classes text[] NOT NULL,
  scope_status scope_status NOT NULL,
  scope_rule_version text NOT NULL,
  scope_source_anchor text,
  decision_method text NOT NULL CHECK (decision_method IN ('deterministic_parser', 'manual_exception')),
  decided_at timestamptz NOT NULL,
  decided_by text NOT NULL,
  reason text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_version_id, scope_rule_version),
  CHECK (jsonb_typeof(fda_product_raw) = 'array'),
  CHECK (scope_status <> 'IN_SCOPE_DRUGS' OR normalized_product_classes @> ARRAY['Drugs']::text[])
);

CREATE INDEX IF NOT EXISTS scope_decisions_letter_idx
  ON scope_decisions (warning_letter_id, decided_at DESC);

CREATE TABLE IF NOT EXISTS source_anchors (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_version_id uuid NOT NULL REFERENCES document_versions(id),
  anchor text NOT NULL,
  section_path text[] NOT NULL DEFAULT '{}',
  ordinal integer NOT NULL CHECK (ordinal >= 0),
  paragraph_start integer NOT NULL CHECK (paragraph_start >= 0),
  paragraph_end integer NOT NULL CHECK (paragraph_end >= paragraph_start),
  text_content text NOT NULL,
  dom_fingerprint char(64) CHECK (dom_fingerprint IS NULL OR dom_fingerprint ~ '^[0-9a-f]{64}$'),
  page_number integer CHECK (page_number IS NULL OR page_number > 0),
  bounding_reference jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (document_version_id, anchor),
  CHECK (bounding_reference IS NULL OR jsonb_typeof(bounding_reference) = 'object')
);

CREATE INDEX IF NOT EXISTS source_anchors_version_idx
  ON source_anchors (document_version_id, ordinal);

CREATE TABLE IF NOT EXISTS ai_summaries (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  idempotency_key text NOT NULL UNIQUE,
  document_version_id uuid NOT NULL REFERENCES document_versions(id),
  provider text NOT NULL,
  model_id text NOT NULL,
  prompt_version text NOT NULL,
  schema_version text NOT NULL,
  taxonomy_version text NOT NULL,
  language text NOT NULL DEFAULT 'en' CHECK (language IN ('en', 'ko')),
  structured_output jsonb NOT NULL,
  validation_report jsonb NOT NULL,
  review_state review_state NOT NULL DEFAULT 'pending',
  based_on_summary_id uuid REFERENCES ai_summaries(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  activated_at timestamptz,
  UNIQUE (document_version_id, model_id, prompt_version, schema_version, taxonomy_version, language, created_at),
  CHECK (jsonb_typeof(structured_output) = 'object'),
  CHECK (jsonb_typeof(validation_report) = 'object'),
  CHECK (review_state NOT IN ('auto_approved', 'approved') OR activated_at IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS ai_summaries_version_idx
  ON ai_summaries (document_version_id, review_state, created_at DESC);

-- Validated Korean translations are immutable, source-version-bound artifacts.
-- The source hash and generation profile form the cache key so a changed FDA
-- source can never silently reuse an older translation.
CREATE TABLE IF NOT EXISTS document_translations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_version_id uuid NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
  language text NOT NULL DEFAULT 'ko' CHECK (language = 'ko'),
  source_hash char(64) NOT NULL CHECK (source_hash ~ '^[0-9a-f]{64}$'),
  translated_sections jsonb NOT NULL,
  validation_report jsonb NOT NULL,
  provider text NOT NULL,
  model_id text NOT NULL,
  prompt_version text NOT NULL,
  schema_version text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (document_version_id, language, source_hash, model_id, prompt_version),
  CHECK (jsonb_typeof(translated_sections) = 'array'),
  CHECK (jsonb_typeof(validation_report) = 'object')
);

CREATE INDEX IF NOT EXISTS document_translations_version_idx
  ON document_translations (document_version_id, language, created_at DESC);

CREATE TABLE IF NOT EXISTS violations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ai_summary_id uuid NOT NULL REFERENCES ai_summaries(id),
  document_version_id uuid NOT NULL REFERENCES document_versions(id),
  label text NOT NULL,
  finding text NOT NULL,
  categories text[] NOT NULL DEFAULT '{}',
  process_lenses text[] NOT NULL DEFAULT '{}',
  regulatory_references text[] NOT NULL DEFAULT '{}',
  fda_requested_actions text[] NOT NULL DEFAULT '{}',
  comparison_points text[] NOT NULL DEFAULT '{}',
  attention_level text NOT NULL CHECK (attention_level IN ('low', 'medium', 'high', 'unknown')),
  confidence numeric(4,3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  review_state review_state NOT NULL DEFAULT 'pending',
  ordinal integer NOT NULL CHECK (ordinal >= 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (ai_summary_id, ordinal)
);

CREATE TABLE IF NOT EXISTS violation_evidence (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  violation_id uuid NOT NULL REFERENCES violations(id),
  source_anchor_id uuid NOT NULL REFERENCES source_anchors(id),
  excerpt text NOT NULL,
  excerpt_sha256 char(64) NOT NULL CHECK (excerpt_sha256 ~ '^[0-9a-f]{64}$'),
  ordinal integer NOT NULL CHECK (ordinal >= 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (violation_id, ordinal)
);

CREATE TABLE IF NOT EXISTS corpora (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  name text NOT NULL,
  data_class text NOT NULL CHECK (data_class IN ('public_source', 'internal', 'internal_confidential', 'controlled')),
  product_scope text NOT NULL,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO corpora (code, name, data_class, product_scope)
VALUES ('fda_drugs', 'FDA Product: Drugs', 'public_source', 'Drugs')
ON CONFLICT (code) DO NOTHING;

CREATE TABLE IF NOT EXISTS corpus_grants (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  corpus_id uuid NOT NULL REFERENCES corpora(id),
  principal_type text NOT NULL CHECK (principal_type IN ('user', 'oidc_group', 'role', 'service_account')),
  principal_id text NOT NULL,
  permission text NOT NULL CHECK (permission IN ('read', 'review', 'admin')),
  effective_from timestamptz NOT NULL DEFAULT now(),
  effective_until timestamptz,
  granted_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (corpus_id, principal_type, principal_id, permission),
  CHECK (effective_until IS NULL OR effective_until > effective_from)
);

CREATE TABLE IF NOT EXISTS document_chunks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  corpus_id uuid NOT NULL REFERENCES corpora(id),
  warning_letter_id uuid NOT NULL REFERENCES warning_letters(id),
  document_version_id uuid NOT NULL REFERENCES document_versions(id),
  source_anchor_id uuid NOT NULL REFERENCES source_anchors(id),
  chunker_version text NOT NULL,
  embedding_model_id text,
  ordinal integer NOT NULL CHECK (ordinal >= 0),
  section_path text[] NOT NULL DEFAULT '{}',
  content text NOT NULL,
  token_count integer NOT NULL CHECK (token_count > 0),
  drug_subtypes text[] NOT NULL DEFAULT '{}',
  categories text[] NOT NULL DEFAULT '{}',
  regulatory_references text[] NOT NULL DEFAULT '{}',
  search_vector tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
  embedding vector(1536),
  authorized_for_retrieval boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (document_version_id, chunker_version, ordinal)
);

CREATE INDEX IF NOT EXISTS document_chunks_fts_idx ON document_chunks USING gin (search_vector);
CREATE INDEX IF NOT EXISTS document_chunks_embedding_hnsw_idx
  ON document_chunks USING hnsw (embedding vector_cosine_ops)
  WHERE embedding IS NOT NULL AND authorized_for_retrieval;
CREATE INDEX IF NOT EXISTS document_chunks_authz_idx
  ON document_chunks (corpus_id, authorized_for_retrieval, warning_letter_id);

-- Embeddings are versioned separately from chunks so an approved embedding-model
-- migration can be backfilled and validated before the active index is switched.
-- The chunk's inline embedding column remains the active/compatibility projection.
CREATE TABLE IF NOT EXISTS chunk_embeddings (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_chunk_id uuid NOT NULL REFERENCES document_chunks(id) ON DELETE CASCADE,
  provider text NOT NULL,
  model_id text NOT NULL,
  dimensions integer NOT NULL CHECK (dimensions = 1536),
  input_schema_version text NOT NULL,
  content_sha256 char(64) NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
  provider_input_sha256 char(64) NOT NULL CHECK (provider_input_sha256 ~ '^[0-9a-f]{64}$'),
  embedding vector(1536) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (
    document_chunk_id,
    provider,
    model_id,
    dimensions,
    input_schema_version,
    content_sha256,
    provider_input_sha256
  )
);

CREATE INDEX IF NOT EXISTS chunk_embeddings_hnsw_idx
  ON chunk_embeddings USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS chunk_embeddings_chunk_model_idx
  ON chunk_embeddings (
    document_chunk_id,
    provider,
    model_id,
    dimensions,
    input_schema_version,
    created_at DESC
  );

CREATE TABLE IF NOT EXISTS change_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  warning_letter_id uuid NOT NULL REFERENCES warning_letters(id),
  document_id uuid REFERENCES documents(id),
  event_type event_type NOT NULL,
  before_version_id uuid REFERENCES document_versions(id),
  after_version_id uuid REFERENCES document_versions(id),
  before_state jsonb,
  after_state jsonb,
  detected_at timestamptz NOT NULL,
  published_at timestamptz,
  notification_state text NOT NULL DEFAULT 'pending' CHECK (notification_state IN ('pending', 'sent', 'suppressed', 'failed')),
  idempotency_key text NOT NULL UNIQUE,
  ingestion_run_id uuid REFERENCES ingestion_runs(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (before_state IS NULL OR jsonb_typeof(before_state) = 'object'),
  CHECK (after_state IS NULL OR jsonb_typeof(after_state) = 'object')
);

CREATE INDEX IF NOT EXISTS change_events_detected_idx ON change_events (detected_at DESC, id);

CREATE TABLE IF NOT EXISTS reviews (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  summary_id uuid NOT NULL REFERENCES ai_summaries(id),
  reviewer_user_id uuid NOT NULL REFERENCES users(id),
  decision review_state NOT NULL CHECK (decision IN ('approved', 'needs_revision', 'rejected')),
  before_value jsonb NOT NULL,
  after_value jsonb NOT NULL,
  reason text NOT NULL,
  change_ticket text,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (jsonb_typeof(before_value) = 'object'),
  CHECK (jsonb_typeof(after_value) = 'object')
);

CREATE TABLE IF NOT EXISTS processing_jobs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ingestion_run_id uuid REFERENCES ingestion_runs(id),
  job_type text NOT NULL,
  status job_status NOT NULL DEFAULT 'queued',
  idempotency_key text NOT NULL UNIQUE,
  subject_type text NOT NULL,
  subject_id uuid,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  attempt integer NOT NULL DEFAULT 0 CHECK (attempt >= 0),
  max_attempts integer NOT NULL DEFAULT 5 CHECK (max_attempts > 0),
  available_at timestamptz NOT NULL DEFAULT now(),
  locked_at timestamptz,
  locked_by text,
  last_error_code text,
  last_error_detail text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (jsonb_typeof(payload) = 'object')
);

CREATE INDEX IF NOT EXISTS processing_jobs_claim_idx
  ON processing_jobs (status, available_at, created_at)
  WHERE status IN ('queued', 'failed');

CREATE TABLE IF NOT EXISTS subscriptions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(id),
  name text NOT NULL,
  description text NOT NULL DEFAULT '',
  criteria jsonb NOT NULL,
  cadence text NOT NULL CHECK (cadence IN ('immediate', 'daily', 'weekly')),
  channel text NOT NULL CHECK (channel IN ('email', 'slack')),
  destination_reference text NOT NULL,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (jsonb_typeof(criteria) = 'object')
);

CREATE TABLE IF NOT EXISTS notification_deliveries (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  change_event_id uuid NOT NULL REFERENCES change_events(id),
  subscription_id uuid NOT NULL REFERENCES subscriptions(id),
  status text NOT NULL CHECK (status IN ('queued', 'sent', 'failed', 'suppressed')),
  destination_identifier text NOT NULL,
  provider_message_id text,
  attempt integer NOT NULL DEFAULT 0 CHECK (attempt >= 0),
  delivered_at timestamptz,
  error_code text,
  idempotency_key text NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chat_threads (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  -- Immutable Google OIDC subject ("google:<sub>"). No local username,
  -- password, Google access token, or refresh token is stored.
  owner_subject text NOT NULL,
  title text NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
  model_preference text NOT NULL DEFAULT 'auto'
    CHECK (model_preference IN ('auto', 'fast', 'balanced', 'deep')),
  retrieval_preference text NOT NULL DEFAULT 'auto'
    CHECK (retrieval_preference IN ('auto', 'none', 'metadata', 'letter', 'corpus')),
  active_letter_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  archived_at timestamptz,
  last_message_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (jsonb_typeof(active_letter_ids) = 'array')
);

CREATE INDEX IF NOT EXISTS chat_threads_owner_recent_idx
  ON chat_threads (owner_subject, archived_at, last_message_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS chat_messages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  thread_id uuid NOT NULL REFERENCES chat_threads(id) ON DELETE CASCADE,
  sequence integer NOT NULL CHECK (sequence >= 1),
  role text NOT NULL CHECK (role IN ('user', 'assistant')),
  content text NOT NULL CHECK (length(content) > 0),
  status text NOT NULL DEFAULT 'completed'
    CHECK (status IN ('pending', 'completed', 'failed')),
  client_message_id text,
  in_reply_to_id uuid REFERENCES chat_messages(id) ON DELETE SET NULL,
  rag_query_id uuid,
  citations jsonb NOT NULL DEFAULT '[]'::jsonb,
  route_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  model_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (thread_id, sequence),
  UNIQUE (thread_id, client_message_id),
  CHECK (jsonb_typeof(citations) = 'array'),
  CHECK (jsonb_typeof(route_metadata) = 'object'),
  CHECK (jsonb_typeof(model_metadata) = 'object')
);

CREATE INDEX IF NOT EXISTS chat_messages_thread_sequence_idx
  ON chat_messages (thread_id, sequence);

CREATE TABLE IF NOT EXISTS chat_thread_focus (
  -- One exact, server-resolved document anchor per conversation. Clients select
  -- a citation; they never supply the parent document/version/letter identities.
  thread_id uuid PRIMARY KEY REFERENCES chat_threads(id) ON DELETE CASCADE,
  warning_letter_id uuid NOT NULL REFERENCES warning_letters(id) ON DELETE CASCADE,
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  document_version_id uuid NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
  source_chunk_id uuid NOT NULL REFERENCES document_chunks(id) ON DELETE CASCADE,
  source_message_id uuid NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
  selected_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS chat_thread_focus_document_version_idx
  ON chat_thread_focus (document_version_id, thread_id);
CREATE INDEX IF NOT EXISTS chat_thread_focus_warning_letter_idx
  ON chat_thread_focus (warning_letter_id);
CREATE INDEX IF NOT EXISTS chat_thread_focus_source_message_idx
  ON chat_thread_focus (source_message_id);

CREATE TABLE IF NOT EXISTS rag_queries (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_id text NOT NULL,
  query_sha256 char(64) NOT NULL CHECK (query_sha256 ~ '^[0-9a-f]{64}$'),
  query_length integer NOT NULL CHECK (query_length >= 0),
  language text NOT NULL DEFAULT 'auto' CHECK (language IN ('auto', 'en', 'ko')),
  filters jsonb NOT NULL DEFAULT '{}'::jsonb,
  retrieved_chunk_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  evidence_sufficient boolean NOT NULL DEFAULT false,
  latency_ms integer CHECK (latency_ms IS NULL OR latency_ms >= 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (jsonb_typeof(filters) = 'object'),
  CHECK (jsonb_typeof(retrieved_chunk_ids) = 'array')
);

CREATE INDEX IF NOT EXISTS rag_queries_actor_created_idx ON rag_queries (actor_id, created_at DESC);

DO $$ BEGIN
  ALTER TABLE chat_messages
    ADD CONSTRAINT chat_messages_rag_query_fk
    FOREIGN KEY (rag_query_id) REFERENCES rag_queries(id) ON DELETE SET NULL;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS audit_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  occurred_at timestamptz NOT NULL DEFAULT now(),
  actor_type actor_type NOT NULL,
  actor_id text NOT NULL,
  corporate_user_id text,
  source_ip inet,
  session_context jsonb NOT NULL DEFAULT '{}'::jsonb,
  request_id text NOT NULL,
  trace_id text,
  operation text NOT NULL,
  object_type text NOT NULL,
  object_id text,
  before_hash char(64) CHECK (before_hash IS NULL OR before_hash ~ '^[0-9a-f]{64}$'),
  after_hash char(64) CHECK (after_hash IS NULL OR after_hash ~ '^[0-9a-f]{64}$'),
  before_value_reference text,
  after_value_reference text,
  result text NOT NULL CHECK (result IN ('success', 'denied', 'failure')),
  reason text,
  change_ticket text,
  application_version text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  CHECK (jsonb_typeof(session_context) = 'object'),
  CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE INDEX IF NOT EXISTS audit_events_occurred_idx ON audit_events (occurred_at DESC, id);
CREATE INDEX IF NOT EXISTS audit_events_actor_idx ON audit_events (actor_type, actor_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS audit_events_object_idx ON audit_events (object_type, object_id, occurred_at DESC);

CREATE OR REPLACE VIEW current_drug_letters AS
SELECT wl.*
FROM warning_letters wl
WHERE wl.current_in_scope
  AND wl.scope_status = 'IN_SCOPE_DRUGS'
  AND wl.normalized_product_classes @> ARRAY['Drugs']::text[];

CREATE OR REPLACE VIEW authorized_drug_chunks AS
SELECT dc.*
FROM document_chunks dc
JOIN corpora c ON c.id = dc.corpus_id
JOIN warning_letters wl ON wl.id = dc.warning_letter_id
JOIN document_versions dv ON dv.id = dc.document_version_id
WHERE c.code = 'fda_drugs'
  AND c.active
  AND dc.authorized_for_retrieval
  AND wl.current_in_scope
  AND wl.scope_status = 'IN_SCOPE_DRUGS'
  AND dv.scope_status = 'IN_SCOPE_DRUGS'
  AND wl.normalized_product_classes @> ARRAY['Drugs']::text[]
  AND dv.normalized_product_classes @> ARRAY['Drugs']::text[];

COMMENT ON VIEW authorized_drug_chunks IS
  'Scope-safe base view only. Query code must additionally join effective corpus_grants before lexical/vector retrieval.';
COMMENT ON COLUMN service_accounts.credential_reference IS
  'Identifier in an approved secret manager; never a raw credential.';
COMMENT ON COLUMN rag_queries.query_sha256 IS
  'One-way audit fingerprint only; raw user questions are retained inside their owner-scoped chat thread.';
COMMENT ON COLUMN document_chunks.embedding IS
  'Starter dimension 1536; change through a migration when the approved embedding model differs.';

COMMIT;
