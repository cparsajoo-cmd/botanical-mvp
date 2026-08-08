from types import SimpleNamespace
from eligibility_gate import EligibilityStatus
from final_decision_policy import (
    FinalDecisionStatus,
    ScientificEvidenceSignal,
    decide_final,
    resolve_scientific_evidence,
)


def _rec(text):
    return {"source_type": "SYSTEMATIC_REVIEW", "assertion_text": text}


def _eligible():
    return SimpleNamespace(status=EligibilityStatus.ELIGIBLE, gate_reason="")


def test_single_unhedged_supportive_review_is_cautious_at_body_level():
    r = resolve_scientific_evidence([_rec("Meta-analysis found a significant improvement in clinical symptoms versus control.")])
    assert r.signal is ScientificEvidenceSignal.SUPPORTIVE_WITH_CAUTION
    assert decide_final(_eligible(), r).status is FinalDecisionStatus.GO_WITH_CAUTION


def test_may_be_beneficial_is_supportive_with_caution():
    r = resolve_scientific_evidence([_rec("The systematic review suggests the intervention may be beneficial for improving blood pressure.")])
    assert r.signal is ScientificEvidenceSignal.SUPPORTIVE_WITH_CAUTION
    assert decide_final(_eligible(), r).status is FinalDecisionStatus.GO_WITH_CAUTION


def test_positive_result_requiring_confirmation_is_caution():
    r = resolve_scientific_evidence([_rec("The meta-analysis found significant improvement, but the observed effects require confirmation in further high-quality trials.")])
    assert r.signal is ScientificEvidenceSignal.SUPPORTIVE_WITH_CAUTION


def test_possible_benefit_but_evidence_uncertain_is_insufficient():
    r = resolve_scientific_evidence([_rec("Possible treatment benefits were observed, but the evidence remains uncertain and is insufficient for firm conclusions.")])
    assert r.signal is ScientificEvidenceSignal.INSUFFICIENT
    assert decide_final(_eligible(), r).status is FinalDecisionStatus.INSUFFICIENT_EVIDENCE


def test_uncertainty_language_does_not_turn_negative_into_caution():
    r = resolve_scientific_evidence([_rec("No clinically meaningful benefit was demonstrated; further studies are needed.")])
    assert r.signal is ScientificEvidenceSignal.INSUFFICIENT
