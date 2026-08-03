"""
Tests for Case 005 (Cimicifuga racemosa / menopausal symptoms).

Scope, per explicit instruction: the MINIMUM tests needed to verify —
1. AssertionState.INSUFFICIENT maps to NOT_ELIGIBLE
2. engine evidence remains empty
3. no whole-case agreement is computed (no expected_decision_direction)
4. Ground Truth source is Cochrane only (EMA never enters the claim)

Does not execute the engine, does not modify gold_case_reference_
grounded_005_cimicifuga_racemosa.py or any other existing file.
"""

from agreement_eligibility import (
    AgreementEligibility, AgreementIneligibilityReason, assess_agreement_eligibility,
)
from assertion_vocabulary import AssertionState
from gold_case_reference_grounded_005_cimicifuga_racemosa import (
    build_gold_case_refgrounded_005_cimicifuga_racemosa_menopausal,
)


def test_insufficient_maps_to_not_eligible():
    """(1) The case's own resolved outcome carries
    AssertionState.INSUFFICIENT, and assess_agreement_eligibility()
    — the real protocol mapping, not a re-implementation of it —
    returns NOT_ELIGIBLE with reason ASSERTION_STATE_UNMAPPED."""
    case = build_gold_case_refgrounded_005_cimicifuga_racemosa_menopausal()

    indication_outcomes = [
        o for o in case.resolved_outcomes if o.subject == "menopausal symptoms"
    ]
    assert len(indication_outcomes) == 1
    assert indication_outcomes[0].assertion_state == AssertionState.INSUFFICIENT

    result = assess_agreement_eligibility(case)
    assert result.eligibility == AgreementEligibility.NOT_ELIGIBLE
    assert result.reason == AgreementIneligibilityReason.ASSERTION_STATE_UNMAPPED
    assert result.mapped_direction is None


def test_engine_evidence_remains_empty():
    """(2) No EngineEvidenceInput was constructed for this case."""
    case = build_gold_case_refgrounded_005_cimicifuga_racemosa_menopausal()
    assert case.engine_evidence == []
    assert case.engine_evidence_origin is None


def test_no_whole_case_agreement_is_computed():
    """(3) expected_output.expected_decision_direction was never set —
    there is nothing for evaluation_run.py to compare a whole-case
    agreement against. This is the case's own state, independent of
    assess_agreement_eligibility()'s separate NOT_ELIGIBLE verdict
    checked in test 1."""
    case = build_gold_case_refgrounded_005_cimicifuga_racemosa_menopausal()
    assert case.expected_output.expected_decision_direction is None


def test_ground_truth_source_is_cochrane_only():
    """(4) Exactly one GoldCaseReference exists (the Cochrane SR); the
    resolved outcome's selected_reference_id points to it; and the
    claim itself (assertion_state/evidence_text/source_reference_id)
    is Cochrane-sourced. EMA appears only in case_provenance, tagged
    to a ValidationUnit/preparation field, never to the resolved
    outcome or to the claim."""
    case = build_gold_case_refgrounded_005_cimicifuga_racemosa_menopausal()

    assert len(case.references) == 1
    gref = case.references[0]
    assert gref.reference.source_type == "SYSTEMATIC_REVIEW"
    assert gref.reference.reference_id == "COCHRANE_CD007244_2012_Leach_black_cohosh_menopausal"

    assert len(gref.claims) == 1
    claim = gref.claims[0]
    assert claim.source_reference_id == gref.reference.reference_id
    assert "insufficient evidence" in claim.evidence_text.original_text.lower()

    indication_outcomes = [
        o for o in case.resolved_outcomes if o.subject == "menopausal symptoms"
    ]
    assert indication_outcomes[0].selected_reference_id == gref.reference.reference_id

    ema_provenance = [
        p for p in case.case_provenance if p.document_id.startswith("EMA_HMPC")
    ]
    assert len(ema_provenance) == 1
    assert "validation_unit" in ema_provenance[0].supported_field
    assert "resolved_outcomes" not in ema_provenance[0].supported_field


if __name__ == "__main__":
    import sys
    import traceback

    tests = [
        test_insufficient_maps_to_not_eligible,
        test_engine_evidence_remains_empty,
        test_no_whole_case_agreement_is_computed,
        test_ground_truth_source_is_cochrane_only,
    ]
    failures = 0
    for test in tests:
        try:
            test()
            print(f"PASS  {test.__name__}")
        except Exception:
            failures += 1
            print(f"FAIL  {test.__name__}")
            traceback.print_exc()
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
