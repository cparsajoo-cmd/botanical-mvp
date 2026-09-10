"""Mandatory regression test (corrective source-traceability pass, gap 3 /
spec §8): a test that merely checks source columns exist in st.dataframe()
is explicitly NOT sufficient. This proves the real production Stage-6 path
(_recommendation_block -> _render_stage6_reference_detail_section) actually
calls render_candidate_reference_detail() for a selected candidate, for
all three sections: Priority, Expert Review, and R&D Discovery.
"""
import unittest.mock as mock

import pandas as pd

import step_rd_candidates as src


def _report_ready_row(plant, call, score, **extra):
    is_eligible = str(call).strip().startswith(("Go", "Investigate"))
    row = {
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
    row.update(extra)
    return row


def test_priority_section_actually_invokes_the_universal_renderer():
    report_ready_df = pd.DataFrame([
        _report_ready_row("Strong plant", "Go", 90.0),
    ])
    with mock.patch.object(src, "st") as mock_st, \
         mock.patch.object(src, "render_candidate_reference_detail") as mock_render:
        mock_st.selectbox.return_value = "Strong plant"
        src._recommendation_block(pd.DataFrame(), report_ready_df)

    assert mock_render.called, "render_candidate_reference_detail was never invoked for Priority"
    called_row = mock_render.call_args_list[0].args[0]
    assert called_row.get("Alternative_Plant") == "Strong plant"


def test_expert_review_section_actually_invokes_the_universal_renderer():
    report_ready_df = pd.DataFrame([
        _report_ready_row(
            "Unresolved plant", "Investigate", 70.0,
            Final_Decision_Status="EXPERT REVIEW REQUIRED",
        ),
    ])
    with mock.patch.object(src, "st") as mock_st, \
         mock.patch.object(src, "render_candidate_reference_detail") as mock_render:
        mock_st.selectbox.return_value = "Unresolved plant"
        src._recommendation_block(pd.DataFrame(), report_ready_df)

    assert mock_render.called, "render_candidate_reference_detail was never invoked for Expert Review"
    plants_rendered = {c.args[0].get("Alternative_Plant") for c in mock_render.call_args_list}
    assert "Unresolved plant" in plants_rendered


def test_discovery_section_actually_invokes_the_universal_renderer():
    report_ready_df = pd.DataFrame([
        _report_ready_row(
            "Discovery plant", "Hold", 20.0,
            RD_Discovery_Lane="R&D Discovery Hypothesis",
            Discovery_Potential_Score=60.0,
            Evidence_Maturity_Score=10.0,
            # has_defensible_admission() requires structured provenance --
            # a linked target is the simplest way to satisfy it.
            Discovery_Linked_Targets="GABA-A receptor",
            Discovery_Linked_Target_Count=1,
        ),
    ])
    with mock.patch.object(src, "st") as mock_st, \
         mock.patch.object(src, "render_candidate_reference_detail") as mock_render:
        mock_st.selectbox.return_value = "Discovery plant"
        src._recommendation_block(pd.DataFrame(), report_ready_df)

    assert mock_render.called, "render_candidate_reference_detail was never invoked for R&D Discovery"


def test_no_selection_made_does_not_call_the_renderer_and_does_not_crash():
    """A fully-mocked st.selectbox() returning a non-string (the default
    MagicMock behavior when a test doesn't emulate widget selection) must
    not crash and must not call the renderer with a bogus row."""
    report_ready_df = pd.DataFrame([_report_ready_row("Strong plant", "Go", 90.0)])
    with mock.patch.object(src, "st") as mock_st, \
         mock.patch.object(src, "render_candidate_reference_detail") as mock_render:
        src._recommendation_block(pd.DataFrame(), report_ready_df)

    mock_render.assert_not_called()


def test_old_human_only_detail_function_is_retired():
    """No two conflicting detail systems left behind."""
    assert not hasattr(src, "_render_human_evidence_source_details")
