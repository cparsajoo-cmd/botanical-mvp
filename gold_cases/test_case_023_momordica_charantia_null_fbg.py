"""Focused tests for Gold Case 023 standalone null human evidence."""
from applicability_check import ReferenceDomain
from assertion_vocabulary import AssertionState, AssertionType, GoldCaseKind
from reference_precedence import ResolutionStatus
from gold_case_reference_grounded_023_momordica_charantia_null_fbg import (
    _SR_ID,
    build_gold_case_refgrounded_023_momordica_charantia_null_fbg,
)


def _case():
    return build_gold_case_refgrounded_023_momordica_charantia_null_fbg()


def test_case_023_is_reference_grounded_single_source():
    c = _case()
    assert c.kind == GoldCaseKind.REFERENCE_GROUNDED
    assert len(c.references) == 1
    assert c.references[0].reference.reference_id == _SR_ID


def test_case_023_uses_verified_systematic_review_source_type():
    ref = _case().references[0].reference
    assert ref.source_type == "SYSTEMATIC_REVIEW"
    assert "PMID:38274207" in ref.version
    assert "10.3389/fnut.2023.1200801" in ref.version


def test_case_023_reference_is_applicable():
    g = _case().references[0]
    assert g.applicability_by_domain[ReferenceDomain.INDICATION_EVIDENCE].applicable is True


def test_case_023_is_null_support_result_not_insufficient():
    o = _case().resolved_outcomes[0]
    assert o.domain == ReferenceDomain.INDICATION_EVIDENCE
    assert o.assertion_type == AssertionType.SUPPORTS_INDICATION
    assert o.assertion_state == AssertionState.ABSENT
    assert o.assertion_state != AssertionState.INSUFFICIENT


def test_case_023_single_systematic_review_is_selected():
    o = _case().resolved_outcomes[0]
    assert o.resolution_status == ResolutionStatus.SELECTED
    assert o.selected_reference_id == _SR_ID
    assert not o.conflicting_reference_ids


def test_case_023_scope_is_fasting_glucose_only():
    c = _case()
    assert c.validation_unit.indication == "reduction of fasting blood glucose"
    assert c.validation_unit.preparation is None
    assert c.validation_unit.dose is None
    assert c.validation_unit.plant_part is None


def test_case_023_has_no_engine_evidence_or_locking_leakage():
    c = _case()
    assert c.engine_evidence == []
    assert c.engine_evidence_origin is None
    assert c.locked is False


def test_case_023_verbatim_excerpt_is_bounded():
    claim = _case().references[0].claims[0]
    assert len(claim.evidence_text.original_text.split()) < 25
    assert "fasting blood glucose" in claim.evidence_text.original_text.lower()


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    for t in tests:
        t(); print("PASS ", t.__name__)
    print(f"{len(tests)}/{len(tests)} passed")
