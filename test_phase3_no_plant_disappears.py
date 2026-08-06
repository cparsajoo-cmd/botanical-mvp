"""End-to-end regression test, post-Phase-3-review correction:

    build_plant_candidate_shortlist() -> merge_authoritative_scores() -> _recommendation_block

must never lose a plant. Specifically proves:
  1. a shortlisted Go/Investigate plant appears as recommended;
  2. an exploratory "Investigate — verify before proceeding" plant appears
     as worth validating (not silently dropped by exact-match filtering);
  3. an excluded Hold/No-Go plant remains in the report-ready frame and
     appears under weak/not recommended (not deleted);
  4. that excluded plant's rejection reason is preserved end to end;
  5. no plant present in the shortlist is missing from the report-ready
     frame or from the recommendation block's displayed sections.
"""

import unittest.mock as mock
import pandas as pd

from candidate_shortlisting import build_plant_candidate_shortlist, merge_authoritative_scores
import step_rd_candidates as src


def _row(**overrides):
    row = {
        "Reference_Plant": "Reference plant",
        "Alternative_Plant": "Candidate plant",
        "Shared_or_Similar_Compound": "specific alkaloid",
        "Novelty_Status": "Rare / differentiating",
        "Target_or_Mechanism": "AMPK",
        "Target_Provenance": "Supported by source record",
        "Evidence_Level": "Clinical / human evidence",
        "Evidence_Hierarchy_Detail": "Human clinical evidence",
        "Candidate_Evidence_Strength_Tier": "Direct evidence",
        "Evidence_Source": "PubMed",
        "Source_Record_IDs": "PMID:123",
        "Applicability_Summary": '{"critical_mismatches":[],"evidence_items":[]}',
        "Safety_Flags": "No explicit flag found",
        "Interaction_Flags": "No explicit flag found",
        "Regulatory_Barriers": "None identified",
        "Decision_Class": "Promising candidate; verify safety and standardization",
        "Has_Negative_Evidence": False,
        "Negative_Evidence_Types": "",
        "R&D_Opportunity_Score": 70,
        # Phase 4 — Eligibility Gate. Default reflects a clean candidate
        # (matches the default Decision_Class above, which is not a
        # no-go/incomplete label) — overridden per-row below for the
        # excluded-plant scenario.
        "Eligibility_Status": "eligible",
        "Eligible_For_Normal_Ranking": True,
    }
    row.update(overrides)
    return row


def test_no_plant_disappears_between_shortlist_and_recommendation_block():
    indication = "Metabolic & blood sugar support"

    shortlist_row = _row(
        Alternative_Plant="Shortlisted plant",
        Scientific_Rationale="clinical evidence of reduced fasting glucose",
        Clinical_Rationale="human clinical trial reported improved HbA1c",
        Evidence_Level="Clinical / human evidence",
        Evidence_Hierarchy_Detail="Clinical trial",
        Source_Record_IDs="PMID:101",
    )
    exploratory_row = _row(
        Alternative_Plant="Exploratory plant",
        Target_or_Mechanism="AMPK activation",
        Scientific_Rationale="AMPK activation in a mechanistic assay",
        Evidence_Level="Preclinical / mechanistic evidence",
        Evidence_Hierarchy_Detail="In vitro evidence",
        Source_Record_IDs="PMID:102",
    )
    excluded_row = _row(
        Alternative_Plant="Excluded plant",
        Target_or_Mechanism="unrelated cosmetic astringent effect",
        Scientific_Rationale="skin tightening effect in a cosmetic assay",
        Applicability_Summary="",
        Source_Record_IDs="PMID:103",
    )

    raw_df = pd.DataFrame([shortlist_row, exploratory_row, excluded_row])

    # --- Step 1: shortlist -------------------------------------------------
    plant_summary, _audit = build_plant_candidate_shortlist(
        raw_df, indication=indication, dosage_form="Infusion",
    )
    statuses = dict(zip(plant_summary["Alternative_Plant"], plant_summary["Scientific_Triage_Status"]))
    assert statuses["Shortlisted plant"] == "Shortlist"
    assert statuses["Exploratory plant"] == "Exploratory"
    assert statuses["Excluded plant"] == "Excluded"
    excluded_reason = plant_summary.loc[
        plant_summary["Alternative_Plant"] == "Excluded plant", "Why_Selected_or_Rejected"
    ].iloc[0]
    assert excluded_reason  # a real, non-empty rejection explanation exists

    # --- Step 2: merge into the authoritative report-ready frame -----------
    report_ready_df = merge_authoritative_scores(raw_df, plant_summary)

    # (5) No plant present in the shortlist is missing from the merged frame.
    assert set(report_ready_df["Alternative_Plant"]) == {
        "Shortlisted plant", "Exploratory plant", "Excluded plant",
    }
    # (3) The excluded plant is present, not dropped.
    excluded_merged = report_ready_df[report_ready_df["Alternative_Plant"] == "Excluded plant"].iloc[0]
    assert excluded_merged["Scientific_Triage_Status"] == "Excluded"
    # (4) Its rejection reason survived the merge unchanged.
    assert excluded_merged["Why_Selected_or_Rejected"] == excluded_reason
    assert excluded_merged["Go_Investigate_Hold_NoGo"] in ("Hold", "No-Go")

    # --- Step 3: recommendation block --------------------------------------
    with mock.patch.object(src, "st") as mock_st:
        src._recommendation_block(raw_df, report_ready_df)

    dataframe_calls = [c.args[0] for c in mock_st.dataframe.call_args_list]
    assert len(dataframe_calls) == 2, "expected both a recommended and a weak section"
    recommended_frame, weak_frame = dataframe_calls

    # (1) The shortlisted Go/Investigate plant is recommended.
    assert "Shortlisted plant" in list(recommended_frame["Alternative_Plant"])
    # (2) The exploratory "Investigate — verify before proceeding" plant is
    # ALSO recommended/worth-validating — not lost to exact-match filtering.
    assert "Exploratory plant" in list(recommended_frame["Alternative_Plant"])
    # (3) The excluded plant appears under weak/not recommended, not nowhere.
    assert "Excluded plant" in list(weak_frame["Alternative_Plant"])
    assert "Excluded plant" not in list(recommended_frame["Alternative_Plant"])

    # (5, restated end to end) every plant shown across both sections
    # together equals every plant the shortlist produced.
    all_shown = set(recommended_frame["Alternative_Plant"]) | set(weak_frame["Alternative_Plant"])
    assert all_shown == {"Shortlisted plant", "Exploratory plant", "Excluded plant"}

    # (4, restated end to end) the rejection reason is still retrievable
    # from what's actually displayed in the weak section.
    if "Why_Selected_or_Rejected" in weak_frame.columns:
        shown_reason = weak_frame.loc[
            weak_frame["Alternative_Plant"] == "Excluded plant", "Why_Selected_or_Rejected"
        ].iloc[0]
        assert shown_reason == excluded_reason
