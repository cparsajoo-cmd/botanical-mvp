"""
Gap 9 — pharmaceutical-grade R&D report, not just a rankings table.

WHAT THIS IS
Turns a botanical_rd_candidate_engine.run() result DataFrame into a
structured Markdown report: an executive summary, then a full
per-candidate write-up for the top-scoring candidates (Go_Investigate_
Hold_NoGo call, scientific/commercial/regulatory rationale, evidence
strengths & weaknesses, safety considerations, next-experiment
suggestion, and source citations), followed by a compact table for
everything else.

WHY THIS IS SMALL
Every piece of content in this report already exists as a column by
the time this module runs — Gap 6/8's structured_rationale.py already
did the actual synthesis work. This module is templating and layout
only; it contains no scoring, classification, or rationale logic of
its own. That's a deliberate consequence of doing Gaps 1-6/8 first —
see the architecture gap report's own sequencing note ("Gap 9... this
is trivial once Gap 6 exists, premature before it").

WHY NOT report_generator.py
That file (confirmed in the Phase 1/7 audit as unreachable from app.py)
references a completely different, older column schema
(Scientific_Name, Evidence_Score, Commercial_Potential, Decision_Reason
— none of which exist in the current OUTPUT_COLUMNS). It's on the
confirmed-legacy list (.github/legacy-files.txt) and should be moved
to archive/ the next time that workflow actually runs — as of this
writing it's identified as legacy but not yet physically moved (see
ARCHITECTURE.md's "Legacy files" section for the current, accurate
status of that migration).

HOW TO USE
    from botanical_rd_candidate_engine import BotanicalRDCandidateEngine
    from pharma_report_generator import generate_pharma_report

    engine = BotanicalRDCandidateEngine(...)
    result = engine.run(indication=..., dosage_form=..., market=...)
    report_markdown = generate_pharma_report(result, indication=..., dosage_form=..., market=...)

WIRED INTO THE UI
step_rd_candidates.py calls this function directly (a "Download R&D
report (Markdown)" button, plus an in-app preview expander) — this
docstring previously said "not wired into the Streamlit UI," which
became stale the moment that wiring landed and was never corrected
here. If you're reading this and it's stale again, check
step_rd_candidates.py directly rather than trusting this comment.
"""

from __future__ import annotations

import pandas as pd

from structured_rationale import build_recommendation_card
from scoring_sensitivity_report import build_robustness_analysis

GO_CALL_ORDER = [
    "Go",
    "Investigate",
    "Investigate — verify before proceeding",
    "Hold",
    "No-Go",
]


def _format_comparison_section(comparison) -> list:
    """Sprint 2 — formats Comparative_Rationale_Structured concisely.
    Formatting only: every value here already exists on the structured
    object built by comparative_rationale.build_comparative_rationale_structured();
    nothing is recomputed or reinterpreted. Deliberately does NOT print
    the raw dict — only the top 2 advantages per side, the primary
    reason, confidence, and limitations, per the "keep the report
    concise" requirement.
    """
    if not comparison:
        return []

    if comparison.get("status") == "group_winner":
        return ["**Head-to-head comparison:** This is the top-ranked candidate for its reference group."]

    lines = [
        "**Head-to-head comparison:**",
        f"- {comparison['candidate']['candidate_name']} vs. {comparison['winner']['candidate_name']} "
        f"(winner) — score gap: {comparison['score_gap']:+.1f}",
        f"- Primary reason: {comparison['primary_reason']}",
    ]

    if comparison["winner_advantages"]:
        top = comparison["winner_advantages"][:2]
        lines.append(
            "- Winner ahead on: " + "; ".join(
                f"{e['dimension']} ({e['difference']:+.1f})" for e in top
            )
        )
    if comparison["candidate_advantages"]:
        top = comparison["candidate_advantages"][:2]
        lines.append(
            "- Candidate ahead on: " + "; ".join(
                f"{e['dimension']} ({abs(e['difference']):+.1f})" for e in top
            )
        )

    confidence = comparison["comparison_confidence"]
    lines.append(f"- Comparison confidence: {confidence['level']} — {confidence['reason']}")

    if comparison["limitations"]:
        lines.append(f"- Comparison limitations: {'; '.join(comparison['limitations'][:2])}")

    return lines


def _format_robustness_section(robustness) -> list:
    """Sprint 3 — formats build_robustness_analysis()'s structured
    object concisely. Formatting only: every value already exists on
    the object built by scoring_sensitivity_report.build_robustness_analysis();
    nothing is recomputed or reinterpreted here. Explicitly labeled as
    model sensitivity, not scientific uncertainty, per the Sprint 3
    requirement.

    `robustness` is passed in from generate_pharma_report()'s single
    build_robustness_analysis(result) call (see that call site's own
    comment) — it is an in-memory dict for this report generation only,
    not a value read from any stored DataFrame column.
    """
    if not robustness:
        return []

    if robustness.get("status") == "insufficient":
        reason = robustness["rank_stability"]["reason"]
        return [f"**Robustness of the ranking:** Insufficient data — {reason}"]

    baseline = robustness["baseline"]
    stability = robustness["rank_stability"]

    lines = [
        "**Robustness of the ranking** (model sensitivity, not scientific uncertainty — "
        "see Evidence_Confidence/Candidate_Evidence_Strength_Tier for the latter):",
        f"- Baseline: {baseline['winner']} ({baseline['winner_score']}) vs. "
        f"{baseline['runner_up']} ({baseline['runner_up_score']}) — "
        f"score gap {baseline['score_gap']:+.1f}",
        f"- Rank stability: {stability['level']} — {stability['reason']}",
    ]

    flipping = [r["dimension_removed"] for r in robustness["leave_one_dimension_out"] if r["winner_changed"]]
    if flipping:
        lines.append(f"- Dimensions whose removal changes the winner: {', '.join(flipping)}")

    if robustness["contribution_shift_thresholds"]:
        shift = robustness["contribution_shift_thresholds"][0]["required_contribution_shift_to_tie"]
        lines.append(f"- Smallest contribution shift required to close the gap: {shift:.1f} points (any comparable dimension)")

    if baseline["winner_reconstruction_status"] not in {"exact", "rounding_consistent"} or \
       baseline["runner_up_reconstruction_status"] not in {"exact", "rounding_consistent"}:
        lines.append(
            f"- Reconstruction limitation: winner={baseline['winner_reconstruction_status']}, "
            f"runner-up={baseline['runner_up_reconstruction_status']}"
        )

    return lines


def _format_evidence_conflict_section(evidence_conflict) -> list:
    """Sprint 4 — formats structured_rationale.build_evidence_conflict_structured()'s
    object concisely. Formatting only: every value already exists on
    the object; nothing is recomputed or reinterpreted here — the
    report does not duplicate the interpretation logic, it only
    presents it.
    """
    if not evidence_conflict:
        return []

    lines = [
        "**Evidence conflict & consistency:**",
        f"- Overall consistency: {evidence_conflict['overall_consistency']}",
        f"- Dominant evidence pattern: {evidence_conflict['dominant_evidence_pattern']}",
        f"- {evidence_conflict['evidence_interpretation']}",
    ]

    if evidence_conflict["possible_explanations"]:
        lines.append(
            "- Possible explanations suggested by detected evidence patterns: "
            + "; ".join(evidence_conflict["possible_explanations"])
        )

    if evidence_conflict["research_gaps"]:
        lines.append(f"- Research gaps: {', '.join(evidence_conflict['research_gaps'])}")

    return lines


def _candidate_section(row: pd.Series, rank: int, robustness=None) -> str:
    """Formats the ONE canonical Recommendation Card
    (structured_rationale.build_recommendation_card) as markdown. This
    function does not compute, re-derive, or duplicate any of the
    card's own reasoning (no local Score_Breakdown parsing, no local
    dimension mapping) — every scientific/clinical/regulatory/
    commercial/safety judgment below comes from the single shared
    build_recommendation_card() call. Only a handful of separate,
    already-existing per-row columns that are NOT part of the card's
    own reasoning scope (R&D_Opportunity_Score, Decision_Class_AH,
    White_Space_Type, Competitive_Positioning, Product_Development_Concept,
    Confidence_Note) are read directly from `row` for surrounding
    context.
    """
    card = build_recommendation_card(row)

    lines = [
        f"### {rank}. {card['botanical']} — {card['final_recommendation']}",
        "",
        f"**Reference:** {row.get('Reference_Plant', '')} / {row.get('Reference_Compound', '')}  ",
        f"**Matched compound:** {row.get('Shared_or_Similar_Compound', '')}  ",
        f"**R&D Opportunity Score:** {row.get('R&D_Opportunity_Score', '')} | "
        f"**Evidence Confidence:** {row.get('Evidence_Confidence', '')}  ",
        f"**Decision class:** {row.get('Decision_Class_AH', '')}",
    ]

    recommendation_confidence = row.get("Recommendation_Confidence_Statement")
    if recommendation_confidence:
        lines.append(f"> **{recommendation_confidence}**")

    competitive_positioning = row.get("Competitive_Positioning")
    if competitive_positioning:
        lines.append(f"\n**{competitive_positioning}**")

    white_space = str(row.get("White_Space_Type", "") or "").strip()
    if white_space:
        lines.append(f"**White space type:** {white_space}")

    development_concept = row.get("Product_Development_Concept")
    if development_concept:
        lines.append("")
        lines.append("**Development concept:**")
        lines.append(str(development_concept))

    confidence_note = str(row.get("Confidence_Note", "") or "").strip()
    if confidence_note:
        lines.append(f"\n> ⚠️ {confidence_note}")

    lines += [
        "",
        f"**Scientific rationale:** {card['scientific_rationale']}",
        f"**Top scientific contributor:** {card['top_scientific_contributor']}",
        "",
        f"**Clinical rationale:** {card['clinical_rationale']}",
        f"**Top clinical contributor:** {card['top_clinical_contributor']}",
        f"**Mechanism of action:** {card['mechanism_of_action']}",
        "",
        f"**Regulatory rationale:** {card['regulatory_rationale']}",
        f"**Regulatory score contribution:** {card['top_regulatory_contributor']}",
        "",
        f"**Commercial rationale:** {card['commercial_rationale']}",
        f"**Top commercial contributor:** {card['top_commercial_contributor']}",
        "",
        f"**Safety profile:** {card['safety_profile']}",
        f"**Top safety factor:** {card['top_safety_factor']}",
        "",
        f"**Evidence conflict reasoning:** {card['evidence_conflict_reasoning']}",
        "",
        f"**Positive drivers:** {card['positive_drivers']}",
        f"**Negative drivers:** {card['negative_drivers']}",
        "",
        f"**Limitations:** {card['limitations']}",
    ]

    if card["missing_information"]:
        lines.append(f"**Missing information:** {'; '.join(card['missing_information'])}")
    if card["not_searched"]:
        lines.append(f"**Not searched:** {'; '.join(card['not_searched'])}")

    connectors = card["connector_unavailable"]
    lines.append(
        f"**Connector status:** patent — {connectors['patent_connector']}; "
        f"retail — {connectors['retail_connector']}"
    )

    lines += [
        "",
        f"**Recommended next step:** {card['recommended_next_step']}",
        "",
        f"**Traceability:** sources — {card['traceability']['source_record_ids']}; "
        f"corroboration — {card['traceability']['corroboration']}",
        "",
    ]

    basis = card["confidence_basis"]
    lines += [
        "**Confidence basis:**",
        f"- Confidence level: {basis['confidence_level']} | Tier: {basis['confidence_tier']}",
        f"- Evidence completeness: {basis['evidence_completeness']}",
        f"- Human evidence availability: {basis['human_evidence_availability']}",
        f"- Regulatory data availability: {basis['regulatory_data_availability']}",
        f"- Safety data availability: {basis['safety_data_availability']}",
        f"- Fallback/default values used: {basis['fallback_or_default_values_used']}",
        "",
    ]

    lines += _format_comparison_section(row.get("Comparative_Rationale_Structured"))
    lines += _format_robustness_section(robustness)
    lines += _format_evidence_conflict_section(row.get("Evidence_Conflict_Structured"))

    lines += [
        "",
        "---",
        "",
    ]
    return "\n".join(lines)


def generate_pharma_report(
    result: pd.DataFrame,
    indication: str,
    dosage_form: str,
    market: str,
    top_n: int = 20,
    standardized_project: dict = None,
) -> str:
    """Builds the full Markdown report. Returns a short, explicit
    "no candidates" report (not an empty string, not an exception) if
    `result` is empty — a report with zero findings is itself a
    finding worth stating plainly.

    standardized_project (optional): the dict question_understanding_engine.
    standardize_project_definition() already builds in step_inputs.py —
    passed straight through, not recomputed here, so this stays a
    formatting layer, not a second source of the same information.
    """
    lines = [
        "# Botanical R&D Decision Intelligence Report",
        "",
        f"**Research question:** Which alternative botanical sources are worth "
        f"investigating for {dosage_form} products targeting {indication} in {market}?",
        "",
    ]

    if standardized_project:
        lines.append("## Project Definition")
        lines.append("")
        lines.append(f"- **Product type:** {standardized_project.get('product_type', 'Not specified')}")
        lines.append(f"- **Route:** {standardized_project.get('route', 'Not specified')}")
        lines.append(f"- **Target population:** {standardized_project.get('target_population', 'Not specified')}")
        lines.append(f"- **Target market:** {standardized_project.get('target_market', market)}")
        constraints = standardized_project.get("constraints") or []
        if constraints:
            lines.append(f"- **Safety constraints:** {', '.join(constraints)}")
        reg_focus = standardized_project.get("regulatory_focus") or []
        if reg_focus:
            lines.append(f"- **Regulatory focus:** {', '.join(reg_focus)}")
        evidence_reqs = standardized_project.get("evidence_requirements") or []
        if evidence_reqs:
            lines.append(f"- **Evidence requirements:** {', '.join(evidence_reqs)}")
        lines.append("")

    if result.empty:
        lines += [
            "**No candidates were evaluated.** This report reflects the absence of "
            "any run() output — check that a reference plant/compound was found "
            "for this indication before treating this as a scientific finding.",
        ]
        return "\n".join(lines)

    total = len(result)
    lines.append(f"**Candidates evaluated:** {total}")
    lines.append("")

    # Executive summary: counts by Go/Investigate/Hold/No-Go.
    lines.append("## Executive Summary")
    lines.append("")
    lines.append("| Call | Count |")
    lines.append("|---|---|")
    if "Go_Investigate_Hold_NoGo" in result.columns:
        counts = result["Go_Investigate_Hold_NoGo"].value_counts()
        for call in GO_CALL_ORDER:
            if call in counts.index:
                lines.append(f"| {call} | {counts[call]} |")
        other_calls = set(counts.index) - set(GO_CALL_ORDER)
        for call in sorted(other_calls):
            lines.append(f"| {call} | {counts[call]} |")
    lines.append("")

    # Full write-ups for the top-scoring candidates.
    sortable = result.copy()
    if "R&D_Opportunity_Score" in sortable.columns:
        sortable = sortable.sort_values("R&D_Opportunity_Score", ascending=False)
    top = sortable.head(top_n)

    # Sprint 3: build_robustness_analysis() is called EXACTLY ONCE here,
    # over the FULL result (not just `top`, so each reference group's
    # winner/runner-up are found correctly even if one falls outside
    # the top_n cutoff) — this is the ONLY call site in this codebase.
    #
    # IMPORTANT — this is NOT a production DataFrame column. Unlike
    # Comparative_Rationale_Structured (Sprint 2) or the Sprint-1 card
    # fields, the robustness object is never written into
    # botanical_rd_candidate_engine.py's OUTPUT_COLUMNS or returned
    # from run() — it exists only as this local, in-memory
    # `robustness_series` variable, computed fresh every time a report
    # is generated, and consumed immediately by _format_robustness_section()
    # below. No engine change was needed or made for this Sprint;
    # do not assume a "Robustness_Structured" (or similarly named)
    # column exists anywhere on a run() result — it does not.
    robustness_series = build_robustness_analysis(result)

    lines.append(f"## Top Candidates (top {len(top)} of {total}, ranked by R&D Opportunity Score)")
    lines.append("")
    for i, (idx, row) in enumerate(top.iterrows(), start=1):
        lines.append(_candidate_section(row, i, robustness_series.get(idx)))

    # Compact summary table for everything else.
    remainder = sortable.iloc[len(top):]
    if not remainder.empty:
        lines.append(f"## Remaining Candidates ({len(remainder)})")
        lines.append("")
        lines.append("| Plant | Compound | Score | Confidence | Call |")
        lines.append("|---|---|---|---|---|")
        for _, row in remainder.iterrows():
            lines.append(
                f"| {row.get('Alternative_Plant', '')} | {row.get('Shared_or_Similar_Compound', '')} | "
                f"{row.get('R&D_Opportunity_Score', '')} | {row.get('Evidence_Confidence', '')} | "
                f"{row.get('Go_Investigate_Hold_NoGo', '')} |"
            )
        lines.append("")

    return "\n".join(lines)
