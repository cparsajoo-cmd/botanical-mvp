import pandas as pd
import evidence_adjudication_engine as eae
import candidate_shortlisting as cs
from step_rd_candidates import _reconcile_final_decision_status, _evidence_coherence_status


def test_adjacent_human_outcome_does_not_count_as_direct_indication_body():
    df = pd.DataFrame([{
        "Alternative_Plant": "Plant alpha",
        "Source_Record_IDs": "E1",
        "Indication_Match_Type": "explicit_field_overlap",
        "Indication_Match_Reason": "Exact indication phrase matched in source text",
        "Study_Design": "Randomized double-blind clinical trial",
        "Primary_Outcome": "fatigue severity and exercise recovery",
        "Evidence_Direction": "positive",
    }])
    items = eae.build_adjudication_evidence_items(df, "Plant alpha", "sleep", 25)
    assert len(items) == 1
    assert items[0]["human_animal_in_vitro"] == "HUMAN"
    assert items[0]["outcome_specific"] is False
    raw = {"Human_Evidence_Strength": "STRONG", "Scientific_Evidence_Confidence": "HIGH", "Evidence_Conflict_Level": "NONE"}
    calibrated = eae._calibrate_ai_evidence_strength(raw, items)
    assert calibrated["Human_Evidence_Strength"] == "NONE"
    assert calibrated["Scientific_Evidence_Confidence"] == "LOW"


def test_human_design_is_recognized_without_population_field():
    assert eae._derive_study_context("", "Randomized placebo-controlled clinical study", "") == "HUMAN"
    assert eae._derive_study_context("", "Systematic review of clinical trials", "") == "HUMAN"


def test_direct_count_requires_indication_specific_outcome_generic():
    row = pd.Series({"Primary_Outcome": "glycemic control and HbA1c"})
    assert cs._row_has_indication_specific_outcome(row, "diabetes") is True
    row2 = pd.Series({"Primary_Outcome": "exercise fatigue and recovery"})
    assert cs._row_has_indication_specific_outcome(row2, "diabetes") is False


def test_direct_human_label_without_outcome_specific_evidence_cannot_be_green():
    row = {
        "Final_Decision_Status": "GO",
        "Decision_Class_AH": "B — Established scientific candidate",
        "Relevance_Gate_Result": "passed_direct",
        "Preparation_Applicability_Class": "direct_match",
        "Evidence_Adjudication_Status": "AI_ADJUDICATION_OK",
        "Indication_Evidence_Direction": "CONSISTENT_POSITIVE",
        "Human_Evidence_Strength": "MODERATE",
        "Evidence_Conflict_Level": "NONE",
        "Scientific_Evidence_Confidence": "MODERATE",
        "Indication_Evidence_Mode": "Direct human/clinical",
        "Direct_Indication_Evidence_Count": 0,
        "Evidence_Adjudication_Evidence_Count": 3,
    }
    assert _reconcile_final_decision_status(row) == "EXPERT REVIEW REQUIRED"
    assert _evidence_coherence_status(row) == "CONTRADICTION_NO_OUTCOME_SPECIFIC_DIRECT_EVIDENCE"
