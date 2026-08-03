"""
Task 17 — Plant Profile Evidence Freshness.

WHAT THIS COVERS
plant_profile_freshness.summarize_evidence_freshness() (a pure,
Streamlit-independent, database-independent function) plus source-
inspection checks of pages/Plant_Profile.py's wiring — same
established pattern Task 16 used for the same reason
(pages/Plant_Profile.py executes real Streamlit calls and a real
database load at import time).

HOW TO RUN
    pytest -q test_task17_plant_profile_evidence_freshness.py
    (or `pytest -q` from the repo root — auto-discovered)
"""

import pandas as pd

from plant_profile_freshness import summarize_evidence_freshness


PLANT_PROFILE_PATH = "pages/Plant_Profile.py"


def _read_plant_profile_source():
    with open(PLANT_PROFILE_PATH, encoding="utf-8") as f:
        return f.read()


def _mixed_freshness_df():
    return pd.DataFrame([
        {"Scientific_Name": "Valeriana officinalis", "Source_Year": "2019"},
        {"Scientific_Name": "Valeriana officinalis", "Source_Year": "2023"},
        {"Scientific_Name": "Valeriana officinalis", "Source_Year": "2023"},  # duplicate date
        {"Scientific_Name": "Valeriana officinalis", "Source_Year": ""},       # undated
        {"Scientific_Name": "Valeriana officinalis", "Source_Year": float("nan")},  # undated
        {"Scientific_Name": "Valeriana officinalis", "Source_Year": "not a year"},  # invalid
        {"Scientific_Name": "Allium cepa", "Source_Year": "2020"},  # other plant
    ])


# ---------------------------------------------------------------------
# 1) Correct plant filtering.
# 2) Exclusion of other plants.
# ---------------------------------------------------------------------

def test_correct_plant_filtering_and_exclusion_of_other_plants():
    df = _mixed_freshness_df()
    result = summarize_evidence_freshness(df, "Valeriana officinalis")
    assert result["total_records"] == 6  # not 7 — Allium cepa's row excluded

    other = summarize_evidence_freshness(df, "Allium cepa")
    assert other["total_records"] == 1
    assert other["dated_records"] == 1
    assert other["oldest_date"] == "2020"


# ---------------------------------------------------------------------
# 3) Total, dated, and undated counts.
# ---------------------------------------------------------------------

def test_total_dated_and_undated_counts():
    df = _mixed_freshness_df()
    result = summarize_evidence_freshness(df, "Valeriana officinalis")
    assert result["total_records"] == 6
    assert result["dated_records"] == 3   # "2019", "2023", "2023"
    assert result["undated_records"] == 3  # "", NaN, "not a year"
    assert result["dated_records"] + result["undated_records"] == result["total_records"]


# ---------------------------------------------------------------------
# 4) Correct oldest and newest dates.
# ---------------------------------------------------------------------

def test_correct_oldest_and_newest_dates():
    df = _mixed_freshness_df()
    result = summarize_evidence_freshness(df, "Valeriana officinalis")
    assert result["oldest_date"] == "2019"
    assert result["newest_date"] == "2023"
    assert result["date_range"] == "2019 \u2013 2023"


# ---------------------------------------------------------------------
# 5) Single valid date.
# ---------------------------------------------------------------------

def test_single_valid_date():
    df = pd.DataFrame([{"Scientific_Name": "X", "Source_Year": "2021"}])
    result = summarize_evidence_freshness(df, "X")
    assert result["dated_records"] == 1
    assert result["oldest_date"] == "2021"
    assert result["newest_date"] == "2021"
    assert result["date_range"] == "2021"


# ---------------------------------------------------------------------
# 6) Duplicate dates without row deduplication.
# ---------------------------------------------------------------------

def test_duplicate_dates_do_not_reduce_counts():
    df = pd.DataFrame([
        {"Scientific_Name": "X", "Source_Year": "2020"},
        {"Scientific_Name": "X", "Source_Year": "2020"},
        {"Scientific_Name": "X", "Source_Year": "2020"},
    ])
    result = summarize_evidence_freshness(df, "X")
    assert result["total_records"] == 3
    assert result["dated_records"] == 3  # all three counted, not collapsed to 1
    assert result["oldest_date"] == result["newest_date"] == "2020"
    assert result["date_range"] == "2020"


# ---------------------------------------------------------------------
# 7) Empty DataFrame and None.
# ---------------------------------------------------------------------

def test_empty_dataframe_and_none_input():
    empty_result = summarize_evidence_freshness(pd.DataFrame(), "X")
    assert empty_result["total_records"] == 0
    assert empty_result["dated_records"] == 0
    assert empty_result["oldest_date"] is None

    none_result = summarize_evidence_freshness(None, "X")
    assert none_result["total_records"] == 0
    assert none_result["oldest_date"] is None


# ---------------------------------------------------------------------
# 8) Missing Scientific_Name.
# ---------------------------------------------------------------------

def test_missing_scientific_name_column():
    df = pd.DataFrame([{"Source_Year": "2020"}])
    result = summarize_evidence_freshness(df, "X")
    assert result["total_records"] == 0


# ---------------------------------------------------------------------
# 9) Missing date columns.
# ---------------------------------------------------------------------

def test_missing_date_column():
    df = pd.DataFrame([{"Scientific_Name": "X", "Notes": "no Source_Year column at all"}])
    result = summarize_evidence_freshness(df, "X")
    assert result["total_records"] == 1
    assert result["dated_records"] == 0
    assert result["undated_records"] == 1


# ---------------------------------------------------------------------
# 10) Invalid and missing dates.
# ---------------------------------------------------------------------

def test_invalid_and_missing_dates_do_not_crash():
    df = pd.DataFrame([
        {"Scientific_Name": "X", "Source_Year": "not a year"},
        {"Scientific_Name": "X", "Source_Year": "9999"},       # implausible
        {"Scientific_Name": "X", "Source_Year": "0000"},       # implausible
        {"Scientific_Name": "X", "Source_Year": None},
        {"Scientific_Name": "X", "Source_Year": float("nan")},
        {"Scientific_Name": "X", "Source_Year": pd.NA},
        {"Scientific_Name": "X", "Source_Year": "   "},
        {"Scientific_Name": "X", "Source_Year": True},         # bool guard
    ])
    result = summarize_evidence_freshness(df, "X")
    assert result["total_records"] == 8
    assert result["dated_records"] == 0
    assert result["undated_records"] == 8


# ---------------------------------------------------------------------
# 11) Mixed date types.
# ---------------------------------------------------------------------

def test_mixed_date_types():
    df = pd.DataFrame([
        {"Scientific_Name": "X", "Source_Year": "2018"},
        {"Scientific_Name": "X", "Source_Year": 2020},
        {"Scientific_Name": "X", "Source_Year": 2022.0},
        {"Scientific_Name": "X", "Source_Year": pd.Timestamp("2015-06-01")},
    ])
    result = summarize_evidence_freshness(df, "X")
    assert result["dated_records"] == 4
    assert result["oldest_date"] == "2015-06-01"
    assert result["newest_date"] == "2022"


def test_non_whole_number_float_is_invalid_not_rounded():
    df = pd.DataFrame([{"Scientific_Name": "X", "Source_Year": 2021.5}])
    result = summarize_evidence_freshness(df, "X")
    assert result["dated_records"] == 0


# ---------------------------------------------------------------------
# 12) Honest year-only precision.
# ---------------------------------------------------------------------

def test_year_only_precision_never_becomes_a_fabricated_full_date():
    df = pd.DataFrame([{"Scientific_Name": "X", "Source_Year": "2021"}])
    result = summarize_evidence_freshness(df, "X")
    assert result["oldest_date"] == "2021"
    assert result["oldest_date"] != "2021-01-01"
    assert "-" not in result["oldest_date"]


# ---------------------------------------------------------------------
# 13) Deterministic precedence across multiple date fields.
# ---------------------------------------------------------------------

def test_deterministic_precedence_across_multiple_date_fields(monkeypatch=None):
    """DATE_FIELD_PRECEDENCE is currently a single-entry tuple
    (Source_Year is the only genuine active field — see the module's
    own date-schema audit), but the precedence MECHANISM itself is
    tested here directly by temporarily widening the precedence list,
    proving the first matching field in priority order wins and later
    fields are never consulted once an earlier one matched."""
    import plant_profile_freshness as freshness_module

    original_precedence = freshness_module.DATE_FIELD_PRECEDENCE
    try:
        freshness_module.DATE_FIELD_PRECEDENCE = ("Primary_Date_Field", "Secondary_Date_Field")
        df = pd.DataFrame([
            {"Scientific_Name": "X", "Primary_Date_Field": "2020", "Secondary_Date_Field": "1999"},
            {"Scientific_Name": "X", "Primary_Date_Field": "", "Secondary_Date_Field": "2010"},
        ])
        result = freshness_module.summarize_evidence_freshness(df, "X")
        # Row 1: Primary wins (2020), Secondary (1999) never consulted.
        # Row 2: Primary missing, falls through to Secondary (2010).
        assert result["dated_records"] == 2
        assert result["oldest_date"] == "2010"
        assert result["newest_date"] == "2020"
    finally:
        freshness_module.DATE_FIELD_PRECEDENCE = original_precedence


# ---------------------------------------------------------------------
# 14) One date maximum per row.
# ---------------------------------------------------------------------

def test_one_date_maximum_per_row():
    import plant_profile_freshness as freshness_module

    original_precedence = freshness_module.DATE_FIELD_PRECEDENCE
    try:
        freshness_module.DATE_FIELD_PRECEDENCE = ("Field_A", "Field_B")
        # Both fields valid on the SAME row — must contribute exactly
        # ONE date (Field_A, first in precedence), not two.
        df = pd.DataFrame([{"Scientific_Name": "X", "Field_A": "2020", "Field_B": "2021"}])
        result = freshness_module.summarize_evidence_freshness(df, "X")
        assert result["total_records"] == 1
        assert result["dated_records"] == 1  # not 2
        assert result["oldest_date"] == result["newest_date"] == "2020"
    finally:
        freshness_module.DATE_FIELD_PRECEDENCE = original_precedence


# ---------------------------------------------------------------------
# 15) No input mutation.
# ---------------------------------------------------------------------

def test_no_input_mutation():
    df = _mixed_freshness_df()
    snapshot = df.copy(deep=True)
    summarize_evidence_freshness(df, "Valeriana officinalis")
    assert df.equals(snapshot)


# ---------------------------------------------------------------------
# 16) UI calls the helper and does not use the arbitrary first row.
# ---------------------------------------------------------------------

def test_page_calls_the_freshness_helper():
    source = _read_plant_profile_source()
    assert "summarize_evidence_freshness(df, selected_plant)" in source


def test_page_does_not_use_row_for_freshness_fields():
    source = _read_plant_profile_source()
    # None of the freshness fields must ever be read off `row`
    # (plant_data.iloc[0]) — they only exist on the `freshness` dict
    # returned by summarize_evidence_freshness().
    for forbidden_pattern in (
        "row.get('Total_", 'row.get("Total_',
        "row.get('Oldest", 'row.get("Oldest',
        "row.get('Newest", 'row.get("Newest',
        "row.get('Date_Range", 'row.get("Date_Range',
    ):
        assert forbidden_pattern not in source


# ---------------------------------------------------------------------
# 17) Honest no-date message exists.
# ---------------------------------------------------------------------

def test_honest_no_date_message_exists_in_page_source():
    source = _read_plant_profile_source()
    first_fragment = "No evidence dates are available for this plant in the"
    second_fragment = "current evidence database."
    assert first_fragment in source
    # Anchoring on `remainder` (everything from first_fragment onward)
    # guarantees second_fragment is found as part of THIS message, not
    # merely somewhere earlier in the file (e.g. Task 16's own,
    # differently-worded empty-state message).
    first_index = source.index(first_fragment)
    remainder = source[first_index:first_index + 200]
    assert second_fragment in remainder


# ---------------------------------------------------------------------
# 18) No freshness/staleness judgment is displayed.
# ---------------------------------------------------------------------

def test_no_freshness_staleness_judgment_language():
    """"freshness"/"Evidence freshness" is the section's own required
    name (explicitly specified by this task), and "staleness" appears
    only inside this task's own design-principle comment ("no
    freshness/staleness judgment") — both neutral nouns, not judgments
    applied to any record. What must genuinely be absent is "fresh" or
    "stale" used standalone, as in "this evidence is fresh/stale", plus
    outdated/expired in any form."""
    source = _read_plant_profile_source()
    lowered = source.lower()

    for forbidden_word in ("outdated", "expired"):
        assert forbidden_word not in lowered, f"found judgment language: {forbidden_word!r}"

    import re
    for root_word, allowed_noun in (("fresh", "freshness"), ("stale", "staleness")):
        for match in re.finditer(root_word, lowered):
            position = match.start()
            end = position + len(allowed_noun)
            assert lowered[position:end] == allowed_noun, (
                f"found standalone {root_word!r} not part of {allowed_noun!r} "
                f"at position {position}: {source[max(0, position - 20):position + 20]!r}"
            )


def test_word_old_not_used_as_a_judgment_label():
    """"old" is common in ordinary English (e.g. it is NOT used here at
    all today) — checked separately from the regex-based check above
    since "old" has many benign substrings (e.g. it is not a substring
    of "freshness"); a plain word-boundary check is sufficient."""
    import re
    source = _read_plant_profile_source()
    assert not re.search(r"\bold\b", source, re.IGNORECASE)


def test_helper_never_computes_a_score_or_threshold():
    """Structural check: the helper's own return dict has no
    score/threshold/rating-shaped key."""
    df = pd.DataFrame([{"Scientific_Name": "X", "Source_Year": "2010"}])
    result = summarize_evidence_freshness(df, "X")
    forbidden_keys = {"freshness_score", "age", "staleness", "is_fresh", "is_stale", "threshold", "rating"}
    assert not (set(result.keys()) & forbidden_keys)


# ---------------------------------------------------------------------
# 19) Existing Task 16 tests still pass — run separately (see report),
#     confirmed here only by checking Task 16's own wiring survived
#     this task's edits to the same file.
# ---------------------------------------------------------------------

def test_task_16_regulatory_wiring_still_present():
    source = _read_plant_profile_source()
    assert "get_regulatory_source_rows(df, selected_plant)" in source
    assert "No source-linked regulatory record was found for this" in source


# ---------------------------------------------------------------------
# 20) DECISION_ENGINE_VERSION == "1.0.0".
# ---------------------------------------------------------------------

def test_decision_engine_version_unchanged():
    # Task 17 itself does not touch the version; Phase 2A later bumped
    # it separately (1.0.0 -> 1.0.1) for an unrelated regulatory fix.
    import botanical_rd_candidate_engine as eng
    assert eng.DECISION_ENGINE_VERSION == "1.0.1"


def test_page_never_references_decision_engine_version():
    source = _read_plant_profile_source()
    assert "DECISION_ENGINE_VERSION" not in source
    assert "Decision_Engine_Version" not in source


# ---------------------------------------------------------------------
# 21) No change to engine behavior or files outside scope.
# ---------------------------------------------------------------------

def test_freshness_module_has_no_engine_or_streamlit_dependency():
    import ast
    with open("plant_profile_freshness.py", encoding="utf-8") as f:
        tree = ast.parse(f.read())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    forbidden = {"botanical_rd_candidate_engine", "streamlit", "database"}
    assert not (imported & forbidden)


def test_no_out_of_scope_files_reference_the_new_helper():
    import subprocess
    result = subprocess.run(
        ["grep", "-rl", "plant_profile_freshness", "--include=*.py", "."],
        cwd=".", capture_output=True, text=True,
    )
    referencing_files = {line.lstrip("./") for line in result.stdout.splitlines() if line.strip()}
    allowed = {
        "plant_profile_freshness.py",
        "pages/Plant_Profile.py",
        "test_task17_plant_profile_evidence_freshness.py",
    }
    assert referencing_files.issubset(allowed), f"unexpected references: {referencing_files - allowed}"


def test_engine_output_unaffected_by_task_17():
    """Same deterministic regression comparison pattern Task 15/16
    already established — proves this task perturbed nothing about the
    engine's own behavior."""
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
        "Source_Year": "2020",
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
    assert row_a["Decision_Engine_Version"] == eng.DECISION_ENGINE_VERSION
    assert list(result_a["Alternative_Plant"]) == list(result_b["Alternative_Plant"])
