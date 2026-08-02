import pandas as pd

from indication_candidate_discovery import discover_indication_candidates


class _Engine:
    def __init__(self):
        self.evidence_df = pd.DataFrame()
        self.scientific_evidence_df = pd.DataFrame()
        self.evidence_records_df = pd.DataFrame([
            {
                "id": 27901,
                "plant": "Ginkgo biloba",
                "target_indication": "Eye health",
                "study_type": "case report",
                "notes": "Fatal Seizures Due to Potential Herb-Drug Interactions with Ginkgo Biloba",
                "adverse_events": [{
                    "event": "fatal breakthrough seizure",
                    "severity": "fatal",
                    "attribution": "possible",
                    "evidence_type": "case report",
                }],
                "interactions_structured": [{
                    "interacting_drug_class": "anticonvulsants",
                    "agents": ["phenytoin", "valproate"],
                    "possible_mechanism": "CYP2C19 induction",
                    "clinical_consequence": "subtherapeutic anticonvulsant concentrations and seizure risk",
                    "attribution": "possible",
                    "evidence_type": "case report",
                }],
            },
            {
                "id": 27890,
                "plant": "Ginkgo biloba",
                "target_indication": "Eye health",
                "study_type": "case report",
                "notes": "Spontaneous hyphema associated with ingestion of Ginkgo biloba extract",
                "adverse_events": [{
                    "event": "spontaneous hyphema",
                    "severity": "serious",
                    "attribution": "associated",
                    "evidence_type": "case report",
                }],
            },
            {
                "id": 70000,
                "plant": "Ginkgo biloba",
                "target_indication": "Type 2 diabetes",
                "study_type": "human trial",
                "primary_outcome": "fasting glucose",
                "result_direction": "positive benefit",
                "evidence_level": "Clinical / human evidence",
            },
        ])

    def _candidate_frame(self):
        return pd.DataFrame([{
            "Scientific_Name": "Ginkgo biloba",
            "Known_Active_Compounds": "ginkgolide",
            "Known_Targets": "blood glucose",
        }])

    def _pick(self, row, names):
        for name in names:
            if name in row and row[name] is not None:
                return str(row[name]).strip()
        return ""

    def _split_compound_terms(self, value):
        return [str(value)] if str(value).strip() else []

    def _evidence_level(self, text):
        return "Clinical / human evidence"


def test_cross_indication_structured_ginkgo_safety_survives_to_step5_output():
    rows = discover_indication_candidates(_Engine(), "Type 2 diabetes")
    row = rows.iloc[0]
    safety = row["Safety_Flags"].lower()
    interactions = row["Interaction_Flags"].lower()

    assert "fatal breakthrough seizure" in safety
    assert "spontaneous hyphema" in safety
    assert "severity: fatal" in safety
    assert "anticonvulsants" in interactions
    assert "phenytoin" in interactions
    assert "valproate" in interactions
    assert "cyp2c19 induction" in interactions
    assert "unknown" not in safety
    assert "eye health" not in safety
    assert "type 2 diabetes" not in safety
