"""
plant_profile_regulatory.py — Task 16.

Pure, Streamlit-independent, database-independent helper for
pages/Plant_Profile.py's regulatory-evidence section.

WHY THIS IS A SEPARATE MODULE, NOT INLINE IN THE PAGE
pages/Plant_Profile.py executes real Streamlit calls (st.set_page_config,
st.selectbox, ...) and a real database load (load_evidence_database())
at import time — there is no function boundary a test could call without
triggering all of that. This module has neither dependency, so it can
be imported and tested directly, the same reasoning every other pure
logic module in this repository (standard_evidence_builder.py,
regulatory_barrier_classifier.py, industrial_feasibility.py, ...)
already follows.

WHY get_regulatory_source_rows() EXISTS (Task 16 audit)
pages/Plant_Profile.py previously took plant_data.iloc[0] — an
arbitrary first evidence row for the selected plant — and displayed
its EMA_Status/WHO_Status/ESCOP_Status/Regulatory_Status as if they
were one confirmed regulatory determination. A plant can have zero,
one, or many evidence_records rows, and only rows with
Source_Type == "Regulatory" genuinely come from a regulatory-source
connector (ema_regulatory_connector.py, via regulatory_connector.py) —
every other row's regulatory-shaped text can be an LLM's relevance
guess or a keyword-derived signal, neither of which is a confirmed
regulatory determination (see the Task 14 and Task 16 audits). This
function isolates exactly the genuinely regulatory-source subset, with
NO aggregation, NO collapsing, and NO synthetic merge of multiple rows
into one status — every matching row is returned, untouched, for the
caller to render individually.

Reuses standard_evidence_builder.normalize_missing_value() (imported,
not duplicated or modified) for the same None/NaN/pandas-NA/""/"nan"
missing-value definition every other activation in this repository
already relies on.
"""

import pandas as pd

from standard_evidence_builder import normalize_missing_value


def _is_regulatory_source_type(value):
    """True only for a normalized Source_Type equal to "regulatory"
    (case-insensitive, whitespace-tolerant) — the same eligibility
    signal standard_evidence_builder.build_regulatory_record() already
    uses (Task 14.1), applied here to a whole column via .map()."""
    normalized = normalize_missing_value(value)
    if normalized is None:
        return False
    return str(normalized).strip().lower() == "regulatory"


def _empty_result(dataframe):
    """An empty DataFrame, preserving the input's columns where
    possible so a caller's downstream .get()/column access still
    behaves predictably rather than raising on a totally shapeless
    empty frame."""
    if dataframe is not None and hasattr(dataframe, "columns"):
        try:
            return pd.DataFrame(columns=dataframe.columns)
        except Exception:
            pass
    return pd.DataFrame()


def get_regulatory_source_rows(dataframe, scientific_name):
    """Returns every row of `dataframe` for `scientific_name` whose
    normalized Source_Type equals "regulatory".

    Parameters
    ----------
    dataframe : the already-loaded evidence DataFrame (e.g.
        evidence_database.load_evidence_database()'s return value —
        this function never loads or queries anything itself).
    scientific_name : the selected plant's Scientific_Name, matched
        exactly (the same equality check the page's own plant selector
        already uses) — not normalized/fuzzed, since the value always
        comes from the same DataFrame's own unique Scientific_Name
        values in the real page.

    Returns
    -------
    A NEW DataFrame (never a view into `dataframe`, never mutates it)
    containing zero, one, or many matching rows, in their original
    order — no aggregation, no deduplication beyond what the caller
    explicitly wants, no synthetic merge.

    Degrades safely to an empty result — never raises — for: `None`,
    a non-DataFrame, an empty DataFrame, a DataFrame missing
    "Scientific_Name" or "Source_Type", a missing/NaN/empty
    `scientific_name`, or any other malformed shape encountered while
    filtering.
    """
    if dataframe is None or not hasattr(dataframe, "empty") or dataframe.empty:
        return _empty_result(dataframe)

    if "Scientific_Name" not in dataframe.columns or "Source_Type" not in dataframe.columns:
        return _empty_result(dataframe)

    normalized_name = normalize_missing_value(scientific_name)
    if normalized_name is None:
        return _empty_result(dataframe)

    try:
        name_mask = dataframe["Scientific_Name"] == normalized_name
        source_type_mask = dataframe["Source_Type"].map(_is_regulatory_source_type)
        matched = dataframe[name_mask & source_type_mask]
    except Exception:
        return _empty_result(dataframe)

    # .copy() so the caller can never accidentally mutate `dataframe`
    # through the returned subset (a defensive guarantee, not just an
    # incidental side effect of boolean masking).
    return matched.copy()
