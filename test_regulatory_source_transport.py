import pandas as pd

from claim_source_map import attach_regulatory_patent_source_traceability


def test_regulatory_stays_not_integrated_with_no_landscape_data():
    report_df = pd.DataFrame([{"Alternative_Plant": "Plantus exampleus"}])
    out = attach_regulatory_patent_source_traceability(report_df)
    row = out.iloc[0]
    assert row["Regulatory_Source_Count"] == 0
    assert row["Regulatory_Primary_Source_URL"] is None
    assert row["Regulatory_Source_Status"] == "NOT_INTEGRATED"


def test_genuine_landscape_url_is_transported_to_stage6():
    report_df = pd.DataFrame([{"Alternative_Plant": "Withania somnifera"}])
    landscape_df = pd.DataFrame([{
        "Alternative_Plant": "Withania somnifera",
        "Market_Landscape_Regulatory_Source": (
            "EMA HMPC monograph on Withania somnifera "
            "(https://www.ema.europa.eu/en/medicines/herbal/withania-somnifera)"
        ),
        "Market_Landscape_EMA_HMPC_Detail": "Traditional use registered",
        "Market_Landscape_EMA_HMPC_Status": "Registered",
    }])
    out = attach_regulatory_patent_source_traceability(report_df, landscape_df)
    row = out.iloc[0]
    assert row["Regulatory_Source_Count"] == 1
    assert row["Regulatory_Primary_Source_URL"] == (
        "https://www.ema.europa.eu/en/medicines/herbal/withania-somnifera"
    )
    assert row["Regulatory_Source_Status"] == "ASSESSED"
    assert row["Regulatory_Authority"] == "EMA / HMPC"


def test_landscape_entry_without_an_embedded_url_stays_not_integrated():
    """Descriptive-only regulatory text (no real URL embedded) must never be
    promoted into a fabricated source."""
    report_df = pd.DataFrame([{"Alternative_Plant": "Unresolved plantus"}])
    landscape_df = pd.DataFrame([{
        "Alternative_Plant": "Unresolved plantus",
        "Market_Landscape_Regulatory_Source": (
            "No EMA HMPC bulk API exists (browse-only site) — needs manual lookup."
        ),
    }])
    out = attach_regulatory_patent_source_traceability(report_df, landscape_df)
    row = out.iloc[0]
    assert row["Regulatory_Source_Count"] == 0
    assert row["Regulatory_Primary_Source_URL"] is None
    assert row["Regulatory_Source_Status"] == "NOT_INTEGRATED"


def test_landscape_data_for_a_different_plant_is_not_misattributed():
    report_df = pd.DataFrame([{"Alternative_Plant": "Plant A"}])
    landscape_df = pd.DataFrame([{
        "Alternative_Plant": "Plant B",
        "Market_Landscape_Regulatory_Source": "EMA note (https://www.ema.europa.eu/plant-b)",
    }])
    out = attach_regulatory_patent_source_traceability(report_df, landscape_df)
    row = out.iloc[0]
    assert row["Regulatory_Source_Count"] == 0
    assert row["Regulatory_Primary_Source_URL"] is None


def test_row_already_carrying_a_real_regulatory_url_is_not_overridden_by_landscape():
    report_df = pd.DataFrame([{
        "Alternative_Plant": "Plantus exampleus",
        "Regulatory_Assessment_Status": "ASSESSED",
        "Regulatory_Source_URL": "https://www.ema.europa.eu/en/medicines/herbal/direct-record",
        "Regulatory_Primary_Source_Title": "Direct EMA record",
    }])
    landscape_df = pd.DataFrame([{
        "Alternative_Plant": "Plantus exampleus",
        "Market_Landscape_Regulatory_Source": "Other note (https://www.ema.europa.eu/other)",
    }])
    out = attach_regulatory_patent_source_traceability(report_df, landscape_df)
    row = out.iloc[0]
    assert row["Regulatory_Primary_Source_URL"] == (
        "https://www.ema.europa.eu/en/medicines/herbal/direct-record"
    )


def test_patent_stays_not_integrated_with_no_patent_data():
    report_df = pd.DataFrame([{"Alternative_Plant": "Plantus exampleus"}])
    out = attach_regulatory_patent_source_traceability(report_df)
    row = out.iloc[0]
    assert row["Patent_Source_Count"] == 0
    assert row["Patent_Primary_Source_URL"] is None
    assert row["Patent_Source_Status"] == "NOT_INTEGRATED"


def test_no_network_call_is_made_reading_a_landscape_frame():
    """The landscape frame is treated as already-computed input data --
    this function must be pure/offline (no patched network client needed
    for it to work), proving no new search happens here."""
    report_df = pd.DataFrame([{"Alternative_Plant": "Plantus exampleus"}])
    landscape_df = pd.DataFrame([{
        "Alternative_Plant": "Plantus exampleus",
        "Market_Landscape_Regulatory_Source": "EMA (https://www.ema.europa.eu/x)",
    }])
    # No mocking of any network/AI client -- if this function tried to
    # reach out, it would raise (no such client is even importable here).
    out = attach_regulatory_patent_source_traceability(report_df, landscape_df)
    assert out.iloc[0]["Regulatory_Source_Count"] == 1
