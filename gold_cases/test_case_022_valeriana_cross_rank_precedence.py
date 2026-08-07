"""Focused tests for Gold Case 022 cross-rank precedence."""
from applicability_check import ReferenceDomain
from assertion_vocabulary import AssertionState, AssertionType
from reference_precedence import ResolutionStatus
from gold_case_reference_grounded_022_valeriana_cross_rank_precedence import (
    _EMA_ID,
    _SR_ID,
    build_gold_case_refgrounded_022_valeriana_cross_rank_precedence,
)


def _case():
    return build_gold_case_refgrounded_022_valeriana_cross_rank_precedence()


def test_two_real_applicable_references_present():
    c = _case()
    assert len(c.references) == 2
    for g in c.references:
        assert g.applicability_by_domain[ReferenceDomain.INDICATION_EVIDENCE].applicable is True


def test_source_types_are_systematic_review_and_ema():
    c = _case()
    assert {g.reference.source_type for g in c.references} == {"SYSTEMATIC_REVIEW", "EMA_HMPC"}


def test_reference_claims_disagree_epistemically():
    c = _case()
    states = {g.reference.reference_id: g.claims[0].assertion_state for g in c.references}
    assert states[_SR_ID] == AssertionState.INSUFFICIENT
    assert states[_EMA_ID] == AssertionState.PRESENT


def test_systematic_review_wins_cross_rank_precedence():
    o = _case().resolved_outcomes[0]
    assert o.resolution_status == ResolutionStatus.SELECTED
    assert o.selected_reference_id == _SR_ID
    assert o.assertion_state == AssertionState.INSUFFICIENT


def test_newer_ema_does_not_override_higher_rank_source():
    c = _case()
    refs = {g.reference.reference_id: g.reference for g in c.references}
    assert refs[_EMA_ID].document_date > refs[_SR_ID].document_date
    assert c.resolved_outcomes[0].selected_reference_id == _SR_ID


def test_not_misclassified_as_same_rank_conflict():
    o = _case().resolved_outcomes[0]
    assert o.resolution_status != ResolutionStatus.REFERENCE_CONFLICT
    assert not o.conflicting_reference_ids


def test_case_is_indication_evidence_only():
    o = _case().resolved_outcomes[0]
    assert o.domain == ReferenceDomain.INDICATION_EVIDENCE
    assert o.assertion_type == AssertionType.SUPPORTS_INDICATION


def test_no_engine_evidence_or_locking_leakage():
    c = _case()
    assert c.engine_evidence == []
    assert c.engine_evidence_origin is None
    assert c.locked is False


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    for t in tests:
        t(); print("PASS ", t.__name__)
    print(f"{len(tests)}/{len(tests)} passed")
