import copy

import pandas as pd
import pytest

import candidate_shortlisting as cs
from phase5_scoring_config import (
    RANKING_COMPONENT_ACTIVE_WEIGHTS,
    RANKING_COMPONENT_BASE_WEIGHTS,
    RANKING_CALIBRATION_STATUS,
)
from ranking_score_model import reweight_score_breakdown, score_from_breakdown
from ranking_calibration import (
    CalibrationDataError,
    calibration_readiness,
    evaluate_expert_benchmark,
    search_candidate_configuration,
)
from scoring_sensitivity_report import build_bounded_weight_robustness


def _full_breakdown(**overrides):
    row = {
        "Indication Relevance": 28.0,
        "Scientific Evidence": 21.0,
        "Compound Support": 4.0,
        "Mechanism Support": 8.0,
        "Safety & Regulatory": 12.0,
        "Novelty & Market": 4.0,
    }
    row.update(overrides)
    return row


def test_active_weight_model_is_identity_preserving_at_baseline():
    raw = _full_breakdown()
    weighted = reweight_score_breakdown(raw, RANKING_COMPONENT_ACTIVE_WEIGHTS)
    assert weighted == pytest.approx(raw)
    assert score_from_breakdown(raw, RANKING_COMPONENT_ACTIVE_WEIGHTS) == pytest.approx(sum(raw.values()))


def test_weights_are_explicit_and_sum_to_100():
    assert set(RANKING_COMPONENT_ACTIVE_WEIGHTS) == set(RANKING_COMPONENT_BASE_WEIGHTS)
    assert sum(RANKING_COMPONENT_ACTIVE_WEIGHTS.values()) == pytest.approx(100.0)


def test_same_genus_annotation_never_changes_scientific_status_or_score():
    frame = pd.DataFrame([
        {
            "Alternative_Plant": "Salvia alpha",
            "Scientific_Triage_Status": "Shortlist",
            "Overall_Score": 82.0,
            "R&D_Opportunity_Score": 82.0,
            "Go_Investigate_Hold_NoGo": "Go",
            "Decision_Class_AH": "B — Established scientific candidate",
            "Indication_Relevance_Score": 30.0,
            "Evidence_Quality_Score": 25.0,
            "Compound_Quality_Score": 4.0,
            "Traceable_Source_Count": 3,
            "Safety_Regulatory_Score": 15.0,
        },
        {
            "Alternative_Plant": "Salvia beta",
            "Scientific_Triage_Status": "Shortlist",
            "Overall_Score": 81.0,
            "R&D_Opportunity_Score": 81.0,
            "Go_Investigate_Hold_NoGo": "Go",
            "Decision_Class_AH": "B — Established scientific candidate",
            "Indication_Relevance_Score": 30.0,
            "Evidence_Quality_Score": 24.0,
            "Compound_Quality_Score": 4.0,
            "Traceable_Source_Count": 3,
            "Safety_Regulatory_Score": 15.0,
        },
    ])
    before = frame[["Scientific_Triage_Status", "Overall_Score", "R&D_Opportunity_Score", "Go_Investigate_Hold_NoGo", "Decision_Class_AH"]].copy()
    after = cs._prune_near_duplicate_congeners(frame)
    pd.testing.assert_frame_equal(
        after[["Scientific_Triage_Status", "Overall_Score", "R&D_Opportunity_Score", "Go_Investigate_Hold_NoGo", "Decision_Class_AH"]].reset_index(drop=True),
        before.reset_index(drop=True),
    )
    assert "same-genus candidate" in after.loc[1, "Duplicate_Pruning_Note"]


def test_evidence_strength_index_is_direction_aware_not_unsigned_quality_only():
    # Same indication relevance; a supportive scientific contribution must yield
    # a higher support-strength index than null/negative (zero/negative) evidence.
    positive = cs._derive_evidence_confidence(30.0, 25.0)
    null = cs._derive_evidence_confidence(30.0, 0.0)
    negative = cs._derive_evidence_confidence(30.0, -4.0)
    assert positive > null
    assert null == negative


def _robustness_df(a_breakdown, b_breakdown):
    return pd.DataFrame([
        {
            "Reference_Plant": "Ref",
            "Reference_Compound": "Cmp",
            "Alternative_Plant": "A",
            "R&D_Opportunity_Score": sum(a_breakdown.values()),
            "Score_Breakdown": a_breakdown,
            "Eligible_For_Normal_Ranking": True,
        },
        {
            "Reference_Plant": "Ref",
            "Reference_Compound": "Cmp",
            "Alternative_Plant": "B",
            "R&D_Opportunity_Score": sum(b_breakdown.values()),
            "Score_Breakdown": b_breakdown,
            "Eligible_For_Normal_Ranking": True,
        },
    ])


def test_bounded_weight_robustness_reports_robust_dominant_winner():
    a = _full_breakdown()
    b = {k: v * 0.8 for k, v in a.items()}
    out = build_bounded_weight_robustness(_robustness_df(a, b))
    obj = out.iloc[0]
    assert obj["status"] == "available"
    assert obj["stability_level"] == "Robust"
    assert obj["winner_retention_fraction"] == 1.0
    assert obj["calibration_status"] == RANKING_CALIBRATION_STATUS
    assert "not a probability" in " ".join(obj["limitations"]).lower()


def test_bounded_weight_robustness_can_detect_real_weight_sensitive_rank():
    # A wins baseline through novelty; B has stronger scientific evidence.
    # +/-10% section-weight corners should flip at least one scenario.
    a = {
        "Indication Relevance": 14.0, "Scientific Evidence": 12.0,
        "Compound Support": 3.5, "Mechanism Support": 7.0,
        "Safety & Regulatory": 12.0, "Novelty & Market": 3.5,
    }
    b = {
        "Indication Relevance": 14.0, "Scientific Evidence": 15.0,
        "Compound Support": 3.5, "Mechanism Support": 4.0,
        "Safety & Regulatory": 12.0, "Novelty & Market": 3.0,
    }
    # make A the baseline winner by a small margin
    assert sum(a.values()) > sum(b.values())
    out = build_bounded_weight_robustness(_robustness_df(a, b))
    obj = out.iloc[0]
    assert obj["winner_changed_in_scenarios"] > 0
    assert obj["stability_level"] in {"Moderately robust", "Sensitive"}


def _expert_benchmark():
    pairs = []
    for i in range(5):
        a = _full_breakdown(**{"Scientific Evidence": 25.0, "Novelty & Market": 3.0 + 0.1 * i})
        b = _full_breakdown(**{"Scientific Evidence": 17.0, "Novelty & Market": 5.0})
        pairs.append({
            "pair_id": f"cal-{i}", "split": "calibration", "preferred": "A",
            "candidate_a": {"score_breakdown": a},
            "candidate_b": {"score_breakdown": b},
        })
    pairs.append({
        "pair_id": "hold-1", "split": "holdout", "preferred": "A",
        "candidate_a": {"score_breakdown": _full_breakdown(**{"Scientific Evidence": 26.0})},
        "candidate_b": {"score_breakdown": _full_breakdown(**{"Scientific Evidence": 15.0})},
    })
    return {
        "pairs": pairs,
        "threshold_cases": [
            {"case_id": "cal-t", "split": "calibration", "score_breakdown": _full_breakdown(**{"Scientific Evidence": 28.0}), "expert_priority": "STRONG_PRIORITY"},
            {"case_id": "hold-t", "split": "holdout", "score_breakdown": _full_breakdown(**{"Scientific Evidence": 10.0}), "expert_priority": "INVESTIGATE"},
        ],
    }


def test_calibration_harness_requires_real_labelled_cases_and_keeps_holdout_separate():
    benchmark = _expert_benchmark()
    ready = calibration_readiness(benchmark)
    assert ready["calibration_pairs"] == 5
    assert ready["holdout_pairs"] == 1

    proposal = search_candidate_configuration(benchmark, multipliers=(0.9, 1.0, 1.1), thresholds=(76, 78, 80))
    assert proposal.status == "CANDIDATE_CONFIGURATION_ONLY_NOT_PRODUCTION"
    report = evaluate_expert_benchmark(
        benchmark,
        weights=proposal.weights,
        strong_threshold=proposal.strong_threshold,
        split="holdout",
    )
    assert report["labelled_pairs"] == 1
    assert report["pairwise_agreement"] == 1.0


def test_calibration_search_refuses_too_few_expert_pairs():
    benchmark = _expert_benchmark()
    benchmark = copy.deepcopy(benchmark)
    benchmark["pairs"] = benchmark["pairs"][:4] + [benchmark["pairs"][-1]]
    with pytest.raises(CalibrationDataError):
        search_candidate_configuration(benchmark, multipliers=(1.0,), thresholds=(78,))
