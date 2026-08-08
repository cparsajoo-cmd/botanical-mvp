from decision_benchmark_v1 import DecisionMetrics
from final_decision_policy import FinalDecisionStatus
from scientific_validity_release_gate import (
    ValidationProtocol, ScientificReleaseProfile, evaluate_scientific_release,
)

LABELS=[x.value for x in FinalDecisionStatus]

def matrix(diagonal=4):
    return {e:{a:(diagonal if e==a else 0) for a in LABELS} for e in LABELS}

def metrics(m=None, accuracy=1.0, macro=1.0):
    m=m or matrix()
    return DecisionMetrics(
        n_scored=24,n_correct=24,accuracy=accuracy,macro_f1=macro,
        per_class_recall={x:1.0 for x in LABELS},
        serious_safety_false_negatives=0,regulatory_false_negatives=0,
        false_no_go=0,expert_review_overuse=0,insufficient_evidence_miss=0,
        confusion_matrix=m,
    )

def protocol(**kw):
    d=dict(
        benchmark_id="final-v1", reference_frozen_before_engine_run=True,
        engine_blinded_to_reference_labels=True, remediation_cases_excluded=True,
        adjudicator_count=2, adjudicators_independent=True,
        inter_rater_agreement=0.85,n_cases=24,
        class_support={x:4 for x in LABELS},
    )
    d.update(kw)
    return ValidationProtocol(**d)

def test_balanced_independent_high_agreement_benchmark_can_pass():
    d=evaluate_scientific_release(protocol(),metrics())
    assert d.releasable is True
    assert d.blockers == ()

def test_leakage_always_blocks_release_even_with_perfect_accuracy():
    d=evaluate_scientific_release(protocol(remediation_cases_excluded=False),metrics())
    assert d.releasable is False
    assert any("remediation" in x.lower() for x in d.blockers)

def test_safety_false_negative_is_zero_tolerance():
    m=metrics()
    bad=DecisionMetrics(**{**m.__dict__,"serious_safety_false_negatives":1})
    d=evaluate_scientific_release(protocol(),bad)
    assert d.releasable is False
    assert any("safety false negatives" in x.lower() for x in d.blockers)

def test_unbalanced_six_class_benchmark_cannot_claim_validation():
    support={x:4 for x in LABELS}; support[FinalDecisionStatus.NO_GO_REGULATORY.value]=0
    d=evaluate_scientific_release(protocol(class_support=support),metrics())
    assert d.releasable is False
    assert any("NO GO REGULATORY" in x for x in d.blockers)

def test_low_go_precision_blocks_even_if_overall_accuracy_looks_good():
    m=matrix()
    # Three caution cases are incorrectly promoted to GO.
    m[FinalDecisionStatus.GO_WITH_CAUTION.value][FinalDecisionStatus.GO_WITH_CAUTION.value]=1
    m[FinalDecisionStatus.GO_WITH_CAUTION.value][FinalDecisionStatus.GO.value]=3
    met=metrics(m=m,accuracy=21/24,macro=0.80)
    met=DecisionMetrics(**{**met.__dict__,
        "per_class_recall":{**met.per_class_recall,FinalDecisionStatus.GO_WITH_CAUTION.value:0.25}})
    d=evaluate_scientific_release(protocol(),met)
    assert d.releasable is False
    assert any("GO precision" in x or "CAUTION recall" in x for x in d.blockers)
