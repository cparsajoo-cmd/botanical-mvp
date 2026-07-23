"""
Architecture audit Q2 — "Why were the others rejected?"

WHAT THIS IS
Every row in a run() result is currently scored and explained in
complete isolation (Scientific_Rationale, Evidence_Strengths/
Weaknesses — all Gap 6/8, all per-row). Nothing ever states a
comparison: "X was picked over Y because...". This module adds that
comparison as a post-processing pass over the ALREADY-COMPLETE result
DataFrame, grouped by (Reference_Plant, Reference_Compound) — the
natural grouping the engine already scores candidates within.

WHY A POST-PROCESSING PASS, NOT A NEW ENGINE
This needs every candidate's FINAL score to already exist before it
can say anything about relative ranking — it can only run after
run()'s per-row scoring loop and the multi-compound merge are both
done. botanical_rd_candidate_engine.py already has exactly this shape
of step (_merge_multi_compound_matches, a DataFrame-wide pass that
runs after row-by-row scoring and before the final column selection) —
this is one more pass of the same kind, wired into the same place, not
a second pipeline.

WHY THIS USES Score_Breakdown RATHER THAN RE-DERIVING A COMPARISON
Score_Breakdown (added to answer Q3, "which evidence contributed
most") already decomposes every row's score into named components.
Comparing two rows' breakdowns tells you EXACTLY which component
explains most of the gap between them — reusing that instead of
writing a second scoring comparison from scratch, which would have
been duplicate logic.
"""

from __future__ import annotations

import pandas as pd


def _parse_score_breakdown(breakdown: str) -> dict:
    """Reverses _format_score_breakdown()'s "Name: +12.3; Other: -4.0"
    format back into a dict. Tolerant of the "; Multi-compound match
    bonus: +N.0" suffix _merge_multi_compound_matches appends, and of
    "No breakdown available" (returns {})."""
    if not breakdown or breakdown == "No breakdown available":
        return {}
    components = {}
    for part in breakdown.split("; "):
        if ":" not in part:
            continue
        name, _, value_str = part.rpartition(":")
        try:
            components[name.strip()] = float(value_str.strip())
        except ValueError:
            continue
    return components


# Public alias — same function, exposed under a non-underscore name so
# other modules (pharma_report_generator.py's build_recommendation_card,
# Sprint 1) can reuse this exact parsing logic instead of duplicating
# it. The private name and every existing call site above are
# untouched, so nothing that already depends on _parse_score_breakdown
# is affected by this.
parse_score_breakdown = _parse_score_breakdown


def _explain_gap(top_row: pd.Series, this_row: pd.Series) -> str:
    gap = round(float(top_row["R&D_Opportunity_Score"]) - float(this_row["R&D_Opportunity_Score"]), 1)
    top_plant = top_row.get("Alternative_Plant", "the top candidate")

    if gap <= 0:
        # Tied (or, defensively, this row scored equal/higher but
        # wasn't picked as the group's max — shouldn't happen given how
        # the caller selects the top row, but stated plainly rather
        # than producing a nonsensical negative gap if it ever does).
        return f"Tied with {top_plant} on R&D_Opportunity_Score; both are top candidates for this reference."

    top_components = _parse_score_breakdown(str(top_row.get("Score_Breakdown", "")))
    this_components = _parse_score_breakdown(str(this_row.get("Score_Breakdown", "")))

    all_names = set(top_components) | set(this_components)
    diffs = {
        name: top_components.get(name, 0.0) - this_components.get(name, 0.0)
        for name in all_names
    }
    # Only components where the TOP candidate scored higher count as
    # part of "why it lost" — a component where THIS row scored higher
    # isn't a reason it was rejected.
    losing_diffs = {name: value for name, value in diffs.items() if value > 0}

    if not losing_diffs:
        return (
            f"Scored {gap:.1f} points below {top_plant} (top candidate for this reference); "
            f"no single component explains the gap on its own — see both rows' Score_Breakdown."
        )

    biggest_component, biggest_value = max(losing_diffs.items(), key=lambda kv: kv[1])
    return (
        f"Scored {gap:.1f} points below {top_plant} (top candidate for this reference), "
        f"mainly due to {biggest_component} ({biggest_value:+.1f} points lower than {top_plant})."
    )


def build_comparative_rationale(df: pd.DataFrame) -> pd.Series:
    """Returns a Series (same index as `df`) explaining, for every row,
    either why it's the top pick for its (Reference_Plant,
    Reference_Compound) group, or why it scored below whichever
    candidate IS the top pick — PLUS (external review #14) where it
    stands across the WHOLE project, not just its own reference group.
    A candidate can be the top pick within its own small group while
    still ranking low across the full portfolio, or vice versa — the
    local comparison alone doesn't tell a reader which is true, and a
    reader skimming for "what's actually worth funding" needs the
    global answer, not just the local one.

    Rows with a missing Reference_Plant/Reference_Compound, or a
    DataFrame with no rows at all, get an empty Series / a neutral
    placeholder — this never raises on malformed input, since it
    always runs as the last step of an otherwise-complete run().
    """
    if df.empty or "Reference_Plant" not in df.columns or "Reference_Compound" not in df.columns:
        return pd.Series(["Not applicable"] * len(df), index=df.index, dtype=str)

    results = pd.Series(index=df.index, dtype=object)

    has_score = "R&D_Opportunity_Score" in df.columns
    total_n = len(df)
    # Global rank (1 = highest score across the ENTIRE result, not just
    # within a reference group) — computed once over the whole
    # DataFrame, independent of the per-group loop below.
    global_ranks = (
        df["R&D_Opportunity_Score"].astype(float).rank(method="min", ascending=False).astype(int)
        if has_score and total_n
        else pd.Series(dtype=int)
    )

    for _, group in df.groupby(["Reference_Plant", "Reference_Compound"], sort=False):
        if "R&D_Opportunity_Score" not in group.columns or group.empty:
            for idx in group.index:
                results[idx] = "Not applicable"
            continue

        top_idx = group["R&D_Opportunity_Score"].astype(float).idxmax()
        top_row = group.loc[top_idx]

        for idx, row in group.iterrows():
            if idx == top_idx:
                local_text = (
                    f"Top-ranked candidate for this reference "
                    f"(R&D_Opportunity_Score {row['R&D_Opportunity_Score']})."
                )
            else:
                local_text = _explain_gap(top_row, row)

            if has_score and total_n:
                global_rank = int(global_ranks.loc[idx])
                global_text = f" Global rank: {global_rank} of {total_n} across the full result set."
            else:
                global_text = ""

            results[idx] = local_text + global_text

    return results
