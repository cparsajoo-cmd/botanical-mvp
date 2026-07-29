"""Tests for assertion_vocabulary.py."""

from assertion_vocabulary import (
    AssertionState, AssertionType, SeverityLevel, TransformationType,
    ExtractionConfidenceLevel, GoldCaseKind, CurationStatus,
    LOCK_ELIGIBLE_CURATION_STATUSES, is_curation_status_lock_eligible,
    ValidationScope,
)


def test_assertion_state_distinguishes_absent_from_not_stated():
    assert AssertionState.ABSENT != AssertionState.NOT_STATED
    assert AssertionState.ABSENT.value != AssertionState.NOT_STATED.value


def test_assertion_state_has_five_values():
    assert len(AssertionState) == 5


def test_draft_is_not_lock_eligible():
    assert CurationStatus.DRAFT not in LOCK_ELIGIBLE_CURATION_STATUSES
    assert is_curation_status_lock_eligible(CurationStatus.DRAFT) is False


def test_reference_curated_is_lock_eligible():
    assert CurationStatus.REFERENCE_CURATED in LOCK_ELIGIBLE_CURATION_STATUSES
    assert is_curation_status_lock_eligible(CurationStatus.REFERENCE_CURATED) is True


def test_internally_reviewed_is_lock_eligible():
    assert is_curation_status_lock_eligible(CurationStatus.INTERNALLY_REVIEWED) is True


def test_expert_adjudicated_is_lock_eligible():
    assert is_curation_status_lock_eligible(CurationStatus.EXPERT_ADJUDICATED) is True


def test_lock_eligible_set_has_exactly_three_members():
    assert len(LOCK_ELIGIBLE_CURATION_STATUSES) == 3


def test_gold_case_kind_has_exactly_two_values():
    assert set(GoldCaseKind) == {GoldCaseKind.SYNTHETIC, GoldCaseKind.REFERENCE_GROUNDED}


def test_validation_scope_has_provided_evidence_and_end_to_end():
    assert ValidationScope.PROVIDED_EVIDENCE.value == "provided-evidence"
    assert ValidationScope.END_TO_END.value == "end-to-end"


def test_severity_level_matches_reference_precedence_vocabulary():
    from reference_precedence import _SEVERITY_ORDER
    assert set(_SEVERITY_ORDER.keys()) == {s.value for s in SeverityLevel}


def test_transformation_type_includes_summarized_by_curator():
    assert TransformationType.SUMMARIZED_BY_CURATOR.value == "Summarized by curator"
