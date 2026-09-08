"""Tests for IMPLEMENTATION_PLAN.md Phase 3's rewiring of
step_rd_candidates.py's _recommendation_block(): it must use the
authoritative, one-row-per-plant report_ready_df (merge_authoritative_scores'
output) when available, instead of independently re-deriving a "best row
per plant" from raw result_df — the exact third divergent path this phase
closes."""

import unittest.mock as mock
import pandas as pd

import step_rd_candidates as src


def _report_ready_row(plant, call, score):
    # Phase 4 — Eligibility Gate compatibility: this test file predates
    # Phase 4's structured Eligibility_Status/Eligible_For_Normal_Ranking
    # columns, which _recommendation_block() now reads directly (see
    # step_rd_candidates.py's _eligible_mask()). Derived here from the
    # same `call` (Go/Investigate/Hold/No-Go) value these tests already
    # parametrize on, so eligibility agrees with what each test's plant
    # name/call combination already implies.
    is_eligible = str(call).strip().startswith(("Go", "Investigate"))
    return {
        "Alternative_Plant": plant,
        "R&D_Opportunity_Score": score,
        "Overall_Score": score,
        "Go_Investigate_Hold_NoGo": call,
        "Decision_Class_AH": (
            "B — Established scientific candidate" if is_eligible
            else "G — Hold / insufficient evidence"
        ),
        "Target_or_Mechanism": "AMPK",
        "Rationale": f"narrative for {plant}",
        "Eligibility_Status": "eligible" if is_eligible else "incomplete",
        "Eligible_For_Normal_Ranking": is_eligible,
    }


def test_uses_report_ready_df_when_available_not_raw_result_df():
    report_ready_df = pd.DataFrame([
        _report_ready_row("Strong plant", "Go", 90.0),
        _report_ready_row("Weak plant", "Hold", 20.0),
    ])
    # A raw result_df that would recommend a DIFFERENT plant if it were
    # used instead — proves the function actually prefers report_ready_df.
    result_df = pd.DataFrame([
        {"Alternative_Plant": "Decoy plant", "R&D_Opportunity_Score": 99,
         "Decision_Class": "Strong candidate"},
    ])

    with mock.patch.object(src, "st") as mock_st:
        src._recommendation_block(result_df, report_ready_df)

    dataframe_calls = [c for c in mock_st.dataframe.call_args_list]
    assert dataframe_calls, "expected st.dataframe to be called"
    recommended_frame = dataframe_calls[0].args[0]
    assert "Strong plant" in list(recommended_frame["Alternative_Plant"])
    assert "Decoy plant" not in list(recommended_frame["Alternative_Plant"])


def test_hold_and_nogo_plants_appear_in_the_weak_section_not_recommended():
    report_ready_df = pd.DataFrame([
        _report_ready_row("Strong plant", "Go", 90.0),
        _report_ready_row("Weak plant", "Hold", 20.0),
    ])
    with mock.patch.object(src, "st") as mock_st:
        src._recommendation_block(pd.DataFrame(), report_ready_df)

    dataframe_calls = [c.args[0] for c in mock_st.dataframe.call_args_list]
    assert len(dataframe_calls) == 2
    recommended_frame, weak_frame = dataframe_calls
    assert "Weak plant" not in list(recommended_frame["Alternative_Plant"])
    assert "Weak plant" in list(weak_frame["Alternative_Plant"])


def test_falls_back_to_legacy_behavior_when_no_report_ready_df():
    # Backward compatibility: a session that ran Step 5 before this change
    # has no report_ready_df yet — must not crash, must fall back cleanly.
    result_df = pd.DataFrame([
        {"Alternative_Plant": "Plant A", "R&D_Opportunity_Score": 80,
         "Decision_Class": "Strong candidate"},
    ])
    with mock.patch.object(src, "st") as mock_st:
        src._recommendation_block(result_df, None)
    assert mock_st.dataframe.called


def test_no_data_at_all_shows_a_warning_not_a_crash():
    with mock.patch.object(src, "st") as mock_st:
        src._recommendation_block(None, None)
    assert mock_st.warning.called


# --- Post-Phase-3-review correction (Issue 1) -----------------------------
# "Investigate — verify before proceeding" (the exact Exploratory call —
# see candidate_shortlisting._derive_go_call) starts with "Investigate" but
# is not equal to the bare string "Investigate". An exact .isin() match
# silently dropped every exploratory candidate from BOTH the recommended
# and the weak section. These tests prove every Investigate-prefixed call
# is classified as recommended/worth-validating and never disappears.

def test_investigate_verify_before_proceeding_appears_in_recommended_section():
    report_ready_df = pd.DataFrame([
        _report_ready_row("Exploratory plant", "Investigate — verify before proceeding", 55.0),
    ])
    with mock.patch.object(src, "st") as mock_st:
        src._recommendation_block(pd.DataFrame(), report_ready_df)

    dataframe_calls = [c.args[0] for c in mock_st.dataframe.call_args_list]
    recommended_frame = dataframe_calls[0]
    assert "Exploratory plant" in list(recommended_frame["Alternative_Plant"])


def test_investigate_verify_before_proceeding_never_appears_in_weak_section():
    report_ready_df = pd.DataFrame([
        _report_ready_row("Exploratory plant", "Investigate — verify before proceeding", 55.0),
        _report_ready_row("Rejected plant", "No-Go", 10.0),
    ])
    with mock.patch.object(src, "st") as mock_st:
        src._recommendation_block(pd.DataFrame(), report_ready_df)

    dataframe_calls = [c.args[0] for c in mock_st.dataframe.call_args_list]
    assert len(dataframe_calls) == 2
    _recommended_frame, weak_frame = dataframe_calls
    assert "Exploratory plant" not in list(weak_frame["Alternative_Plant"])
    assert "Rejected plant" in list(weak_frame["Alternative_Plant"])


def test_all_go_investigate_variants_are_present_somewhere_none_vanish():
    # Every plant fed in must appear in exactly one of the two sections —
    # never silently disappear because its exact call string wasn't in a
    # hardcoded exact-match list.
    report_ready_df = pd.DataFrame([
        _report_ready_row("Go plant", "Go", 95.0),
        _report_ready_row("Plain investigate plant", "Investigate", 70.0),
        _report_ready_row("Verify plant", "Investigate — verify before proceeding", 55.0),
        _report_ready_row("Hold plant", "Hold", 30.0),
        _report_ready_row("No-go plant", "No-Go", 5.0),
    ])
    with mock.patch.object(src, "st") as mock_st:
        src._recommendation_block(pd.DataFrame(), report_ready_df)

    dataframe_calls = [c.args[0] for c in mock_st.dataframe.call_args_list]
    all_shown_plants = set()
    for frame in dataframe_calls:
        all_shown_plants.update(frame["Alternative_Plant"])
    assert all_shown_plants == {
        "Go plant", "Plain investigate plant", "Verify plant", "Hold plant", "No-go plant",
    }


# --- RD Discovery Hypotheses section (external review, 2026-09-08) -------
# candidate_shortlisting.build_rd_discovery_hypothesis_view() is called
# inside _recommendation_block() to give discovery-hypothesis candidates a
# third, positively-framed section, ranked by Discovery_Potential_Score,
# instead of leaving them undifferentiated inside "Weak / not recommended".

def _discovery_report_ready_row(plant, lane, discovery_potential, call="Hold"):
    row = _report_ready_row(plant, call, 20.0)
    row["RD_Discovery_Lane"] = lane
    row["Discovery_Potential_Score"] = discovery_potential
    row["Evidence_Maturity_Score"] = 10.0
    return row


def test_discovery_hypothesis_section_renders_as_a_third_table():
    report_ready_df = pd.DataFrame([
        _report_ready_row("Strong plant", "Go", 90.0),
        _discovery_report_ready_row("Hypothesis plant", "R&D Discovery Hypothesis", 70.0),
    ])
    with mock.patch.object(src, "st") as mock_st:
        src._recommendation_block(pd.DataFrame(), report_ready_df)

    dataframe_calls = [c.args[0] for c in mock_st.dataframe.call_args_list]
    assert len(dataframe_calls) == 3
    _recommended, _weak, discovery_frame = dataframe_calls
    assert "Hypothesis plant" in list(discovery_frame["Alternative_Plant"])


def test_discovery_hypothesis_section_absent_when_no_lane_data():
    # No RD_Discovery_Lane column at all -- must not add a third, empty
    # section (matches the pre-existing two-section tests above).
    report_ready_df = pd.DataFrame([
        _report_ready_row("Strong plant", "Go", 90.0),
        _report_ready_row("Weak plant", "Hold", 20.0),
    ])
    with mock.patch.object(src, "st") as mock_st:
        src._recommendation_block(pd.DataFrame(), report_ready_df)

    dataframe_calls = [c.args[0] for c in mock_st.dataframe.call_args_list]
    assert len(dataframe_calls) == 2


def test_discovery_hypothesis_section_ranks_by_discovery_potential():
    report_ready_df = pd.DataFrame([
        _report_ready_row("Strong plant", "Go", 90.0),
        _discovery_report_ready_row("Weak hypothesis", "R&D Discovery Hypothesis", 40.0),
        _discovery_report_ready_row("Strong hypothesis", "R&D Discovery Hypothesis", 85.0),
    ])
    with mock.patch.object(src, "st") as mock_st:
        src._recommendation_block(pd.DataFrame(), report_ready_df)

    dataframe_calls = [c.args[0] for c in mock_st.dataframe.call_args_list]
    discovery_frame = dataframe_calls[-1]
    assert list(discovery_frame["Alternative_Plant"]) == [
        "Strong hypothesis", "Weak hypothesis",
    ]


def test_regulatory_prohibition_never_appears_in_discovery_section():
    report_ready_df = pd.DataFrame([
        _report_ready_row("Strong plant", "Go", 90.0),
        _discovery_report_ready_row("Banned plant", "Regulatory Prohibition", 95.0, call="No-Go"),
    ])
    with mock.patch.object(src, "st") as mock_st:
        src._recommendation_block(pd.DataFrame(), report_ready_df)

    dataframe_calls = [c.args[0] for c in mock_st.dataframe.call_args_list]
    # Only recommended + weak -- the high Discovery_Potential_Score on the
    # banned plant must not earn it a discovery-section appearance.
    assert len(dataframe_calls) == 2
    _recommended, weak_frame = dataframe_calls
    assert "Banned plant" in list(weak_frame["Alternative_Plant"])


def test_safety_hard_stop_candidate_now_appears_in_discovery_section():
    # External review, second pass (2026-09-08): a genuine safety
    # hard-stop can still be a legitimate pharmacological R&D question --
    # the row must be SHOWN in the discovery section (clearly labelled),
    # not hidden from it entirely as before.
    report_ready_df = pd.DataFrame([
        _report_ready_row("Strong plant", "Go", 90.0),
        _discovery_report_ready_row(
            "Toxic-but-interesting plant",
            "Not Currently Developable (Safety)", 88.0, call="No-Go",
        ),
    ])
    with mock.patch.object(src, "st") as mock_st:
        src._recommendation_block(pd.DataFrame(), report_ready_df)

    dataframe_calls = [c.args[0] for c in mock_st.dataframe.call_args_list]
    assert len(dataframe_calls) == 3
    _recommended, _weak, discovery_frame = dataframe_calls
    assert "Toxic-but-interesting plant" in list(discovery_frame["Alternative_Plant"])
    shown_row = discovery_frame[
        discovery_frame["Alternative_Plant"] == "Toxic-but-interesting plant"
    ].iloc[0]
    assert shown_row["RD_Discovery_Lane"] == "Not Currently Developable (Safety)"
