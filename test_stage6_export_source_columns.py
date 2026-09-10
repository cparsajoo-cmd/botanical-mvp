"""Corrective pass (2026-09-10), spec §7: the final decision CSV must
include the new mechanism/compound/claim-map source columns. This test
runs the SAME attach_* pipeline, in the SAME order, that step_rd_candidates.py's
real CSV download-button call site runs -- not a reimplementation -- so it
actually exercises the code that produces the exported dataframe.
"""
import pandas as pd

from evidence_source_resolver import (
    attach_human_evidence_source_traceability,
    attach_safety_evidence_source_traceability,
    attach_mechanistic_evidence_source_traceability,
    attach_scientific_source_summary,
)
from compound_source_traceability import attach_compound_source_traceability
from commercial_source_traceability import attach_commercial_source_traceability
from claim_source_map import (
    attach_regulatory_patent_source_traceability,
    attach_claim_source_map,
)
from source_linkage_consistency import attach_source_linkage_consistency

_REQUIRED_EXPORT_COLUMNS = (
    "Mechanistic_Evidence_Record_IDs",
    "Mechanistic_Source_Count",
    "Mechanistic_Primary_Source_Title",
    "Mechanistic_Primary_Source_URL",
    "Mechanistic_Source_URLs",
    "Target_Source_Map",
    "Mechanism_Source_Map",
    "Compound_Source_Count",
    "Compound_Primary_Source_Title",
    "Compound_Primary_Source_URL",
    "Compound_Source_URLs",
    "Compound_Source_Map",
    "Claim_Source_Map",
    "Derived_Claim_Provenance",
    "Human_Evidence_Record_IDs",
    "Human_Evidence_Source_Count",
    "Safety_Evidence_Record_IDs",
    "Safety_Source_Count",
    "Commercial_Source_Count",
    "Regulatory_Source_Count",
    "Patent_Source_Count",
)


def _run_export_pipeline(report_df, evidence_df):
    out = attach_human_evidence_source_traceability(report_df, evidence_df)
    out = attach_safety_evidence_source_traceability(out, evidence_df)
    out = attach_mechanistic_evidence_source_traceability(out, evidence_df)
    out = attach_scientific_source_summary(out)
    out = attach_compound_source_traceability(out)
    out = attach_commercial_source_traceability(out)
    out = attach_regulatory_patent_source_traceability(out)
    out = attach_claim_source_map(out)
    out = attach_source_linkage_consistency(out)
    return out


def test_export_dataframe_contains_all_required_source_columns():
    report_df = pd.DataFrame([{
        "Alternative_Plant": "Withania somnifera",
        "Direct_Human_Outcome_Evidence_IDs": ["E1"],
        "Safety_Evidence_IDs": ["S1"],
        "Mechanistic_Evidence_Record_IDs": ["M1"],
        "Target_Source_Map": {"GABA-A receptor": ["M1"]},
        "Mechanism_Source_Map": {"GABAergic modulation": ["M1"]},
        "Discovery_Linked_Compounds": "Withanolide A",
    }])
    evidence_df = pd.DataFrame([
        {"Evidence_Record_ID": "E1", "Source_Title": "Human RCT", "Source_URL": "https://example.org/e1"},
        {"Evidence_Record_ID": "S1", "Source_Title": "Safety report", "Source_URL": "https://example.org/s1"},
        {"Evidence_Record_ID": "M1", "Source_Title": "Mechanistic study", "Source_URL": "https://example.org/m1"},
    ])
    out = _run_export_pipeline(report_df, evidence_df)

    missing = [c for c in _REQUIRED_EXPORT_COLUMNS if c not in out.columns]
    assert not missing, f"CSV export is missing required columns: {missing}"

    # The export is real content, not empty placeholders.
    row = out.iloc[0]
    assert row["Mechanistic_Source_Count"] == 1
    assert row["Compound_Source_Count"] == 1
    assert row["Claim_Source_Map"] and row["Claim_Source_Map"] != "{}"


def test_export_dataframe_is_csv_serializable():
    """Dict/list-valued columns (Target_Source_Map etc.) must be JSON
    strings by this point, or to_csv() would just dump a Python repr."""
    report_df = pd.DataFrame([{
        "Alternative_Plant": "Withania somnifera",
        "Mechanistic_Evidence_Record_IDs": ["M1"],
        "Target_Source_Map": {"GABA-A receptor": ["M1"]},
        "Mechanism_Source_Map": {},
    }])
    evidence_df = pd.DataFrame([
        {"Evidence_Record_ID": "M1", "Source_Title": "Mechanistic study", "Source_URL": "https://example.org/m1"},
    ])
    out = _run_export_pipeline(report_df, evidence_df)
    csv_bytes = out.to_csv(index=False).encode("utf-8")
    assert b"GABA-A receptor" in csv_bytes
    # Round-trippable JSON, not a Python dict repr (which would use single quotes).
    assert b"{'GABA-A" not in csv_bytes
