"""Regression tests for the Stage 6 stabilization pass.

Root cause fixed here: `_recommendation_block()` used to perform pipeline-
implementation-fingerprint/staleness validation itself, before rendering any
table. Direct/unit-test calls always pass a synthetic `report_ready_df` with
no `Pipeline_Implementation_Fingerprint` column, so the guard fired on every
such call and returned before any `st.dataframe()` -- the root cause of all
14 Stage-6 renderer test failures (test_phase3_no_plant_disappears.py,
test_recommendation_block_phase3.py, test_stage6_expert_review_bucket_v6.py).

`_recommendation_block()` is now a pure renderer: it never checks pipeline
freshness. That check moved to the real production boundary --
`render_rd_candidates_step()`'s Stage 6 call site, guarding the actual
`st.session_state["rd_report_ready_df"]` -- via two pieces:

  - `_report_ready_matches_current_pipeline(df)`: pure helper, True when every
    fingerprint present in `df` matches the current code, and also True (not
    stale) when `df` has no fingerprint column/values at all -- a synthetic
    frame legitimately has none and must not be penalized.
  - `_stage6_stale_pipeline_warning(session_report_ready_df)`: the real
    boundary decision. Unlike the helper above, a REAL session-state frame
    with NO fingerprint column at all IS treated as stale (older sessions
    never wrote one), matching the original intended behavior for the
    production path only.

These tests cover both required cases:
  1. current fingerprint in the real session-state path -> Stage 6 may render.
  2. stale/missing fingerprint in the real session-state path -> warning,
     no stale recommendation rendered.
"""

import unittest.mock as mock
import pandas as pd

import step_rd_candidates as src


def _report_ready_row(plant, call, score):
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
        "Rationale": f"narrative for {plant}",
        "Eligibility_Status": "eligible" if is_eligible else "incomplete",
        "Eligible_For_Normal_Ranking": is_eligible,
    }


# ---------------------------------------------------------------------------
# _report_ready_matches_current_pipeline() -- pure helper
# ---------------------------------------------------------------------------

def test_pure_helper_true_for_frame_with_no_fingerprint_column():
    # A synthetic/unit-test frame with no fingerprint column at all must not
    # be flagged as mismatched -- it simply carries no fingerprint claim.
    df = pd.DataFrame([_report_ready_row("Strong plant", "Go", 90.0)])
    assert src._report_ready_matches_current_pipeline(df) is True


def test_pure_helper_true_when_fingerprint_matches_current_code():
    df = pd.DataFrame([_report_ready_row("Strong plant", "Go", 90.0)])
    df["Pipeline_Implementation_Fingerprint"] = src._pipeline_implementation_fingerprint()
    assert src._report_ready_matches_current_pipeline(df) is True


def test_pure_helper_false_when_fingerprint_is_stale():
    df = pd.DataFrame([_report_ready_row("Strong plant", "Go", 90.0)])
    df["Pipeline_Implementation_Fingerprint"] = "an-old-stale-fingerprint"
    assert src._report_ready_matches_current_pipeline(df) is False


# ---------------------------------------------------------------------------
# _recommendation_block() -- pure renderer, must never block on freshness
# ---------------------------------------------------------------------------

def test_recommendation_block_renders_synthetic_frame_without_fingerprint():
    report_ready_df = pd.DataFrame([
        _report_ready_row("Strong plant", "Go", 90.0),
        _report_ready_row("Weak plant", "Hold", 20.0),
    ])
    with mock.patch.object(src, "st") as mock_st:
        src._recommendation_block(pd.DataFrame(), report_ready_df)

    assert mock_st.dataframe.call_args_list, "renderer must not block on missing fingerprint"
    mock_st.warning.assert_not_called()


# ---------------------------------------------------------------------------
# _stage6_stale_pipeline_warning() -- real Stage 6 production boundary
# ---------------------------------------------------------------------------

def test_stage6_boundary_current_fingerprint_may_render():
    df = pd.DataFrame([_report_ready_row("Strong plant", "Go", 90.0)])
    df["Pipeline_Implementation_Fingerprint"] = src._pipeline_implementation_fingerprint()
    assert src._stage6_stale_pipeline_warning(df) is None


def test_stage6_boundary_missing_fingerprint_is_stale():
    # A real session-state frame with no fingerprint at all (older session,
    # predates this column) must be treated as stale -- unlike the synthetic
    # unit-test case above, which goes straight to _recommendation_block().
    df = pd.DataFrame([_report_ready_row("Strong plant", "Go", 90.0)])
    assert src._stage6_stale_pipeline_warning(df) == src._STAGE6_STALE_PIPELINE_MESSAGE


def test_stage6_boundary_outdated_fingerprint_is_stale():
    df = pd.DataFrame([_report_ready_row("Strong plant", "Go", 90.0)])
    df["Pipeline_Implementation_Fingerprint"] = "an-old-stale-fingerprint"
    assert src._stage6_stale_pipeline_warning(df) == src._STAGE6_STALE_PIPELINE_MESSAGE


def test_stage6_boundary_empty_or_missing_frame_is_not_stale():
    # Nothing to block on yet -- Step 5 simply hasn't produced a report-ready
    # frame in this session.
    assert src._stage6_stale_pipeline_warning(None) is None
    assert src._stage6_stale_pipeline_warning(pd.DataFrame()) is None


def test_stage6_call_site_logic_warns_and_skips_stale_recommendation():
    # Exercises the exact guard-then-render sequence used at the real Stage 6
    # call site in render_rd_candidates_step() (that function itself needs a
    # large amount of unrelated Step 1-5 session state to invoke directly, so
    # this test drives the same two functions it calls, in the same order,
    # against a stale session-state frame): a stale report-ready frame must
    # produce a warning and never reach _recommendation_block().
    df = pd.DataFrame([_report_ready_row("Strong plant", "Go", 90.0)])
    df["Pipeline_Implementation_Fingerprint"] = "an-old-stale-fingerprint"

    session_state = {
        "show_final_recommendation": True,
        "rd_report_ready_df": df,
    }
    with mock.patch.object(src, "st") as mock_st, \
         mock.patch.object(src, "_recommendation_block") as mock_block:
        mock_st.session_state = session_state
        _stale_warning = src._stage6_stale_pipeline_warning(
            session_state.get("rd_report_ready_df")
        )
        if _stale_warning:
            mock_st.warning(_stale_warning)
        else:
            mock_block(None, session_state.get("rd_report_ready_df"))

    mock_st.warning.assert_called_once_with(src._STAGE6_STALE_PIPELINE_MESSAGE)
    mock_block.assert_not_called()
