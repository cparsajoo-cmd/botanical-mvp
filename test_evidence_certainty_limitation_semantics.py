from final_decision_policy import (
    EvidenceLimitationTier,
    ScientificEvidenceSignal,
    _evidence_limitation_tier,
    _final_decision_direction,
    resolve_scientific_evidence,
)
from evidence_interpretation import DIRECTION_MIXED, DIRECTION_NULL


def rec(source_type, text, year=2024, study_design="Systematic Review and Meta-analysis"):
    return {
        "source_type": source_type,
        "assertion_text": text,
        "source_year": year,
        "study_design": study_design,
    }


def test_positive_review_with_explicit_heterogeneity_is_caution():
    r = resolve_scientific_evidence([
        rec("SYSTEMATIC_REVIEW", "Meta-analysis found significant benefit, but high heterogeneity was present across studies.")
    ])
    assert r.signal == ScientificEvidenceSignal.SUPPORTIVE_WITH_CAUTION


def test_positive_review_needing_more_evidence_is_caution():
    r = resolve_scientific_evidence([
        rec("SYSTEMATIC_REVIEW", "Meta-analysis found significant reductions, but more evidence is needed to assess long-term effects.")
    ])
    assert r.signal == ScientificEvidenceSignal.SUPPORTIVE_WITH_CAUTION


def test_plain_supportive_review_without_limitations_stays_supportive():
    r = resolve_scientific_evidence([
        rec("SYSTEMATIC_REVIEW", "Meta-analysis found significant improvement versus placebo.")
    ])
    assert r.signal == ScientificEvidenceSignal.SUPPORTIVE


def test_insufficient_to_establish_benefit_is_null_direction():
    text = "Systematic review found the evidence insufficient to establish clear clinical benefit across indications."
    assert _evidence_limitation_tier(text) == EvidenceLimitationTier.FIRM_UNCERTAINTY
    assert _final_decision_direction(text) == DIRECTION_NULL


def test_equal_rank_positive_and_firm_insufficient_review_requires_conflict():
    r = resolve_scientific_evidence([
        rec("SYSTEMATIC_REVIEW", "Systematic review found the evidence insufficient to establish clear clinical benefit.", 2010),
        rec("SYSTEMATIC_REVIEW", "Meta-analysis found significant improvement in clinical outcomes.", 2025),
    ])
    assert r.signal == ScientificEvidenceSignal.CONFLICT


def test_endpoint_split_conclusion_is_mixed_not_hard_null():
    text = "Meta-analysis found beneficial HbA1c findings but fasting glucose estimates were not significant."
    assert _final_decision_direction(text) == DIRECTION_MIXED


def test_limitation_qualified_synthesis_plus_supportive_direct_trial_is_caution():
    r = resolve_scientific_evidence([
        rec("SYSTEMATIC_REVIEW", "The putative efficacy is not adequately corroborated because of methodological weaknesses."),
        rec("CLINICAL_TRIAL", "Both treatments were effective, although no significant difference was found between the active groups.", 2025, "Randomized Controlled Trial"),
    ])
    assert r.signal == ScientificEvidenceSignal.SUPPORTIVE_WITH_CAUTION


def test_single_supportive_rct_without_higher_tier_synthesis_is_caution():
    r = resolve_scientific_evidence([
        rec("CLINICAL_TRIAL", "Randomized placebo-controlled trial found significant symptom reduction.", 2025, "Randomized Controlled Trial")
    ])
    assert r.signal == ScientificEvidenceSignal.SUPPORTIVE_WITH_CAUTION


def test_active_comparator_no_between_group_difference_does_not_erase_efficacy():
    text = "The randomized trial found both interventions were effective with no significant between-group difference."
    assert _final_decision_direction(text) in {"positive", "mixed"}
