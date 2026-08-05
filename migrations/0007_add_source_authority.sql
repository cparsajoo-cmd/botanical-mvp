-- migrations/0007_add_source_authority.sql
-- Phase 3 — Source Authority / Evidence Quality integration.
--
-- WHY THIS MIGRATION EXISTS
-- See PHASE3_SOURCE_AUTHORITY_AUDIT.md §1 for the full trace: prior to
-- Phase 3, "Source_Authority_Weight" was generated at collection time
-- (multi_source_collector.py, from source_registry.py's connector-level
-- config), survived standardization, and even mapped onto
-- EvidenceRecord.source_authority in memory — but was never written to
-- this table by save_evidence_record(), and never read back by
-- load_evidence_records(). It was collected and silently discarded
-- before every persist. This migration adds the columns Phase 3 actually
-- writes to and reads from (database.py's _OPTIONAL_EVIDENCE_COLUMNS /
-- save_evidence_record() / load_evidence_records()).
--
-- NUMBERING NOTE
-- migrations/0001, 0003, and 0006 are referenced in code comments and
-- prior implementation reports but are not present in this repository
-- copy (consistent with this project's documented "no migration runner,
-- applied by hand against the live Supabase instance" precedent — see
-- database.py's own header comments). 0007 is the next number that does
-- not collide with anything actually on disk (0002, 0004, 0005 present).
--
-- HOW TO APPLY
-- No migration runner exists in this repository. Run this file by hand
-- in the Supabase SQL editor against the `evidence_records` table.
--
-- SAFE TO RUN MULTIPLE TIMES / SAFE TO DEFER
-- Every column uses IF NOT EXISTS, is nullable, and has no default that
-- changes any existing row's meaning. database.py's
-- _insert_evidence_with_optional_schema_fallback() already tolerates any
-- subset of these three columns being absent (they are registered in
-- _OPTIONAL_EVIDENCE_COLUMNS), so rows written before this migration is
-- applied, and rows written to a deployment where it is never applied,
-- both keep working exactly as they did before Phase 3.
--
-- WHY TEXT/NUMERIC, NOT AN ENUM, FOR source_authority
-- evidence_authority.AUTHORITY_LABELS is a fixed, documented Python-side
-- taxonomy (14 labels), but is kept as free TEXT here rather than a SQL
-- ENUM so that adding a 15th label in a future phase never requires a
-- blocking ALTER TYPE migration — the same reasoning already applied to
-- every other classification-label column on this table (study_type,
-- result_direction, evidence_level).

ALTER TABLE evidence_records
    ADD COLUMN IF NOT EXISTS source_authority         TEXT,
    ADD COLUMN IF NOT EXISTS source_authority_score    NUMERIC,
    ADD COLUMN IF NOT EXISTS source_authority_reason   TEXT;

CREATE INDEX IF NOT EXISTS idx_evidence_records_source_authority
    ON evidence_records (source_authority);
