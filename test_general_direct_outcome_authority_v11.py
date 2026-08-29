import pandas as pd
import evidence_adjudication_engine as eae
import step_rd_candidates as step


def _row(**kw):
    base = {
        "Evidence_Record_ID": "E1",
        "Alternative_Plant": "Plantus testus",
        "Indication_Match_Type": "explicit_field_overlap",
        "Canonical_Study_Context": "HUMAN",
        "Study_Type": "Clinical trial",
        "Source_Evidence_Text": "",
        "Source_Outcome_Text": "",
        "Outcome_Specific_Direct_Evidence": False,
    }
    base.update(kw)
    return base


def test_ai_context_only_record_cannot_create_efficacy_direction(monkeypatch):
    df = pd.DataFrame([_row(Source_Evidence_Text="Background disease context; unrelated oncology outcome")])

    def fake(**kwargs):
        return {
            "indication_evidence_direction": "CONSISTENT_POSITIVE",
            "human_evidence_strength": "MODERATE",
            "evidence_conflict_level": "NONE",
            "negative_evidence_severity": "NONE",
            "scientific_evidence_confidence": "HIGH",
            "positive_evidence_ids": ["E1"],
            "negative_evidence_ids": [],
            "key_human_evidence_ids": ["E1"],
            "direct_outcome_evidence_ids": [],
            "direct_human_outcome_evidence_ids": [],
            "preparation_mismatch_evidence_ids": [],
            "summary_note": "Context only.",
        }

    monkeypatch.setattr(eae.llm_client, "call_structured_json", fake)
    out = eae.adjudicate_candidate("Plantus testus", "metabolic support", df)
    assert out["Evidence_Adjudication_Status"] == "AI_ADJUDICATION_OK"
    assert out["Direct_Outcome_Evidence_IDs"] == []
    assert out["Direct_Human_Outcome_Evidence_IDs"] == []
    assert out["Indication_Evidence_Direction"] == "INSUFFICIENT"
    assert out["Human_Evidence_Strength"] == "NONE"
    assert out["Scientific_Evidence_Confidence"] == "LOW"


def test_ai_verified_direct_human_outcome_survives(monkeypatch):
    df = pd.DataFrame([_row(
        Source_Evidence_Text="Randomized trial reported improved glycemic outcome.",
        Source_Outcome_Text="blood glucose improved",
        Outcome_Specific_Direct_Evidence=True,
        Outcome_Specific_Human_Evidence=True,
    )])

    def fake(**kwargs):
        return {
            "indication_evidence_direction": "MOSTLY_POSITIVE",
            "human_evidence_strength": "MODERATE",
            "evidence_conflict_level": "LOW",
            "negative_evidence_severity": "NONE",
            "scientific_evidence_confidence": "MODERATE",
            "positive_evidence_ids": ["E1"],
            "negative_evidence_ids": [],
            "key_human_evidence_ids": ["E1"],
            "direct_outcome_evidence_ids": ["E1"],
            "direct_human_outcome_evidence_ids": ["E1"],
            "preparation_mismatch_evidence_ids": [],
            "summary_note": "Direct human outcome.",
        }

    monkeypatch.setattr(eae.llm_client, "call_structured_json", fake)
    out = eae.adjudicate_candidate("Plantus testus", "metabolic support", df)
    assert out["Direct_Outcome_Evidence_IDs"] == ["E1"]
    assert out["Direct_Human_Outcome_Evidence_IDs"] == ["E1"]
    assert out["Indication_Evidence_Direction"] == "MOSTLY_POSITIVE"
    assert out["Human_Evidence_Strength"] == "WEAK"  # one independent direct human record


def _decision_row(**kw):
    base = {
        "Final_Decision_Status": "GO WITH CAUTION",
        "Decision_Class_AH": "B — Established scientific candidate",
        "Relevance_Gate_Result": "passed_direct",
        "Preparation_Applicability_Class": "direct_match",
        "Evidence_Adjudication_Status": "AI_ADJUDICATION_OK",
        "Indication_Evidence_Direction": "CONSISTENT_POSITIVE",
        "Human_Evidence_Strength": "MODERATE",
        "Evidence_Conflict_Level": "LOW",
        "Scientific_Evidence_Confidence": "MODERATE",
        "Indication_Evidence_Mode": "Direct human/clinical",
        "Direct_Indication_Evidence_Count": 3,
        "Outcome_Specific_Direct_Evidence_Count": 0,
        "Outcome_Specific_Human_Evidence_Count": 0,
        "Evidence_Adjudication_Evidence_Count": 10,
        "Safety_Flags": "",
    }
    base.update(kw)
    return pd.Series(base)


def test_final_priority_requires_ai_verified_direct_outcome_when_v2_schema_present():
    row = _decision_row(
        Direct_Outcome_Evidence_IDs=[],
        Direct_Human_Outcome_Evidence_IDs=[],
    )
    assert step._reconcile_final_decision_status(row) == "EXPERT REVIEW REQUIRED"


def test_final_priority_can_remain_cautious_with_verified_direct_human_outcome():
    row = _decision_row(
        Direct_Outcome_Evidence_IDs=["E1"],
        Direct_Human_Outcome_Evidence_IDs=["E1"],
        Human_Evidence_Strength="WEAK",
        Scientific_Evidence_Confidence="LOW",
    )
    assert step._reconcile_final_decision_status(row) == "GO WITH CAUTION"
