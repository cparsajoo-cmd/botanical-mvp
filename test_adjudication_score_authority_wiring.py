"""Regression coverage for the B2 ("ghost final score") and B12
(explicit UNKNOWN defaults) fixes applied to
step_rd_candidates._run_evidence_adjudication.

WHY THESE TESTS EXIST
A prior audit found that Final_R&D_Opportunity_Score was computed by
evidence_adjudication_engine.compute_deterministic_adjustments() but
never written back into plant_summary_df["Overall_Score"] -- so
Overall_Score (and therefore R&D_Opportunity_Score, the Streamlit
shortlist/exploratory tables, which read plant_summary_df directly, and
the merged report-ready frame) kept ranking/displaying the
PRE-adjudication score, while Final_R&D_Opportunity_Score sat unused as
a column nobody actually read. These tests pin the fix: Overall_Score
must equal Final_R&D_Opportunity_Score after adjudication runs, for
both adjudicated and non-adjudicated rows, and non-adjudicated
categorical fields must be explicit "UNKNOWN", not None.
"""
import pandas as pd

import step_rd_candidates as src


def _plant_summary(rows):
    return pd.DataFrame(rows)


def test_overall_score_is_overwritten_by_final_adjudicated_score(monkeypatch):
    # Adjudication still runs and still characterizes the evidence
    # (MODERATE negative severity, MODERATE human strength) -- but this
    # session's correction means that characterization no longer
    # subtracts a second, arbitrary numerical penalty from the score
    # (the deterministic scientific score already represents negative
    # evidence upstream -- see evidence_adjudication_engine.
    # compute_deterministic_adjustments' docstring). So
    # Final_R&D_Opportunity_Score/Overall_Score must equal the base
    # score unchanged, even though adjudication found negative evidence.
    def _fake_adjudicate_candidate(plant, indication, evidence_df, **kwargs):
        return {
            "Indication_Evidence_Direction": "MOSTLY_NEGATIVE",
            "Human_Evidence_Strength": "MODERATE",
            "Evidence_Conflict_Level": "LOW",
            "Negative_Evidence_Severity": "MODERATE",
            "Scientific_Evidence_Confidence": "MODERATE",
            "Preparation_Compatibility": "DIRECT",
            "Plant_Part_Compatibility": "DIRECT",
            "Route_Compatibility": "DIRECT",
            "Positive_Evidence_IDs": [], "Negative_Evidence_IDs": ["E1"],
            "Key_Human_Evidence_IDs": ["E1"], "Preparation_Mismatch_Evidence_IDs": [],
            "Evidence_Adjudication_Status": "AI_ADJUDICATION_OK",
            "Evidence_Adjudication_Fallback_Reason": None,
            "Evidence_Adjudication_Evidence_Count": 1,
            "Evidence_Adjudication_Rationale": "Moderate human evidence mostly does not support.",
        }

    monkeypatch.setattr(src, "adjudicate_candidate", _fake_adjudicate_candidate)

    plant_summary_df = _plant_summary([
        {
            "Alternative_Plant": "Plant A", "Overall_Score": 60.0,
            "Scientific_Triage_Status": "Shortlist",
            "Decision_Class_AH": "B — Established scientific candidate",
            "Go_Investigate_Hold_NoGo": "Go",
        },
    ])
    evidence_df = pd.DataFrame([{"Evidence_Record_ID": "E1", "Scientific_Name": "Plant A"}])

    result = src._run_evidence_adjudication(plant_summary_df, evidence_df, "sleep", {})

    # No double-counting: negative evidence already represented upstream
    # gets a 0.0 adjustment, so Final == Base == the original Overall_Score.
    assert result.loc[0, "Final_R&D_Opportunity_Score"] == 60.0
    assert result.loc[0, "Overall_Score"] == 60.0
    assert result.loc[0, "Base_R&D_Opportunity_Score"] == 60.0
    assert result.loc[0, "Evidence_Adjudication_Adjustment"] == 0.0
    assert result.loc[0, "Negative_Human_Evidence_Adjustment"] == 0.0


def test_non_adjudicated_row_overall_score_is_a_no_op():
    # A row outside Shortlist/Exploratory is never sent to adjudication;
    # Overall_Score must be left exactly as it was (Base == Final ==
    # original Overall_Score), not blanked or altered.
    plant_summary_df = _plant_summary([
        {
            "Alternative_Plant": "Plant B", "Overall_Score": 12.0,
            "Scientific_Triage_Status": "Excluded",
            "Decision_Class_AH": "F — Exploratory hypothesis",
            "Go_Investigate_Hold_NoGo": "Hold",
        },
    ])
    evidence_df = pd.DataFrame([{"Evidence_Record_ID": "E1", "Scientific_Name": "Plant B"}])

    result = src._run_evidence_adjudication(plant_summary_df, evidence_df, "sleep", {})

    assert result.loc[0, "Overall_Score"] == 12.0
    assert result.loc[0, "Evidence_Adjudication_Status"] == "AI_ADJUDICATION_NOT_RUN"
    # part B12 -- explicit UNKNOWN, not None, for a row that was never
    # adjudicated.
    assert result.loc[0, "Indication_Evidence_Direction"] == "UNKNOWN"
    assert result.loc[0, "Human_Evidence_Strength"] == "UNKNOWN"
    assert result.loc[0, "Positive_Evidence_IDs"] == []


# ---------------------------------------------------------------------
# Part 5 (this session) -- explicit agreement check: Overall_Score,
# R&D_Opportunity_Score, and the authoritative final adjudicated score
# must all agree in the merged report-ready frame.
# ---------------------------------------------------------------------
def test_overall_score_rd_opportunity_score_and_final_score_all_agree(monkeypatch):
    import candidate_shortlisting as cs

    def _fake_adjudicate_candidate(plant, indication, evidence_df, **kwargs):
        return {
            "Indication_Evidence_Direction": "MOSTLY_NEGATIVE", "Human_Evidence_Strength": "MODERATE",
            "Evidence_Conflict_Level": "LOW", "Negative_Evidence_Severity": "MODERATE",
            "Scientific_Evidence_Confidence": "MODERATE", "Preparation_Compatibility": "DIRECT",
            "Plant_Part_Compatibility": "DIRECT", "Route_Compatibility": "DIRECT",
            "Positive_Evidence_IDs": [], "Negative_Evidence_IDs": ["E1"],
            "Key_Human_Evidence_IDs": ["E1"], "Preparation_Mismatch_Evidence_IDs": [],
            "Evidence_Adjudication_Status": "AI_ADJUDICATION_OK",
            "Evidence_Adjudication_Fallback_Reason": None, "Evidence_Adjudication_Evidence_Count": 1,
            "Evidence_Adjudication_Rationale": "ok",
        }

    monkeypatch.setattr(src, "adjudicate_candidate", _fake_adjudicate_candidate)

    plant_summary_df = _plant_summary([{
        "Alternative_Plant": "Plant C", "Overall_Score": 70.0,
        "Scientific_Triage_Status": "Shortlist",
        "Decision_Class_AH": "B — Established scientific candidate",
        "Go_Investigate_Hold_NoGo": "Go",
    }])
    evidence_df = pd.DataFrame([{"Evidence_Record_ID": "E1", "Scientific_Name": "Plant C"}])
    adjudicated_summary = src._run_evidence_adjudication(plant_summary_df, evidence_df, "sleep", {})

    raw_df = pd.DataFrame([{"Alternative_Plant": "Plant C", "R&D_Opportunity_Score": 70.0}])
    merged = cs.merge_authoritative_scores(raw_df, adjudicated_summary)

    final_score = adjudicated_summary.loc[0, "Final_R&D_Opportunity_Score"]
    assert merged.loc[0, "Overall_Score"] == final_score
    assert merged.loc[0, "R&D_Opportunity_Score"] == final_score
