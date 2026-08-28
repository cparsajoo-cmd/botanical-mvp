import unittest.mock as mock
import pandas as pd
import step_rd_candidates as src


def _row(plant, final, call="Investigate — verify preparation applicability", gate="passed_direct"):
    return {
        "Alternative_Plant": plant,
        "Overall_Score": 70.0,
        "R&D_Opportunity_Score": 70.0,
        "Go_Investigate_Hold_NoGo": call,
        "Final_Decision_Status": final,
        "Decision_Class_AH": "C — Alternative-source R&D candidate",
        "Eligibility_Status": "eligible" if not str(call).startswith(("Hold", "No-Go")) else "incomplete",
        "Eligible_For_Normal_Ranking": not str(call).startswith(("Hold", "No-Go")),
        "Relevance_Gate_Result": gate,
        "Indication_Relevance": "High relevance",
        "Evidence_Coherence_Status": "CONTRADICTION_HUMAN_CLASSIFICATION" if final == "EXPERT REVIEW REQUIRED" else "COHERENT",
    }


def test_expert_review_is_amber_not_weak_or_recommended():
    df = pd.DataFrame([
        _row("Priority plant", "GO WITH CAUTION"),
        _row("Unresolved plant", "EXPERT REVIEW REQUIRED"),
        _row("Weak plant", "INSUFFICIENT EVIDENCE", call="Hold"),
    ])
    with mock.patch.object(src, "st") as st:
        src._recommendation_block(pd.DataFrame(), df)

    frames = [c.args[0] for c in st.dataframe.call_args_list]
    assert len(frames) == 3
    priority, review, weak = frames
    assert "Priority plant" in set(priority["Alternative_Plant"])
    assert "Unresolved plant" in set(review["Alternative_Plant"])
    assert "Unresolved plant" not in set(priority["Alternative_Plant"])
    assert "Unresolved plant" not in set(weak["Alternative_Plant"])
    assert "Weak plant" in set(weak["Alternative_Plant"])
    assert set(review["Stage_6_Section"]) == {"Requires expert review — unresolved scientific decision"}


def test_exploratory_expert_review_is_not_duplicated_into_red_bucket():
    df = pd.DataFrame([
        _row(
            "Exploratory plant",
            "EXPERT REVIEW REQUIRED",
            call="Investigate — verify before proceeding",
            gate="passed_indirect_exploratory_only",
        )
    ])
    with mock.patch.object(src, "st") as st:
        src._recommendation_block(pd.DataFrame(), df)

    frames = [c.args[0] for c in st.dataframe.call_args_list]
    # With an authoritative final decision it belongs only to amber review.
    assert len(frames) == 2  # empty priority/exploratory table + amber review
    all_sections = pd.concat(frames, ignore_index=True)
    matches = all_sections[all_sections["Alternative_Plant"] == "Exploratory plant"]
    assert len(matches) == 1
    assert matches.iloc[0]["Stage_6_Section"] == "Requires expert review — unresolved scientific decision"
