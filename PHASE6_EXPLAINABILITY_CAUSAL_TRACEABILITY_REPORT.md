# Phase 6 — Explainability & Causal Traceability Report

## 1. Architecture before change

Observed production path in `botanical-mvp-main (92).zip`:

1. Evidence enters through connector/collector/standardization/database paths and is read defensively de-duplicated before candidate scoring.
2. `botanical_rd_candidate_engine.py` produces row-level plant/compound candidates and structured gate fields, including Phase-4 gate evidence IDs.
3. `candidate_shortlisting.build_plant_candidate_shortlist()` aggregates raw rows to one authoritative plant row.
4. Phase 5 scientific scoring is calculated in `_scientific_evidence_components()` using already de-duplicated record-level evidence, direction, consistency, source authority, and applicability.
5. The authoritative final score is the six-component `Overall_Score` in `candidate_shortlisting.py`:
   - Indication Relevance (max 35)
   - Scientific Evidence (max 30)
   - Compound Support (max 5)
   - Mechanism Support (max 10)
   - Safety & Regulatory (max 15)
   - Novelty & Market (max 5)
6. `merge_authoritative_scores()` makes `Overall_Score` authoritative and aliases it to `R&D_Opportunity_Score`.
7. `step_rd_candidates.py` constructs `decision_metadata` once from the report-ready frame.
8. `candidate_output_adapter.py` validates candidate records and `decision_record_persistence.py` stores append-only decision snapshots.
9. Ranking is produced from the authoritative plant score after shortlist/status logic; the older row-level ranking remains upstream/audit context only.

Important pre-existing explainability assets that were reused rather than duplicated:

- `Score_Breakdown`
- `Component_Source_Record_IDs`
- `Record_Applicability_Summary`
- `Gate_Results`
- `Gate_Evidence_IDs`, `Safety_Gate_Evidence_IDs`, `Regulatory_Gate_Evidence_IDs`
- `decision_metadata.py`
- `score_breakdown_schema.py`
- `decision_record_persistence.py` / candidate-level `score_context`

## 2. Where traceability was lost

The main confirmed break was not Evidence -> Candidate. The final plant scorer already retained component-level source IDs. The break occurred after authoritative plant scoring because there was no single persisted causal object that joined:

Evidence -> Applicability -> Component -> Gate -> Override/Rule -> Final Decision -> Reproducibility metadata.

`decision_record_persistence._build_score_context()` explicitly and correctly refused to fabricate per-component evidence attribution. It retained only candidate-level evidence IDs and marked `component_attribution_available=False`. However, Phase 3/5 later introduced real `Component_Source_Record_IDs` in `candidate_shortlisting.py`; this richer, real attribution never reached the old candidate-level `score_context` persistence object.

A second gap was per-evidence score impact. `Scientific_Evidence_Score` is nonlinear, therefore equally allocating the component score across records would be fabricated. Phase 6 records a deterministic leave-one-evidence-out marginal score effect instead.

## 3. Files changed

- `decision_explainability.py` — new minimal central structured explanation/diff/summary module.
- `candidate_shortlisting.py` — exposes Phase-5 scientific evidence marginal effects and carries them through the authoritative merge.
- `step_rd_candidates.py` — attaches one `Decision_Explanation` per report-ready candidate after the single decision-metadata object is built; passes explanations to existing persistence.
- `decision_record_persistence.py` — stores the supplied explanation verbatim inside the existing append-only `records` JSON; no parallel table/schema.
- `test_phase6_decision_explainability.py` — Phase-6 tests.

No UI, connectors, market engine, safety logic, regulatory ontology, score weights, or score formula were changed.

## 4. New Decision Explanation structure

Each report-ready candidate now gets `Decision_Explanation`, containing:

- `candidate_id`
- `final_decision`
- `eligibility_status`
- `raw_score`
- `final_score`
- `score_components`
- `score_reconciliation`
- `evidence_contributions`
- `applied_gates`
- `overrides`
- `missing_data`
- `source_failures`
- `evidence_ids`
- `rules_applied`
- `scoring_version`
- `rule_version`
- `evidence_schema_version`
- `data_snapshot`
- `generated_time`
- `execution_time`
- `configuration_hash`
- `human_summary`

The object is generated only from structured fields already present in the pipeline and is persisted verbatim.

## 5. Evidence Contribution structure

For every traceable audit evidence ID:

- `evidence_id`
- `entered_score`
- `components`
- `score_points`
- `score_effect_method`
- `excluded_reason`

For Phase-5 primary-tier scientific evidence, `score_points` is a real `leave_one_evidence_out` marginal effect:

`Scientific_Evidence_Score(with record) - Scientific_Evidence_Score(without record)`.

The trace also stores the with/without score, study design label, source-authority label/score, evidence direction, and record applicability. For components whose current scoring implementation does not expose a unique additive per-record allocation, Phase 6 deliberately leaves individual point allocation `None` rather than inventing it; component-to-evidence causality still comes from the pre-existing `Component_Source_Record_IDs`.

Evidence audit rows not used by any authoritative score component are recorded with a structured exclusion reason where the current audit data proves one, including Wrong preparation, Wrong indication, Safety/regulatory hard stop, Protocol, Review citation, or the exact triage reason. Duplicate article rows eliminated upstream cannot be retrospectively named if the upstream deduplication layer did not preserve the removed record IDs; Phase 6 does not fabricate them.

## 6. Gate Attribution

The explanation consumes existing gate structures instead of re-running safety/regulatory logic:

- gate name/type
- status
- reason
- evidence IDs
- authority (when supplied upstream)
- severity (when supplied upstream)
- override flag
- expert-review-required flag

Phase-4 eligibility gate evidence IDs are included where present. No gate decision is recalculated in the explainability layer.

## 7. Rule Attribution

Structured rule entries are emitted for observed authoritative operations, including:

- `score.authoritative_six_component_sum`
- `ranking.overall_score_desc`
- `triage.exclusion` when exclusion changed the decision
- `triage.exploratory_cap` when exploratory status applies
- `ranking.near_duplicate_congener_pruning` when the existing duplicate-congener override is present

Each rule records whether it was applied, changed the decision, created an override, and its existing structured reason where available.

## 8. Decision Diff

`decision_diff(old, new)` reports:

- score changed / delta
- component changes
- evidence added
- evidence removed
- rules added/removed
- configuration/weight hash changed
- gate changed
- decision changed
- old/new decision

It compares two already-produced explanations and never recomputes either decision.

## 9. Human Summary

`build_human_summary()` is deterministic template logic only. No LLM/free text synthesis is used. A sentence is emitted only when the corresponding structured field/count exists. It can state score/component count, number of evidence records linked to scoring, structured exclusion reasons, blocking gate count, source-unavailable status, or incomplete/unperformed data collection. It does not invent study types, authorities, EMA status, or causal claims absent from the structure.

## 10. Tests added

`test_phase6_decision_explainability.py` currently verifies:

1. Score Breakdown sums exactly to Final Score.
2. Every used evidence contribution has an Evidence ID.
3. Scientific evidence point effect is recorded as leave-one-evidence-out marginal impact.
4. Wrong preparation is a structured exclusion.
5. Wrong indication is a structured exclusion.
6. Gate attribution carries evidence IDs.
7. Override/rule attribution carries a reason.
8. No Evidence, Search Not Performed, and Source Unavailable remain distinct.
9. Fixed-input/fixed-timestamp repeated explanation generation is identical.
10. Decision Diff detects score, component, evidence, and decision changes.
11. Human Summary does not invent EMA/RCT claims.
12. Attachment adds the explanation without changing the authoritative score.

Existing de-duplication tests remain the authority for upstream duplicate prevention; Phase 6 does not create a second deduplication path.

## 11. Test execution result

Targeted regression set with a local `supabase` import stub (only because the sandbox lacks the third-party package):

- **155 passed**
- Includes Phase-6 tests, Phase-5 calibration tests, Phase-3 authority/score tests, candidate adapter tests, existing decision-record persistence tests, and existing Task-12.1 evidence-traceability tests.

Persistence smoke test using the existing fake-client pattern:

- `Decision_Explanation` was confirmed to be serialized inside the existing `decision_records.records` JSON: **PASS**.

Broad repository run, excluding the two Streamlit-dependent tests that cannot collect in this sandbox:

- Modified tree: **2510 passed, 3 xfailed, 1 failed**.
- Untouched baseline ZIP under the identical environment: **2500 passed, 3 xfailed, 1 failed**.
- The single broad-suite failure is the same pre-existing `test_production_dependency_integrity.py::test_app_py_and_direct_production_modules_are_import_resolvable` full-suite interaction (`ValueError: not enough values to unpack`). The same test passes in isolation on the untouched baseline; therefore it was not introduced by Phase 6.
- Two additional tests (`test_phase3_no_plant_disappears.py`, `test_recommendation_block_phase3.py`) cannot collect here because `streamlit` is not installed.

## 12. Remaining limitations

1. **Historical duplicate identities:** read-time deduplication removes duplicates before candidate scoring. The current dedup API does not persist a tombstone/`removed_duplicate_of` event with both evidence IDs into the candidate audit. Phase 6 therefore cannot truthfully say “Evidence 55 rejected: duplicate DOI” for a duplicate that no longer exists in the downstream dataframe. Closing that requires extending dedup provenance, not scoring logic.
2. **Nonlinear non-scientific components:** the live model has real component-to-evidence IDs, but not every component exposes a mathematically unique per-evidence additive point allocation. Phase 6 does not fabricate one. Scientific Evidence now exposes exact leave-one-out marginal effects; extending the same counterfactual method to every other component is possible but would add significant runtime and should be done only after profiling.
3. **Gate authority/severity:** Phase-4 gate structures expose evidence IDs reliably, but authority/severity are not populated on every live gate object. Phase 6 records them only when upstream supplied them.
4. **Source failure propagation:** the requested three-way missingness taxonomy is represented, but `Source Unavailable` can only be emitted when a source-failure field actually reaches the candidate/report-ready row. Connector failure provenance is still not universally propagated through the current ingestion path.
5. **Evidence schema version:** there was no existing central evidence-schema version constant. Phase 6 uses `evidence-record-phase2` locally rather than falsely claiming an upstream version that does not exist. A future schema migration should centralize this constant.
6. **UI:** intentionally unchanged. `Decision_Explanation` is data/persistence infrastructure only in this phase.
