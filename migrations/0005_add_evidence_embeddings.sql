-- migrations/0005_add_evidence_embeddings.sql
-- Hybrid indication-relevance architecture -- precomputed evidence
-- embeddings + pgvector similarity search.
--
-- HOW TO APPLY
-- Same situation as 0002_extend_evidence_records.sql and
-- 0004_add_decision_metadata.sql: no migration runner exists in this
-- repository. Run by hand in the Supabase SQL editor.
--
-- SAFE TO RUN MULTIPLE TIMES / SAFE TO DEFER
-- Every statement uses IF NOT EXISTS / CREATE OR REPLACE. This migration
-- creates a new table and a new RPC function only -- it does not alter,
-- rename, or drop any column on evidence_records, plants, or any other
-- existing table. The deterministic lexical relevance engine
-- (general_indication_relevance.py) does not depend on this table existing
-- and continues to work identically whether or not this migration has been
-- applied -- see EMBEDDING_ARCHITECTURE_REVIEW.md section 10
-- (failure/fallback behavior).
--
-- WHY A SEPARATE TABLE, NOT A COLUMN ON evidence_records
-- (1) One evidence record may need re-embedding under more than one model/
--     version over time (embedding_model rollout, dimension change) --
--     a single column can only ever hold one vector at a time, which would
--     make a model migration destructive instead of additive.
-- (2) evidence_records is read via the existing paginated REST loader
--     (supabase_data.load_evidence_records_df()) for every Step 5 run;
--     a 1536-dim halfvec column on every row would roughly double that
--     payload for a value the deterministic-only code path never reads.
-- (3) HNSW index maintenance and vector storage are naturally isolated
--     from evidence_records' own write/read pattern.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS evidence_embeddings (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    evidence_record_id  bigint NOT NULL,
    plant_id            bigint NOT NULL,
    embedding           extensions.halfvec(1536) NOT NULL,
    embedding_text      text NOT NULL,
    embedding_model     text NOT NULL,
    embedding_version   text NOT NULL,
    content_hash        text NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_evidence_embeddings_evidence_record
        FOREIGN KEY (evidence_record_id)
        REFERENCES evidence_records(id)
        ON DELETE CASCADE,
    CONSTRAINT uq_evidence_embeddings_record_model_version
        UNIQUE (evidence_record_id, embedding_model, embedding_version)
);

CREATE INDEX IF NOT EXISTS idx_evidence_embeddings_plant_id
    ON evidence_embeddings (plant_id);

-- HNSW cosine index. Built on the (model, version)-partitioned data
-- implicitly via the unique constraint above; the RPC below additionally
-- filters on embedding_model/embedding_version at query time so a
-- mid-migration model change never mixes incompatible vectors in one
-- similarity comparison.
CREATE INDEX IF NOT EXISTS idx_evidence_embeddings_embedding_hnsw
    ON evidence_embeddings
    USING hnsw (embedding extensions.halfvec_cosine_ops);

-- Keep updated_at current on upsert without requiring every caller to set
-- it explicitly.
CREATE OR REPLACE FUNCTION evidence_embeddings_set_updated_at()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_evidence_embeddings_updated_at ON evidence_embeddings;
CREATE TRIGGER trg_evidence_embeddings_updated_at
    BEFORE UPDATE ON evidence_embeddings
    FOR EACH ROW
    EXECUTE FUNCTION evidence_embeddings_set_updated_at();

-- Vector similarity search RPC. Called ONCE per Step 5 run with the query
-- embedding (see indication_candidate_discovery.py) -- never once per
-- plant and never once per evidence record. Cosine distance
-- (`<=>` operator); returned as cosine_similarity = 1 - distance so callers
-- work in a 0..1 "higher is more similar" space, matching every other
-- relevance component in this engine.
CREATE OR REPLACE FUNCTION match_evidence_embeddings(
    query_embedding extensions.halfvec(1536),
    match_count integer DEFAULT 200,
    similarity_threshold double precision DEFAULT 0.0,
    embedding_model_filter text DEFAULT NULL,
    embedding_version_filter text DEFAULT NULL,
    optional_plant_ids bigint[] DEFAULT NULL
)
RETURNS TABLE (
    evidence_record_id bigint,
    plant_id bigint,
    cosine_similarity double precision,
    embedding_model text,
    embedding_version text
)
LANGUAGE sql STABLE AS $$
    SELECT
        ee.evidence_record_id,
        ee.plant_id,
        1 - (ee.embedding <=> query_embedding) AS cosine_similarity,
        ee.embedding_model,
        ee.embedding_version
    FROM evidence_embeddings ee
    WHERE (embedding_model_filter IS NULL OR ee.embedding_model = embedding_model_filter)
      AND (embedding_version_filter IS NULL OR ee.embedding_version = embedding_version_filter)
      AND (optional_plant_ids IS NULL OR ee.plant_id = ANY(optional_plant_ids))
      AND 1 - (ee.embedding <=> query_embedding) >= similarity_threshold
    ORDER BY ee.embedding <=> query_embedding ASC
    LIMIT match_count;
$$;
