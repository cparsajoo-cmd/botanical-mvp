import pandas as pd

import evidence_adjudication_engine as eae
from safety_interaction_attribution import extract_structured_safety_interactions
from standard_evidence_builder import evaluate_applicability
from step_rd_candidates import _reconcile_final_decision_status


def _item(eid, *, human=True, direct=True, design="Clinical trial"):
    return {
        "evidence_id": eid,
        "human_animal_in_vitro": "HUMAN" if human else "ANIMAL_OR_IN_VITRO",
        "indication_match_strength": "DIRECT" if direct else "SUPPORTIVE",
        "study_model": "human" if human else "animal",
        "study_type_design": design,
    }


def test_ai_strength_is_capped_by_independent_direct_human_body():
    raw = {
        "Human_Evidence_Strength": "STRONG",
        "Scientific_Evidence_Confidence": "HIGH",
        "Evidence_Conflict_Level": "NONE",
    }
    one = eae._calibrate_ai_evidence_strength(raw, [_item("E1")])
    assert one["Human_Evidence_Strength"] == "WEAK"
    assert one["Scientific_Evidence_Confidence"] == "LOW"

    three = eae._calibrate_ai_evidence_strength(raw, [_item("E1"), _item("E2"), _item("E3")])
    assert three["Human_Evidence_Strength"] == "MODERATE"
    assert three["Scientific_Evidence_Confidence"] == "MODERATE"

    four = eae._calibrate_ai_evidence_strength(raw, [_item(f"E{i}") for i in range(4)])
    assert four["Human_Evidence_Strength"] == "STRONG"
    assert four["Scientific_Evidence_Confidence"] == "HIGH"


def test_legacy_preparation_compatibility_is_partial_not_direct_match():
    row = {"Dosage_Form_Compatibility": "Compatible"}
    ctx = {"Target_Preparation": "infusion", "Target_Preparation_Category": "aqueous"}
    result = evaluate_applicability(row, ctx)
    assert result["Dimension_Status"]["preparation"] == "PARTIAL"


def test_no_adverse_events_is_reassurance_not_safety_flag():
    result = extract_structured_safety_interactions(
        "No adverse events were reported by any subjects.", None, plant_name="Example plant"
    )
    assert result["adverse_events"] == []
    assert result["safety_reassurance"]


def test_therapeutic_list_with_hemorrhage_is_not_adverse_signal():
    text = "The seeds have therapeutic effects against many ailments such as diabetes, intrinsic hemorrhage, asthma and cough."
    result = extract_structured_safety_interactions(text, None, plant_name="Example plant")
    assert result["adverse_events"] == []


def test_serious_non_hard_stop_safety_signal_cannot_be_go():
    row = {
        "Final_Decision_Status": "GO WITH CAUTION",
        "Decision_Class_AH": "C — Alternative-source R&D candidate",
        "Relevance_Gate_Result": "passed_direct",
        "Preparation_Applicability_Class": "direct_match",
        "Evidence_Adjudication_Status": "AI_ADJUDICATION_OK",
        "Indication_Evidence_Direction": "CONSISTENT_POSITIVE",
        "Human_Evidence_Strength": "STRONG",
        "Evidence_Conflict_Level": "NONE",
        "Scientific_Evidence_Confidence": "HIGH",
        "Indication_Evidence_Mode": "Direct human/clinical",
        "Direct_Indication_Evidence_Count": 4,
        "Evidence_Adjudication_Evidence_Count": 4,
        "Safety_Flags": "Published reports describe hepatotoxicity associated with the intervention.",
    }
    assert _reconcile_final_decision_status(row) == "EXPERT REVIEW REQUIRED"
