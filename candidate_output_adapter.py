"""
Data Contracts adapter (external review, repeated across rounds:
"Data Contracts هنوز وارد مسیر اجرایی نشده‌اند... یک Adapter کوچک کافی
است").

WHAT THIS IS
A validation boundary at the OUTPUT of botanical_rd_candidate_engine.run():
takes the real result DataFrame and converts each row into a validated
data_contracts.CandidateAssessment instance, or collects an explicit
error for any row that doesn't fit the contract. This is the "Raw
DataFrames -> Contract validation/normalization -> Canonical records"
adapter the review asked for.

WHY THIS IS AN OUTPUT ADAPTER, NOT AN INTERNAL REWRITE
The review was explicit: "لازم نیست کل پروژه بازنویسی شود" (no need to
rewrite the whole project). Rewriting botanical_rd_candidate_engine.py's
internal DataFrame-based pipeline to pass CandidateAssessment objects
through every function would be a large, invasive change touching
dozens of functions that are already tested against today's DataFrame
shape. Validating at the boundary — after run() already produced its
result — gets the real benefit (column-name drift becomes a loud,
specific error instead of a silent bug three functions downstream)
without that risk. If a column gets renamed or a type changes,
validate_result_df() will say exactly which row and which field broke,
immediately, rather than surfacing as a confusing failure somewhere
else later.

WHY THIS MODULE, NOT INLINE IN run()
Keeping this as a separate, optional call (not something run() invokes
automatically) means validation failures never block the existing
CSV/report/UI path that already works — this is a diagnostic and
contract-enforcement TOOL, called explicitly (see step_rd_candidates.py's
"Validate output contract" check), the same opt-in pattern already
used for market landscape enrichment and the sensitivity report.

HOW LIST-TYPED FIELDS ARE HANDLED
The real DataFrame stores list-like data (co_compounds, safety_flags,
source_record_ids, etc.) as "; "-joined strings, not native lists —
this adapter splits them back into lists to match CandidateAssessment's
actual field types, and treats known "nothing found" placeholder
strings (e.g. "No explicit flag found", "None identified") as an empty
list, not a single-item list containing that placeholder text.
"""

from __future__ import annotations

import math
from typing import Optional

import pandas as pd

from data_contracts import CandidateAssessment

# Columns whose real DataFrame values are "; "-joined strings that
# should become lists on CandidateAssessment.
_LIST_COLUMNS = {
    "Co_Compounds": "co_compounds",
    "Safety_Flags": "safety_flags",
    "Interaction_Flags": "interaction_flags",
    "Source_Record_IDs": "source_record_ids",
    "Negative_Evidence_Types": "negative_evidence_types",
    "Regulatory_Barriers": "regulatory_barriers",
    "Evidence_Strengths": "evidence_strengths",
    "Evidence_Weaknesses": "evidence_weaknesses",
}

# Values that mean "nothing found" in the real output and must become
# an empty list, not a single-item list containing this placeholder.
_EMPTY_PLACEHOLDERS = {
    "", "none identified", "no explicit flag found",
    "no specific source record identified", "not clearly extracted",
    "not clearly reported", "not applicable",
}

# Plain-string columns, mapped to their CandidateAssessment field name.
_STRING_COLUMNS = {
    "Reference_Plant": "reference_plant",
    "Reference_Plant_Part": "reference_plant_part",
    "Reference_Compound": "reference_compound",
    "Alternative_Plant": "alternative_plant",
    "Alternative_Plant_Part": "alternative_plant_part",
    "Shared_or_Similar_Compound": "alternative_compound",
    "Target_or_Mechanism": "target_or_mechanism",
    "Target_Provenance": "target_provenance",
    "Concentration_Info": "occurrence_evidence",
    "Extraction_Method": "extraction_method",
    "Industrial_Feasibility": "industrial_feasibility",
    "Evidence_Source": "evidence_source",
    "Occurrence_Corroboration": "occurrence_corroboration",
    "Candidate_Evidence_Strength_Tier": "candidate_evidence_strength_tier",
    "Evidence_Level": "evidence_level",
    "Evidence_Hierarchy_Detail": "evidence_hierarchy_detail",
    "Market_Status": "market_status",
    "Novelty_Status": "novelty_status",
    "Score_Breakdown": "score_breakdown",
    "Decision_Class": "decision_class",
    "Decision_Class_AH": "decision_class_ah",
    "White_Space_Type": "white_space_type",
    "Confidence_Note": "confidence_note",
    "Go_Investigate_Hold_NoGo": "go_investigate_hold_no_go",
    "Scientific_Rationale": "scientific_rationale",
    "Commercial_Regulatory_Rationale": "commercial_regulatory_rationale",
    "Next_Experiment_Suggestion": "next_experiment_suggestion",
    "Comparative_Rationale": "comparative_rationale",
    "Rationale": "rationale",
}

_FLOAT_COLUMNS = {
    "R&D_Opportunity_Score": "rd_opportunity_score",
    "Evidence_Confidence": "evidence_confidence",
}


def _split_list(value) -> list:
    text = str(value).strip() if value is not None else ""
    if text.lower() in _EMPTY_PLACEHOLDERS:
        return []
    return [part.strip() for part in text.split(";") if part.strip()]


def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _to_bool(value) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def validate_row(row, indication: str, project_id: str = "unspecified-run"):
    """Converts one result-DataFrame row into a validated
    CandidateAssessment. Returns (record, errors) — record is None if
    a REQUIRED field (reference_plant, alternative_plant) is missing;
    errors is a list of human-readable problems found, empty if none.
    Never raises — a malformed row is reported, not a crash."""
    errors = []
    kwargs = {"project_id": project_id, "indication": indication}

    reference_plant = str(row.get("Reference_Plant", "") or "").strip()
    alternative_plant = str(row.get("Alternative_Plant", "") or "").strip()
    if not reference_plant:
        errors.append("Missing required field: Reference_Plant")
    if not alternative_plant:
        errors.append("Missing required field: Alternative_Plant")
    if errors:
        return None, errors

    kwargs["reference_plant"] = reference_plant
    kwargs["alternative_plant"] = alternative_plant
    kwargs["product_type"] = None
    kwargs["dosage_form"] = None
    kwargs["target_market"] = None
    kwargs["reference_compound_id"] = None
    kwargs["alternative_compound_id"] = None

    for csv_col, field_name in _STRING_COLUMNS.items():
        if csv_col in {"Reference_Plant", "Alternative_Plant"}:
            continue
        value = row.get(csv_col)
        kwargs[field_name] = str(value).strip() if value not in (None, "") else None

    for csv_col, field_name in _LIST_COLUMNS.items():
        kwargs[field_name] = _split_list(row.get(csv_col))

    for csv_col, field_name in _FLOAT_COLUMNS.items():
        parsed = _to_float(row.get(csv_col))
        if csv_col in row and parsed is None and row.get(csv_col) not in (None, ""):
            errors.append(f"Could not parse {csv_col}={row.get(csv_col)!r} as a number")
        kwargs[field_name] = parsed

    has_negative = _to_bool(row.get("Has_Negative_Evidence"))
    if "Has_Negative_Evidence" in row and has_negative is None and row.get("Has_Negative_Evidence") not in (None, ""):
        errors.append(f"Could not parse Has_Negative_Evidence={row.get('Has_Negative_Evidence')!r} as a boolean")
    kwargs["has_negative_evidence"] = has_negative

    try:
        record = CandidateAssessment(**kwargs)
    except TypeError as exc:
        errors.append(f"CandidateAssessment construction failed: {exc}")
        return None, errors

    return record, errors


def validate_result_df(result_df: pd.DataFrame, indication: str, project_id: str = "unspecified-run"):
    """Validates every row of a botanical_rd_candidate_engine.run()
    result. Returns (records, errors_df):
      - records: list[CandidateAssessment], one per row that validated
        cleanly (or with only non-fatal issues — see validate_row).
      - errors_df: a DataFrame with one row per validation problem
        found (row_index, alternative_plant, error) — empty if nothing
        was wrong. A non-empty errors_df is itself the signal that the
        contract and the real output have drifted apart.
    """
    if result_df is None or result_df.empty:
        return [], pd.DataFrame(columns=["row_index", "alternative_plant", "error"])

    records = []
    error_rows = []

    for idx, row in result_df.iterrows():
        record, errors = validate_row(row, indication=indication, project_id=project_id)
        if record is not None:
            records.append(record)
        for err in errors:
            error_rows.append({
                "row_index": idx,
                "alternative_plant": row.get("Alternative_Plant", ""),
                "error": err,
            })

    return records, pd.DataFrame(error_rows, columns=["row_index", "alternative_plant", "error"])
