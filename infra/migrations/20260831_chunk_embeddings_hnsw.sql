-- Run with the migration identity after the initial embedding backfill has been
-- validated. CONCURRENTLY must run outside an explicit transaction.
CREATE INDEX CONCURRENTLY IF NOT EXISTS chunk_embeddings_embedding_hnsw_idx
  ON public.chunk_embeddings
  USING hnsw (embedding vector_cosine_ops);

ANALYZE public.chunk_embeddings;
