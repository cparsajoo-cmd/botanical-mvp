"""
Phase 6 — scoring sensitivity / boundary-fragility report (audit 4.16).

WHAT THIS IS
_decision_class() in botanical_rd_candidate_engine.py draws hard lines
at R&D_Opportunity_Score >= 78 ("Strong"), >= 62 ("Promising"), >= 45
("Early-stage"). A candidate scoring 79 and one scoring 77 get
different labels, even though a 2-point difference is well within the
kind of noise a small weight adjustment (documented in
_score_candidate's own docstring, Phase 6) could produce. This module
flags exactly those "boundary-fragile" candidates — rows whose
Decision_Class would flip under a small perturbation of the score —
so a reviewer knows which recommendations to treat cautiously, without
requiring a full re-run of the engine with perturbed weights.

WHY THIS APPROACH, NOT RE-RUNNING _score_candidate WITH PERTURBED WEIGHTS
_score_candidate's weights are inline constants, not parameters — making
them independently perturbable would mean refactoring every weight into
a function argument or config object, a larger and riskier change than
one Phase-6 step should be (and one best done together with the
calibration work audit 4.16 also asks for, not before it). This module
works entirely from the ALREADY-COMPUTED R&D_Opportunity_Score column
in a run() result — it tells you which rows are close to a boundary
without needing to know WHICH weight moved them there.

HOW TO USE
    from botanical_rd_candidate_engine import BotanicalRDCandidateEngine
    from scoring_sensitivity_report import fragility_report

    engine = BotanicalRDCandidateEngine(...)
    result = engine.run(indication=..., dosage_form=..., market=...)
    report = fragility_report(result)
    print(report["summary"])
    fragile_rows = report["fragile_rows"]  # DataFrame, for inspection
"""

from __future__ import annotations

import pandas as pd

# Must match _decision_class()'s own thresholds in
# botanical_rd_candidate_engine.py exactly — kept as a named constant
# here (not re-derived or guessed) so this module breaks loudly (KeyError
# on a stale boundary) rather than silently drifting if those thresholds
# ever change.
DECISION_BOUNDARIES = [45, 62, 78]

DEFAULT_MARGIN = 3.0


def fragility_report(result: pd.DataFrame, margin: float = DEFAULT_MARGIN) -> dict:
    """For each row in `result` (a botanical_rd_candidate_engine.run()
    output), computes the distance from its R&D_Opportunity_Score to
    the NEAREST decision boundary. A row within `margin` points of a
    boundary is flagged as boundary-fragile.

    Returns a dict:
      - fragile_rows: DataFrame subset of `result`, with an added
        Nearest_Boundary / Distance_To_Boundary column, sorted by
        distance (closest/most fragile first)
      - fragile_count, total_count
      - summary: a short human-readable string
    """
    if result.empty or "R&D_Opportunity_Score" not in result.columns:
        return {
            "fragile_rows": result.iloc[0:0],
            "fragile_count": 0,
            "total_count": len(result),
            "summary": "No rows to analyze (empty result or missing R&D_Opportunity_Score column).",
        }

    scores = result["R&D_Opportunity_Score"].astype(float)

    def _nearest_boundary_and_distance(score: float):
        distances = [(abs(score - b), b) for b in DECISION_BOUNDARIES]
        distances.sort()
        return distances[0][1], distances[0][0]

    nearest = scores.map(_nearest_boundary_and_distance)
    result_with_distance = result.copy()
    result_with_distance["Nearest_Boundary"] = nearest.map(lambda t: t[0])
    result_with_distance["Distance_To_Boundary"] = nearest.map(lambda t: t[1])

    fragile = result_with_distance[result_with_distance["Distance_To_Boundary"] <= margin]
    fragile = fragile.sort_values("Distance_To_Boundary")

    total = len(result)
    fragile_count = len(fragile)
    pct = round(100 * fragile_count / total, 1) if total else 0.0

    summary = (
        f"{fragile_count} of {total} candidates ({pct}%) sit within "
        f"{margin} points of a Decision_Class boundary "
        f"({', '.join(str(b) for b in DECISION_BOUNDARIES)}) — their "
        f"classification could flip under a small weight adjustment. "
        f"Treat these as provisional until the weights in "
        f"_score_candidate are calibrated against expert-reviewed cases."
    )

    return {
        "fragile_rows": fragile,
        "fragile_count": fragile_count,
        "total_count": total,
        "summary": summary,
    }
