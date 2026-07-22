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
— none of which exist in the current OUTPUT_COLUMNS) and was moved to
archive/ rather than reused.

HOW TO USE
    from botanical_rd_candidate_engine import BotanicalRDCandidateEngine
    from pharma_report_generator import generate_pharma_report

    engine = BotanicalRDCandidateEngine(...)
    result = engine.run(indication=..., dosage_form=..., market=...)
    report_markdown = generate_pharma_report(result, indication=..., dosage_form=..., market=...)

Not wired into the Streamlit UI in this change — that's a one-line
follow-up (a "Download report" button in step_rd_candidates.py calling
this function) once the report format itself has been reviewed.
"""

from __future__ import annotations

import pandas as pd

GO_CALL_ORDER = [
    "Go",
    "Investigate",
    "Investigate — verify before proceeding",
    "Hold",
    "No-Go",
]


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

    white_space = str(row.get("White_Space_Type", "") or "").strip()
    if white_space:
        lines.append(f"**White space type:** {white_space}")

    confidence_note = str(row.get("Confidence_Note", "") or "").strip()
    if confidence_note:
        lines.append(f"\n> ⚠️ {confidence_note}")

    lines += [
        "",
        f"**Scientific rationale:** {row.get('Scientific_Rationale', '')}",
        "",
        f"**Commercial & regulatory rationale:** {row.get('Commercial_Regulatory_Rationale', '')}",
        "",
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
) -> str:
    """Builds the full Markdown report. Returns a short, explicit
    "no candidates" report (not an empty string, not an exception) if
    `result` is empty — a report with zero findings is itself a
    finding worth stating plainly."""
    lines = [
        "# Botanical R&D Decision Intelligence Report",
        "",
        f"**Research question:** Which alternative botanical sources are worth "
        f"investigating for {dosage_form} products targeting {indication} in {market}?",
        "",
    ]

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
