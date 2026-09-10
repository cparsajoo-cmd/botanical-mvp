import pandas as pd

from source_linkage_consistency import (
    attach_source_linkage_consistency,
    check_source_linkage_consistency,
)


def test_no_issues_when_everything_resolved():
    row = pd.Series({
        "Human_Evidence_Source_Resolution_Status": "ALL_RECORDS_RESOLVED",
        "Safety_Source_Resolution_Status": "ALL_RECORDS_RESOLVED",
        "Safety_Concern_Level": "LOW",
        "Commercial_Source_Resolution_Status": "ALL_RECORDS_RESOLVED",
        "Commercial_Status_Overall": "VERIFIED_MARKETED",
        "Commercial_Source_Count": 2,
        "Regulatory_Source_Status": "NOT_INTEGRATED",
        "Regulatory_Source_Count": 0,
        "Patent_Source_Status": "NOT_INTEGRATED",
        "Patent_Source_Count": 0,
    })
    assert check_source_linkage_consistency(row) == []


def test_serious_safety_without_resolved_source_flagged():
    row = pd.Series({
        "Safety_Source_Resolution_Status": "SOURCE_LINKAGE_INCOMPLETE",
        "Safety_Concern_Level": "SERIOUS",
    })
    issues = check_source_linkage_consistency(row)
    assert any("SERIOUS" in i for i in issues)


def test_marketed_claim_with_zero_commercial_sources_flagged():
    row = pd.Series({
        "Commercial_Status_Overall": "CROWDED_MARKET",
        "Commercial_Source_Count": 0,
    })
    issues = check_source_linkage_consistency(row)
    assert any("Commercial" in i for i in issues)


def test_regulatory_assessed_with_zero_sources_flagged():
    row = pd.Series({
        "Regulatory_Source_Status": "ASSESSED",
        "Regulatory_Source_Count": 0,
    })
    issues = check_source_linkage_consistency(row)
    assert any("Regulatory" in i for i in issues)


def test_patent_assessed_with_zero_sources_flagged():
    row = pd.Series({
        "Patent_Source_Status": "ASSESSED",
        "Patent_Source_Count": 0,
    })
    issues = check_source_linkage_consistency(row)
    assert any("Patent" in i for i in issues)


def test_regulatory_not_integrated_with_zero_sources_not_flagged():
    row = pd.Series({
        "Regulatory_Source_Status": "NOT_INTEGRATED",
        "Regulatory_Source_Count": 0,
    })
    assert check_source_linkage_consistency(row) == []


def test_attach_source_linkage_consistency_status_column():
    report_df = pd.DataFrame([{
        "Safety_Source_Resolution_Status": "SOURCE_LINKAGE_INCOMPLETE",
        "Safety_Concern_Level": "SERIOUS",
    }])
    out = attach_source_linkage_consistency(report_df)
    row = out.iloc[0]
    assert row["Evidence_Source_Linkage_Status"] == "SOURCE_LINKAGE_INCOMPLETE"
    assert "SERIOUS" in row["Evidence_Source_Linkage_Issues"]


def test_attach_source_linkage_consistency_ok_status():
    report_df = pd.DataFrame([{"Safety_Concern_Level": "LOW"}])
    out = attach_source_linkage_consistency(report_df)
    assert out.iloc[0]["Evidence_Source_Linkage_Status"] == "SOURCE_LINKAGE_OK"


def test_empty_report_df_returns_unchanged():
    empty = pd.DataFrame()
    assert attach_source_linkage_consistency(empty).empty
