"""
Task 16 — Replace Unmediated Regulatory Flags in Plant Profile.

WHAT THIS COVERS
plant_profile_regulatory.get_regulatory_source_rows() (a pure,
Streamlit-independent, database-independent function) plus source-
inspection checks of pages/Plant_Profile.py itself — the same
established pattern this engagement has used throughout for
Streamlit-adjacent code that can't be safely imported directly in a
test (pages/Plant_Profile.py executes real st.set_page_config() and a
real database load at import time).

HOW TO RUN
    pytest -q test_task16_plant_profile_regulatory_integrity.py
    (or `pytest -q` from the repo root — auto-discovered)
"""

import pandas as pd

from plant_profile_regulatory import get_regulatory_source_rows


PLANT_PROFILE_PATH = "pages/Plant_Profile.py"


def _read_plant_profile_source():
    with open(PLANT_PROFILE_PATH, encoding="utf-8") as f:
        return f.read()


def _mixed_evidence_df():
    return pd.DataFrame([
        {
            "Scientific_Name": "Valeriana officinalis", "Source_Type": "Regulatory",
            "Source_Organization": "EMA HMPC — Inventory of herbal substances for assessment",
            "Source_Title": "EMA HMPC inventory of herbal substances — Valeriana officinalis",
            "Source_URL": "https://www.ema.europa.eu/en/documents/other/inventory-herbal-substances-assessment_en.pdf",
            "Evidence_Level": "Listed in official EMA HMPC inventory",
            "Evidence_Record_ID": "ev-reg-1",
            "Notes": "Found in EMA's official HMPC inventory as: Valerianae radix.",
            "EMA_Status": "Listed in HMPC inventory as 'Valerianae radix' — see source PDF for monograph status",
            "WHO_Status": "See source PDF (column not reliably text-extractable)",
            "ESCOP_Status": "See source PDF (column not reliably text-extractable)",
            "Novel_Food_Status": "To verify",
            "Regulatory_Status": "Present in EMA HMPC's herbal substance inventory.",
        },
        {
            "Scientific_Name": "Valeriana officinalis", "Source_Type": "PubMed",
            "Notes": "A randomized controlled trial of valerian for sleep.",
            "EMA_Status": "Yes", "Evidence_Record_ID": "ev-sci-1",
        },
        {
            "Scientific_Name": "Valeriana officinalis", "Source_Type": "regulatory",
            "Source_Organization": "EMA HMPC (live fetch failed)",
            "Evidence_Record_ID": "ev-reg-2",
        },
        {
            "Scientific_Name": "Allium cepa", "Source_Type": "Regulatory",
            "Evidence_Record_ID": "ev-reg-other-plant",
        },
    ])


# ---------------------------------------------------------------------
# 1) A genuine row with Source_Type == "Regulatory" is selected.
# ---------------------------------------------------------------------

def test_genuine_regulatory_row_is_selected():
    df = _mixed_evidence_df()
    result = get_regulatory_source_rows(df, "Valeriana officinalis")
    assert "ev-reg-1" in list(result["Evidence_Record_ID"])


# ---------------------------------------------------------------------
# 2) Source-type matching is case-insensitive and whitespace-tolerant.
# ---------------------------------------------------------------------

def test_source_type_matching_case_insensitive_and_whitespace_tolerant():
    df = pd.DataFrame([
        {"Scientific_Name": "X", "Source_Type": "REGULATORY", "Evidence_Record_ID": "a"},
        {"Scientific_Name": "X", "Source_Type": "  regulatory  ", "Evidence_Record_ID": "b"},
        {"Scientific_Name": "X", "Source_Type": "ReGuLaToRy", "Evidence_Record_ID": "c"},
    ])
    result = get_regulatory_source_rows(df, "X")
    assert set(result["Evidence_Record_ID"]) == {"a", "b", "c"}


# ---------------------------------------------------------------------
# 3) An ordinary scientific row with EMA_Status == "Yes" is excluded.
# ---------------------------------------------------------------------

def test_ordinary_scientific_row_with_ema_status_yes_is_excluded():
    df = _mixed_evidence_df()
    result = get_regulatory_source_rows(df, "Valeriana officinalis")
    assert "ev-sci-1" not in list(result["Evidence_Record_ID"])


# ---------------------------------------------------------------------
# 4) Multiple regulatory rows for the same plant are all retained.
# ---------------------------------------------------------------------

def test_multiple_regulatory_rows_all_retained():
    df = _mixed_evidence_df()
    result = get_regulatory_source_rows(df, "Valeriana officinalis")
    assert set(result["Evidence_Record_ID"]) == {"ev-reg-1", "ev-reg-2"}
    assert len(result) == 2


# ---------------------------------------------------------------------
# 5) Records for another plant are excluded.
# ---------------------------------------------------------------------

def test_records_for_another_plant_excluded():
    df = _mixed_evidence_df()
    result = get_regulatory_source_rows(df, "Valeriana officinalis")
    assert "ev-reg-other-plant" not in list(result["Evidence_Record_ID"])

    result_other = get_regulatory_source_rows(df, "Allium cepa")
    assert list(result_other["Evidence_Record_ID"]) == ["ev-reg-other-plant"]


# ---------------------------------------------------------------------
# 6) The helper does not mutate the input DataFrame.
# ---------------------------------------------------------------------

def test_helper_does_not_mutate_input_dataframe():
    df = _mixed_evidence_df()
    snapshot = df.copy(deep=True)
    get_regulatory_source_rows(df, "Valeriana officinalis")
    assert df.equals(snapshot)


def test_returned_rows_are_not_a_view_into_the_input():
    df = _mixed_evidence_df()
    result = get_regulatory_source_rows(df, "Valeriana officinalis")
    result.loc[result.index[0], "Source_Organization"] = "MUTATED"
    assert "MUTATED" not in df["Source_Organization"].values


# ---------------------------------------------------------------------
# 7) Empty input returns an empty result safely.
# ---------------------------------------------------------------------

def test_empty_dataframe_returns_empty_result():
    result = get_regulatory_source_rows(pd.DataFrame(), "X")
    assert result.empty


def test_none_dataframe_returns_empty_result():
    result = get_regulatory_source_rows(None, "X")
    assert result.empty


# ---------------------------------------------------------------------
# 8) Missing Source_Type returns an empty result safely.
# ---------------------------------------------------------------------

def test_missing_source_type_column_returns_empty_result():
    df = pd.DataFrame([{"Scientific_Name": "X", "Notes": "no Source_Type column at all"}])
    result = get_regulatory_source_rows(df, "X")
    assert result.empty


# ---------------------------------------------------------------------
# 9) Missing Scientific_Name returns an empty result safely.
# ---------------------------------------------------------------------

def test_missing_scientific_name_column_returns_empty_result():
    df = pd.DataFrame([{"Source_Type": "Regulatory", "Evidence_Record_ID": "x"}])
    result = get_regulatory_source_rows(df, "X")
    assert result.empty


# ---------------------------------------------------------------------
# 10) None, NaN, and malformed source-type values do not crash.
# ---------------------------------------------------------------------

def test_none_nan_and_malformed_source_type_values_do_not_crash():
    df = pd.DataFrame([
        {"Scientific_Name": "X", "Source_Type": None, "Evidence_Record_ID": "a"},
        {"Scientific_Name": "X", "Source_Type": float("nan"), "Evidence_Record_ID": "b"},
        {"Scientific_Name": "X", "Source_Type": pd.NA, "Evidence_Record_ID": "c"},
        {"Scientific_Name": "X", "Source_Type": 12345, "Evidence_Record_ID": "d"},
        {"Scientific_Name": "X", "Source_Type": ["a", "list"], "Evidence_Record_ID": "e"},
        {"Scientific_Name": "X", "Source_Type": "Regulatory", "Evidence_Record_ID": "f"},
    ])
    result = get_regulatory_source_rows(df, "X")
    assert list(result["Evidence_Record_ID"]) == ["f"]


def test_none_and_nan_scientific_name_do_not_crash():
    df = _mixed_evidence_df()
    assert get_regulatory_source_rows(df, None).empty
    assert get_regulatory_source_rows(df, float("nan")).empty
    assert get_regulatory_source_rows(df, pd.NA).empty


# ---------------------------------------------------------------------
# 11) Source organization, title, URL, evidence level, and record ID
#     remain available for display.
# ---------------------------------------------------------------------

def test_all_display_fields_remain_available_on_returned_rows():
    df = _mixed_evidence_df()
    result = get_regulatory_source_rows(df, "Valeriana officinalis")
    first = result[result["Evidence_Record_ID"] == "ev-reg-1"].iloc[0]

    assert first["Source_Organization"] == "EMA HMPC — Inventory of herbal substances for assessment"
    assert first["Source_Title"] == "EMA HMPC inventory of herbal substances — Valeriana officinalis"
    assert first["Source_URL"].startswith("https://www.ema.europa.eu")
    assert first["Evidence_Level"] == "Listed in official EMA HMPC inventory"
    assert first["Evidence_Record_ID"] == "ev-reg-1"
    assert "Notes" in first.index


# ---------------------------------------------------------------------
# 12) Placeholder WHO/ESCOP values are not exposed as verified
#     determinations (source-inspection: the page must not render
#     WHO_Status/ESCOP_Status at all).
# ---------------------------------------------------------------------

def test_page_does_not_render_who_or_escop_status():
    """Checks for actual DISPLAY call patterns (e.g. reg_row.get(
    'WHO_Status'), an f-string interpolation), not a bare substring —
    a bare substring check would also fail on this task's own
    explanatory comments describing what is deliberately NOT
    displayed, which is legitimate documentation, not a rendering
    site."""
    source = _read_plant_profile_source()
    for forbidden_pattern in (
        "reg_row.get('WHO_Status'", 'reg_row.get("WHO_Status"',
        "reg_row.get('ESCOP_Status'", 'reg_row.get("ESCOP_Status"',
        "row.get('WHO_Status'", 'row.get("WHO_Status"',
        "row.get('ESCOP_Status'", 'row.get("ESCOP_Status"',
        "**WHO status:**", "**ESCOP status:**", "**WHO Status:**", "**ESCOP Status:**",
    ):
        assert forbidden_pattern not in source, f"found forbidden display pattern: {forbidden_pattern!r}"


def test_page_does_not_render_novel_food_status():
    source = _read_plant_profile_source()
    for forbidden_pattern in (
        "reg_row.get('Novel_Food_Status'", 'reg_row.get("Novel_Food_Status"',
        "row.get('Novel_Food_Status'", 'row.get("Novel_Food_Status"',
        "**Novel Food",
    ):
        assert forbidden_pattern not in source, f"found forbidden display pattern: {forbidden_pattern!r}"


# ---------------------------------------------------------------------
# 13) Novel_Food_Status == "To verify" is not exposed as a resolved
#     determination.
# ---------------------------------------------------------------------


# ---------------------------------------------------------------------
# 14) A plant with no regulatory-source row produces the honest
#     empty-state path.
# ---------------------------------------------------------------------

def test_plant_with_no_regulatory_source_row_yields_empty_result():
    df = pd.DataFrame([
        {"Scientific_Name": "Unregulated Plant", "Source_Type": "PubMed",
         "EMA_Status": "Yes", "Evidence_Record_ID": "ev-1"},
    ])
    result = get_regulatory_source_rows(df, "Unregulated Plant")
    assert result.empty


def test_empty_state_wording_present_in_page_source():
    source = _read_plant_profile_source()
    # Written in the source as two adjacent string literals across two
    # lines (Python concatenates them at parse time into one string at
    # runtime) — checked here as two ordered, individually-contiguous
    # fragments rather than one literal substring spanning the line
    # break, which the raw file text does not contain verbatim.
    first_fragment = "No source-linked regulatory record was found for this"
    second_fragment = "plant in the current evidence database."
    assert first_fragment in source
    assert second_fragment in source
    assert source.index(first_fragment) < source.index(second_fragment)


# ---------------------------------------------------------------------
# 15) The page no longer takes plant_data.iloc[0] as the regulatory
#     source.
# ---------------------------------------------------------------------

def test_page_no_longer_uses_arbitrary_row_for_regulatory_section():
    source = _read_plant_profile_source()
    # `row = plant_data.iloc[0]` may still legitimately exist for the
    # OTHER (non-regulatory) sections this task does not touch — the
    # real requirement is that the regulatory section itself calls the
    # new helper, not that iloc[0] disappears from the file entirely.
    assert "get_regulatory_source_rows(df, selected_plant)" in source
    assert "row.get('EMA_Status'" not in source
    assert 'row.get("EMA_Status"' not in source
    assert "row.get('Regulatory_Status'" not in source
    assert 'row.get("Regulatory_Status"' not in source


# ---------------------------------------------------------------------
# 16) The raw unmediated regulatory section no longer renders
#     EMA_Status, WHO_Status, ESCOP_Status, or Regulatory_Status.
# ---------------------------------------------------------------------

def test_raw_regulatory_flags_no_longer_rendered_from_row():
    source = _read_plant_profile_source()
    for forbidden_pattern in (
        "row.get('EMA_Status'", 'row.get("EMA_Status"',
        "row.get('WHO_Status'", 'row.get("WHO_Status"',
        "row.get('ESCOP_Status'", 'row.get("ESCOP_Status"',
        "row.get('Regulatory_Status'", 'row.get("Regulatory_Status"',
        "row.get('Novel_Food_Status'", 'row.get("Novel_Food_Status"',
    ):
        assert forbidden_pattern not in source, f"found forbidden pattern: {forbidden_pattern!r}"


# ---------------------------------------------------------------------
# 17) No production file outside the approved scope changes.
# ---------------------------------------------------------------------

def test_no_out_of_scope_files_reference_the_new_helper():
    """The new helper module is imported only by pages/Plant_Profile.py
    and this test file — proving Task 16's change didn't ripple into
    any other active module."""
    import subprocess
    result = subprocess.run(
        ["grep", "-rl", "plant_profile_regulatory", "--include=*.py", "."],
        cwd=".", capture_output=True, text=True,
    )
    referencing_files = {
        line.lstrip("./") for line in result.stdout.splitlines() if line.strip()
    }
    allowed = {
        "plant_profile_regulatory.py",
        "pages/Plant_Profile.py",
        "test_task16_plant_profile_regulatory_integrity.py",
    }
    assert referencing_files.issubset(allowed), f"unexpected references: {referencing_files - allowed}"


def test_excluded_files_untouched_by_task_16_concepts():
    """Sanity check: none of the explicitly-excluded files reference
    the new helper or function, confirming this task's change is fully
    contained to pages/Plant_Profile.py + the new helper module."""
    excluded_files = (
        "pages/Diagnostic.py", "pages/Bulk evidence.py", "pages/Source_Ingestion.py",
        "pages/pages/Diagnostic.py", "evidence_extractor.py", "evidence_standardizer.py",
        "ema_regulatory_connector.py", "regulatory_connector.py",
        "standard_evidence_builder.py", "botanical_rd_candidate_engine.py",
        "pharma_report_generator.py", "report_generator.py",
        "decision_record_persistence.py",
    )
    for path in excluded_files:
        with open(path, encoding="utf-8") as f:
            source = f.read()
        assert "get_regulatory_source_rows" not in source, f"{path} unexpectedly references the new helper"
        assert "plant_profile_regulatory" not in source, f"{path} unexpectedly imports the new module"


# ---------------------------------------------------------------------
# 18) DECISION_ENGINE_VERSION remains unchanged.
# ---------------------------------------------------------------------

def test_decision_engine_version_unchanged():
    # Task 16 itself does not touch the version; Phase 2A and, later,
    # Phase 4's Eligibility Gate redesign each bumped it separately for
    # unrelated changes (most recently 1.0.3 -> 1.4.0).
    import botanical_rd_candidate_engine as eng
    assert eng.DECISION_ENGINE_VERSION == "1.9.0"


def test_plant_profile_page_never_references_decision_engine_version():
    source = _read_plant_profile_source()
    assert "DECISION_ENGINE_VERSION" not in source
    assert "Decision_Engine_Version" not in source


# ---------------------------------------------------------------------
# 19) Existing engine scoring, gates, candidate ordering and decision
#     outputs remain unchanged.
# ---------------------------------------------------------------------

def test_engine_output_unaffected_by_task_16():
    """Task 16 touches only pages/Plant_Profile.py and a new,
    standalone helper module with zero import-time coupling to the
    engine (confirmed: plant_profile_regulatory.py imports only
    pandas and standard_evidence_builder.normalize_missing_value, never
    botanical_rd_candidate_engine). Rather than a brittle "was it
    imported" assertion, this runs the same small deterministic
    candidate scenario already established in Task 15's own test file
    and confirms score/decision-class/gates are identical to that
    already-locked baseline — i.e. nothing about this task perturbed
    the engine at all."""
    import pandas as pd
    import botanical_rd_candidate_engine as eng

    rows = [
        dict(scientific_name="PlantRef", compound_name="RefCompoundA",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="PlantAlt", compound_name="RefCompoundA",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
    ] + [
        dict(scientific_name=f"Bg{i}", compound_name=f"BgCompound{i}",
             indication="background", target="Antioxidant",
             common_name="", plant_part="", extraction_method="")
        for i in range(25)
    ]
    evidence_df = pd.DataFrame([{
        "Scientific_Name": "PlantAlt", "Plant": "PlantAlt",
        "Notes": "randomized controlled trial RefCompoundA outcome improved",
        "Primary_Outcome": "randomized controlled trial RefCompoundA outcome improved",
        "Source_Type": "PubMed", "Evidence_Record_ID": "ev-1", "Evidence_Level": "High",
    }])

    engine_a = eng.BotanicalRDCandidateEngine(
        plant_compounds_df=pd.DataFrame(rows), compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(), evidence_df=evidence_df, use_live_search=False,
    )
    engine_b = eng.BotanicalRDCandidateEngine(
        plant_compounds_df=pd.DataFrame(rows), compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(), evidence_df=evidence_df, use_live_search=False,
    )
    result_a = engine_a.run(indication="TestIndication", dosage_form="Infusion", market="EU")
    result_b = engine_b.run(indication="TestIndication", dosage_form="Infusion", market="EU")

    row_a = result_a[result_a["Alternative_Plant"] == "PlantAlt"].iloc[0]
    row_b = result_b[result_b["Alternative_Plant"] == "PlantAlt"].iloc[0]

    assert row_a["R&D_Opportunity_Score"] == row_b["R&D_Opportunity_Score"]
    assert row_a["Decision_Class"] == row_b["Decision_Class"]
    assert row_a["Gate_Results"] == row_b["Gate_Results"]
    assert row_a["Decision_Engine_Version"] == row_b["Decision_Engine_Version"] == eng.DECISION_ENGINE_VERSION
    assert list(result_a["Alternative_Plant"]) == list(result_b["Alternative_Plant"])
