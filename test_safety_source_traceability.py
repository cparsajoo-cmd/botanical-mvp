import json

import pandas as pd

from evidence_source_resolver import (
    attach_safety_evidence_source_traceability,
    build_source_bundle,
)


def _evidence_df():
    return pd.DataFrame([
        {
            "Evidence_Record_ID": "S1",
            "Source_Title": "Case report: interaction with warfarin",
            "Source_Type": "PubMed",
            "Source_Year": 2021,
            "Source_URL": "https://example.org/article/S1",
            "PMID": "22222222",
            "DOI": "",
            "Study_Type": "Case report",
        },
        {
            "Evidence_Record_ID": "S2",
            "Source_Title": "Internal safety note",
            "Source_URL": "",
            "PMID": "",
            "DOI": "",
        },
    ])


# ---------------------------------------------------------------------------
# build_source_bundle — generic reusable abstraction (spec §2/§4)
# ---------------------------------------------------------------------------

def test_build_source_bundle_zero_sources():
    bundle = build_source_bundle([], _evidence_df())
    assert bundle["source_count"] == 0
    assert bundle["resolved_source_count"] == 0
    assert bundle["unresolved_source_count"] == 0
    assert bundle["primary_source_title"] is None
    assert bundle["primary_source_url"] is None
    assert bundle["sources"] == []


def test_build_source_bundle_one_resolved_source():
    bundle = build_source_bundle(["S1"], _evidence_df())
    assert bundle["source_count"] == 1
    assert bundle["resolved_source_count"] == 1
    assert bundle["unresolved_source_count"] == 0
    assert bundle["primary_source_url"] == "https://example.org/article/S1"
    assert bundle["primary_source_title"] == "Case report: interaction with warfarin"


def test_build_source_bundle_multiple_sources_and_duplicate_ids():
    bundle = build_source_bundle(["S1", "S2", "S1"], _evidence_df())
    # normalize_evidence_ids dedupes while preserving order (existing contract)
    assert bundle["record_ids"] == ["S1", "S2"]
    assert bundle["source_count"] == 2
    assert bundle["resolved_source_count"] == 2


def test_build_source_bundle_unresolved_record():
    bundle = build_source_bundle(["S1", "SXX"], _evidence_df())
    assert bundle["source_count"] == 2
    assert bundle["resolved_source_count"] == 1
    assert bundle["unresolved_source_count"] == 1


def test_build_source_bundle_internal_only_provenance():
    bundle = build_source_bundle(["S2"], _evidence_df())
    assert bundle["resolved_source_count"] == 1
    assert bundle["primary_source_url"] is None
    assert bundle["sources"][0]["Resolution_Status"] == "INTERNAL_ID_ONLY"


def test_build_source_bundle_custom_rank_fn():
    # A custom rank_fn must control which resolved source is primary.
    def _prefer_s2(source):
        return (0 if source.get("Evidence_Record_ID") == "S2" else 1, "")

    bundle = build_source_bundle(["S1", "S2"], _evidence_df(), rank_fn=_prefer_s2)
    assert bundle["primary_source_title"] == "Internal safety note"


# ---------------------------------------------------------------------------
# attach_safety_evidence_source_traceability
# ---------------------------------------------------------------------------

def test_safety_serious_concern_with_resolved_source():
    report_df = pd.DataFrame([{
        "Safety_Concern_Level": "SERIOUS",
        "Safety_Evidence_IDs": ["S1"],
    }])
    out = attach_safety_evidence_source_traceability(report_df, _evidence_df())
    row = out.iloc[0]
    assert row["Safety_Source_Count"] == 1
    assert row["Safety_Primary_Source_URL"] == "https://example.org/article/S1"
    assert row["Safety_Source_Resolution_Status"] == "ALL_RECORDS_RESOLVED"


def test_safety_serious_concern_missing_ids_flags_incomplete():
    report_df = pd.DataFrame([{
        "Safety_Concern_Level": "SERIOUS",
        "Safety_Evidence_IDs": [],
    }])
    out = attach_safety_evidence_source_traceability(report_df, _evidence_df())
    row = out.iloc[0]
    assert row["Safety_Source_Count"] == 0
    assert row["Safety_Source_Resolution_Status"] == "SOURCE_LINKAGE_INCOMPLETE"


def test_safety_non_serious_no_ids_is_not_flagged_incomplete():
    report_df = pd.DataFrame([{
        "Safety_Concern_Level": "LOW",
        "Safety_Evidence_IDs": [],
    }])
    out = attach_safety_evidence_source_traceability(report_df, _evidence_df())
    row = out.iloc[0]
    assert row["Safety_Source_Resolution_Status"] == "NO_SAFETY_EVIDENCE_IDS"


def test_safety_unresolved_id_counts_as_unresolved():
    report_df = pd.DataFrame([{
        "Safety_Concern_Level": "MODERATE",
        "Safety_Evidence_IDs": ["SXX"],
    }])
    out = attach_safety_evidence_source_traceability(report_df, _evidence_df())
    row = out.iloc[0]
    assert row["Safety_Unresolved_Source_Count"] == 1
    assert row["Safety_Source_Resolution_Status"] == "SOURCE_LINKAGE_INCOMPLETE"


def test_safety_source_never_reused_from_unrelated_efficacy_record():
    """No source-laundering (spec §23): only Safety_Evidence_IDs are resolved,
    never a generic efficacy record that happens to share the same plant."""
    evidence_df = pd.DataFrame([
        {"Evidence_Record_ID": "EFF1", "Source_Title": "Efficacy RCT", "Source_URL": "https://example.org/eff1"},
        {"Evidence_Record_ID": "S1", "Source_Title": "Safety case report", "Source_URL": "https://example.org/s1"},
    ])
    report_df = pd.DataFrame([{
        "Safety_Concern_Level": "MODERATE",
        "Safety_Evidence_IDs": ["S1"],
        "Direct_Human_Outcome_Evidence_IDs": ["EFF1"],
    }])
    out = attach_safety_evidence_source_traceability(report_df, evidence_df)
    sources = json.loads(out.iloc[0]["Safety_Sources_JSON"])
    ids = [s["Evidence_Record_ID"] for s in sources]
    assert ids == ["S1"]
    assert "EFF1" not in ids


def test_safety_empty_report_df_returns_unchanged():
    empty = pd.DataFrame()
    assert attach_safety_evidence_source_traceability(empty, _evidence_df()).empty
