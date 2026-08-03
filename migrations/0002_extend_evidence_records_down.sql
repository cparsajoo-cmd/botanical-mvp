-- migrations/0002_extend_evidence_records_down.sql
-- Rollback for 0002_extend_evidence_records.sql.
--
-- Safe: every column being dropped here was added, not altered, by the
-- up-migration, and none is read by database.py's core (mandatory)
-- evidence fields — only by the Phase 2 optional-column fallback path
-- (_OPTIONAL_EVIDENCE_COLUMNS in database.py), which already degrades
-- gracefully when these columns are absent. No other table or column is
-- affected.

DROP INDEX IF EXISTS idx_evidence_records_plant_source_indication_form;
DROP INDEX IF EXISTS idx_evidence_records_doi;
DROP INDEX IF EXISTS idx_evidence_records_pmid;

ALTER TABLE evidence_records
    DROP COLUMN IF EXISTS pmid,
    DROP COLUMN IF EXISTS doi,
    DROP COLUMN IF EXISTS nct_id,
    DROP COLUMN IF EXISTS mechanism,
    DROP COLUMN IF EXISTS target,
    DROP COLUMN IF EXISTS effect_size,
    DROP COLUMN IF EXISTS p_value,
    DROP COLUMN IF EXISTS administration_route,
    DROP COLUMN IF EXISTS plant_part,
    DROP COLUMN IF EXISTS extraction_method,
    DROP COLUMN IF EXISTS duration,
    DROP COLUMN IF EXISTS adverse_events,
    DROP COLUMN IF EXISTS interactions_structured,
    DROP COLUMN IF EXISTS data_quality_score;
