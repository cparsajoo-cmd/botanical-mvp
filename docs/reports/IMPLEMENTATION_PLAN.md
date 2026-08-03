# IMPLEMENTATION_PLAN.md

---

## Phase 1 — Shared Score_Breakdown constants module; remove duplicated parsers

**Files to modify:**
- New: `score_breakdown_schema.py`
- Modify: `scoring_sensitivity_report.py`
- Modify: `structured_rationale.py`
- Modify: `comparative_rationale.py`

**Database migrations:** None.

**Tests:**
- New: `test_score_breakdown_schema.py`
- Update: `test_scoring_sensitivity_report.py` (add case for current indication-mode section names)
- Update: `test_structured_rationale.py` (add case for current indication-mode section names)
- Update: `test_comparative_rationale.py` (no behavior change expected — re-run only)
- Run full existing suite.

**Expected outputs:**
- `score_breakdown_schema.py` exports one `parse_score_breakdown()`, one `CANONICAL_SECTIONS`, one `INDICATION_CANONICAL_SECTIONS`, one `COMPONENT_TO_DIMENSIONS`.
- `scoring_sensitivity_report.py`, `structured_rationale.py`, `comparative_rationale.py` import from `score_breakdown_schema.py` instead of defining their own copies.
- Existing module-level names (`_parse_score_breakdown`, `_local_parse_score_breakdown`, `_CANONICAL_SECTIONS`, `_INDICATION_CANONICAL_SECTIONS`, `_COMPONENT_TO_DIMENSIONS`) remain importable from their original modules for backward compatibility, now bound to the shared implementation.
- Indication-mode `Score_Breakdown` (current key: `"Compound support (non-gating; max 5)"`) is classified as complete/reconcilable in all three modules.
- All existing tests pass. New tests pass.

**Rollback plan:**
- Revert the four modified/new files to their pre-Phase-1 versions.
- No data migration involved, no state to unwind.

---

## Phase 2 — Evidence record schema extension (Supabase, additive only)

**Files to modify:**
- New: `migrations/0002_extend_evidence_records.sql`
- Modify: `database.py`
- Modify: relevant per-source connector files (PMID/DOI/sample size/P value mapping, source-dependent)

**Database migrations:**
- Add nullable columns to `evidence_records`: `mechanism`, `target`, `effect_size`, `p_value`, `pmid`, `doi`, `administration_route`, `plant_part`, `extraction_method`, `duration`, `adverse_events`, `interactions_structured`, `data_quality_score`.
- No column removed or renamed. No default value that changes existing row meaning.

**Tests:**
- New: `test_database_evidence_schema_extension.py` (schema has new columns; old `save_evidence_record()` calls without new fields still succeed)
- Update: connector tests exercising the sources that can populate the new fields.
- Run full existing suite.

**Expected outputs:**
- Old evidence rows unaffected; new columns null.
- New collection runs populate whichever new fields the source provides; unmapped fields stay null with no error.

**Rollback plan:**
- Migration is additive-only; rollback = drop the new columns (`migrations/0002_extend_evidence_records_down.sql`), no data loss for pre-existing columns.

---

## Phase 3 — Single scoring engine (reconcile `R&D_Opportunity_Score` and `Overall_Score`)

**Files to modify:**
- Modify: `candidate_shortlisting.py`
- Modify: `indication_candidate_discovery.py`
- Modify: `botanical_rd_candidate_engine.py` (call-site only, no scoring logic change outside the reconciliation itself)
- Modify: `pharma_report_generator.py` (render one score, not two)

**Database migrations:** None.

**Tests:**
- Update: `test_candidate_shortlisting.py`
- Update: `test_indication_candidate_discovery.py`
- Update: `test_pharma_report_generator.py`
- New: `test_single_scoring_engine.py` (asserts no second independent score computation exists in the candidate output)
- Run full existing suite.

**Expected outputs:**
- One score column drives both shortlist status and report ranking.
- `Score_Breakdown` for every row sums to that one score (verified via `score_breakdown_schema.parse_score_breakdown`).

**Rollback plan:**
- Revert the four modified files.
- No stored data depends on the removed duplicate score; no migration to unwind.

---

## Phase 4 — Reproducibility metadata (scoring version, evidence snapshot, decision timestamp)

**Files to modify:**
- New: `migrations/0003_add_decision_records.sql`
- New: `decision_record_persistence.py` extension (or confirm existing `persist_decision_record()` already covers this — verify before writing new code)
- Modify: `step_rd_candidates.py` (call site)

**Database migrations:**
- New table `decision_records` (or extend existing one if `decision_record_persistence.py` already has one — verify in Phase 4, not assumed here): `analysis_id`, `scoring_version`, `evidence_snapshot_ref`, `decision_timestamp`, `indication`, `discovery_mode`.

**Tests:**
- New: `test_decision_record_reproducibility.py` (same inputs + same scoring_version reproduce the same recommendation)
- Run full existing suite.

**Expected outputs:**
- Every generated recommendation has a retrievable `scoring_version`, `evidence_snapshot_ref`, `decision_timestamp`.

**Rollback plan:**
- New table only; drop it to roll back. No existing table altered.

---

## Phase 5 — Explicit Evidence Normalization / Evidence Validation stages

**Files to modify:**
- New: `evidence_normalization.py`
- New: `evidence_validation.py`
- Modify: `indication_candidate_discovery.py` (call the two new stages before scoring)
- Modify: `pharma_report_generator.py` (surface normalization/validation results)

**Database migrations:** None.

**Tests:**
- New: `test_evidence_normalization.py`
- New: `test_evidence_validation.py`
- Update: `test_indication_candidate_discovery.py`
- Run full existing suite.

**Expected outputs:**
- Report shows what was normalized and what was validated, separately from the final score.

**Rollback plan:**
- Revert the four files; no migration involved.

---

## Phase 6 — Cleanup and conceptual validation

**Files to modify:**
- Modify: `seed_data.py` (remove `schema.py`/SQLite import)
- Delete or archive: `schema.py` (confirm zero remaining importers via `repo_dependency_audit.py` before removal)
- New: `VALIDATION_RESULTS.md`

**Database migrations:** None.

**Tests:**
- Run `repo_dependency_audit.py validate` to confirm `schema.py` is unreachable before deletion.
- Run full existing suite.
- Conceptual validation runs (documented, not code) for: type 2 diabetes, metabolic syndrome, sleep, skin aging, Alzheimer's disease.

**Expected outputs:**
- `VALIDATION_RESULTS.md` documents, per indication: no evidence leakage, compound similarity did not create any candidate, plant-specific evidence required, no unsupported plant reached shortlist.

**Rollback plan:**
- Restore `schema.py` and its import in `seed_data.py` if `repo_dependency_audit.py` reports any live dependency.

---

Only Phase 1 is implemented in this turn, per instruction. Phases 2-6 remain unimplemented until each is separately approved.
