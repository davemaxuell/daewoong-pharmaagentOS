-- Apply before deploying code that writes immutable embedding-space provenance.
-- The legacy template version is deliberately not considered active by the application;
-- current chunks are re-embedded once the new worker consumes v2 jobs/backfill.
ALTER TABLE public.chunk_embeddings
  ADD COLUMN IF NOT EXISTS input_schema_version text;

UPDATE public.chunk_embeddings
SET input_schema_version = 'legacy-unknown-v0'
WHERE input_schema_version IS NULL;

ALTER TABLE public.chunk_embeddings
  ALTER COLUMN input_schema_version SET NOT NULL;

ALTER TABLE public.chunk_embeddings
  DROP CONSTRAINT IF EXISTS uq_chunk_embedding_model_content;
ALTER TABLE public.chunk_embeddings
  DROP CONSTRAINT IF EXISTS chunk_embeddings_document_chunk_id_model_id_content_sha256_key;
ALTER TABLE public.chunk_embeddings
  DROP CONSTRAINT IF EXISTS uq_chunk_embedding_space_input;

ALTER TABLE public.chunk_embeddings
  ADD CONSTRAINT uq_chunk_embedding_space_input UNIQUE (
    document_chunk_id,
    provider,
    model_id,
    dimensions,
    input_schema_version,
    content_sha256,
    provider_input_sha256
  );

DROP INDEX IF EXISTS public.ix_chunk_embeddings_model_dimensions;
CREATE INDEX IF NOT EXISTS ix_chunk_embeddings_space
  ON public.chunk_embeddings (
    provider,
    model_id,
    dimensions,
    input_schema_version
  );

ANALYZE public.chunk_embeddings;
