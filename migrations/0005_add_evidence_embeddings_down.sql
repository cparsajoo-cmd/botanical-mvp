-- migrations/0005_add_evidence_embeddings_down.sql
-- Rollback for 0005_add_evidence_embeddings.sql.
--
-- Drops the RPC function, trigger, indexes, and table, in dependency
-- order. Does not touch evidence_records, plants, sources, or any other
-- existing table -- this migration only ever created new objects.
--
-- Safe to run even if 0005_add_evidence_embeddings.sql was only partially
-- applied (every statement uses IF EXISTS).
--
-- The `vector` extension itself is intentionally NOT dropped here: other
-- objects in the database may depend on it independently of this feature,
-- and DROP EXTENSION is destructive in a way this rollback should not be
-- responsible for. Drop it by hand only if you are certain nothing else
-- uses it.

DROP FUNCTION IF EXISTS match_evidence_embeddings(
    extensions.halfvec, integer, double precision, text, text, bigint[]
);

DROP TRIGGER IF EXISTS trg_evidence_embeddings_updated_at ON evidence_embeddings;
DROP FUNCTION IF EXISTS evidence_embeddings_set_updated_at();

DROP INDEX IF EXISTS idx_evidence_embeddings_embedding_hnsw;
DROP INDEX IF EXISTS idx_evidence_embeddings_plant_id;

DROP TABLE IF EXISTS evidence_embeddings;
