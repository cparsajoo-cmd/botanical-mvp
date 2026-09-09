"""Root-cause regression tests: Stage-5 R&D discovery hypotheses were never
selected for commercial enrichment.

WHAT WAS WRONG
_step5_commercial_enrichment_plants() (step_rd_candidates.py) first dropped
every row with Scientific_Triage_Status == "Excluded", then kept only
plants within a small margin of the top-50 Overall_Score boundary. Stage-5
R&D discovery hypotheses (RD_Discovery_Lane ==
DISCOVERY_LANE_HYPOTHESIS / DISCOVERY_LANE_CATALOGUE_HYPOTHESIS) are, by
construction (rd_discovery_classification.py), typically
Scientific_Triage_Status == "Excluded" or "Exploratory" with a low
Overall_Score -- their entire premise is "scientifically interesting
despite little or no direct evidence today". They were therefore dropped
by the first filter, or excluded by the score window, before ever being
considered for commercial enrichment. Stage 6 then showed these candidates
with the neutral "Search not performed" / "Commercial novelty not
assessed" defaults forever -- which is indistinguishable, to an investor,
from "we searched and found nothing" (Commercial White Space).

THE FIX
_step5_commercial_enrichment_plants() now has a second, additive selection
path: any plant whose RD_Discovery_Lane is DISCOVERY_LANE_HYPOTHESIS or
DISCOVERY_LANE_CATALOGUE_HYPOTHESIS is included regardless of
Scientific_Triage_Status or Overall_Score, bounded by its own small budget
(_STEP5_COMMERCIAL_DISCOVERY_LANE_MAX_PLANTS) so a large discovery set
still can't trigger unbounded commercial lookups. The pre-existing
score-window path is untouched.
"""

import pandas as pd

import step_rd_candidates as src
from rd_discovery_classification import (
    DISCOVERY_LANE_HYPOTHESIS,
    DISCOVERY_LANE_CATALOGUE_HYPOTHESIS,
    DISCOVERY_LANE_EVIDENCE_BACKED,
    DISCOVERY_LANE_INSUFFICIENT,
)


def _base_row(**overrides):
    row = {
        "Alternative_Plant": "Placeholder plant",
        "Scientific_Triage_Status": "Excluded",
        "Overall_Score": 0.0,
        "RD_Discovery_Lane": DISCOVERY_LANE_INSUFFICIENT,
    }
    row.update(overrides)
    return row


def test_discovery_hypothesis_lane_is_selected_despite_excluded_status_and_low_score():
    """The exact bug scenario: an Excluded, near-zero-score plant that is
    nonetheless a Stage-5 mechanistic R&D hypothesis must still be selected
    for commercial enrichment.
    """
    df = pd.DataFrame([
        _base_row(
            Alternative_Plant="Obscura testii",
            Scientific_Triage_Status="Excluded",
            Overall_Score=6.0,
            RD_Discovery_Lane=DISCOVERY_LANE_HYPOTHESIS,
        ),
    ])
    plants = src._step5_commercial_enrichment_plants(df)
    assert "Obscura testii" in plants


def test_catalogue_hypothesis_lane_is_selected_despite_exploratory_status_and_low_score():
    df = pd.DataFrame([
        _base_row(
            Alternative_Plant="Catalogue plant",
            Scientific_Triage_Status="Exploratory",
            Overall_Score=14.0,
            RD_Discovery_Lane=DISCOVERY_LANE_CATALOGUE_HYPOTHESIS,
        ),
    ])
    plants = src._step5_commercial_enrichment_plants(df)
    assert "Catalogue plant" in plants


def test_non_discovery_low_score_excluded_plant_is_still_not_selected():
    """Guard against over-correction: a plant that is simply weak (not a
    discovery hypothesis) must still be excluded, exactly as before.
    """
    df = pd.DataFrame([
        _base_row(
            Alternative_Plant="Weak plant",
            Scientific_Triage_Status="Excluded",
            Overall_Score=2.0,
            RD_Discovery_Lane=DISCOVERY_LANE_INSUFFICIENT,
        ),
    ])
    plants = src._step5_commercial_enrichment_plants(df)
    assert "Weak plant" not in plants


def test_score_window_path_is_unchanged_for_evidence_backed_candidates():
    """Non-regression: ordinary evidence-backed, high-scoring candidates
    still get selected via the pre-existing score-window path.
    """
    rows = []
    for i in range(60):
        rows.append(_base_row(
            Alternative_Plant=f"Strong plant {i}",
            Scientific_Triage_Status="Shortlist",
            Overall_Score=100.0 - i,
            RD_Discovery_Lane=DISCOVERY_LANE_EVIDENCE_BACKED,
        ))
    df = pd.DataFrame(rows)
    plants = src._step5_commercial_enrichment_plants(df)
    assert "Strong plant 0" in plants
    assert "Strong plant 49" in plants


def test_discovery_lane_plants_are_merged_without_duplicates():
    """A plant that qualifies via BOTH paths (e.g. a hypothesis that also
    happens to score well) must appear only once in the returned list.
    """
    df = pd.DataFrame([
        _base_row(
            Alternative_Plant="Dual path plant",
            Scientific_Triage_Status="Exploratory",
            Overall_Score=90.0,
            RD_Discovery_Lane=DISCOVERY_LANE_HYPOTHESIS,
        ),
    ])
    plants = src._step5_commercial_enrichment_plants(df)
    assert plants.count("Dual path plant") == 1


def test_discovery_lane_budget_is_bounded():
    """The additive discovery-lane path must not allow unbounded cost --
    it is capped independently of the score-window budget.
    """
    rows = [
        _base_row(
            Alternative_Plant=f"Hypothesis plant {i}",
            Scientific_Triage_Status="Excluded",
            Overall_Score=1.0,
            RD_Discovery_Lane=DISCOVERY_LANE_HYPOTHESIS,
        )
        for i in range(500)
    ]
    df = pd.DataFrame(rows)
    plants = src._step5_commercial_enrichment_plants(df)
    assert len(plants) <= src._STEP5_COMMERCIAL_DISCOVERY_LANE_MAX_PLANTS


def test_missing_rd_discovery_lane_column_does_not_break_selector():
    """Backward compatibility: a plant_summary_df built by an older code
    path without RD_Discovery_Lane must fall back to score-window-only
    behavior, not raise.
    """
    df = pd.DataFrame([
        {
            "Alternative_Plant": "Legacy plant",
            "Scientific_Triage_Status": "Shortlist",
            "Overall_Score": 80.0,
        },
    ])
    plants = src._step5_commercial_enrichment_plants(df)
    assert "Legacy plant" in plants


def test_empty_and_none_inputs_return_empty_list():
    assert src._step5_commercial_enrichment_plants(pd.DataFrame()) == []
    assert src._step5_commercial_enrichment_plants(None) == []
