# Phase 5 — Scientific Score Calibration: Test Results

## 1. Phase 5 desired-behavior / characterization tests

File: `test_phase5_scoring_calibration_addendum.py`

```
51 collected, 51 passed, 0 failed, 0 xfailed, 0 skipped, 0 collection errors
```

| # | Test | Result |
|---|---|---|
| 1 | test_characterizes_current_legacy_behavior_overall_score_is_authoritative | PASSED |
| 2 | test_characterizes_current_legacy_behavior_rd_opportunity_score_equals_overall_score_after_merge | PASSED |
| 3 | test_characterizes_current_legacy_behavior_raw_score_selects_richest_narrative_row_not_overall_score | PASSED |
| 4 | test_characterizes_current_legacy_behavior_row_level_decision_class_ah_is_overwritten | PASSED |
| 5 | test_characterizes_current_legacy_behavior_row_level_evidence_confidence_is_overwritten | PASSED |
| 6 | test_characterizes_current_legacy_behavior_eligibility_no_go_returns_before_score_threshold | PASSED |
| 7 | test_characterizes_current_legacy_behavior_duplicate_evidence_removed_in_evidence_quality | PASSED |
| 8 | test_characterizes_current_legacy_behavior_source_authority_applied_once_in_published_evidence_quality | PASSED |
| 9 | test_characterizes_current_legacy_behavior_global_ranking_score_affects_only_sourcing_fallback | PASSED |
| 10 | test_desired_positive_high_quality_human_rct_increases_scientific_efficacy_support | PASSED |
| 11 | test_desired_negative_high_quality_human_rct_does_not_add_positive_efficacy_support | PASSED |
| 12 | test_desired_negative_rct_reduces_final_scientific_support_relative_to_identical_positive_rct | **PASSED** (was failing pre-implementation) |
| 13 | test_desired_null_rct_does_not_add_positive_efficacy_points | PASSED |
| 14 | test_desired_mixed_evidence_receives_limited_contribution | PASSED |
| 15 | test_desired_conflicting_evidence_reduces_consistency_factor | **PASSED** (was failing) |
| 16 | test_desired_mixed_only_evidence_pool_scores_lower_than_clean_positive_through_real_pipeline | **PASSED** (was failing) |
| 17 | test_desired_one_positive_rct_plus_three_negative_rcts_cannot_produce_strong_positive_consistency | **PASSED** (was failing) |
| 18 | test_desired_several_weak_observational_studies_cannot_reverse_systematic_review_direction | **PASSED** (was failing) |
| 19 | test_desired_multiple_animal_studies_cannot_outweigh_strong_negative_human_evidence | **PASSED** (was failing) |
| 20 | test_desired_several_low_quality_studies_show_diminishing_returns | PASSED |
| 21 | test_desired_duplicate_article_does_not_change_score | PASSED |
| 22 | test_desired_same_article_from_multiple_connectors_counted_once | PASSED |
| 23 | test_desired_unknown_data_receives_no_positive_default_reward | **PASSED** (was failing) |
| 24 | test_desired_search_not_performed_receives_no_positive_default_reward | **PASSED** (was failing) |
| 25 | test_desired_source_unavailable_receives_no_positive_default_reward | **PASSED** (was failing) |
| 26 | test_desired_different_plant_part_reduces_applicability | **PASSED** (was failing) |
| 27 | test_desired_different_preparation_reduces_applicability | **PASSED** (was failing) |
| 28 | test_desired_different_route_reduces_applicability | **PASSED** (was failing) |
| 29 | test_desired_large_dose_mismatch_reduces_applicability | **PASSED** (was failing) |
| 30 | test_desired_dose_with_incompatible_or_missing_units_is_unknown_not_invented | **PASSED** (was failing) |
| 31 | test_desired_different_indication_is_not_treated_as_direct_evidence | PASSED |
| 32 | test_desired_missing_applicability_information_does_not_receive_full_applicability | **PASSED** (was failing) |
| 33 | test_desired_different_plant_species_reduces_applicability | **PASSED** (was failing) |
| 34 | test_desired_applicability_factor_is_actually_consumed_by_authoritative_scoring | **PASSED** (was failing) |
| 35 | test_desired_multi_dimensional_applicability_aggregation_is_deterministic | **PASSED** (was failing) |
| 36 | test_desired_partial_preparation_requires_explicit_matching_parent_category_not_free_text | **PASSED** (was failing) |
| 37 | test_desired_record_to_plant_applicability_aggregation_is_quality_weighted_mean | **PASSED** (was failing) |
| 38 | test_desired_eligibility_no_go_overrides_a_high_opportunity_score | PASSED |
| 39 | test_desired_incomplete_evidence_cannot_yield_a_validated_strong_decision | PASSED |
| 40 | test_desired_decision_threshold_boundary_tests | PASSED |
| 41 | test_desired_score_breakdown_sums_to_final_score | PASSED |
| 42 | test_desired_every_component_stays_within_its_declared_range | PASSED |
| 43 | test_desired_scoring_model_version_is_present_in_authoritative_output | **PASSED** (was failing) |
| 44 | test_desired_a_small_evidence_change_near_a_threshold_is_documented_as_a_boundary_transition | PASSED |
| 45 | test_desired_duplicate_raw_rows_do_not_change_the_authoritative_plant_score | PASSED |
| 46 | test_desired_narrative_gate_provenance_cannot_silently_mismatch_the_authoritative_selected_plant_result | **PASSED** (was failing) |
| 47 | test_phase5_lower_tiers_are_score_inert_when_a_primary_tier_exists | **PASSED** (new supervisory regression) |
| 48 | test_phase5_lower_tiers_cannot_change_a_primary_tier_go_decision | **PASSED** (new supervisory regression) |
| 49 | test_phase5_unreported_outcomes_remain_in_consistency_denominator | **PASSED** (new supervisory regression) |
| 50 | test_phase5_consistency_distinguishes_no_records_from_unreported_records | **PASSED** (new supervisory regression) |
| 51 | test_phase5_component_provenance_includes_non_empirical_score_contributors | **PASSED** (new supervisory regression) |

Every test marked "was failing" is one of the 22 desired-behavior gaps
confirmed in the pre-implementation audit rounds — all 22 now pass, with
no `xfail`/`skip` added and no assertion weakened to accept a lesser
result than originally specified. Tests 47–51 cover four additional
production-level gaps discovered by independent post-implementation review.

## 2. Phase 1–4 tests

```
273 passed, 0 failed, 3 xfailed (pre-existing, unrelated to Phase 5), 0 collection errors
```
Files: `test_phase1_evidence_direction.py`, `test_phase2_evidence_architecture.py`,
`test_phase2c_regulatory_single_source_of_truth.py`,
`test_phase2d_a_canonical_ema_wiring.py`, `test_phase2e_safety_aggregate_reorder.py`,
`test_phase3_authority_quality_integration.py`, `test_phase3_no_plant_disappears.py`,
`test_phase3_report_shortlist_consistency.py`,
`test_phase4_eligibility_gate_characterization.py`,
`test_phase4_eligibility_gate_desired_behavior.py`, `test_phase4_metadata_consistency.py`.

No behavior in these files changed — confirmed identical pass count and
identical 3 pre-existing xfails before and after this implementation.

## 3. Full suite

```
2509 passed, 0 failed, 3 xfailed, 0 skipped, 0 collection errors
```
(158 test files, `gold_cases/` included.) The correction sandbox did not
contain the real pinned `streamlit`/`supabase` distributions and could not
download them. Phase-5 tests ran directly. Phase 1–4 and the full suite were
run with minimal test-only import stubs outside the project tree; those stubs
are not part of the deliverable and do not change project code. This validates
the project logic exercised by the suite, but the same commands should also be
rerun in the deployment environment with the real dependencies installed.

## 4. Regressions found and resolved during implementation

Six pre-existing tests (outside the Phase 5 addendum file) broke when the
approved architecture was wired in — each investigated, confirmed as an
intended consequence of an approved fix (not a defect), and updated with
an in-place comment explaining the old value, the new value, and why:

| File | Test | Old value | New value | Cause |
|---|---|---|---|---|
| `test_gate_layer.py` | `test_deterministic_output_contract_locked_engineering_regression` | `R&D_Opportunity_Score` 38.0/23.0, ordered list [38.0, 23.0] | 35.0/20.0, [35.0, 20.0] | `market_neutral_default` +3 → 0.0 fix (§10) |
| `test_occurrence_seed.py` | `test_run_end_to_end_unaffected_for_plants_outside_the_seed_dataset` | 38.0 | 35.0 | same |
| `test_scoring_config.py` | `test_default_scoring_config_reproduces_identical_scores_to_pre_task_hardcoded_values` | 38.0/23.0 | 35.0/20.0 | same |
| `test_scoring_config.py` | `test_default_scoring_config_field_values_match_documented_pre_task_weights` | `market_neutral_default == 3` | `== 0.0` | same |
| `test_step5_scientific_result_preparation_safety.py` | `test_null_human_evidence_cannot_be_go_or_high_relevance` | `Indication_Relevance_Score <= 15` | `== 33.4` (unchanged by direction) + new `Evidence_Consistency_Class`/`Direction_Factor`/`Scientific_Evidence_Score` assertions | Direction removed from Indication Relevance (§1/§9) |
| `test_step5_scientific_result_preparation_safety.py` | `test_go_requires_positive_results_compatible_preparation_and_explicit_safety` | `Go_Investigate_Hold_NoGo == "Go"` | `Overall_Score == 77.8`, `"Investigate"` | Applicability now genuinely wired into scoring; this fixture never supplies `Indication_Match_Type`, so the indication dimension is honestly `UNKNOWN`, capping `Plant_Applicability_Factor` at 0.60 |

All six were caught by the full-suite run (not assumed) and each fix was
itself re-verified by re-running the specific file before the final
full-suite confirmation.

## 5. Environment notes

- The correction sandbox did not contain the real pinned `supabase` and
  `streamlit` distributions and could not download them from its package
  index.
- Phase-5 tests ran directly without either package. Phase 1–4 and the
  full suite used minimal test-only import stubs located outside the
  project tree. The stubs are not included in the deliverable ZIP.
- No test was skipped; no collection error remained under that test-only
  import setup. The deployment environment should rerun the same suite
  with the real dependencies installed before release.

## 6. Summary

```
Ordinary Phase 5 failures remaining:     0
Unexpected Phase 1-4 regressions:        0
New xfail/skip added:                    0
Full suite failures:                     0
```

## 7. Additional supervisory regressions fixed

| Reproduced defect | Regression now enforced |
|---|---|
| Lower-tier records increased primary-tier Evidence Quality and Overall Score | Primary-tier score fields stay identical; only supporting/all-tier diagnostics change |
| Lower-tier negative records changed a positive RCT programme from Go to Investigate | Primary-tier outcome profile drives efficacy gates and Go/Hold |
| `unreported` records were omitted from the consistency denominator | Explicit `total`/`unreported` semantics tested, including invalid-total rejection |
| Market/safety rows changed published components without appearing in authoritative provenance | Component-level source mapping and complete authoritative union tested through the merged output |
