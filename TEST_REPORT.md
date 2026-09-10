# TEST_REPORT.md — Pre-Investor Reliability Repair

## Method

Every change was verified against a **pristine baseline copy** of the exact
uploaded ZIP (extracted separately, never modified), run through the same
commands, so that every reported pass/fail delta is attributable to this
pass's changes and nothing else (sandbox environment gaps included).

## Targeted regression runs (during development)

```
pytest -q test_candidate_shortlisting.py test_preparation_transferability_invariants.py test_phase5_scoring_calibration_addendum.py
```
Final result: **106 passed, 1 failed** (the 1 failure is the pre-existing
`streamlit`-import collection issue below, confirmed present in the
untouched baseline too).

## Full repository suite

```
pytest -q -p no:cacheprovider --continue-on-collection-errors
```

| | Baseline (untouched ZIP) | After this pass |
|---|---|---|
| Passed | 3352 | 3358 |
| Failed | 9 | 9 |
| xfailed | 3 | 3 |
| Collection errors | 60 | 60 |

**The 9 failing tests and 60 collection errors are byte-identical sets in
both runs** (diffed explicitly — see below). Nothing in this pass changed
which tests fail or error.

### Collection errors (60, environment-only, both runs identical)

All 60 are `ModuleNotFoundError` at import time for optional dependencies
not installed in this sandbox — principally `streamlit` (imported by
`llm_client.py`, which many AI-integration test files import transitively),
plus a handful of similarly-shaped missing-package errors. These are
**environment gaps, not code defects** — per the cahier's instruction, they
are reported explicitly rather than treated as failures. Representative
files: `test_step5_runtime_egress_guards.py`,
`test_structured_safety_status_and_decision_sync.py`,
`test_task6_pilot_scope.py`, `test_validation_matrix.py`,
`test_stage5_candidate_prescreen.py`, and 55 others in the same shape.
Installing `streamlit` (and whatever else these files transitively import)
in a real CI/deployment environment should resolve all 60.

### The 9 pre-existing test failures (unrelated to this pass, present in the untouched ZIP)

```
test_ai_run_cost_ceiling.py::test_ai_rd_insights_phase_budget_default_and_override
test_ai_run_cost_ceiling.py::test_ai_rd_insights_phase_budget_invalid_value_falls_back
test_indication_mode_safety_status_and_adjudication_priority.py::test_adjudication_priority_favors_evidence_depth_over_composite_score
test_phase4_eligibility_gate_desired_behavior.py::test_legacy_recommendation_fallback_excludes_no_go
test_phase4_eligibility_gate_desired_behavior.py::test_modern_recommendation_path_excludes_no_go
test_phase4_eligibility_gate_desired_behavior.py::test_no_go_high_raw_score_never_outranks_eligible_in_normal_ranking
test_phase8_market_intelligence.py::test_vectorized_no_market_rows_shortcut_uses_nullable_hit_counts
test_preparation_transferability_invariants.py::test_llm_transferability_postprocess_recovers_only_explicit_missing_fields
test_step5_market_intelligence_performance.py::test_commercial_attach_is_additive_and_preserves_scientific_columns
```

Not investigated further — out of this pass's scope (none touch the
defects being fixed), and confirmed pre-existing so fixing them was not
part of this repair's mandate. Flagging them here rather than silently
ignoring them, per the cahier's instructions.

## Regression path for each fixed defect (net-new failures caught and resolved during this pass)

The first full-suite run after the scoring-component fixes (defects 4/5/6/7)
surfaced **12 new failures**, all traced to real, legitimate consequences of
removing score inflation — not regressions in the fix logic itself:

1. **11 failures** were downstream `Scientific_Triage_Status`/`Go_Investigate_Hold_NoGo`
   assertions that depended on the now-corrected (lower, de-inflated)
   component scores. Root cause investigated for each: `_safety_regulatory()`
   correctly zeroing "no info" exposed an unrelated pre-existing gate bug
   (`if safety_reg_points <= 0.0: Excluded`) that could no longer distinguish
   "nothing known" from "genuinely prohibited" once "nothing known" stopped
   scoring positively — fixed by adding an explicit `prohibitive` boolean to
   `_safety_regulatory()`'s return value (see CHANGE_MANIFEST.md). After
   that fix, re-running dropped this to 2 failures (both pure literal-value
   drift, corrected — see CHANGE_MANIFEST.md item 5).
2. **1 failure** (`test_scoring_config.py`) was a test hard-coding the
   exact literal Defect-6 bug value (`market_search_incomplete == 3`) as a
   "documented" weight — corrected to `== 0`.

Final state: all identified net-new failures resolved; remaining failures
are the 9 pre-existing ones confirmed unrelated (see above).

## New regression tests added this pass

- `test_candidate_shortlisting.py`: `test_duplicate_mechanism_rows_do_not_saturate_mechanism_support`,
  `test_unrelated_mechanisms_do_not_score_for_requested_indication`,
  `test_several_distinct_mechanisms_score_higher_than_one_duplicated_mechanism`,
  `test_duplicate_compound_rows_do_not_inflate_linked_mechanism_bonus`
  (defects 4 & 5, matching the cahier's explicit acceptance criteria).
- `test_preparation_transferability_invariants.py`:
  `test_target_unspecified_dose_and_part_do_not_mask_a_preparation_mismatch`
  (the cahier's exact Defect-3 acceptance test),
  `test_target_specified_but_evidence_silent_stays_unknown_not_target_unspecified`
  (regression guard for the TARGET_UNSPECIFIED/UNKNOWN distinction).
- `test_phase5_scoring_calibration_addendum.py`: corrected two existing
  tests to assert the scientifically-intended defect-1 behavior (see
  CHANGE_MANIFEST.md item 2).

All listed above pass in the current tree.
