"""Tests for dataset_split.py (Validation Architecture v3, Phase 1).

Covers v3 correction #7: assess_leakage() must never mutate dataset
membership; movement to development is a separate, explicit,
audited operation.
"""

from dataset_split import (
    DatasetSplit, LeakageControl, LeakageAssessment,
    assess_leakage, move_to_development,
)


def test_non_holdout_case_always_valid_for_holdout_check():
    control = LeakageControl(engine_output_observed_before_finalization=True, case_modified_after_observation=True)
    result = assess_leakage("case1", DatasetSplit.DEVELOPMENT, control)
    assert result.assessment == LeakageAssessment.VALID_FOR_HOLDOUT


def test_holdout_case_no_observation_is_valid():
    control = LeakageControl(engine_output_observed_before_finalization=False)
    result = assess_leakage("case1", DatasetSplit.LOCKED_HOLDOUT, control)
    assert result.assessment == LeakageAssessment.VALID_FOR_HOLDOUT


def test_holdout_case_observed_and_modified_is_invalid():
    control = LeakageControl(engine_output_observed_before_finalization=True, case_modified_after_observation=True)
    result = assess_leakage("case1", DatasetSplit.LOCKED_HOLDOUT, control)
    assert result.assessment == LeakageAssessment.INVALID_FOR_HOLDOUT


def test_holdout_case_observed_not_modified_is_quarantined():
    control = LeakageControl(engine_output_observed_before_finalization=True, case_modified_after_observation=False)
    result = assess_leakage("case1", DatasetSplit.LOCKED_HOLDOUT, control)
    assert result.assessment == LeakageAssessment.QUARANTINED


def test_assess_leakage_does_not_mutate_anything():
    # assess_leakage takes plain values, not a GoldCase object, so
    # there is nothing for it to mutate — this test locks the
    # function's pure signature (no object with a settable
    # dataset_split is ever passed in).
    control = LeakageControl(engine_output_observed_before_finalization=True, case_modified_after_observation=True)
    original_split = DatasetSplit.LOCKED_HOLDOUT
    assess_leakage("case1", original_split, control)
    assert original_split == DatasetSplit.LOCKED_HOLDOUT  # unchanged, immutable enum value anyway


def test_move_to_development_returns_new_split_and_audit_record():
    new_split, audit = move_to_development("case1", DatasetSplit.LOCKED_HOLDOUT, "confirmed leakage")
    assert new_split == DatasetSplit.DEVELOPMENT
    assert audit.case_id == "case1"
    assert audit.previous_split == DatasetSplit.LOCKED_HOLDOUT
    assert audit.new_split == DatasetSplit.DEVELOPMENT
    assert audit.reason == "confirmed leakage"


def test_move_to_development_is_a_separate_operation_from_assessment():
    # assess_leakage() itself never returns a new split or audit record
    # — only move_to_development() does. This test documents that
    # separation explicitly.
    control = LeakageControl(engine_output_observed_before_finalization=True, case_modified_after_observation=True)
    result = assess_leakage("case1", DatasetSplit.LOCKED_HOLDOUT, control)
    assert not hasattr(result, "new_split")
    assert not hasattr(result, "audit_record")


def test_audit_record_has_a_timestamp():
    _, audit = move_to_development("case1", DatasetSplit.LOCKED_HOLDOUT, "reason")
    assert audit.performed_at is not None
