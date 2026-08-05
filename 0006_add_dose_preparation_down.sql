-- migrations/0006_add_dose_preparation_down.sql
-- Reverses migrations/0006_add_dose_preparation.sql. Same precedent as
-- 0002_extend_evidence_records_down.sql / 0004_add_decision_metadata_down.sql
-- / 0005_add_evidence_embeddings_down.sql -- destructive, keep only as a
-- documented rollback path, not something normally run.

ALTER TABLE evidence_records
    DROP COLUMN IF EXISTS dose,
    DROP COLUMN IF EXISTS preparation;
