import pandas as pd

from candidate_shortlisting import build_plant_candidate_shortlist


def _row(plant="Plant A", source="PMID:1", direction="positive", preparation="Compatible", safety="Well tolerated; no serious adverse events"):
    return {
        "Alternative_Plant": plant,
        "Reference_Plant": "Indication-centric discovery",
        "Reference_Compound": "Not used as candidate gate",
        "Shared_or_Similar_Compound": "specific-marker",
        "Novelty_Status": "Search not performed",
        "Target_or_Mechanism": "blood glucose; insulin resistance",
        "Target_Provenance": "Candidate-specific indication evidence",
        "Evidence_Level": "Randomized clinical trial",
        "Evidence_Hierarchy_Detail": "Randomized controlled trial",
        "Candidate_Evidence_Strength_Tier": "Direct human evidence",
        "Scientific_Rationale": "Type 2 diabetes blood glucose fasting glucose outcome",
        "Clinical_Rationale": "Human randomized clinical evidence",
        "Evidence_Source": source,
        "Source_Record_IDs": source,
        "Result_Direction": direction,
        "Has_Negative_Evidence": direction in {"no significant difference", "no effect", "worsened"},
        "Negative_Evidence_Types": "Negative/null reported result" if direction in {"no significant difference", "no effect", "worsened"} else "",
        "Preparation_Applicability": preparation,
        "Applicability_Summary": {
            "critical_mismatches": ["preparation mismatch"] if preparation == "Mismatch" else [],
            "evidence_items": [{"applicability_classification": preparation}],
        },
        "Safety_Flags": safety,
        "Interaction_Flags": "",
        "Regulatory_Barriers": "Traditional use monograph",
        "Market_Status": "Search not performed",
        "R&D_Opportunity_Score": 50,
    }


def test_null_human_evidence_cannot_be_go_or_high_relevance():
    rows = [_row(source="PMID:1", direction="no significant difference"),
            _row(source="PMID:2", direction="no effect")]
    summary, _ = build_plant_candidate_shortlist(pd.DataFrame(rows), indication="type 2 diabetes", dosage_form="Infusion")
    row = summary.iloc[0]
    assert row["Indication_Relevance_Score"] <= 15
    assert row["Scientific_Triage_Status"] == "Exploratory"
    assert not str(row["Go_Investigate_Hold_NoGo"]).startswith("Go")
    assert row["Outcome_Consistency"] == "No demonstrated benefit"


def test_mixed_results_score_below_consistently_positive_results():
    positive_rows = [_row("Positive plant", "PMID:1", "positive"), _row("Positive plant", "PMID:2", "improved")]
    mixed_rows = [_row("Mixed plant", "PMID:3", "positive"), _row("Mixed plant", "PMID:4", "no significant difference")]
    summary, _ = build_plant_candidate_shortlist(pd.DataFrame(positive_rows + mixed_rows), indication="type 2 diabetes", dosage_form="Infusion")
    scores = summary.set_index("Alternative_Plant")["Overall_Score"]
    assert scores["Positive plant"] > scores["Mixed plant"]


def test_preparation_mismatch_is_excluded_for_selected_product_form():
    summary, _ = build_plant_candidate_shortlist(pd.DataFrame([_row(preparation="Mismatch")]), indication="type 2 diabetes", dosage_form="Infusion")
    row = summary.iloc[0]
    assert row["Scientific_Triage_Status"] == "Excluded"
    assert "preparation" in row["Why_Selected_or_Rejected"].lower()


def test_unknown_safety_or_preparation_blocks_go_but_not_scientific_review():
    summary, _ = build_plant_candidate_shortlist(
        pd.DataFrame([_row(preparation="Unknown", safety="")]),
        indication="type 2 diabetes", dosage_form="Infusion",
    )
    row = summary.iloc[0]
    assert row["Scientific_Triage_Status"] == "Shortlist"
    assert str(row["Go_Investigate_Hold_NoGo"]).startswith("Investigate")


def test_go_requires_positive_results_compatible_preparation_and_explicit_safety():
    rows = [_row(source=f"PMID:{i}", direction="positive") for i in range(1, 8)]
    summary, _ = build_plant_candidate_shortlist(pd.DataFrame(rows), indication="type 2 diabetes", dosage_form="Infusion")
    row = summary.iloc[0]
    assert row["Scientific_Triage_Status"] == "Shortlist"
    assert row["Outcome_Consistency"] == "Predominantly positive results"
    assert row["Dosage_Form_Compatibility"] == "Compatible"
    assert row["Go_Investigate_Hold_NoGo"] == "Go"


def test_discovery_preserves_record_result_preparation_and_safety_fields():
    from indication_candidate_discovery import discover_indication_candidates

    class Engine:
        def __init__(self):
            self.evidence_df = pd.DataFrame()
            self.scientific_evidence_df = pd.DataFrame()
            self.evidence_records_df = pd.DataFrame([{
                "id": 10,
                "plant": "Ginkgo biloba",
                "target_indication": "Type 2 diabetes",
                "study_type": "Systematic review and meta-analysis",
                "primary_outcome": "HbA1c and fasting glucose",
                "result_direction": "no significant difference",
                "preparation": "standardized dry extract capsule",
                "safety_findings": "bleeding interaction concern",
                "interactions": "anticoagulant interaction",
                "source_url": "https://example.org/ginkgo",
            }])
        def _candidate_frame(self):
            return pd.DataFrame([{"Scientific_Name": "Ginkgo biloba", "Known_Active_Compounds": "ginkgolide", "Known_Targets": "blood glucose"}])
        def _pick(self, row, names):
            for name in names:
                if name in row and pd.notna(row[name]) and str(row[name]).strip():
                    return str(row[name])
            return ""
        def _split_compound_terms(self, value):
            return [str(value)] if str(value).strip() else []
        def _evidence_level(self, text):
            return "Systematic review and meta-analysis"

    raw = discover_indication_candidates(Engine(), "Type 2 diabetes", dosage_form="Infusion")
    row = raw.iloc[0]
    assert row["Result_Direction"] == "no significant difference"
    assert row["Preparation_Applicability"] == "Mismatch"
    assert "bleeding" in row["Safety_Flags"].lower()
    assert "anticoagulant" in row["Interaction_Flags"].lower()
    assert bool(row["Has_Negative_Evidence"])
