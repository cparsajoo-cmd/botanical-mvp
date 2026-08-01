"""Focused regression tests for corrected Case 012."""
from applicability_check import ReferenceDomain
from assertion_vocabulary import AssertionState
from reference_precedence import ResolutionStatus
from gold_case_reference_grounded_012_lavandula_angustifolia_sleep import build_gold_case_refgrounded_012_lavandula_angustifolia_sleep

def _case():
    return build_gold_case_refgrounded_012_lavandula_angustifolia_sleep()

def test_source_type_is_protocol_recognized():
    case=_case()
    assert case.references[0].reference.source_type == "EMA_HMPC"

def test_reference_is_applicable():
    case=_case()
    result=case.references[0].applicability_by_domain[ReferenceDomain.INDICATION_EVIDENCE]
    assert result.applicable is True, result.detail

def test_outcome_selected():
    case=_case()
    assert len(case.resolved_outcomes)==1
    outcome=case.resolved_outcomes[0]
    assert outcome.resolution_status == ResolutionStatus.SELECTED
    assert outcome.selected_reference_id == 'EMA_HMPC_530968_2012_lavandulae_aetheroleum_summary'
    assert outcome.assertion_state == AssertionState.PRESENT

def test_no_engine_evidence_leakage():
    case=_case()
    assert case.engine_evidence == []
    assert case.engine_evidence_origin is None

def test_evidence_is_traceable():
    claim=_case().references[0].claims[0]
    assert claim.source_locator
    assert claim.evidence_text is not None
    assert claim.evidence_text.original_text

if __name__ == "__main__":
    tests=[v for k,v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for test in tests:
        test(); print("PASS", test.__name__)
    print(f"{len(tests)}/{len(tests)} passed")
