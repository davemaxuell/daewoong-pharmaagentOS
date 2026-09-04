-- Milestone 4 ACL-safe internal knowledge, revision graph, and impact hypotheses.
-- Apply after 20260904_agent_os_orchestration.sql.

BEGIN;

CREATE TABLE IF NOT EXISTS public.internal_assets (
  id varchar(36) PRIMARY KEY,
  asset_key varchar(160) NOT NULL UNIQUE,
  asset_type varchar(80) NOT NULL,
  title varchar(500) NOT NULL,
  domain varchar(160) NOT NULL,
  classification varchar(40) NOT NULL DEFAULT 'INTERNAL_SYNTHETIC',
  synthetic boolean NOT NULL DEFAULT true,
  lifecycle_status varchar(32) NOT NULL DEFAULT 'ACTIVE',
  current_version_id varchar(36),
  created_by varchar(255) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_internal_assets_classification CHECK (
    classification IN ('INTERNAL_SYNTHETIC', 'INTERNAL', 'CONFIDENTIAL')
  ),
  CONSTRAINT ck_internal_assets_lifecycle CHECK (
    lifecycle_status IN ('ACTIVE', 'RETIRED')
  ),
  CONSTRAINT ck_internal_assets_synthetic_label CHECK (
    classification <> 'INTERNAL_SYNTHETIC' OR synthetic
  )
);

CREATE TABLE IF NOT EXISTS public.internal_asset_versions (
  id varchar(36) PRIMARY KEY,
  asset_id varchar(36) NOT NULL
    REFERENCES public.internal_assets(id) ON DELETE RESTRICT,
  revision integer NOT NULL,
  status varchar(20) NOT NULL DEFAULT 'DRAFT',
  effective_from date,
  effective_to date,
  content text NOT NULL,
  content_sha256 varchar(64) NOT NULL,
  anchors jsonb NOT NULL DEFAULT '[]'::jsonb,
  asset_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  search_text text NOT NULL,
  embedding vector(64),
  created_by varchar(255) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_internal_asset_versions_revision UNIQUE (asset_id, revision),
  CONSTRAINT uq_internal_asset_versions_hash UNIQUE (asset_id, content_sha256),
  CONSTRAINT ck_internal_asset_versions_revision CHECK (revision >= 1),
  CONSTRAINT ck_internal_asset_versions_status CHECK (
    status IN ('DRAFT', 'EFFECTIVE', 'OBSOLETE', 'RETIRED')
  ),
  CONSTRAINT ck_internal_asset_versions_hash CHECK (length(content_sha256) = 64),
  CONSTRAINT ck_internal_asset_versions_effective_dates CHECK (
    effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from
  ),
  CONSTRAINT ck_internal_asset_versions_anchors CHECK (jsonb_typeof(anchors) = 'array'),
  CONSTRAINT ck_internal_asset_versions_metadata CHECK (
    jsonb_typeof(asset_metadata) = 'object'
  )
);

ALTER TABLE public.internal_assets
  DROP CONSTRAINT IF EXISTS fk_internal_assets_current_version;
ALTER TABLE public.internal_assets
  ADD CONSTRAINT fk_internal_assets_current_version
  FOREIGN KEY (current_version_id)
  REFERENCES public.internal_asset_versions(id) ON DELETE RESTRICT;

CREATE TABLE IF NOT EXISTS public.internal_asset_acl (
  id varchar(36) PRIMARY KEY,
  asset_id varchar(36) NOT NULL
    REFERENCES public.internal_assets(id) ON DELETE RESTRICT,
  principal_kind varchar(20) NOT NULL,
  principal_value varchar(255) NOT NULL,
  permission varchar(20) NOT NULL DEFAULT 'READ',
  created_by varchar(255) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_internal_asset_acl_grant UNIQUE (
    asset_id, principal_kind, principal_value, permission
  ),
  CONSTRAINT ck_internal_asset_acl_principal_kind CHECK (
    principal_kind IN ('ROLE', 'SUBJECT')
  ),
  CONSTRAINT ck_internal_asset_acl_permission CHECK (permission = 'READ')
);

CREATE TABLE IF NOT EXISTS public.asset_relations (
  id varchar(36) PRIMARY KEY,
  source_asset_id varchar(36) NOT NULL
    REFERENCES public.internal_assets(id) ON DELETE RESTRICT,
  target_asset_id varchar(36) NOT NULL
    REFERENCES public.internal_assets(id) ON DELETE RESTRICT,
  relation_type varchar(80) NOT NULL,
  status varchar(20) NOT NULL DEFAULT 'PROPOSED',
  confidence double precision NOT NULL,
  rationale text NOT NULL,
  proposed_by varchar(255) NOT NULL,
  reviewed_by varchar(255),
  review_reason text,
  reviewed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_asset_relations_edge UNIQUE (
    source_asset_id, target_asset_id, relation_type
  ),
  CONSTRAINT ck_asset_relations_distinct CHECK (source_asset_id <> target_asset_id),
  CONSTRAINT ck_asset_relations_status CHECK (
    status IN ('PROPOSED', 'APPROVED', 'REJECTED')
  ),
  CONSTRAINT ck_asset_relations_confidence CHECK (confidence BETWEEN 0 AND 1),
  CONSTRAINT ck_asset_relations_review CHECK (
    status = 'PROPOSED' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)
  )
);

CREATE TABLE IF NOT EXISTS public.relation_evidence (
  id varchar(36) PRIMARY KEY,
  relation_id varchar(36) NOT NULL
    REFERENCES public.asset_relations(id) ON DELETE RESTRICT,
  asset_version_id varchar(36) NOT NULL
    REFERENCES public.internal_asset_versions(id) ON DELETE RESTRICT,
  content_sha256 varchar(64) NOT NULL,
  anchor varchar(255) NOT NULL,
  excerpt_sha256 varchar(64) NOT NULL,
  evidence_role varchar(40) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_relation_evidence_anchor UNIQUE (
    relation_id, asset_version_id, anchor
  ),
  CONSTRAINT ck_relation_evidence_hashes CHECK (
    length(content_sha256) = 64 AND length(excerpt_sha256) = 64
  ),
  CONSTRAINT ck_relation_evidence_role CHECK (
    evidence_role IN ('SOURCE', 'TARGET')
  )
);

CREATE TABLE IF NOT EXISTS public.impact_hypotheses (
  id varchar(36) PRIMARY KEY,
  case_id varchar(36) NOT NULL
    REFERENCES public.agent_cases(id) ON DELETE RESTRICT,
  run_id varchar(36),
  finding_id varchar(160) NOT NULL,
  asset_id varchar(36) NOT NULL
    REFERENCES public.internal_assets(id) ON DELETE RESTRICT,
  asset_version_id varchar(36) NOT NULL
    REFERENCES public.internal_asset_versions(id) ON DELETE RESTRICT,
  relationship_type varchar(80) NOT NULL,
  statement text NOT NULL,
  known_facts jsonb NOT NULL DEFAULT '[]'::jsonb,
  derived_relationships jsonb NOT NULL DEFAULT '[]'::jsonb,
  assumptions jsonb NOT NULL DEFAULT '[]'::jsonb,
  counterevidence jsonb NOT NULL DEFAULT '[]'::jsonb,
  unknowns jsonb NOT NULL DEFAULT '[]'::jsonb,
  recommended_verification jsonb NOT NULL DEFAULT '[]'::jsonb,
  external_evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
  internal_evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
  confidence double precision NOT NULL,
  review_priority varchar(20) NOT NULL,
  status varchar(20) NOT NULL DEFAULT 'PROPOSED',
  hypothesis_sha256 varchar(64) NOT NULL UNIQUE,
  created_by varchar(255) NOT NULL,
  reviewed_by varchar(255),
  review_reason text,
  reviewed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT fk_impact_hypotheses_run_case FOREIGN KEY (run_id, case_id)
    REFERENCES public.case_runs(id, case_id) ON DELETE RESTRICT,
  CONSTRAINT uq_impact_hypotheses_case_mapping UNIQUE (
    case_id, finding_id, asset_version_id, relationship_type
  ),
  CONSTRAINT ck_impact_hypotheses_confidence CHECK (confidence BETWEEN 0 AND 1),
  CONSTRAINT ck_impact_hypotheses_priority CHECK (
    review_priority IN ('LOW', 'MEDIUM', 'HIGH')
  ),
  CONSTRAINT ck_impact_hypotheses_status CHECK (
    status IN ('PROPOSED', 'ACCEPTED', 'REJECTED')
  ),
  CONSTRAINT ck_impact_hypotheses_hash CHECK (length(hypothesis_sha256) = 64),
  CONSTRAINT ck_impact_hypotheses_evidence CHECK (
    jsonb_array_length(external_evidence) > 0
    AND jsonb_array_length(internal_evidence) > 0
  ),
  CONSTRAINT ck_impact_hypotheses_review CHECK (
    status = 'PROPOSED' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)
  )
);

CREATE INDEX IF NOT EXISTS ix_internal_assets_type_domain
  ON public.internal_assets (asset_type, domain);
CREATE INDEX IF NOT EXISTS ix_internal_asset_versions_asset_status
  ON public.internal_asset_versions (asset_id, status);
CREATE INDEX IF NOT EXISTS ix_internal_asset_versions_embedding_hnsw
  ON public.internal_asset_versions USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS ix_internal_asset_versions_search_text
  ON public.internal_asset_versions USING gin (to_tsvector('english', search_text));
CREATE INDEX IF NOT EXISTS ix_internal_asset_acl_principal
  ON public.internal_asset_acl (principal_kind, principal_value, permission);
CREATE INDEX IF NOT EXISTS ix_asset_relations_source_status
  ON public.asset_relations (source_asset_id, status);
CREATE INDEX IF NOT EXISTS ix_asset_relations_target_status
  ON public.asset_relations (target_asset_id, status);
CREATE INDEX IF NOT EXISTS ix_impact_hypotheses_case_status
  ON public.impact_hypotheses (case_id, status);

CREATE OR REPLACE FUNCTION public.pharma_agent_protect_internal_revision()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'internal asset revisions are immutable' USING ERRCODE = '55000';
END;
$$;

CREATE OR REPLACE FUNCTION public.pharma_agent_protect_impact_binding()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'impact hypotheses cannot be deleted' USING ERRCODE = '55000';
  END IF;
  IF NEW.case_id IS DISTINCT FROM OLD.case_id
     OR NEW.run_id IS DISTINCT FROM OLD.run_id
     OR NEW.finding_id IS DISTINCT FROM OLD.finding_id
     OR NEW.asset_id IS DISTINCT FROM OLD.asset_id
     OR NEW.asset_version_id IS DISTINCT FROM OLD.asset_version_id
     OR NEW.relationship_type IS DISTINCT FROM OLD.relationship_type
     OR NEW.statement IS DISTINCT FROM OLD.statement
     OR NEW.known_facts IS DISTINCT FROM OLD.known_facts
     OR NEW.derived_relationships IS DISTINCT FROM OLD.derived_relationships
     OR NEW.assumptions IS DISTINCT FROM OLD.assumptions
     OR NEW.counterevidence IS DISTINCT FROM OLD.counterevidence
     OR NEW.unknowns IS DISTINCT FROM OLD.unknowns
     OR NEW.recommended_verification IS DISTINCT FROM OLD.recommended_verification
     OR NEW.external_evidence IS DISTINCT FROM OLD.external_evidence
     OR NEW.internal_evidence IS DISTINCT FROM OLD.internal_evidence
     OR NEW.confidence IS DISTINCT FROM OLD.confidence
     OR NEW.review_priority IS DISTINCT FROM OLD.review_priority
     OR NEW.hypothesis_sha256 IS DISTINCT FROM OLD.hypothesis_sha256
     OR NEW.created_by IS DISTINCT FROM OLD.created_by
     OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
    RAISE EXCEPTION 'impact hypothesis evidence binding is immutable'
      USING ERRCODE = '55000';
  END IF;
  IF OLD.status <> 'PROPOSED' AND NEW IS DISTINCT FROM OLD THEN
    RAISE EXCEPTION 'reviewed impact hypothesis is immutable'
      USING ERRCODE = '55000';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_internal_asset_versions_immutable
  ON public.internal_asset_versions;
CREATE TRIGGER trg_internal_asset_versions_immutable
BEFORE UPDATE OR DELETE ON public.internal_asset_versions
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_protect_internal_revision();

DROP TRIGGER IF EXISTS trg_relation_evidence_immutable ON public.relation_evidence;
CREATE TRIGGER trg_relation_evidence_immutable
BEFORE UPDATE OR DELETE ON public.relation_evidence
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_protect_internal_revision();

DROP TRIGGER IF EXISTS trg_impact_hypotheses_guard ON public.impact_hypotheses;
CREATE TRIGGER trg_impact_hypotheses_guard
BEFORE UPDATE OR DELETE ON public.impact_hypotheses
FOR EACH ROW EXECUTE FUNCTION public.pharma_agent_protect_impact_binding();

COMMIT;
