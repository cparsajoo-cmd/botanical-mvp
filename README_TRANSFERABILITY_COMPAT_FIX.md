# Transferability compatibility hotfix

Apply this package on top of `BOTANICAL_STEP5_STABLE_ROLLBACK_FOR_DEMO`.

Modified files:
- `phase5_scoring_config.py`
- `standard_evidence_builder.py`

Purpose:
Preserve the stable Step-5 scoring/triage behavior from the previous working version while restoring the newer, scientifically safer transferability semantics expected by the current test suite.

Fixes:
1. Adds `TARGET_UNSPECIFIED` as a distinct state from `UNKNOWN`.
2. A target dimension never specified by the project (e.g. dose or plant part) no longer penalizes evidence transferability.
3. A target dimension that was specified but is missing in the evidence remains `UNKNOWN` and is penalized appropriately.
4. A matching infusion preparation can score 1.0 even when unrelated target dimensions were never specified.
5. Capsule remains a dosage form and is not automatically treated as a botanical preparation.
6. Adds `Target_Definition_Completeness` diagnostics without changing the stable Step-5 triage logic.

Validation:
The two previously failing tests now pass:
- test_capsule_is_dosage_form_not_automatically_a_preparation_and_missing_context_is_not_full_match
- test_target_unspecified_dose_and_part_do_not_mask_a_preparation_mismatch
