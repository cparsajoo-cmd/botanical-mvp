import pytest

from final_decision_policy import (
    EvidenceLimitationTier,
    FinalDecisionStatus,
    ScientificEvidenceSignal,
    _evidence_limitation_tier,
    _final_decision_direction,
    resolve_scientific_evidence,
    decide_final,
)
from eligibility_gate import EligibilityDecision, EligibilityStatus

def _eligible():
    from eligibility_gate import (
        SafetyFinding, RegulatoryFinding, SafetySeverity, FindingScope,
        ContextRelevance, DataCompleteness, RegulatoryDataStatus,
        evaluate_eligibility,
    )
    safety=SafetyFinding(
        severity=SafetySeverity.NONE,
        scope=FindingScope.SPECIES_WIDE,
        context_relevance=ContextRelevance.RELEVANT,
        data_completeness=DataCompleteness.COMPLETE,
        same_plant=True,
    )
    regulatory=RegulatoryFinding(
        status=RegulatoryDataStatus.CLEAR,
        scope=FindingScope.SPECIES_WIDE,
        context_relevance=ContextRelevance.RELEVANT,
        same_plant=True,
    )
    return evaluate_eligibility(safety, regulatory)

def test_positive_systematic_review_with_material_limitations_is_caution():
    records=[{
        "source_type":"SYSTEMATIC_REVIEW",
        "study_design":"Systematic Review and Meta-analysis",
        "assertion_text":"Meta-analysis found significant improvement, but very high heterogeneity and further high-quality trials are needed.",
        "source_year":2024,
    }]
    r=resolve_scientific_evidence(records)
    assert r.signal == ScientificEvidenceSignal.SUPPORTIVE_WITH_CAUTION

def test_little_to_no_difference_is_null_and_insufficient():
    records=[{
        "source_type":"SYSTEMATIC_REVIEW",
        "study_design":"Systematic Review and Meta-analysis",
        "assertion_text":"Systematic review found little to no difference in symptoms or quality of life.",
        "source_year":2024,
    }]
    r=resolve_scientific_evidence(records)
    assert r.signal == ScientificEvidenceSignal.INSUFFICIENT

def test_unresolved_scientific_evidence_never_defaults_to_go():
    from final_decision_policy import ScientificEvidenceResolution
    sci=ScientificEvidenceResolution(
        ScientificEvidenceSignal.UNRESOLVED,
        "No usable direction could be assigned.",
    )
    d=decide_final(_eligible(), sci)
    assert d.status == FinalDecisionStatus.INSUFFICIENT_EVIDENCE

def test_single_clean_positive_synthesis_is_caution_not_unconditional_go():
    records=[{
        "source_type":"SYSTEMATIC_REVIEW",
        "study_design":"Systematic Review and Meta-analysis",
        "assertion_text":"Meta-analysis found significant improvement versus placebo.",
        "source_year":2024,
    }]
    r=resolve_scientific_evidence(records)
    assert r.signal == ScientificEvidenceSignal.SUPPORTIVE_WITH_CAUTION
    d=decide_final(_eligible(), r)
    assert d.status == FinalDecisionStatus.GO_WITH_CAUTION


def test_limitation_language_order_variants_are_caution():
    samples = [
        "Benefit was observed, but heterogeneity was very high and further high-quality studies were needed.",
        "Effects were positive, but certainty of evidence was low.",
        "Benefits were reported, but studies were small and reporting quality varied.",
        "Benefit was observed, but heterogeneity across preparations required cautious interpretation.",
    ]
    for text in samples:
        assert _evidence_limitation_tier(text) == EvidenceLimitationTier.CAUTION

def test_positive_plus_equally_ranked_unclear_is_caution_not_full_go():
    records=[
        {"source_type":"SYSTEMATIC_REVIEW","assertion_text":"Meta-analysis found significant improvement.","source_year":2024},
        {"source_type":"SYSTEMATIC_REVIEW","assertion_text":"Review described evidence that could not be assigned a clear direction.","source_year":2023},
    ]
    r=resolve_scientific_evidence(records)
    assert r.signal == ScientificEvidenceSignal.SUPPORTIVE_WITH_CAUTION


def test_recognized_monograph_therapeutic_indication_is_usable_support():
    records=[{
        "source_type":"ESCOP_MONOGRAPH",
        "assertion_text":"ESCOP lists recurrent upper respiratory tract infections among therapeutic indications.",
    }]
    r=resolve_scientific_evidence(records)
    assert r.signal == ScientificEvidenceSignal.SUPPORTIVE

def test_eligibility_restriction_remains_caution_even_without_efficacy_resolution():
    from final_decision_policy import ScientificEvidenceResolution
    from eligibility_gate import (
        SafetyFinding, RegulatoryFinding, SafetySeverity, FindingScope,
        ContextRelevance, DataCompleteness, RegulatoryDataStatus,
        evaluate_eligibility,
    )
    safety=SafetyFinding(
        severity=SafetySeverity.NONE, scope=FindingScope.SPECIES_WIDE,
        context_relevance=ContextRelevance.RELEVANT,
        data_completeness=DataCompleteness.COMPLETE, same_plant=True,
    )
    regulatory=RegulatoryFinding(
        status=RegulatoryDataStatus.RESTRICTED, scope=FindingScope.DOSE_SPECIFIC,
        context_relevance=ContextRelevance.RELEVANT, same_plant=True,
    )
    elig=evaluate_eligibility(safety, regulatory)
    sci=ScientificEvidenceResolution(ScientificEvidenceSignal.UNRESOLVED,"No efficacy synthesis.")
    assert decide_final(elig,sci).status == FinalDecisionStatus.GO_WITH_CAUTION


def test_ema_traditional_use_positive_support_is_caution_not_unconditional_go():
    records=[{
        "source_type":"EMA_HMPC",
        "study_design":"regulatory monograph",
        "assertion_text":(
            "EMA HMPC classifies this indication as traditional use: accepted "
            "on the basis of sufficient safety data and plausible efficacy from "
            "long-standing use rather than the well-established-use evidence standard."
        ),
        "source_result_direction":"Positive",
        "primary_outcome":"target symptom",
        "comparator":"not applicable",
        "risk_of_bias":"not applicable",
        "applicability_classification":"applicable",
        "source_year":2020,
    }]
    r=resolve_scientific_evidence(records)
    assert r.signal == ScientificEvidenceSignal.SUPPORTIVE_WITH_CAUTION
    assert decide_final(_eligible(), r).status == FinalDecisionStatus.GO_WITH_CAUTION


def test_ema_well_established_use_is_not_downgraded_as_traditional_use():
    records=[{
        "source_type":"EMA_HMPC",
        "study_design":"regulatory monograph",
        "assertion_text":"EMA HMPC classifies this indication as well-established use based on sufficient efficacy and safety data.",
        "source_result_direction":"Positive",
        "primary_outcome":"target symptom",
        "comparator":"not applicable",
        "risk_of_bias":"not applicable",
        "applicability_classification":"applicable",
        "source_year":2020,
    }]
    r=resolve_scientific_evidence(records)
    assert r.signal == ScientificEvidenceSignal.SUPPORTIVE

@pytest.mark.parametrize("wording", [
    "EMA HMPC describes this indication as a traditional herbal medicinal product based on long-standing use.",
    "EMA HMPC supports this indication under traditional use based on long-standing medicinal use.",
    "These oral preparations are traditional herbal medicinal products for relief of the target symptom.",
])
def test_ema_formal_traditional_use_wording_is_capped_at_caution(wording):
    records=[{
        "source_type":"EMA_HMPC",
        "study_design":"regulatory monograph",
        "assertion_text":wording,
        "source_result_direction":"Positive",
        "primary_outcome":"target symptom",
        "comparator":"not applicable",
        "risk_of_bias":"not applicable",
        "applicability_classification":"applicable",
        "source_year":2025,
    }]
    r=resolve_scientific_evidence(records)
    assert r.signal == ScientificEvidenceSignal.SUPPORTIVE_WITH_CAUTION
    assert decide_final(_eligible(), r).status == FinalDecisionStatus.GO_WITH_CAUTION
