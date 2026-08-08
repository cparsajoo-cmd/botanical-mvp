from decision_benchmark_v1 import DecisionMetrics
from final_decision_policy import FinalDecisionStatus
from scientific_validity_release_gate import (
    ReferenceValidationProtocol, evaluate_reference_grounded_release,
)

LABELS=[x.value for x in FinalDecisionStatus]

def matrix():
    return {e:{a:(4 if e==a else 0) for a in LABELS} for e in LABELS}

def metrics(**kw):
    d=dict(
        n_scored=24,n_correct=24,accuracy=1.0,macro_f1=1.0,
        per_class_recall={x:1.0 for x in LABELS},
        serious_safety_false_negatives=0,regulatory_false_negatives=0,
        false_no_go=0,expert_review_overuse=0,insufficient_evidence_miss=0,
        confusion_matrix=matrix(),
    ); d.update(kw); return DecisionMetrics(**d)

def protocol(**kw):
    d=dict(
        benchmark_id="reference-final-v1",
        reference_frozen_before_engine_run=True,
        engine_blinded_to_reference_labels=True,
        remediation_cases_excluded=True,
        reference_evidence_excluded_from_engine_input=True,
        provenance_complete=True,
        n_cases=24,
        class_support={x:4 for x in LABELS},
        reference_source_support={f"case_{i:02d}":1 for i in range(24)},
    ); d.update(kw); return ReferenceValidationProtocol(**d)

def test_clean_reference_grounded_protocol_can_pass_without_human_adjudicator_fields():
    r=evaluate_reference_grounded_release(protocol(),metrics())
    assert r.releasable
    assert r.claim.startswith("REFERENCE-GROUNDED")

def test_reference_evidence_leakage_blocks_release():
    r=evaluate_reference_grounded_release(
        protocol(reference_evidence_excluded_from_engine_input=False),metrics()
    )
    assert not r.releasable
    assert any("leaked" in x.lower() for x in r.blockers)

def test_missing_provenance_blocks_release():
    r=evaluate_reference_grounded_release(protocol(provenance_complete=False),metrics())
    assert not r.releasable

def test_remediation_case_reuse_blocks_release():
    r=evaluate_reference_grounded_release(protocol(remediation_cases_excluded=False),metrics())
    assert not r.releasable

def test_serious_safety_false_negative_remains_zero_tolerance():
    r=evaluate_reference_grounded_release(protocol(),metrics(serious_safety_false_negatives=1))
    assert not r.releasable

def test_every_case_requires_reference_source_accounting():
    refs={f"case_{i:02d}":1 for i in range(23)}
    r=evaluate_reference_grounded_release(protocol(reference_source_support=refs),metrics())
    assert not r.releasable
    assert any("23/24" in x for x in r.blockers)
