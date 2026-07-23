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

SPRINT SCOPE NOTE (added during Sprint 1 review): this module and
Comparative_Rationale belong conceptually to a later "Comparative
Reasoning" sprint, not Sprint 1 ("Explainable Recommendation"). They
were implemented ahead of that planned sprint, in an earlier session,
and are working, tested code that predates Sprint 1 — nothing here has
been expanded or redesigned as part of Sprint 1, and this module is
explicitly NOT part of Sprint 1's acceptance criteria. Any further
comparative-reasoning work (e.g. extending this module) should be
scoped to that later sprint, not folded into Sprint 1 corrections.
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


# =====================================================================
# Sprint 2 — Comparative Decision Intelligence: structured comparison
# object, additive alongside the existing Comparative_Rationale string
# above.
#
# WHY THIS IS A SEPARATE COMPUTATION PATH, NOT A REFACTOR OF THE ABOVE
# _parse_score_breakdown(), _explain_gap(), and build_comparative_rationale()
# above are UNTOUCHED by this section — not one line changed. That is a
# deliberate backward-compatibility choice: refactoring them to share
# state with the structured builder below would risk changing
# Comparative_Rationale's exact tested string output, which the Sprint 2
# spec explicitly forbids ("Do not silently change the type of
# Comparative_Rationale... Legacy consumers must continue to work").
# The cost is that this section re-parses/re-diffs the same
# Score_Breakdown values _explain_gap() already diffed — cheap dict
# arithmetic over ~6 named components, not a second scoring engine, and
# a small price for a hard backward-compatibility guarantee.
#
# WHAT THIS DOES NOT DO
# No score is recomputed. No ranking is changed. Every winner/candidate
# rank below is a DISPLAY rank (pandas .rank() over the already-final
# R&D_Opportunity_Score), the same technique build_comparative_rationale()
# already used for "Global rank" — not a new ranking algorithm.
# =====================================================================

_SCORE_BREAKDOWN_MISSING_LIMITATION = "Score_Breakdown missing or unparseable for one or both candidates."

# The one Score_Breakdown component that folds regulatory and
# commercial signals together (see structured_rationale.py's own
# NO_REGULATORY_SCORE_CONTRIBUTION_MESSAGE for the fuller explanation —
# NOT imported from there, per this sprint's explicit instruction not
# to modify or add new coupling to structured_rationale.py; the
# equivalent honest message is restated locally instead).
_REGULATORY_FOLDED_COMPONENT = "Market signal"
_NO_INDEPENDENT_REGULATORY_SCORE_LIMITATION = (
    "No independent regulatory score contribution exists in the current scoring "
    "model — regulatory signals are folded into the \"Market signal\" component, "
    "which also covers commercial factors."
)


def _dimension_comparison_entries(winner_components: dict, candidate_components: dict) -> list:
    """One entry per component present in EITHER row's Score_Breakdown.
    A component present in only one row is marked "unavailable" and
    its counterpart value is left as None — NEVER treated as zero,
    since the scoring format does not represent an absent component as
    a zero contribution."""
    all_names = sorted(set(winner_components) | set(candidate_components))
    entries = []
    for name in all_names:
        in_winner = name in winner_components
        in_candidate = name in candidate_components
        if in_winner and in_candidate:
            winner_value = winner_components[name]
            candidate_value = candidate_components[name]
            difference = round(winner_value - candidate_value, 2)
            if difference > 0:
                favours = "winner"
                explanation = (
                    f"{name}: winner ahead by {difference:.1f} "
                    f"({winner_value:+.1f} vs {candidate_value:+.1f})."
                )
            elif difference < 0:
                favours = "candidate"
                explanation = (
                    f"{name}: candidate ahead by {abs(difference):.1f} "
                    f"({candidate_value:+.1f} vs {winner_value:+.1f})."
                )
            else:
                favours = "tie"
                explanation = f"{name}: tied at {winner_value:+.1f}."
            entries.append({
                "dimension": name, "winner_value": winner_value, "candidate_value": candidate_value,
                "difference": difference, "favours": favours, "explanation": explanation,
            })
        else:
            only_in = "winner" if in_winner else "candidate"
            entries.append({
                "dimension": name,
                "winner_value": winner_components.get(name),
                "candidate_value": candidate_components.get(name),
                "difference": None,
                "favours": "unavailable",
                "explanation": (
                    f"{name} is present only for the {only_in} — not directly "
                    f"comparable (not treated as zero for the missing side)."
                ),
            })
    return entries


def _comparison_confidence(winner_components: dict, candidate_components: dict) -> dict:
    """Confidence in THIS COMPARISON's completeness — never a
    substitute for either candidate's own Evidence_Confidence (a
    scientific-evidence measure, an entirely different thing).

    Documented thresholds (not arbitrary):
      Insufficient — either Score_Breakdown is missing/unparseable, or
                      zero components are present in both.
      High         — >=80% of the union of components are present in
                      both breakdowns.
      Moderate     — 50-79% overlap.
      Low          — <50% overlap (but at least one comparable component).
    """
    if not winner_components or not candidate_components:
        return {"level": "Insufficient", "reason": _SCORE_BREAKDOWN_MISSING_LIMITATION}

    comparable = set(winner_components) & set(candidate_components)
    total = set(winner_components) | set(candidate_components)

    if not comparable:
        return {
            "level": "Insufficient",
            "reason": "No components are present in both candidates' Score_Breakdown.",
        }

    overlap_ratio = len(comparable) / len(total)
    if overlap_ratio >= 0.8:
        level = "High"
    elif overlap_ratio >= 0.5:
        level = "Moderate"
    else:
        level = "Low"

    return {
        "level": level,
        "reason": (
            f"{len(comparable)} of {len(total)} score components are directly "
            f"comparable ({overlap_ratio:.0%} overlap)."
        ),
    }


def _comparison_limitations(
    winner_components: dict, candidate_components: dict, score_gap, entries: list,
    winner_name, candidate_name,
) -> list:
    limitations = []

    if not winner_components or not candidate_components:
        limitations.append(_SCORE_BREAKDOWN_MISSING_LIMITATION)

    unavailable = [e["dimension"] for e in entries if e["favours"] == "unavailable"]
    if unavailable:
        limitations.append(f"Component(s) present for only one candidate: {', '.join(unavailable)}.")

    if any(e["dimension"] == _REGULATORY_FOLDED_COMPONENT for e in entries):
        limitations.append(_NO_INDEPENDENT_REGULATORY_SCORE_LIMITATION)

    limitations.append(
        "This comparison is based on scoring components (Score_Breakdown), not a "
        "direct review of the underlying raw scientific records."
    )

    if score_gap is not None and abs(score_gap) < 1.0:
        limitations.append(
            f"Scores are close ({score_gap:+.1f} points) — the ranking between "
            f"these two candidates is not strongly separated."
        )

    if _is_missing(winner_name) or _is_missing(candidate_name):
        limitations.append(
            "Legacy row: candidate name missing from one or both rows being compared."
        )

    return limitations


def _winner_status_object(row, local_rank: int, global_rank) -> dict:
    """For the group winner's own row — never falsely compared against
    itself. No score gap, no advantages, no fabricated comparison."""
    return {
        "status": "group_winner",
        "winner": {
            "candidate_name": row.get("Alternative_Plant", "Unknown"),
            "score": row.get("R&D_Opportunity_Score"),
            "local_rank": local_rank,
            "global_rank": global_rank,
        },
        "candidate": None,
        "score_gap": None,
        "primary_reason": "This is the top-ranked candidate for its reference group.",
        "winner_advantages": [],
        "candidate_advantages": [],
        "ties": [],
        "dimension_comparison": [],
        "comparison_confidence": {
            "level": "Not applicable",
            "reason": "This row is the group winner; no comparison is being made against it.",
        },
        "limitations": [],
        "traceability": [
            "R&D_Opportunity_Score", "Local rank (within reference group)",
            "Global rank (across full result set)",
        ],
    }


def _is_missing(value) -> bool:
    """True for None, NaN (pandas' representation of a missing value in
    a mixed-type column — 'not nan' is False in plain Python, since any
    non-zero float is truthy, which silently missed this case before),
    and empty string."""
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    return value == ""


def _pair_comparison_object(
    winner_row, candidate_row, winner_local_rank: int, candidate_local_rank: int,
    winner_global_rank, candidate_global_rank,
) -> dict:
    """The full structured comparison for a non-winning candidate
    against its group's winner. Reuses parse_score_breakdown (the same
    parser _explain_gap() uses) — never recomputes a score."""
    winner_name = winner_row.get("Alternative_Plant")
    candidate_name = candidate_row.get("Alternative_Plant")

    winner_score = float(winner_row.get("R&D_Opportunity_Score", 0) or 0)
    candidate_score = float(candidate_row.get("R&D_Opportunity_Score", 0) or 0)
    score_gap = round(winner_score - candidate_score, 2)

    winner_components = _parse_score_breakdown(str(winner_row.get("Score_Breakdown", "")))
    candidate_components = _parse_score_breakdown(str(candidate_row.get("Score_Breakdown", "")))

    entries = _dimension_comparison_entries(winner_components, candidate_components)
    winner_advantages = sorted(
        (e for e in entries if e["favours"] == "winner"),
        key=lambda e: abs(e["difference"]), reverse=True,
    )
    candidate_advantages = sorted(
        (e for e in entries if e["favours"] == "candidate"),
        key=lambda e: abs(e["difference"]), reverse=True,
    )
    ties = [e for e in entries if e["favours"] == "tie"]

    if winner_advantages:
        top = winner_advantages[0]
        primary_reason = (
            f"{top['dimension']} favours the winner by {abs(top['difference']):.1f} points "
            f"({top['winner_value']:+.1f} vs {top['candidate_value']:+.1f})."
        )
    else:
        primary_reason = "No dominant score-component difference could be identified from the available breakdown."

    return {
        "status": "compared",
        "winner": {
            "candidate_name": "Unknown" if _is_missing(winner_name) else winner_name, "score": winner_score,
            "local_rank": winner_local_rank, "global_rank": winner_global_rank,
        },
        "candidate": {
            "candidate_name": "Unknown" if _is_missing(candidate_name) else candidate_name, "score": candidate_score,
            "local_rank": candidate_local_rank, "global_rank": candidate_global_rank,
        },
        "score_gap": score_gap,
        "primary_reason": primary_reason,
        "winner_advantages": winner_advantages,
        "candidate_advantages": candidate_advantages,
        "ties": ties,
        "dimension_comparison": entries,
        "comparison_confidence": _comparison_confidence(winner_components, candidate_components),
        "limitations": _comparison_limitations(
            winner_components, candidate_components, score_gap, entries, winner_name, candidate_name,
        ),
        "traceability": [
            "Score_Breakdown (winner)", "Score_Breakdown (candidate)", "R&D_Opportunity_Score",
            "Local rank (within reference group)", "Global rank (across full result set)",
        ],
    }


def build_comparative_rationale_structured(df: pd.DataFrame) -> pd.Series:
    """Sprint 2 — additive companion to build_comparative_rationale()
    above. Returns a machine-readable structured dict per row (or None
    for rows with no valid reference group), alongside — never
    replacing — the existing human-readable Comparative_Rationale
    string. Never raises on malformed/legacy input; a row missing the
    columns this needs gets None, not a crash.
    """
    if df.empty or "Reference_Plant" not in df.columns or "Reference_Compound" not in df.columns:
        return pd.Series([None] * len(df), index=df.index, dtype=object)

    results = pd.Series(index=df.index, dtype=object)
    has_score = "R&D_Opportunity_Score" in df.columns
    total_n = len(df)
    global_ranks = (
        df["R&D_Opportunity_Score"].astype(float).rank(method="min", ascending=False).astype(int)
        if has_score and total_n else pd.Series(dtype=int)
    )

    for _, group in df.groupby(["Reference_Plant", "Reference_Compound"], sort=False):
        if "R&D_Opportunity_Score" not in group.columns or group.empty:
            for idx in group.index:
                results[idx] = None
            continue

        group_scores = group["R&D_Opportunity_Score"].astype(float)
        top_idx = group_scores.idxmax()
        top_row = group.loc[top_idx]
        local_ranks = group_scores.rank(method="min", ascending=False).astype(int)

        for idx, row in group.iterrows():
            local_rank = int(local_ranks.loc[idx])
            global_rank = int(global_ranks.loc[idx]) if has_score and total_n else None
            winner_global_rank = int(global_ranks.loc[top_idx]) if has_score and total_n else None

            if idx == top_idx:
                results[idx] = _winner_status_object(row, local_rank, global_rank)
            else:
                results[idx] = _pair_comparison_object(
                    top_row, row,
                    winner_local_rank=1, candidate_local_rank=local_rank,
                    winner_global_rank=winner_global_rank, candidate_global_rank=global_rank,
                )

    return results
