-- migrations/0004_add_decision_metadata_down.sql
-- Rollback for 0004_add_decision_metadata.sql.
--
-- Safe: every column being dropped here was added, not altered, by the
-- up-migration. None is read by decision_record_persistence.py's core
-- (mandatory) fields — only by the Phase 4 optional-column fallback path,
-- which already degrades gracefully when these columns are absent.

DROP INDEX IF EXISTS idx_decision_records_candidate_set_fingerprint;
DROP INDEX IF EXISTS idx_decision_records_evidence_snapshot_id;

ALTER TABLE decision_records
    DROP COLUMN IF EXISTS scoring_model_version,
    DROP COLUMN IF EXISTS evidence_snapshot_id,
    DROP COLUMN IF EXISTS evidence_snapshot_status,
    DROP COLUMN IF EXISTS normalization_version,
    DROP COLUMN IF EXISTS validation_version,
    DROP COLUMN IF EXISTS discovery_mode,
    DROP COLUMN IF EXISTS dosage_form,
    DROP COLUMN IF EXISTS market,
    DROP COLUMN IF EXISTS candidate_set_fingerprint;
