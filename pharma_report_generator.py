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

from comparative_rationale import parse_score_breakdown

GO_CALL_ORDER = [
    "Go",
    "Investigate",
    "Investigate — verify before proceeding",
    "Hold",
    "No-Go",
]

# Maps botanical_rd_candidate_engine.py's actual Score_Breakdown
# component names (see _format_score_breakdown / _score_candidate's
# docstring) onto the 5 dimensions Sprint 1 asks for. This is an
# HONEST mapping, not a forced clean split: "Market signal" is a
# single component that the engine itself doesn't separate into
# commercial vs. regulatory, so it's counted toward both rather than
# arbitrarily assigned to one. No new scoring is introduced here —
# this only re-reads the same ranked breakdown the engine already
# produces per row.
_COMPONENT_TO_DIMENSIONS = {
    "Chemical/mechanistic link": ["Scientific"],
    "Novelty": ["Scientific"],
    "Multi-compound match bonus": ["Scientific"],
    "Evidence quality": ["Clinical"],
    "Product-development fit": ["Commercial"],
    "Market signal": ["Commercial", "Regulatory"],
    "Safety/interaction/self-row penalty": ["Safety"],
}


def _top_contributor_for_dimension(components: dict, dimension: str) -> str:
    """Largest-magnitude Score_Breakdown component that maps to
    `dimension`, formatted as "Name: +N.0" — or an explicit
    "No score-affecting factor identified for this dimension" when
    none of the row's actual components touch it, rather than
    guessing."""
    relevant = {
        name: value for name, value in components.items()
        if dimension in _COMPONENT_TO_DIMENSIONS.get(name, [])
    }
    if not relevant:
        return f"No {dimension.lower()} factor identified in the score breakdown for this candidate."
    top_name = max(relevant, key=lambda n: abs(relevant[n]))
    return f"{top_name}: {relevant[top_name]:+.1f}"


def build_recommendation_card(row) -> dict:
    """Sprint 1 — the Explainable Recommendation Card. Assembles fields
    that ALREADY exist on a run() output row (Scientific_Rationale,
    Clinical_Rationale, Target_or_Mechanism, Regulatory_Rationale,
    Commercial_Rationale, Safety_Rationale, Evidence_Weaknesses,
    Evidence_Confidence, Recommendation_Confidence_Statement,
    Go_Investigate_Hold_NoGo) into one structured object, plus a
    dimension-mapped read of Score_Breakdown to answer "which X
    contributed most" precisely (audit questions 2-7). No new data is
    collected or invented — every value here traces to an existing
    column, and the mapping used to build the dimension breakdown is
    documented above (_COMPONENT_TO_DIMENSIONS).

    Returns a plain dict (not markdown) so it can be reused anywhere a
    structured view is more useful than prose — a future UI card,
    JSON export, or (as done here) the existing markdown report.
    """
    components = parse_score_breakdown(str(row.get("Score_Breakdown", "")))
    score_reducing = {name: value for name, value in components.items() if value < 0}

    return {
        "botanical": row.get("Alternative_Plant", "Unknown plant"),
        "final_recommendation": row.get("Go_Investigate_Hold_NoGo", "Unknown"),
        # Q1: why selected
        "scientific_rationale": row.get("Scientific_Rationale", ""),
        # Q2: which scientific evidence contributed most
        "top_scientific_contributor": _top_contributor_for_dimension(components, "Scientific"),
        # Q3: which clinical evidence contributed most
        "clinical_rationale": row.get("Clinical_Rationale", ""),
        "top_clinical_contributor": _top_contributor_for_dimension(components, "Clinical"),
        "mechanism_of_action": row.get("Target_or_Mechanism", "Not clearly extracted"),
        # Q4: which regulatory information increased confidence
        "regulatory_rationale": row.get("Regulatory_Rationale", ""),
        "top_regulatory_contributor": _top_contributor_for_dimension(components, "Regulatory"),
        # Q5: which commercial factors improved the recommendation
        "commercial_rationale": row.get("Commercial_Rationale", ""),
        "top_commercial_contributor": _top_contributor_for_dimension(components, "Commercial"),
        # Q6: which safety considerations affected the score
        "safety_profile": row.get("Safety_Rationale", ""),
        "top_safety_factor": _top_contributor_for_dimension(components, "Safety"),
        # Q7: which factors reduced the final score
        "score_reducing_factors": score_reducing if score_reducing else "None — no component reduced the score.",
        "limitations": row.get("Evidence_Weaknesses", "None identified"),
        "confidence_level": row.get("Evidence_Confidence", ""),
        "confidence_statement": row.get("Recommendation_Confidence_Statement", ""),
        "evidence_conflict_reasoning": row.get("Evidence_Conflict_Reasoning", ""),
    }


def _candidate_section(row: pd.Series, rank: int) -> str:
    lines = [
        f"### {rank}. {row.get('Alternative_Plant', 'Unknown plant')} — "
        f"{row.get('Go_Investigate_Hold_NoGo', 'Unknown')}",
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
        f"**Scientific rationale:** {row.get('Scientific_Rationale', '')}",
        "",
        f"**Evidence conflict reasoning:** {row.get('Evidence_Conflict_Reasoning', '')}",
        "",
        f"**Commercial & regulatory rationale:** {row.get('Commercial_Regulatory_Rationale', '')}",
        "",
    ]

    card = build_recommendation_card(row)
    lines += [
        "**Score drivers by dimension** (Sprint 1 — which factor contributed "
        "most in each area, read directly from Score_Breakdown):",
        f"- Scientific: {card['top_scientific_contributor']}",
        f"- Clinical: {card['top_clinical_contributor']}",
        f"- Regulatory: {card['top_regulatory_contributor']}",
        f"- Commercial: {card['top_commercial_contributor']}",
        f"- Safety: {card['top_safety_factor']}",
        "",
    ]

    lines += [
        f"**Evidence strengths:** {row.get('Evidence_Strengths', 'None identified')}",
        "",
        f"**Evidence weaknesses:** {row.get('Evidence_Weaknesses', 'None identified')}",
        "",
        f"**Safety considerations:** {row.get('Safety_Flags', 'No explicit flag found')}"
        + (
            f" | **Interactions:** {row.get('Interaction_Flags')}"
            if str(row.get("Interaction_Flags", "")).strip()
            and row.get("Interaction_Flags") != "No explicit flag found"
            else ""
        ),
        "",
        f"**Suggested next step:** {row.get('Next_Experiment_Suggestion', '')}",
        "",
        f"**Corroboration:** {row.get('Occurrence_Corroboration', '')}  ",
        f"**Sources:** {row.get('Source_Record_IDs', 'No specific source record identified')}",
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

    lines.append(f"## Top Candidates (top {len(top)} of {total}, ranked by R&D Opportunity Score)")
    lines.append("")
    for i, (_, row) in enumerate(top.iterrows(), start=1):
        lines.append(_candidate_section(row, i))

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
