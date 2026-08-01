import sys
import types

import pandas as pd

if "supabase" not in sys.modules:
    fake_supabase = types.ModuleType("supabase")
    fake_supabase.create_client = lambda *args, **kwargs: None
    sys.modules["supabase"] = fake_supabase
if "streamlit" not in sys.modules:
    fake_streamlit = types.ModuleType("streamlit")
    fake_streamlit.secrets = {}
    sys.modules["streamlit"] = fake_streamlit

import supabase_data
from indication_candidate_discovery import discover_indication_candidates
from standard_evidence_builder import build_standard_evidence


def test_supabase_loader_flattens_phase2_result_safety_interaction_fields(monkeypatch):
    raw = pd.DataFrame([{
        "id": 77,
        "plant_id": 4,
        "plants": {"scientific_name": "Ginkgo biloba", "common_name": "Ginkgo"},
        "sources": {"url": "https://example.org/77", "title": "Trial", "source_type": "journal"},
        "target_indication": "type 2 diabetes",
        "primary_outcome": "HbA1c: no significant difference",
        "result_direction": "no significant difference",
        "study_type": "systematic review",
        "extraction_method": "standardized dry extract capsule",
        "administration_route": "oral",
        "effect_size": {"metric": "mean difference", "value": 0.01},
        "p_value": {"value": 0.82},
        "adverse_events": {"bleeding": "reported concern"},
        "interactions_structured": ["anticoagulants", "antiplatelets"],
        "safety_signal": "bleeding risk",
    }])
    monkeypatch.setattr(supabase_data, "_fetch_table_df", lambda *a, **k: raw)
    out = supabase_data.load_evidence_records_df().iloc[0]
    assert out["Result_Direction"] == "no significant difference"
    assert out["Extraction_Method"] == "standardized dry extract capsule"
    assert out["Adverse_Events"] == {"bleeding": "reported concern"}
    assert out["Interactions_Structured"] == ["anticoagulants", "antiplatelets"]
    assert out["Safety_Findings"] == {"bleeding": "reported concern"}


def test_standard_builder_does_not_overwrite_literal_outcome_and_safety_with_empty_llm_fields():
    record = {
        "Scientific_Name": "Plant A",
        "Primary_Outcome": "fasting glucose decreased",
        "Result_Direction": "positive benefit",
        "Safety_Signal": "mild gastrointestinal adverse events",
        "Adverse_Events": {"gi": "mild"},
        "Interactions_Structured": ["hypoglycemic medicines"],
        "LLM_Main_Outcome": "",
        "LLM_Result_Direction": "",
        "LLM_Safety_Signal": "",
    }
    out = build_standard_evidence(record)
    assert out["Primary_Outcome"] == "fasting glucose decreased"
    assert out["Result_Direction"] == "positive benefit"
    assert out["Safety_Signal"] == "mild gastrointestinal adverse events"
    assert out["Adverse_Events"] == {"gi": "mild"}
    assert out["Interactions_Structured"] == ["hypoglycemic medicines"]


class _Engine:
    def __init__(self, row):
        self.evidence_df = pd.DataFrame()
        self.scientific_evidence_df = pd.DataFrame()
        self.evidence_records_df = pd.DataFrame([row])

    def _candidate_frame(self):
        return pd.DataFrame([{
            "Scientific_Name": "Ginkgo biloba",
            "Known_Active_Compounds": "ginkgolide",
            "Known_Targets": "blood glucose",
        }])

    def _pick(self, row, names):
        for name in names:
            if name in row and row[name] is not None:
                value = row[name]
                if isinstance(value, (dict, list)) or str(value).strip():
                    return value
        return ""

    def _split_compound_terms(self, value):
        return [str(value)] if str(value).strip() else []

    def _evidence_level(self, text):
        return "Systematic review and meta-analysis"


def test_discovery_transports_jsonb_safety_interactions_and_explicit_null_outcome():
    row = {
        "Evidence_Record_ID": 77,
        "Scientific_Name": "Ginkgo biloba",
        "Target_Indication": "type 2 diabetes",
        "Study_Type": "Systematic review and meta-analysis",
        "Primary_Outcome": "HbA1c: no significant difference",
        # Deliberately empty: explicit wording in Primary_Outcome must be used.
        "Result_Direction": "",
        "Extraction_Method": "standardized dry extract capsule",
        "Adverse_Events": {"bleeding": "reported concern"},
        "Interactions_Structured": ["anticoagulants", "antiplatelets"],
        "Source_URL": "https://example.org/77",
    }
    out = discover_indication_candidates(_Engine(row), "type 2 diabetes", dosage_form="Infusion")
    result = out.iloc[0]
    assert result["Result_Direction"] == "no significant benefit"
    assert bool(result["Has_Negative_Evidence"])
    assert result["Preparation_Applicability"] == "Mismatch"
    assert "bleeding" in result["Safety_Flags"].lower()
    assert "anticoagulants" in result["Interaction_Flags"].lower()
