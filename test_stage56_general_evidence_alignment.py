import pandas as pd

import evidence_adjudication_engine as ea


def _processed_row(record_id, *, plant="Plantus generalis", direction="Positive"):
    return {
        "Alternative_Plant": plant,
        "Source_Record_IDs": record_id,
        "Indication_Match_Type": "exact_indication",
        "Indication_Match_Score": 1.0,
        "Evidence_Hierarchy_Detail": "Clinical trial",
        "Study_Design": "randomized double-blind placebo-controlled trial",
        "Evidence_Direction": direction,
        "Evidence_Source": "PubMed",
        "Extraction_Method": "aqueous extract",
        "Target_or_Mechanism": "receptor pathway",
        "Rationale": "candidate-specific evidence",
    }


def test_processed_stage5_rows_are_valid_adjudication_evidence_for_any_indication():
    df = pd.DataFrame([
        _processed_row("PMID:1"),
        _processed_row("PMID:2"),
        _processed_row("PMID:1"),  # duplicate projection of the same record
    ])
    items = ea.build_adjudication_evidence_items(
        df, "Plantus generalis", "glycemic control", max_items=25
    )
    assert [item["evidence_id"] for item in items] == ["PMID:1", "PMID:2"]
    assert all(item["indication_match_strength"] == "DIRECT" for item in items)
    assert all(item["human_animal_in_vitro"] == "HUMAN" for item in items)
    assert all(item["result_direction"] == "Positive" for item in items)


def test_bundle_consistency_prevents_none_human_when_human_records_are_supplied():
    items = ea.build_adjudication_evidence_items(
        pd.DataFrame([_processed_row("PMID:10")]),
        "Plantus generalis",
        "joint discomfort",
    )
    structured = {
        "Indication_Evidence_Direction": "CONSISTENT_POSITIVE",
        "Human_Evidence_Strength": "NONE",
        "Evidence_Conflict_Level": "NONE",
        "Negative_Evidence_Severity": "NONE",
        "Scientific_Evidence_Confidence": "HIGH",
        "Positive_Evidence_IDs": ["PMID:10"],
        "Negative_Evidence_IDs": [],
        "Key_Human_Evidence_IDs": ["PMID:10"],
        "Preparation_Mismatch_Evidence_IDs": [],
    }
    fixed = ea._enforce_bundle_consistency(structured, items)
    assert fixed["Human_Evidence_Strength"] == "WEAK"
    assert fixed["Key_Human_Evidence_IDs"] == ["PMID:10"]


def test_bundle_consistency_removes_impossible_human_strength_from_nonhuman_bundle():
    row = _processed_row("REC:ANIMAL")
    row["Evidence_Hierarchy_Detail"] = "Validated ex vivo / in vivo"
    row["Study_Design"] = "rat model in vivo"
    items = ea.build_adjudication_evidence_items(
        pd.DataFrame([row]), "Plantus generalis", "respiratory symptoms"
    )
    structured = {
        "Indication_Evidence_Direction": "MOSTLY_POSITIVE",
        "Human_Evidence_Strength": "STRONG",
        "Evidence_Conflict_Level": "LOW",
        "Negative_Evidence_Severity": "NONE",
        "Scientific_Evidence_Confidence": "MODERATE",
        "Positive_Evidence_IDs": ["REC:ANIMAL"],
        "Negative_Evidence_IDs": [],
        "Key_Human_Evidence_IDs": ["REC:ANIMAL"],
        "Preparation_Mismatch_Evidence_IDs": [],
    }
    fixed = ea._enforce_bundle_consistency(structured, items)
    assert fixed["Human_Evidence_Strength"] == "NONE"
    assert fixed["Key_Human_Evidence_IDs"] == []
