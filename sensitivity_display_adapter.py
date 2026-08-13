"""
Task 2 — pure, Streamlit-free adapter over the EXISTING
scoring_sensitivity_report.py entry points (fragility_report,
build_robustness_analysis).

WHAT THIS IS
A thin reshaping/summarizing layer for step_rd_candidates.py's
"Scoring sensitivity and ranking robustness" expander. It does not
compute sensitivity itself, does not perturb any weight, does not call
BotanicalRDCandidateEngine, and does not read or write Gate_Results,
Decision_Class, or R&D_Opportunity_Score. All of the actual analysis
comes from the two existing public functions in
scoring_sensitivity_report.py — see that module's docstring for what
they do and (extensively) do NOT do.

WHY A SEPARATE MODULE
step_rd_candidates.py needs Streamlit; this module doesn't, and isn't
allowed to need it (Task 2 requirement 7) — so the compact payload this
produces can be unit-tested without importing streamlit at all. The
Streamlit file only renders whatever dict this returns.

NON-MUTATION
Neither fragility_report() nor build_robustness_analysis() mutates its
input (documented in scoring_sensitivity_report.py, and covered by that
module's own test_robustness_analysis_does_not_mutate_input_dataframe).
This adapter calls both directly on the DataFrame it's given — no
defensive copy is made, because none is needed; Task 2's own test suite
verifies this independently rather than relying solely on that claim.
"""

from __future__ import annotations

import pandas as pd

from scoring_sensitivity_report import (
    build_robustness_analysis, fragility_report, build_bounded_weight_robustness,
)
from phase5_scoring_config import RANKING_CALIBRATION_STATUS, RANKING_CALIBRATION_NOTICE

# Required verbatim by Task 2 — the exact scientific-boundary statement
# the UI must display.
BOUNDARY_STATEMENT = "Model sensitivity is not scientific evidence confidence."

BOUNDARY_EXPLANATION = (
    "It describes how the ranking and Decision_Class labels above respond "
    "to small changes in model assumptions or scoring weights — it does "
    "not assess whether the underlying clinical, chemistry, safety, "
    "regulatory, manufacturing, or market evidence is scientifically "
    "reliable. A stable ranking does not prove scientific validity; it "
    "only means this particular conclusion doesn't hinge on one scoring "
    "section. An unstable ranking means the result depends heavily on "
    "model assumptions and warrants expert review before being treated "
    "as a recommendation."
)

# Human-readable labels for the rank-stability levels
# _classify_rank_stability() in scoring_sensitivity_report.py already
# produces — reused here for display grouping only; the labels
# themselves are not redefined or reclassified in any way.
_KNOWN_STABILITY_LEVELS = {
    "Stable", "Moderately stable", "Fragile", "Tied", "Insufficient",
}


def prepare_sensitivity_payload(result_df) -> dict:
    """Builds a compact, display-ready payload from an existing
    engine.run() result. Never raises — every condition that can't
    produce a real analysis returns status="insufficient_data" with a
    short, honest message, never a fabricated fragility/robustness
    metric.

    Returns a dict shaped:
        {
          "status": "ok" | "insufficient_data",
          "message": str,                 # set only when insufficient_data
          "boundary_statement": str,       # always present, verbatim
          "boundary_explanation": str,     # always present
          "fragility": {"fragile_count": int, "total_count": int, "summary": str} | None,
          "rank_stability_counts": {level: count, ...} | None,
          "weight_perturbation_stability_counts": {level: count, ...} | None,
          "ranking_calibration_status": str,
          "ranking_calibration_notice": str,
          "total_rows": int,
        }
    """
    base = {
        "boundary_statement": BOUNDARY_STATEMENT,
        "boundary_explanation": BOUNDARY_EXPLANATION,
        "fragility": None,
        "rank_stability_counts": None,
        "weight_perturbation_stability_counts": None,
        "ranking_calibration_status": RANKING_CALIBRATION_STATUS,
        "ranking_calibration_notice": RANKING_CALIBRATION_NOTICE,
        "total_rows": 0,
    }

    if result_df is None:
        return {
            **base,
            "status": "insufficient_data",
            "message": "No candidate results are available yet — run candidate discovery first.",
        }

    if not isinstance(result_df, pd.DataFrame):
        return {
            **base,
            "status": "insufficient_data",
            "message": "Candidate results are not in a usable table format.",
        }

    if result_df.empty:
        return {
            **base,
            "status": "insufficient_data",
            "message": "No candidate rows to analyze.",
        }

    if "R&D_Opportunity_Score" not in result_df.columns:
        return {
            **base,
            "status": "insufficient_data",
            "message": (
                "Required scoring columns are missing from this result — "
                "sensitivity analysis is unavailable."
            ),
        }

    total_rows = len(result_df)
    base["total_rows"] = total_rows

    if total_rows < 2:
        return {
            **base,
            "status": "insufficient_data",
            "message": (
                "Only one candidate is present — ranking robustness needs "
                "at least two candidates to compare."
            ),
        }

    # --- Existing entry point #1: decision-boundary fragility. Never
    # recomputed here — fragility_report() already handles empty/missing
    # columns internally and never raises. ---
    frag = fragility_report(result_df)
    fragility_summary = {
        "fragile_count": frag.get("fragile_count", 0),
        "total_count": frag.get("total_count", total_rows),
        "summary": frag.get("summary", ""),
    }

    # --- Existing entry point #2: rank-stability robustness. Every row
    # within a (Reference_Plant, Reference_Compound) group shares the
    # IDENTICAL object reference (by build_robustness_analysis's own
    # design) — dedupe by identity so a 5-row group isn't counted as 5
    # separate rank-stability verdicts in the compact summary below. ---
    robustness_series = build_robustness_analysis(result_df)
    counts: dict = {}
    seen_object_ids = set()
    for obj in robustness_series:
        if not isinstance(obj, dict):
            continue
        marker = id(obj)
        if marker in seen_object_ids:
            continue
        seen_object_ids.add(marker)
        level = obj.get("rank_stability", {}).get("level", "Insufficient")
        counts[level] = counts.get(level, 0) + 1

    if not counts:
        return {
            **base,
            "status": "insufficient_data",
            "message": "Ranking robustness could not be computed for these results.",
            "fragility": fragility_summary,
        }

    # Phase 7: actual bounded section-weight perturbation. Deduplicate the
    # shared group-level objects by identity exactly as above.
    perturbation = build_bounded_weight_robustness(result_df)
    perturb_counts: dict = {}
    seen_perturb_ids = set()
    for obj in perturbation:
        if not isinstance(obj, dict):
            continue
        marker = id(obj)
        if marker in seen_perturb_ids:
            continue
        seen_perturb_ids.add(marker)
        level = obj.get("stability_level")
        if level:
            perturb_counts[level] = perturb_counts.get(level, 0) + 1

    return {
        **base,
        "status": "ok",
        "message": "",
        "fragility": fragility_summary,
        "rank_stability_counts": counts,
        "weight_perturbation_stability_counts": perturb_counts or None,
    }
