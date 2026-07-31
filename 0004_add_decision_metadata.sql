-- migrations/0004_add_decision_metadata.sql
-- IMPLEMENTATION_PLAN.md Phase 4 — reproducibility metadata for decision_records.
--
-- HOW TO APPLY
-- Same situation as 0002_extend_evidence_records.sql: no migration runner
-- exists in this repository. Run by hand in the Supabase SQL editor
-- against the `decision_records` table (created outside version control —
-- see decision_record_persistence.py's own module docstring).
--
-- SAFE TO RUN MULTIPLE TIMES / SAFE TO DEFER
-- Every column uses IF NOT EXISTS and is nullable. Nothing here renames or
-- drops a column. decision_record_persistence.py's insert already
-- tolerates any subset of these being absent (extended in this same
-- change with the same optional-column PGRST204 fallback already used by
-- database.py's evidence_records inserts) — rows written before this
-- migration, and to a table where it's never applied, both keep working.
--
-- WHY NO decision_timestamp COLUMN
-- decision_records already has `created_at`, which is exactly what
-- "decision_timestamp" means. Adding a second column for the same value
-- would be the kind of duplicated-source-of-truth this phase exists to
-- avoid — decision_metadata.build_decision_metadata()'s
-- "decision_timestamp" field is populated independently at call time (see
-- that module) but is not given its own column here; it is recoverable
-- from created_at for any already-persisted row.

ALTER TABLE decision_records
    ADD COLUMN IF NOT EXISTS scoring_model_version       TEXT,
    ADD COLUMN IF NOT EXISTS evidence_snapshot_id          TEXT,
    ADD COLUMN IF NOT EXISTS evidence_snapshot_status        TEXT,
    ADD COLUMN IF NOT EXISTS normalization_version             TEXT,
    ADD COLUMN IF NOT EXISTS validation_version                  TEXT,
    ADD COLUMN IF NOT EXISTS discovery_mode                        TEXT,
    ADD COLUMN IF NOT EXISTS dosage_form                              TEXT,
    ADD COLUMN IF NOT EXISTS market                                    TEXT,
    ADD COLUMN IF NOT EXISTS candidate_set_fingerprint                  TEXT;

-- Index for reproducibility lookups ("has this exact evidence/candidate
-- combination been decided on before?") — not required for correctness.
CREATE INDEX IF NOT EXISTS idx_decision_records_evidence_snapshot_id
ON decision_records(evidence_snapshot_id);
CREATE INDEX IF NOT EXISTS idx_decision_records_candidate_set_fingerprint
ON decision_records(candidate_set_fingerprint);
