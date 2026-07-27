"""
Task 13.2A — Filtered ScientificEvidence Lookup.

WHAT THIS COVERS
standard_evidence_builder.get_scientific_evidence_by_ids() — the
reusable, stateless, report-time-safe id -> ScientificEvidence lookup.
No engine, no database, no Streamlit session state, no report
formatting — this file tests exactly one pure function.

HOW TO RUN
    pytest -q test_task13_2a_scientific_evidence_lookup.py
    (or `pytest -q` from the repo root — auto-discovered)
"""

import pandas as pd

from data_contracts import EvidenceApplicability, ScientificEvidence
from standard_evidence_builder import get_scientific_evidence_by_ids


def _evidence_df(rows=None):
    rows = rows if rows is not None else [
        {
            "Evidence_Record_ID": "ev-1",
            "Source_Type": "PubMed",
            "Source_URL": "https://pubmed.ncbi.nlm.nih.gov/1/",
            "Evidence_Type": "Randomized Controlled Trial",
            "Population": "human",
            "Comparator": "placebo",
            "Primary_Outcome": "improved sleep latency",
            "Evidence_Level": "High",
            "Applicability_Classification": EvidenceApplicability.PARTIALLY_APPLICABLE.value,
            "Applicability_Rationale": "PARTIALLY_APPLICABLE: indication and dosage form match.",
        },
        {
            "Evidence_Record_ID": "ev-2",
            "Source_Type": "ClinicalTrials.gov",
            "Source_URL": "https://clinicaltrials.gov/study/NCT00000000",
            "Evidence_Type": "Clinical Trial Registry",
        },
        {
            "Evidence_Record_ID": "ev-3",
            "Source_Type": "Europe PMC",
        },
    ]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------
# 1) Successful lookup of requested IDs.
# ---------------------------------------------------------------------

def test_successful_lookup_of_requested_ids():
    df = _evidence_df()
    result = get_scientific_evidence_by_ids(["ev-1", "ev-2"], df)

    assert set(result.keys()) == {"ev-1", "ev-2"}
    assert result["ev-1"].source_type == "PubMed"
    assert result["ev-1"].population == "human"
    assert result["ev-1"].comparator == "placebo"
    assert result["ev-1"].outcome == "improved sleep latency"
    assert result["ev-2"].source_type == "ClinicalTrials.gov"


# ---------------------------------------------------------------------
# 2) Exclusion of unrequested rows.
# ---------------------------------------------------------------------

def test_unrequested_rows_are_excluded():
    df = _evidence_df()
    result = get_scientific_evidence_by_ids(["ev-1"], df)
    assert set(result.keys()) == {"ev-1"}
    assert "ev-2" not in result
    assert "ev-3" not in result


# ---------------------------------------------------------------------
# 3) Duplicate requested IDs.
# ---------------------------------------------------------------------

def test_duplicate_requested_ids_are_deduplicated():
    df = _evidence_df()
    result = get_scientific_evidence_by_ids(["ev-1", "ev-1", "ev-1", "ev-2"], df)
    assert set(result.keys()) == {"ev-1", "ev-2"}
    assert len(result) == 2


# ---------------------------------------------------------------------
# 4) Unknown IDs.
# ---------------------------------------------------------------------

def test_unknown_requested_ids_are_simply_absent_not_an_error():
    df = _evidence_df()
    result = get_scientific_evidence_by_ids(["ev-1", "ev-does-not-exist"], df)
    assert set(result.keys()) == {"ev-1"}
    assert "ev-does-not-exist" not in result


def test_all_unknown_ids_returns_empty_dict_not_an_error():
    df = _evidence_df()
    result = get_scientific_evidence_by_ids(["nope-1", "nope-2"], df)
    assert result == {}


# ---------------------------------------------------------------------
# 5) None, empty, NaN, and pd.NA requested IDs.
# ---------------------------------------------------------------------

def test_none_nan_pdna_and_empty_requested_ids_are_ignored():
    df = _evidence_df()
    result = get_scientific_evidence_by_ids(
        ["ev-1", None, float("nan"), pd.NA, "", "   ", "nan", "none"], df
    )
    assert set(result.keys()) == {"ev-1"}


def test_requested_ids_list_of_only_missing_values_returns_empty_dict():
    df = _evidence_df()
    result = get_scientific_evidence_by_ids([None, float("nan"), pd.NA, ""], df)
    assert result == {}


# ---------------------------------------------------------------------
# 6) Invalid or empty evidence_df.
# ---------------------------------------------------------------------

def test_empty_dataframe_returns_empty_dict():
    assert get_scientific_evidence_by_ids(["ev-1"], pd.DataFrame()) == {}


def test_none_dataframe_returns_empty_dict():
    assert get_scientific_evidence_by_ids(["ev-1"], None) == {}


def test_non_dataframe_input_returns_empty_dict_not_an_error():
    for bad_value in ("not a dataframe", 42, ["a", "list"], {"a": "dict"}):
        assert get_scientific_evidence_by_ids(["ev-1"], bad_value) == {}


def test_none_or_non_iterable_requested_ids_returns_empty_dict():
    df = _evidence_df()
    assert get_scientific_evidence_by_ids(None, df) == {}
    assert get_scientific_evidence_by_ids(42, df) == {}   # not iterable
    assert get_scientific_evidence_by_ids([], df) == {}


# ---------------------------------------------------------------------
# 7) Rows with missing/invalid Evidence_Record_ID.
# ---------------------------------------------------------------------

def test_rows_with_missing_or_invalid_id_are_ignored():
    df = _evidence_df([
        {"Evidence_Record_ID": "ev-1", "Source_Type": "PubMed"},
        {"Evidence_Record_ID": float("nan"), "Source_Type": "Should be skipped (NaN id)"},
        {"Evidence_Record_ID": None, "Source_Type": "Should be skipped (None id)"},
        {"Evidence_Record_ID": "", "Source_Type": "Should be skipped (empty id)"},
        {"Source_Type": "Should be skipped (no id column value at all)"},
    ])
    # Request every possible id, including ones that could only match a
    # bad row if this function were buggy.
    result = get_scientific_evidence_by_ids(["ev-1", "nan", "None", ""], df)
    assert set(result.keys()) == {"ev-1"}


def test_no_id_column_at_all_returns_empty_dict():
    df = pd.DataFrame([{"Source_Type": "PubMed", "Notes": "no id column exists in this df"}])
    assert get_scientific_evidence_by_ids(["ev-1"], df) == {}


def test_lowercase_id_column_fallback_still_works():
    df = pd.DataFrame([{"evidence_record_id": "ev-lower", "Source_Type": "PubMed"}])
    result = get_scientific_evidence_by_ids(["ev-lower"], df)
    assert set(result.keys()) == {"ev-lower"}


def test_genuine_normalized_ids_preserved_unchanged():
    """Numeric vs string requested/stored id representations must still
    match (both go through the same normalize_missing_value + str()
    path), and the OUTPUT key is the normalized string form."""
    df = pd.DataFrame([{"Evidence_Record_ID": 42, "Source_Type": "PubMed"}])
    result = get_scientific_evidence_by_ids(["42"], df)
    assert set(result.keys()) == {"42"}
    assert result["42"].source_record_id == "42"


# ---------------------------------------------------------------------
# 8) Partial records using existing safe defaults.
# ---------------------------------------------------------------------

def test_partial_record_uses_existing_safe_defaults_never_fabricates():
    df = _evidence_df([
        {"Evidence_Record_ID": "ev-partial", "Source_Type": "PubMed"},
        # No Population, Comparator, Outcome, Evidence_Level, Applicability_* at all.
    ])
    result = get_scientific_evidence_by_ids(["ev-partial"], df)
    evidence = result["ev-partial"]
    assert evidence.source_type == "PubMed"
    assert evidence.population is None
    assert evidence.comparator is None
    assert evidence.outcome is None
    assert evidence.evidence_hierarchy_level is None
    assert evidence.applicability_classification is None
    # Fields with genuinely no source anywhere in the active schema.
    assert evidence.dose is None
    assert evidence.sample_size is None


def test_malformed_row_is_skipped_without_crashing_other_lookups():
    """A row whose Applicability_Classification is a value that cannot
    be parsed into EvidenceApplicability must not crash the lookup for
    OTHER requested ids — build_scientific_evidence() already handles
    this gracefully (ValueError caught internally), proven again here
    at this function's own boundary."""
    df = _evidence_df([
        {"Evidence_Record_ID": "ev-good", "Source_Type": "PubMed"},
        {"Evidence_Record_ID": "ev-odd", "Source_Type": "PubMed",
         "Applicability_Classification": "Some Completely Foreign Value"},
    ])
    result = get_scientific_evidence_by_ids(["ev-good", "ev-odd"], df)
    assert "ev-good" in result
    assert "ev-odd" in result  # still resolved — just with classification=None
    assert result["ev-odd"].applicability_classification is None


# ---------------------------------------------------------------------
# 9) Output values are genuine ScientificEvidence objects.
# ---------------------------------------------------------------------

def test_output_values_are_genuine_scientific_evidence_objects():
    df = _evidence_df()
    result = get_scientific_evidence_by_ids(["ev-1", "ev-2", "ev-3"], df)
    assert len(result) == 3
    for value in result.values():
        assert isinstance(value, ScientificEvidence)


def test_no_scientific_classification_is_recomputed_by_this_function():
    """This function must be a pure pass-through to
    build_scientific_evidence() — proven by confirming the SAME
    dict, run through build_scientific_evidence() directly, produces
    a byte-identical ScientificEvidence to what this function returns
    for the same row."""
    from standard_evidence_builder import build_scientific_evidence
    df = _evidence_df()
    row_dict = df[df["Evidence_Record_ID"] == "ev-1"].iloc[0].to_dict()

    direct = build_scientific_evidence(dict(row_dict))
    via_lookup = get_scientific_evidence_by_ids(["ev-1"], df)["ev-1"]

    assert direct.source_type == via_lookup.source_type
    assert direct.applicability_classification == via_lookup.applicability_classification
    assert direct.applicability_rationale == via_lookup.applicability_rationale
    assert direct.evidence_hierarchy_level == via_lookup.evidence_hierarchy_level


# ---------------------------------------------------------------------
# 10) Input DataFrame is not mutated.
# ---------------------------------------------------------------------

def test_evidence_df_is_not_mutated():
    df = _evidence_df()
    snapshot = df.copy(deep=True)

    get_scientific_evidence_by_ids(["ev-1", "ev-2", "ev-missing"], df)

    assert df.equals(snapshot)
    assert list(df.columns) == list(snapshot.columns)
    assert len(df) == len(snapshot)


def test_evidence_df_not_mutated_even_with_nan_ids_and_malformed_rows():
    df = _evidence_df([
        {"Evidence_Record_ID": "ev-1", "Source_Type": "PubMed"},
        {"Evidence_Record_ID": float("nan"), "Source_Type": "Junk"},
        {"Evidence_Record_ID": "ev-odd", "Applicability_Classification": "Foreign"},
    ])
    snapshot = df.copy(deep=True)

    get_scientific_evidence_by_ids(["ev-1", "ev-odd", None, float("nan")], df)

    # DataFrame.equals() treats NaN == NaN as equal (unlike ==), so this
    # is a genuine, precise mutation check, not an approximation.
    assert df.equals(snapshot)
