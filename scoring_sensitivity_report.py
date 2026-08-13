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

=====================================================================
SPRINT 3 EXTENSION — contribution-shift threshold & rank-stability
analysis (build_robustness_analysis, classify_baseline_reconstruction,
and their helpers, below).

This is a SEPARATE analysis from fragility_report() above — the two
are deliberately not merged into one function or one output shape,
since they measure different things:
  fragility_report()       — distance to a DECISION-CLASS boundary
                              (45/62/78), i.e. classification fragility.
  build_robustness_analysis() — whether the WINNER vs. RUNNER-UP
                              ranking within a reference group would
                              survive removing one scoring section,
                              i.e. rank fragility. A candidate can be
                              far from any decision-class boundary
                              while still having a fragile #1-vs-#2
                              rank, or vice versa.
Both are exposed; neither replaces the other.

REQUIRED DOCUMENTATION POINTS (Sprint 3 spec):

1. Post-processing only. Every function below reads ONLY already-
   existing columns (R&D_Opportunity_Score, Score_Breakdown,
   Reference_Plant, Reference_Compound) from a completed run() result.
   Nothing here calls botanical_rd_candidate_engine.py, imports
   _score_candidate, or mutates any input DataFrame — verified by a
   dedicated test (test_robustness_analysis_does_not_mutate_input_dataframe).

2. Production scoring and ranking are unchanged. No weight is read,
   written, or parameterized from outside _score_candidate(); no
   R&D_Opportunity_Score or Decision_Class_AH value is ever altered.

3. "Contribution-shift threshold" is NOT a raw weight threshold. The
   repository does not preserve enough information to recover the
   original weight/raw-input pair for every section (see point 5) — so
   this only ever states how much an already-computed SECTION
   CONTRIBUTION would need to shift to close the observed score gap,
   never what raw input or weight change would produce that shift.
   Every contribution_shift_thresholds entry's own "interpretation"
   text restates this explicitly, not just this module docstring.

4. Leave-one-dimension-out is section-level only. It removes one named
   Score_Breakdown section's stored contribution (e.g. "Evidence
   quality") — it cannot decompose a section into its own internal
   sub-terms (e.g. Product-development fit's concentration/extraction/
   co-compound/target sub-terms), because those sub-terms are not
   separately stored anywhere after _score_candidate() sums them.

5. Score_Breakdown may not exactly reconstruct a clamped score.
   _score_candidate() clamps the final score to [0, 100] but never
   records the clamp adjustment as its own line item — see
   classify_baseline_reconstruction()'s "clamp_affected" status, which
   exists specifically to catch and label this case rather than
   silently treating the sum as authoritative.

6. Rank stability is MODEL sensitivity, not scientific evidence
   confidence. _classify_rank_stability() never reads Evidence_Confidence,
   Candidate_Evidence_Strength_Tier, or any other scientific-evidence
   signal — verified by test_rank_stability_never_reads_evidence_confidence.
   A "Fragile" rank-stability label says the #1-vs-#2 ranking is
   sensitive to which scoring section is removed; it says nothing about
   whether the underlying science is solid.

7. No probabilistic uncertainty is estimated anywhere in this module —
   no probability, confidence interval, or distribution is computed. Phase 7
   adds a deterministic bounded-weight stress envelope; its scenario-retention
   fraction is explicitly NOT a probability.

8. Phase 7 includes deterministic section-weight perturbation only. It does
   not expose user-tunable commercial/evidence profiles and does not alter
   production scores. The active weights are perturbed symmetrically around
   their current values and renormalized to 100.

9. Sub-component sensitivity is unavailable (see point 4) — this is a
   repository data-availability limit, not an implementation choice
   that could be trivially lifted.

10. Missing-data stress testing (comparing the current result against
    a documented conservative treatment of "not searched"/"connector
    unavailable"/etc. states) is explicitly DEFERRED, not implemented
    in this Sprint. It would require field-specific treatment rules
    and additional scientific/model assumptions beyond what
    section-level contribution-shift and leave-one-out analysis need.
=====================================================================
"""

from __future__ import annotations

import pandas as pd

from score_breakdown_schema import (
    CANONICAL_SECTIONS as _CANONICAL_SECTIONS,
    INDICATION_CANONICAL_SECTIONS as _INDICATION_CANONICAL_SECTIONS,
    AUTHORITATIVE_CANONICAL_SECTIONS as _AUTHORITATIVE_CANONICAL_SECTIONS,
    parse_score_breakdown as _parse_score_breakdown,
)

# Every known Score_Breakdown schema, checked in this order. Generalized to
# a tuple + loop (Phase 3) instead of one hand-written if-check per schema —
# adding a schema here is the only place it needs registering, avoiding the
# exact drift Phase 1 was created to close (a schema's section names
# changing, or a new schema appearing, without every consumer being updated).
_KNOWN_CANONICAL_SCHEMAS = (
    _CANONICAL_SECTIONS, _INDICATION_CANONICAL_SECTIONS, _AUTHORITATIVE_CANONICAL_SECTIONS,
)

# Must match _decision_class()'s own thresholds in
# botanical_rd_candidate_engine.py exactly — kept as a named constant
# here (not re-derived or guessed) so this module breaks loudly (KeyError
# on a stale boundary) rather than silently drifting if those thresholds
# ever change.
DECISION_BOUNDARIES = [45, 62, 78]

DEFAULT_MARGIN = 3.0


def _nearest_boundary_and_distance(score: float):
    """Shared per-row computation: which DECISION_BOUNDARIES entry is
    closest to `score`, and how far away. Factored out of
    fragility_report() (Task 5) so boundary_fragility_series() below
    can reuse the exact same logic instead of re-deriving it — the two
    functions can never silently drift apart on what "nearest boundary"
    means. Behavior is byte-identical to the pre-Task-5 inline closure
    this replaced.
    """
    distances = [(abs(score - b), b) for b in DECISION_BOUNDARIES]
    distances.sort()
    return distances[0][1], distances[0][0]


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


def boundary_fragility_series(result: pd.DataFrame, margin: float = DEFAULT_MARGIN) -> pd.Series:
    """Task 5 — per-row companion to fragility_report() above, for
    callers that want boundary-fragility exposed as an additive
    DataFrame COLUMN on every row (not just the fragile subset) — this
    is what lets BotanicalRDCandidateEngine.run() attach sensitivity
    information automatically to every comparison, per Chapter 8 of
    the whitepaper's "formal robustness analysis is supported through
    a separate, standalone post-processing tool... but this analysis
    is not yet run automatically as part of every comparison" gap.

    Same index as `result`; each entry is a small dict:
      {"nearest_boundary": int, "distance_to_boundary": float,
       "is_boundary_fragile": bool, "margin": float}

    Reuses the exact same _nearest_boundary_and_distance() computation
    fragility_report() uses — never a second, differently-derived
    notion of "fragile." Purely additive and read-only: never calls
    _score_candidate(), never mutates `result`, never changes
    R&D_Opportunity_Score or Decision_Class. Row order and index are
    preserved exactly (unlike fragility_report()'s fragile_rows, which
    is a sorted subset) — a caller assigning this Series directly onto
    `result` as a new column gets one entry per row, aligned by index.
    """
    if result.empty or "R&D_Opportunity_Score" not in result.columns:
        return pd.Series([None] * len(result), index=result.index, dtype=object)

    scores = result["R&D_Opportunity_Score"].astype(float)

    def _build(score: float) -> dict:
        boundary, distance = _nearest_boundary_and_distance(score)
        return {
            "nearest_boundary": boundary,
            "distance_to_boundary": distance,
            "is_boundary_fragile": distance <= margin,
            "margin": margin,
        }

    return scores.map(_build)


# =====================================================================
# Sprint 3 — Rank-stability robustness analysis, additive to the
# decision-boundary fragility analysis above (fragility_report() is
# UNTOUCHED by everything below — different question: that function
# asks "is this score near a Decision_Class cutoff," this section asks
# "is the winner-vs-runner-up ranking within a reference group robust
# to which section contributed what."
#
# TERMINOLOGY, BINDING ON THIS ENTIRE SECTION
# botanical_rd_candidate_engine.py's weights (_score_candidate) are
# inline constants, not parameters — the raw pre-modifier input and the
# weight applied to it are not both separately recoverable from a
# run() result for every section (confirmed: Chemical link's
# target-specificity decay and commonality penalty, and Product-
# development fit's 4 sub-terms, are only ever stored as their already-
# combined final contribution). Therefore nothing in this section is
# called a "weight threshold." Everything is a CONTRIBUTION-SHIFT
# THRESHOLD: the minimum change in an ALREADY-COMPUTED section's
# stored point contribution that would close the observed score gap,
# holding everything else constant. This says nothing about which raw
# input or weight would need to change to produce that shift, or
# whether such a shift is scientifically plausible.
#
# WHAT THIS NEVER DOES (Option A, confirmed in the Sprint 3 audit)
# Never calls _score_candidate() or any other production scoring
# function. Never mutates a stored score. Every number below is
# arithmetic over Score_Breakdown's ALREADY-STORED components and
# R&D_Opportunity_Score — nothing is recomputed from raw evidence.
# =====================================================================

# Canonical section-name sets and the Score_Breakdown parser now live in
# score_breakdown_schema.py (single source of truth — see IMPLEMENTATION_PLAN.md
# Phase 1) and are imported above as _CANONICAL_SECTIONS /
# _INDICATION_CANONICAL_SECTIONS / _parse_score_breakdown.

# Documented rounding tolerance: each section is stored as round(x, 1),
# and the final score is separately round()ed after summing — across
# up to 7 components (6 sections + the optional merge bonus), the
# worst-case accumulated rounding error is bounded by roughly
# 7 * 0.05 = 0.35, but in practice is almost always under 0.1. 0.15 is
# used as a deliberately slightly generous but still tight tolerance —
# tight enough that a real unexplained mismatch (a genuine bug) isn't
# hidden by it, loose enough that ordinary rounding isn't misreported
# as "unexplained."
RECONSTRUCTION_ROUNDING_TOLERANCE = 0.15

# A score sitting at or within this distance of 0 or 100 is treated as
# "at the clamp boundary" — final_score = round(max(0, min(100, score)), 1)
# in _score_candidate() means a raw sum below 0 or above 100 is
# silently clamped, and clamping is never itself recorded as a line
# item, so a mismatch AT the boundary is presumptively clamp-related
# rather than unexplained.
_CLAMP_BOUNDARY_TOLERANCE = 0.05

# Baseline reconstruction statuses safe enough to build leave-one-
# dimension-out analysis on top of (spec rule A/B).
_SAFE_RECONSTRUCTION_STATUSES = {"exact", "rounding_consistent"}

# Tie tolerance for rank_stability's "Tied" classification — same
# rounding-scale reasoning as RECONSTRUCTION_ROUNDING_TOLERANCE, kept
# as its own named constant since it answers a different question
# (are the two FINAL scores themselves indistinguishable, not whether
# Score_Breakdown reconstructs them).
RANK_STABILITY_TIE_TOLERANCE = 0.1


def classify_baseline_reconstruction(score_breakdown, rd_opportunity_score):
    """Returns (status, components). Never assumes Score_Breakdown
    exactly reconstructs R&D_Opportunity_Score — checks it explicitly
    and reports one of six honest statuses:
      unparseable           — Score_Breakdown is missing, empty, or contains no
                               recognizable "Name: value" pairs
      incomplete            — one or more of the always-expected canonical
                               sections is missing (checked BEFORE any
                               arithmetic comparison — see the ordering
                               note below)
      exact                 — a COMPLETE breakdown whose sum matches the
                               score to within rounding noise (<0.01)
      rounding_consistent   — a COMPLETE breakdown whose sum matches
                               within RECONSTRUCTION_ROUNDING_TOLERANCE
      clamp_affected        — score sits at the 0/100 boundary and doesn't match the sum
      unexplained_mismatch  — none of the above explains a real mismatch

    ORDERING, CORRECTED: missing-section detection runs BEFORE the
    exact/rounding_consistent arithmetic check. An earlier version
    checked arithmetic first, which meant a PARTIAL breakdown whose
    available components happened to sum to the stored score (by
    coincidence, or because the missing section's true contribution
    was exactly 0) was wrongly labeled "exact" — completeness and
    arithmetic correctness are different claims, and a breakdown
    missing data should never be reported as fully reconstructed no
    matter what its partial sum equals.

    Multi-compound match bonus (added only for merged multi-compound
    rows — see botanical_rd_candidate_engine.py's
    _merge_multi_compound_matches) is deliberately NOT one of the
    canonical sections checked here — its absence never triggers
    "incomplete", since it is legitimately optional and most rows never
    have it.
    """
    components = _parse_score_breakdown(score_breakdown)
    if not components:
        return "unparseable", components

    try:
        score = float(rd_opportunity_score)
    except (TypeError, ValueError):
        return "unparseable", components

    missing_sections = min(
        (schema - set(components.keys()) for schema in _KNOWN_CANONICAL_SCHEMAS),
        key=len,
    )
    if missing_sections:
        return "incomplete", components

    raw_sum = round(sum(components.values()), 2)
    diff = round(score - raw_sum, 2)

    if abs(diff) < 0.01:
        return "exact", components
    if abs(diff) <= RECONSTRUCTION_ROUNDING_TOLERANCE:
        return "rounding_consistent", components

    at_clamp_boundary = score <= _CLAMP_BOUNDARY_TOLERANCE or score >= (100 - _CLAMP_BOUNDARY_TOLERANCE)
    if at_clamp_boundary:
        return "clamp_affected", components

    return "unexplained_mismatch", components


def _contribution_shift_thresholds(winner_components: dict, runner_up_components: dict, score_gap) -> list:
    """For every section present in BOTH rows, states the contribution
    shift (to either side) that would close the CURRENT total score
    gap — deliberately the simplest, most auditable version (per
    Sprint 3 scope): the same required shift value for every
    dimension, since shifting ANY one dimension by the full gap amount
    closes the total gap regardless of which dimension it is. This
    does not claim any dimension is more "capable" of that shift than
    another, and does not imply the shift is scientifically feasible.
    """
    if score_gap is None:
        return []

    comparable = sorted(set(winner_components) & set(runner_up_components))
    required_shift = round(abs(score_gap), 2)
    entries = []
    for name in comparable:
        winner_value = winner_components[name]
        runner_up_value = runner_up_components[name]
        entries.append({
            "dimension": name,
            "current_winner_contribution": winner_value,
            "current_runner_up_contribution": runner_up_value,
            "current_dimension_difference": round(winner_value - runner_up_value, 2),
            "required_contribution_shift_to_tie": required_shift,
            "direction": ["runner_up_contribution_increase", "winner_contribution_decrease"],
            "interpretation": (
                f"All else held constant, {name}'s runner-up contribution would need "
                f"to increase by {required_shift:.1f} points (or the winner's decrease "
                f"by the same amount) to close the current {required_shift:.1f}-point "
                f"score gap. This is a contribution-shift threshold on an already-"
                f"computed section, not a raw weight change."
            ),
            "limitations": [
                "Does not indicate whether a shift of this size is scientifically "
                "plausible for this dimension.",
            ],
        })
    return entries


def _leave_one_dimension_out(
    winner_components: dict, runner_up_components: dict,
    winner_status: str, runner_up_status: str,
    winner_name: str, runner_up_name: str,
) -> list:
    """For each section present in BOTH rows, removes it from both
    candidates' stored contributions, re-applies the SAME [0,100] clamp
    production scoring uses (documented explicitly — this is an
    analysis-only score, never written back to any row), and checks
    whether the winner would change. Gated on both baseline
    reconstruction statuses being safe (spec rule A/B) — returns []
    (not a guess) when reconstruction isn't reliable enough to trust
    this arithmetic.
    """
    if winner_status not in _SAFE_RECONSTRUCTION_STATUSES or runner_up_status not in _SAFE_RECONSTRUCTION_STATUSES:
        return []

    comparable = sorted(set(winner_components) & set(runner_up_components))
    results = []
    for dim in comparable:
        winner_without = {k: v for k, v in winner_components.items() if k != dim}
        runner_up_without = {k: v for k, v in runner_up_components.items() if k != dim}

        winner_analysis_score = round(max(0.0, min(100.0, sum(winner_without.values()))), 1)
        runner_up_analysis_score = round(max(0.0, min(100.0, sum(runner_up_without.values()))), 1)

        analysis_winner = winner_name if winner_analysis_score >= runner_up_analysis_score else runner_up_name
        winner_changed = analysis_winner != winner_name

        results.append({
            "dimension_removed": dim,
            "analysis_winner": analysis_winner,
            "winner_changed": winner_changed,
            "analysis_scores": {
                "original_winner": winner_analysis_score,
                "original_runner_up": runner_up_analysis_score,
            },
            "analysis_gap": round(winner_analysis_score - runner_up_analysis_score, 2),
            "interpretation": (
                f"With {dim} excluded from both candidates' stored contributions "
                f"(all else held constant, [0,100] clamp reapplied), "
                + (f"the winner would change to {analysis_winner}." if winner_changed
                   else f"the winner would remain {winner_name}.")
            ),
            "limitations": [
                "Section-level only — sub-components within this dimension "
                "cannot be isolated from stored data.",
                "Assumes the remaining sections are unaffected by this dimension's "
                "removal, which may not reflect true model interdependence.",
            ],
        })
    return results


def _classify_rank_stability(score_gap, winner_status: str, runner_up_status: str, leave_one_out_results: list):
    """Deterministic, documented rules only — never reads
    Evidence_Confidence or any scientific-evidence field. This is a
    MODEL-ROBUSTNESS label, not a scientific-confidence label."""
    if winner_status not in _SAFE_RECONSTRUCTION_STATUSES or runner_up_status not in _SAFE_RECONSTRUCTION_STATUSES:
        return "Insufficient", (
            f"Baseline score reconstruction is not reliable enough to assess rank "
            f"stability (winner status: {winner_status}, runner-up status: {runner_up_status})."
        )

    if score_gap is not None and abs(score_gap) <= RANK_STABILITY_TIE_TOLERANCE:
        return "Tied", f"Baseline scores are equal within the documented tolerance ({RANK_STABILITY_TIE_TOLERANCE} points)."

    if not leave_one_out_results:
        return "Insufficient", "No comparable scoring dimensions were available for leave-one-dimension-out analysis."

    flips = [r for r in leave_one_out_results if r["winner_changed"]]

    if not flips:
        return "Stable", (
            "No single comparable dimension's removal changes the winner, and "
            "baseline reconstruction is reliable for both candidates."
        )
    if len(flips) == 1:
        return "Moderately stable", (
            f"The winner changes only when {flips[0]['dimension_removed']} is "
            f"removed — a single especially influential dimension controls this outcome."
        )
    return "Fragile", (
        f"The winner changes under {len(flips)} of {len(leave_one_out_results)} "
        f"leave-one-dimension-out tests."
    )


def _critical_dimensions(leave_one_out_results: list, threshold_entries: list) -> list:
    """"Critical to the current MODEL RANKING" — never "critical to
    therapeutic efficacy" or any scientific claim."""
    critical = []
    for r in leave_one_out_results:
        if r["winner_changed"]:
            critical.append({
                "dimension": r["dimension_removed"],
                "reason": "Removing this dimension changes the winner — critical to the current model ranking.",
            })

    if threshold_entries:
        dominant = max(threshold_entries, key=lambda e: abs(e["current_dimension_difference"]))
        if not any(c["dimension"] == dominant["dimension"] for c in critical):
            critical.append({
                "dimension": dominant["dimension"],
                "reason": (
                    "Dominates the current contribution difference between winner "
                    "and runner-up — critical to the current model ranking."
                ),
            })

    return critical


def _insufficient_robustness_status(reason: str) -> dict:
    return {
        "status": "insufficient",
        "scope": "reference_group_top_two",
        "baseline": None,
        "rank_stability": {"level": "Insufficient", "reason": reason},
        "contribution_shift_thresholds": [],
        "leave_one_dimension_out": [],
        "critical_dimensions": [],
        "limitations": [reason],
        "traceability": [],
    }


def _group_robustness_object(winner_row, runner_up_row) -> dict:
    winner_name = winner_row.get("Alternative_Plant", "Unknown")
    runner_up_name = runner_up_row.get("Alternative_Plant", "Unknown")
    winner_score = winner_row.get("R&D_Opportunity_Score")
    runner_up_score = runner_up_row.get("R&D_Opportunity_Score")

    winner_status, winner_components = classify_baseline_reconstruction(
        winner_row.get("Score_Breakdown"), winner_score,
    )
    runner_up_status, runner_up_components = classify_baseline_reconstruction(
        runner_up_row.get("Score_Breakdown"), runner_up_score,
    )

    score_gap = None
    if winner_score is not None and runner_up_score is not None:
        try:
            score_gap = round(float(winner_score) - float(runner_up_score), 2)
        except (TypeError, ValueError):
            score_gap = None

    threshold_entries = _contribution_shift_thresholds(winner_components, runner_up_components, score_gap)
    leave_one_out_results = _leave_one_dimension_out(
        winner_components, runner_up_components, winner_status, runner_up_status, winner_name, runner_up_name,
    )
    stability_level, stability_reason = _classify_rank_stability(
        score_gap, winner_status, runner_up_status, leave_one_out_results,
    )
    critical = _critical_dimensions(leave_one_out_results, threshold_entries)

    limitations = [
        "Contribution-shift thresholds describe an already-computed section's "
        "stored contribution, not a raw weight change.",
        "Leave-one-dimension-out is section-level only; sub-components within a "
        "section (e.g. extraction fit inside Product-development fit) cannot be "
        "isolated from stored data.",
        "This is model sensitivity, not scientific evidence uncertainty — see "
        "Evidence_Confidence / Candidate_Evidence_Strength_Tier for the latter.",
    ]
    if winner_status not in _SAFE_RECONSTRUCTION_STATUSES or runner_up_status not in _SAFE_RECONSTRUCTION_STATUSES:
        limitations.append(
            f"Baseline reconstruction status: winner={winner_status}, "
            f"runner-up={runner_up_status} — leave-one-dimension-out was skipped "
            f"as a result."
        )

    return {
        "status": "available",
        "scope": "reference_group_top_two",
        "baseline": {
            "winner": winner_name, "winner_score": winner_score,
            "runner_up": runner_up_name, "runner_up_score": runner_up_score,
            "score_gap": score_gap,
            "winner_reconstruction_status": winner_status,
            "runner_up_reconstruction_status": runner_up_status,
        },
        "rank_stability": {"level": stability_level, "reason": stability_reason},
        "contribution_shift_thresholds": threshold_entries,
        "leave_one_dimension_out": leave_one_out_results,
        "critical_dimensions": critical,
        "limitations": limitations,
        "traceability": [
            "Score_Breakdown (winner)", "Score_Breakdown (runner-up)", "R&D_Opportunity_Score",
        ],
    }


def build_robustness_analysis(df: pd.DataFrame) -> pd.Series:
    """Sprint 3 — the structured robustness object, one per row, built
    ONLY from R&D_Opportunity_Score/Score_Breakdown/reference-group
    membership already in `df`. Never calls into
    botanical_rd_candidate_engine.py, never mutates any score.

    Scope: within each (Reference_Plant, Reference_Compound) group,
    only the top two candidates (by R&D_Opportunity_Score) are
    compared — no all-pairs analysis. Every row in a group receives
    the SAME serialized group-level object (the lowest-risk of the
    patterns the Sprint 3 spec allowed) — this includes rows ranked
    3rd or lower within their group, which are given the top-two
    analysis for context, not a personal comparison of their own.

    A group with fewer than 2 valid candidates gets an honest
    "insufficient" status, never a fabricated comparison.
    """
    if df.empty or "Reference_Plant" not in df.columns or "Reference_Compound" not in df.columns:
        return pd.Series([None] * len(df), index=df.index, dtype=object)

    results = pd.Series(index=df.index, dtype=object)

    for _, group in df.groupby(["Reference_Plant", "Reference_Compound"], sort=False):
        if "R&D_Opportunity_Score" not in group.columns:
            obj = _insufficient_robustness_status(
                "No R&D_Opportunity_Score column available for this reference group."
            )
            for idx in group.index:
                results[idx] = obj
            continue

        if len(group) < 2:
            obj = _insufficient_robustness_status(
                "Only one candidate in this reference group — no runner-up available for comparison."
            )
            for idx in group.index:
                results[idx] = obj
            continue

        sorted_group = group.sort_values("R&D_Opportunity_Score", ascending=False)
        winner_row = sorted_group.iloc[0]
        runner_up_row = sorted_group.iloc[1]

        obj = _group_robustness_object(winner_row, runner_up_row)
        for idx in group.index:
            results[idx] = obj

    return results

# =====================================================================
# Phase 7 — bounded ACTUAL weight perturbation
# =====================================================================
# Unlike leave-one-dimension-out above, this analysis genuinely changes the
# section weights (within a documented deterministic envelope), renormalizes
# them to 100, and recomputes candidate ranking from the stored section
# contributions. It remains a sensitivity analysis, NOT a probability model.

from itertools import product as _product
from phase5_scoring_config import (
    RANKING_COMPONENT_ACTIVE_WEIGHTS as _ACTIVE_RANKING_WEIGHTS,
    DEFAULT_WEIGHT_PERTURBATION_RELATIVE_DELTA as _DEFAULT_WEIGHT_DELTA,
    RANKING_CALIBRATION_STATUS as _RANKING_CALIBRATION_STATUS,
    RANKING_CALIBRATION_NOTICE as _RANKING_CALIBRATION_NOTICE,
)
from ranking_score_model import normalize_weights as _normalize_ranking_weights


def _utilities_from_weighted_breakdown(breakdown) -> dict[str, float] | None:
    parsed = _parse_score_breakdown(breakdown)
    if not parsed:
        return None
    utilities = {}
    for name, weight in _ACTIVE_RANKING_WEIGHTS.items():
        if name not in parsed or float(weight) == 0:
            return None
        utilities[name] = float(parsed[name]) / float(weight)
    return utilities


def _bounded_weight_scenarios(relative_delta: float = _DEFAULT_WEIGHT_DELTA) -> list[dict[str, float]]:
    """All deterministic +/-delta corners plus the active baseline.

    Six dimensions => 64 corners, small enough to enumerate exactly. Every
    corner is renormalized to a 100-point weight vector. The returned set is
    an engineering stress envelope, not a sample from a probability
    distribution and therefore must never be described as a confidence level.
    """
    delta = float(relative_delta)
    if not 0 < delta < 0.5:
        raise ValueError("relative_delta must be between 0 and 0.5")
    names = list(_ACTIVE_RANKING_WEIGHTS)
    scenarios = [dict(_ACTIVE_RANKING_WEIGHTS)]
    for signs in _product((-1.0, 1.0), repeat=len(names)):
        raw = {
            name: float(_ACTIVE_RANKING_WEIGHTS[name]) * (1.0 + sign * delta)
            for name, sign in zip(names, signs)
        }
        scenarios.append(_normalize_ranking_weights(raw))
    # de-duplicate after normalization while preserving deterministic order
    seen = set()
    unique = []
    for sc in scenarios:
        key = tuple(round(sc[n], 10) for n in names)
        if key not in seen:
            seen.add(key)
            unique.append(sc)
    return unique


def _scenario_score(utilities: dict[str, float], weights: dict[str, float]) -> float:
    return round(max(0.0, min(100.0, sum(utilities[n] * weights[n] for n in weights))), 6)


def build_bounded_weight_robustness(
    df: pd.DataFrame,
    relative_delta: float = _DEFAULT_WEIGHT_DELTA,
) -> pd.Series:
    """Per-row group robustness under real +/- weight perturbations.

    The active baseline winner is compared with EVERY other normally-rankable
    candidate in the same (Reference_Plant, Reference_Compound) group under
    all 64 deterministic corner perturbations. When an
    Eligible_For_Normal_Ranking column exists, excluded/hold candidates are
    removed before ranking sensitivity is assessed; model robustness must not
    accidentally resurrect a scientific hard-stop.
    """
    results = pd.Series(index=df.index, dtype=object)
    if df.empty:
        return results
    group_cols = [c for c in ("Reference_Plant", "Reference_Compound") if c in df.columns]
    if len(group_cols) < 2:
        obj = {
            "status": "insufficient",
            "reason": "Reference_Plant/Reference_Compound grouping columns are required.",
            "calibration_status": _RANKING_CALIBRATION_STATUS,
        }
        for idx in df.index:
            results[idx] = obj
        return results

    scenarios = _bounded_weight_scenarios(relative_delta)
    for _, original_group in df.groupby(group_cols, sort=False):
        group = original_group
        if "Eligible_For_Normal_Ranking" in group.columns:
            mask = group["Eligible_For_Normal_Ranking"].map(
                lambda v: bool(v) if not pd.isna(v) else False
            )
            eligible = group[mask]
            if not eligible.empty:
                group = eligible

        usable = []
        for idx, row in group.iterrows():
            utilities = _utilities_from_weighted_breakdown(row.get("Score_Breakdown"))
            if utilities is not None:
                usable.append((idx, str(row.get("Alternative_Plant", idx)), utilities))

        if len(usable) < 2:
            obj = {
                "status": "insufficient",
                "reason": "At least two candidates with reconstructable Score_Breakdown are required.",
                "calibration_status": _RANKING_CALIBRATION_STATUS,
            }
        else:
            baseline_weights = _normalize_ranking_weights(_ACTIVE_RANKING_WEIGHTS)
            baseline_scores = [(_scenario_score(u, baseline_weights), name, idx) for idx, name, u in usable]
            baseline_scores.sort(key=lambda x: (-x[0], x[1]))
            baseline_winner = baseline_scores[0][1]
            winners = []
            ranks = []
            gaps = []
            for weights in scenarios:
                scored = [(_scenario_score(u, weights), name) for _, name, u in usable]
                scored.sort(key=lambda x: (-x[0], x[1]))
                winners.append(scored[0][1])
                rank = next(i + 1 for i, (_, name) in enumerate(scored) if name == baseline_winner)
                ranks.append(rank)
                if len(scored) >= 2:
                    gaps.append(scored[0][0] - scored[1][0])

            retained = sum(1 for w in winners if w == baseline_winner)
            retention = retained / len(winners)
            if retention == 1.0:
                level = "Robust"
            elif retention >= 0.90:
                level = "Moderately robust"
            else:
                level = "Sensitive"
            obj = {
                "status": "available",
                "scope": "reference_group_all_normally_rankable_candidates",
                "relative_weight_delta": float(relative_delta),
                "scenario_count": len(scenarios),
                "baseline_winner": baseline_winner,
                "winner_retention_fraction": round(retention, 4),
                "baseline_winner_worst_rank": max(ranks),
                "winner_changed_in_scenarios": len(winners) - retained,
                "minimum_top_two_gap": round(min(gaps), 4) if gaps else None,
                "maximum_top_two_gap": round(max(gaps), 4) if gaps else None,
                "stability_level": level,
                "calibration_status": _RANKING_CALIBRATION_STATUS,
                "interpretation": (
                    f"{baseline_winner} remained first in {retained}/{len(winners)} "
                    f"deterministic +/-{relative_delta:.0%} weight scenarios."
                ),
                "limitations": [
                    _RANKING_CALIBRATION_NOTICE,
                    "Scenario retention is not a probability or confidence interval.",
                    "Only section weights are perturbed; evidence extraction and scientific gates are fixed.",
                ],
            }

        for idx in original_group.index:
            results[idx] = obj
    return results
