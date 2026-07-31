-- migrations/0002_extend_evidence_records.sql
-- IMPLEMENTATION_PLAN.md Phase 2 — additive evidence record schema extension.
--
-- HOW TO APPLY
-- This repository has no migration runner (see ARCHITECTURE.md's "Known
-- oddities" and database.py's Task-10.2 comment block for the same,
-- already-established precedent). Run this file by hand in the Supabase
-- SQL editor against the `evidence_records` table.
--
-- SAFE TO RUN MULTIPLE TIMES / SAFE TO DEFER
-- Every column uses IF NOT EXISTS and is nullable with no default that
-- changes existing row meaning. Nothing here renames or drops a column,
-- and nothing here is required for the application to keep running:
-- database.py's save_evidence_record() already tolerates any subset of
-- these columns being absent (see _OPTIONAL_EVIDENCE_COLUMNS / the
-- PGRST204 schema-fallback retry it was extended with in this same
-- change) — rows written before this migration is applied, and rows
-- written to a table where it is never applied, both keep working.
--
-- WHY TEXT/JSONB, NOT NUMERIC, FOR effect_size AND p_value
-- A bare number for effect size is not scientifically meaningful without
-- the effect-size type (e.g. mean difference, OR, HR, RR), unit,
-- confidence interval, and timepoint attached to it — collapsing those
-- into a single float would misrepresent the finding. Both are stored as
-- JSONB so a future writer can carry that context explicitly; nothing in
-- Phase 2 populates them yet (no connector currently extracts this
-- reliably from source text) — see IMPLEMENTATION_PLAN.md Phase 2's
-- "Known limitations".

ALTER TABLE evidence_records
    ADD COLUMN IF NOT EXISTS pmid                    TEXT,
    ADD COLUMN IF NOT EXISTS doi                      TEXT,
    ADD COLUMN IF NOT EXISTS nct_id                    TEXT,
    ADD COLUMN IF NOT EXISTS mechanism                  TEXT,
    ADD COLUMN IF NOT EXISTS target                      TEXT,
    ADD COLUMN IF NOT EXISTS effect_size                  JSONB,
    ADD COLUMN IF NOT EXISTS p_value                       JSONB,
    ADD COLUMN IF NOT EXISTS administration_route            TEXT,
    ADD COLUMN IF NOT EXISTS plant_part                       TEXT,
    ADD COLUMN IF NOT EXISTS extraction_method                 TEXT,
    ADD COLUMN IF NOT EXISTS duration                           TEXT,
    ADD COLUMN IF NOT EXISTS adverse_events                      JSONB,
    ADD COLUMN IF NOT EXISTS interactions_structured               JSONB,
    ADD COLUMN IF NOT EXISTS data_quality_score                     NUMERIC;

-- Indexes for the two identifiers connectors already provide and this
-- change starts persisting (pmid, doi) — useful for de-duplication /
-- lookup, not required for correctness.
CREATE INDEX IF NOT EXISTS idx_evidence_records_pmid ON evidence_records(pmid);
CREATE INDEX IF NOT EXISTS idx_evidence_records_doi ON evidence_records(doi);

-- Supporting index for save_evidence_record()'s duplicate-evidence lookup
-- (database.py), which now correctly includes plant_id (post-Phase-2
-- correction: two different plants sharing the same source/indication/
-- dosage form must never be collapsed into one evidence row). Not UNIQUE
-- — a future version may legitimately store multiple observations from
-- one study for the same plant.
CREATE INDEX IF NOT EXISTS idx_evidence_records_plant_source_indication_form
ON evidence_records
(
    plant_id,
    source_id,
    target_indication,
    dosage_form
);
