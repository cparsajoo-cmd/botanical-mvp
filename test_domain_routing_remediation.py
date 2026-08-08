from pathlib import Path

from decision_benchmark_v1 import discover_reference_grounded_cases
from final_decision_policy import AssessmentDomain, assessment_domain_from_indication, FinalDecisionStatus
from independent_holdout_e2e import load_snapshot, run_snapshot
from interaction_severity_classifier import classify_interaction_assertion, InteractionSeverityTier


def _case(n: int):
    return next(
        c for c in discover_reference_grounded_cases(Path(__file__).resolve().parent)
        if f"_{n:03d}_" in c.case_id
    )


def test_domain_label_mapping_is_narrow_and_generic():
    assert assessment_domain_from_indication("Preparation specification") is AssessmentDomain.PREPARATION_SPEC
    assert assessment_domain_from_indication("Identity/Quality") is AssessmentDomain.IDENTITY_QUALITY
    assert assessment_domain_from_indication("Safety") is AssessmentDomain.SAFETY
    assert assessment_domain_from_indication("Sleep and relaxation") is AssessmentDomain.THERAPEUTIC
    assert assessment_domain_from_indication("Safety and tolerability in insomnia") is AssessmentDomain.THERAPEUTIC


def test_advises_caution_when_combining_is_not_mechanism_only():
    r = classify_interaction_assertion(
        "An interaction study indicates possible transporter inhibition and advises caution when combining the botanical with a medicine."
    )
    assert r.tier is InteractionSeverityTier.PRECAUTION_CAUTION


def test_preparation_and_identity_holdout_regressions_route_to_expert_review():
    for n in (7, 8, 13, 15, 17):
        actual, _row = run_snapshot(_case(n), load_snapshot(n))
        assert actual is FinalDecisionStatus.EXPERT_REVIEW_REQUIRED


def test_safety_interaction_holdout_regression_routes_to_expert_review():
    actual, row = run_snapshot(_case(14), load_snapshot(14))
    assert actual is FinalDecisionStatus.EXPERT_REVIEW_REQUIRED
    assert "interaction" in str(row.get("Interaction_Flags", "")).lower()
