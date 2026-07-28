"""Tests for gold_case.py (Validation Architecture v3, Phase 1)."""

from applicability_check import ApplicabilityResult, ReferenceDomain
from dataset_split import DatasetSplit
from gold_case import GoldCase, GoldCaseReference, ExpectedOutput, RiskStratum, DecisionDirection
from reference_descriptor import ReferenceDescriptor
from validation_unit import ValidationUnit


def test_gold_case_defaults():
    case = GoldCase(case_id="c1", validation_unit=ValidationUnit(taxon="X"))
    assert case.risk_strata == []
    assert case.references == []
    assert case.dataset_split == DatasetSplit.DEVELOPMENT
    assert case.correct_abstention_expected is False


def test_gold_case_can_carry_multiple_risk_strata():
    case = GoldCase(
        case_id="c1", validation_unit=ValidationUnit(taxon="X"),
        risk_strata=[RiskStratum.SAFETY_SERIOUS, RiskStratum.VULNERABLE_POPULATION],
    )
    assert len(case.risk_strata) == 2


def test_expected_output_defaults():
    output = ExpectedOutput()
    assert output.expected_gate_results == {}
    assert output.expected_decision_direction is None
    assert output.expected_warnings == []


def test_expected_output_acceptable_range_not_single_point():
    output = ExpectedOutput(
        acceptable_decision_class_min="Early-stage candidate; more evidence needed",
        acceptable_decision_class_max="Strong R&D candidate",
    )
    assert output.acceptable_decision_class_min != output.acceptable_decision_class_max


# ---------------------------------------------------------------------
# Applicability stored PER-REFERENCE-PER-DOMAIN (v3 correction #5) —
# not one global value on GoldCase.
# ---------------------------------------------------------------------

def test_gold_case_has_no_single_global_applicability_field():
    case = GoldCase(case_id="c1", validation_unit=ValidationUnit(taxon="X"))
    assert not hasattr(case, "applicability")
    assert not hasattr(case, "reference_conflict")  # v2's old global field, removed in v3


def test_applicability_stored_per_reference_per_domain():
    ref = ReferenceDescriptor(reference_id="r1", source_type="EMA_HMPC", version="v1")
    gold_ref = GoldCaseReference(reference=ref)
    gold_ref.applicability_by_domain[ReferenceDomain.SAFETY] = ApplicabilityResult(
        reference_id="r1", domain=ReferenceDomain.SAFETY, applicable=True,
    )
    gold_ref.applicability_by_domain[ReferenceDomain.IDENTITY_QUALITY] = ApplicabilityResult(
        reference_id="r1", domain=ReferenceDomain.IDENTITY_QUALITY, applicable=False,
        failed_dimensions=[], detail={},
    )
    assert gold_ref.applicability_by_domain[ReferenceDomain.SAFETY].applicable is True
    assert gold_ref.applicability_by_domain[ReferenceDomain.IDENTITY_QUALITY].applicable is False


def test_same_reference_can_be_applicable_for_one_domain_and_not_another():
    # The exact scenario v3 correction #5 exists to support.
    ref = ReferenceDescriptor(reference_id="r1", source_type="EMA_HMPC", version="v1")
    gold_ref = GoldCaseReference(reference=ref)
    gold_ref.applicability_by_domain[ReferenceDomain.IDENTITY_QUALITY] = ApplicabilityResult(
        reference_id="r1", domain=ReferenceDomain.IDENTITY_QUALITY, applicable=True,
    )
    gold_ref.applicability_by_domain[ReferenceDomain.SAFETY] = ApplicabilityResult(
        reference_id="r1", domain=ReferenceDomain.SAFETY, applicable=False,
    )
    applicable = gold_ref.applicable_domains()
    assert ReferenceDomain.IDENTITY_QUALITY in applicable
    assert ReferenceDomain.SAFETY not in applicable


def test_applicable_domains_returns_empty_list_when_nothing_checked_yet():
    ref = ReferenceDescriptor(reference_id="r1", source_type="EMA_HMPC", version="v1")
    gold_ref = GoldCaseReference(reference=ref)
    assert gold_ref.applicable_domains() == []


def test_gold_case_with_multiple_references():
    ref1 = ReferenceDescriptor(reference_id="r1", source_type="EMA_HMPC", version="v1")
    ref2 = ReferenceDescriptor(reference_id="r2", source_type="WHO_MONOGRAPH", version="v1")
    case = GoldCase(
        case_id="c1", validation_unit=ValidationUnit(taxon="X"),
        references=[GoldCaseReference(reference=ref1), GoldCaseReference(reference=ref2)],
    )
    assert len(case.references) == 2
