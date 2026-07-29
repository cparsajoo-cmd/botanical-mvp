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


# ---------------------------------------------------------------------
# v4: is_lockable() / lock_gold_case() — strengthened lock invariants
# ---------------------------------------------------------------------

from datetime import date as _date

from applicability_check import check_applicability
from assertion_vocabulary import (
    AssertionState, AssertionType, SeverityLevel, GoldCaseKind,
    CurationStatus, TransformationType,
)
from gold_case import is_lockable, lock_gold_case, GoldCaseNotReadyError
from reference_claim import ReferenceClaim, NormalizedEvidenceText
from resolved_expected_outcome import resolve_expected_outcomes


def _lockable_unit():
    return ValidationUnit(
        taxon="Valeriana officinalis L.", population="Adults",
        jurisdiction="Germany", indication="Sleep",
    )


def _lockable_reference_and_claim(ref_id="ref1"):
    ref = ReferenceDescriptor(reference_id=ref_id, source_type="EMA_HMPC", version="v1")
    claim = ReferenceClaim(
        domain=ReferenceDomain.SAFETY, assertion_type=AssertionType.CONTRAINDICATION,
        subject="pregnancy", assertion_state=AssertionState.PRESENT, severity=SeverityLevel.SERIOUS,
        source_reference_id=ref_id, source_locator="section 4.3",
        evidence_text=NormalizedEvidenceText("orig", "norm", TransformationType.VERBATIM, "1.0", "section 4.3"),
    )
    return ref, claim


def _fully_ready_case(curation_status=CurationStatus.REFERENCE_CURATED):
    unit = _lockable_unit()
    ref, claim = _lockable_reference_and_claim()
    gref = GoldCaseReference(reference=ref, claims=[claim])
    gref.applicability_by_domain[ReferenceDomain.SAFETY] = check_applicability(ref, unit, ReferenceDomain.SAFETY)
    case = GoldCase(
        case_id="lock_test", validation_unit=unit, references=[gref],
        curation_status=curation_status,
    )
    case.resolved_outcomes = resolve_expected_outcomes(case)
    return case


def test_draft_curation_status_never_lockable():
    case = _fully_ready_case(curation_status=CurationStatus.DRAFT)
    ok, reasons = is_lockable(case)
    assert ok is False
    assert any("not lock-eligible" in r for r in reasons)


def test_reference_curated_is_sufficient_when_all_else_passes():
    case = _fully_ready_case(curation_status=CurationStatus.REFERENCE_CURATED)
    ok, reasons = is_lockable(case)
    assert ok is True
    assert reasons == []


def test_internally_reviewed_is_also_sufficient():
    case = _fully_ready_case(curation_status=CurationStatus.INTERNALLY_REVIEWED)
    ok, _ = is_lockable(case)
    assert ok is True


def test_expert_adjudicated_is_also_sufficient():
    case = _fully_ready_case(curation_status=CurationStatus.EXPERT_ADJUDICATED)
    ok, _ = is_lockable(case)
    assert ok is True


def test_curation_status_alone_never_sufficient_without_resolved_outcomes():
    case = GoldCase(
        case_id="c1", validation_unit=_lockable_unit(),
        curation_status=CurationStatus.EXPERT_ADJUDICATED,  # highest status, still not enough
    )
    ok, reasons = is_lockable(case)
    assert ok is False
    assert any("No resolved expected outcomes" in r for r in reasons)


def test_non_selected_resolution_status_blocks_locking():
    case = _fully_ready_case()
    case.references = []  # remove the reference so nothing applies
    case.resolved_outcomes = resolve_expected_outcomes(case)  # empty now
    ok, reasons = is_lockable(case)
    assert ok is False


def test_selected_reference_not_matching_any_case_reference_blocks_locking():
    case = _fully_ready_case()
    # Corrupt the resolved outcome to point at a reference that doesn't exist.
    case.resolved_outcomes[0].selected_reference_id = "nonexistent_ref"
    ok, reasons = is_lockable(case)
    assert ok is False
    assert any("does not match any reference" in r for r in reasons)


def test_applicability_not_computed_for_domain_blocks_locking():
    case = _fully_ready_case()
    case.references[0].applicability_by_domain = {}  # wipe it out
    ok, reasons = is_lockable(case)
    assert ok is False
    assert any("applicability was never computed" in r for r in reasons)


def test_applicability_disagreeing_with_resolution_blocks_locking():
    case = _fully_ready_case()
    # Force applicability to say NOT applicable, disagreeing with the
    # already-SELECTED resolution.
    from applicability_check import ApplicabilityResult
    case.references[0].applicability_by_domain[ReferenceDomain.SAFETY] = ApplicabilityResult(
        reference_id="ref1", domain=ReferenceDomain.SAFETY, applicable=False,
    )
    ok, reasons = is_lockable(case)
    assert ok is False
    assert any("NOT applicable" in r for r in reasons)


def test_missing_source_locator_on_claim_blocks_locking():
    case = _fully_ready_case()
    case.references[0].claims[0].source_locator = ""
    ok, reasons = is_lockable(case)
    assert ok is False
    assert any("no source_locator" in r for r in reasons)


def test_summarized_by_curator_blocks_locking_for_reference_grounded_kind():
    case = _fully_ready_case()
    case.kind = GoldCaseKind.REFERENCE_GROUNDED
    case.references[0].claims[0].evidence_text.transformation_type = TransformationType.SUMMARIZED_BY_CURATOR
    ok, reasons = is_lockable(case)
    assert ok is False
    assert any("SUMMARIZED_BY_CURATOR" in r for r in reasons)


def test_summarized_by_curator_allowed_for_synthetic_kind():
    case = _fully_ready_case()
    case.kind = GoldCaseKind.SYNTHETIC
    case.references[0].claims[0].evidence_text.transformation_type = TransformationType.SUMMARIZED_BY_CURATOR
    ok, reasons = is_lockable(case)
    assert ok is True


def test_lock_gold_case_raises_when_not_lockable():
    case = _fully_ready_case(curation_status=CurationStatus.DRAFT)
    try:
        lock_gold_case(case)
        assert False, "should have raised"
    except GoldCaseNotReadyError as e:
        assert len(e.reasons) > 0


def test_lock_gold_case_succeeds_and_sets_hash():
    case = _fully_ready_case()
    locked = lock_gold_case(case)
    assert locked.locked is True
    assert locked.dataset_snapshot_hash is not None
    assert len(locked.dataset_snapshot_hash) == 64


def test_lock_gold_case_never_mutates_original():
    case = _fully_ready_case()
    lock_gold_case(case)
    assert case.locked is False
    assert case.dataset_snapshot_hash is None


def test_lock_gold_case_returns_distinct_object():
    case = _fully_ready_case()
    locked = lock_gold_case(case)
    assert locked is not case


def test_is_lockable_never_mutates_input():
    case = _fully_ready_case()
    is_lockable(case)
    assert case.locked is False
    assert case.dataset_snapshot_hash is None
