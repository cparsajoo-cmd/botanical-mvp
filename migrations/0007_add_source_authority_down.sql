-- migrations/0007_add_source_authority_down.sql
-- Rollback for 0007_add_source_authority.sql.
--
-- Safe: every column being dropped here was added, not altered, by the
-- up-migration, and none is read by database.py's core (mandatory)
-- evidence fields — only by the Phase 3 optional-column fallback path
-- (_OPTIONAL_EVIDENCE_COLUMNS in database.py), which already degrades
-- gracefully when these columns are absent. No other table or column is
-- affected.

DROP INDEX IF EXISTS idx_evidence_records_source_authority;

ALTER TABLE evidence_records
    DROP COLUMN IF EXISTS source_authority,
    DROP COLUMN IF EXISTS source_authority_score,
    DROP COLUMN IF EXISTS source_authority_reason;
