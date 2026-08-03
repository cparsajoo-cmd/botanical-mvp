"""Tests for including Relevance_Score in the weighted global ranking score.

Covers:
a. an exact indication match outranks a token-overlap candidate when their
   other scores are equal;
b. relevance does not allow mechanism-only candidates to pass the
   eligibility gate;
c. the weighted components sum to exactly 1.0.

No live API calls are made -- GLOBAL_PLANT_CANDIDATES is monkeypatched with
small synthetic fixtures for (a) and (b).
"""
import pytest

import global_candidate_ranking_engine as gcre


def _make_candidate(name, indications, known_targets=("target A",)):
    """Two candidates built with this helper differ ONLY in whatever is
    passed explicitly (Indications / Known_Targets) -- every other scored
    input (compounds, extraction method, EMA status, research priority,
    region) is identical, so any difference in Global_Ranking_Score must
    come from the differing field(s).
    """
    return {
        "Scientific_Name": name,
        "Common_Name": name,
        "Region": "Europe",
        "Indications": list(indications),
        "Known_Active_Compounds": ["compound A", "compound B"],
        "Known_Targets": list(known_targets),
        "Plant_Part": "Leaf",
        "Extraction_Method": "Hydroalcoholic extract",
        "EMA_Status": "Yes",
        "Research_Priority": "Medium",
    }


# ---------------------------------------------------------------------
# c. weighted components sum to exactly 1.0
# ---------------------------------------------------------------------

def test_ranking_weights_sum_to_one():
    assert sum(gcre.RANKING_WEIGHTS.values()) == pytest.approx(1.0)


def test_relevance_weight_is_moderate_10_to_15_percent():
    assert 0.10 <= gcre.RANKING_WEIGHTS["Relevance_Score"] <= 0.15


def test_relevance_weight_added_without_dominating_clinical_evidence():
    # Relevance informs ranking; it must not outweigh direct clinical
    # evidence, which remains the largest single weighted component.
    assert gcre.RANKING_WEIGHTS["Clinical_Score"] >= gcre.RANKING_WEIGHTS["Relevance_Score"]
    assert gcre.RANKING_WEIGHTS["Clinical_Score"] == max(gcre.RANKING_WEIGHTS.values())


# ---------------------------------------------------------------------
# a. exact indication relevance outranks weak token-overlap relevance when
#    remaining candidate characteristics are comparable
# ---------------------------------------------------------------------

def test_exact_relevance_outranks_token_overlap_when_other_scores_equal(monkeypatch):
    exact = _make_candidate("Exact Plant", ["Sleep and relaxation"])
    weak = _make_candidate("Weak Plant", ["general vitality and sleep support"])
    monkeypatch.setattr(gcre, "GLOBAL_PLANT_CANDIDATES", [exact, weak])

    df = gcre.rank_global_candidates(
        indication="Sleep and relaxation",
        dosage_form="Infusion",
        market="European Union",
        target_count=10,
    )

    assert set(df["Scientific_Name"]) == {"Exact Plant", "Weak Plant"}
    exact_row = df[df["Scientific_Name"] == "Exact Plant"].iloc[0]
    weak_row = df[df["Scientific_Name"] == "Weak Plant"].iloc[0]

    # Sanity check: every other scored input was identical by construction.
    for column in (
        "Clinical_Score", "Chemistry_Score", "Active_Compound_Score",
        "Target_Score", "Extraction_Score", "Regulatory_Score",
        "Safety_Score", "Novelty_Score", "Market_Score", "Commercial_Score",
    ):
        assert exact_row[column] == weak_row[column]

    assert exact_row["Relevance_Score"] > weak_row["Relevance_Score"]
    assert exact_row["Global_Ranking_Score"] > weak_row["Global_Ranking_Score"]
    # The exact match must sort first.
    assert df.iloc[0]["Scientific_Name"] == "Exact Plant"


def test_final_weighted_score_reflects_relevance_difference_directly():
    base_row = {
        "Clinical_Score": 60, "Chemistry_Score": 60, "Active_Compound_Score": 60,
        "Target_Score": 60, "Extraction_Score": 60, "Regulatory_Score": 60,
        "Safety_Score": 60, "Novelty_Score": 60, "Market_Score": 60, "Commercial_Score": 60,
    }
    high_relevance = dict(base_row, Relevance_Score=100)
    low_relevance = dict(base_row, Relevance_Score=40)
    assert gcre._final_weighted_score(high_relevance) > gcre._final_weighted_score(low_relevance)
    # The gap must correspond to the configured 12% weight, not swamp or
    # vanish relative to the other 88% of comparable-quality components.
    gap = gcre._final_weighted_score(high_relevance) - gcre._final_weighted_score(low_relevance)
    expected_gap = round((100 - 40) * gcre.RANKING_WEIGHTS["Relevance_Score"], 1)
    assert gap == pytest.approx(expected_gap, abs=0.1)


def test_final_weighted_score_backward_compatible_without_relevance_column():
    # A row/caller that predates the Relevance_Score column must not crash;
    # missing relevance simply contributes 0.
    row = {
        "Clinical_Score": 50, "Chemistry_Score": 50, "Active_Compound_Score": 50,
        "Target_Score": 50, "Extraction_Score": 50, "Regulatory_Score": 50,
        "Safety_Score": 50, "Novelty_Score": 50, "Market_Score": 50, "Commercial_Score": 50,
    }
    score = gcre._final_weighted_score(row)
    assert score == pytest.approx(50 * (1.0 - gcre.RANKING_WEIGHTS["Relevance_Score"]), abs=0.1)


# ---------------------------------------------------------------------
# b. mechanism-only similarity must still not pass the eligibility gate
# ---------------------------------------------------------------------

def test_mechanism_only_candidate_does_not_pass_eligibility_gate(monkeypatch):
    # Indications is entirely unrelated to the query; only Known_Targets
    # happens to mention a mechanism ("GABA-A receptor") that overlaps the
    # Sleep therapeutic area's mechanism vocabulary. Mechanism similarity
    # alone must never satisfy the eligibility gate, so this candidate must
    # not appear in the ranked results at all.
    mechanism_only = _make_candidate(
        "Mechanism Only Plant",
        ["Unrelated topic entirely"],
        known_targets=["GABA-A receptor", "adenosine system"],
    )
    monkeypatch.setattr(gcre, "GLOBAL_PLANT_CANDIDATES", [mechanism_only])

    df = gcre.rank_global_candidates(
        indication="Sleep and relaxation",
        dosage_form="Infusion",
        market="European Union",
        target_count=10,
    )
    assert df.empty


def test_matches_indication_wrapper_still_boolean_and_excludes_mechanism_only():
    mechanism_only = _make_candidate(
        "Mechanism Only Plant",
        ["Unrelated topic entirely"],
        known_targets=["GABA-A receptor"],
    )
    assert gcre._matches_indication(mechanism_only, "Sleep and relaxation") is False
