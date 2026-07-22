"""
Gap 6 + Gap 8 — structured rationale and the "WHY" knowledge layer.

WHAT THIS IS
_rationale() in botanical_rd_candidate_engine.py produces one narrative
paragraph mixing chemical basis, market, evidence, and decision into a
single string — a reviewer has to re-parse it by hand every time to
separate "why scientifically" from "why commercially" from "what's
still missing." This module builds that separation, plus two genuinely
new pieces of content: an explicit Go/Investigate/Hold/No-Go call, and
a templated next-experiment suggestion.

WHY A SEPARATE MODULE, NOT A REWRITE OF _rationale()
Every input this module reads (match_quality, Target_Provenance,
Evidence_Hierarchy_Detail, Occurrence_Corroboration, Market_Status,
White_Space_Type, Decision_Class_AH, Safety_Flags, ...) already exists
on the row by the time _rationale() runs — this is a second, structured
view over the SAME inputs, wired in as additional columns exactly like
Evidence_Hierarchy_Detail/Decision_Class_AH/White_Space_Type were.
_rationale()'s existing free-text paragraph is untouched; nothing that
already reads it (Rationale column, the CSV, prior tests) needs to
change.

THE "WHY" LAYER (Gap 8), directly answered by these functions:
    "WHY is this better than existing alternatives?"
        -> scientific_rationale(): states the match type (exact/
           target-verified/class-only) and how corroborated it is.
    "WHY is this commercially interesting?"
        -> commercial_regulatory_rationale(): states the market/
           regulatory/white-space picture in one sentence.
    "WHY is this compound a better candidate?"
        -> evidence_strengths(): the concrete, itemized reasons.
    "WHY does this deserve lab validation?"
        -> next_experiment_suggestion(): the concrete next step, tied
           to which specific evidence is still missing.

HONESTY ABOUT WHAT THIS IS NOT
These are TEMPLATES over existing structured signals, not a reasoning
model — every sentence traces back to a specific field on the row, on
purpose, so a reviewer can verify each claim against the column that
produced it. This is deliberately more limited (and more auditable)
than an LLM-generated narrative would be.
"""

from __future__ import annotations

from typing import Optional


def go_investigate_hold_no_go(decision_class_ah: str) -> str:
    """Explicit Go/Investigate/Hold/No-Go call, mapped from
    Decision_Class_AH (Phase 6) — the audit asked for this exact label
    set; Decision_Class_AH already carries the information, it was
    just never rendered in these terms."""
    letter = (decision_class_ah or "").strip()[:1].upper()
    return {
        "A": "Go",
        "B": "Go",
        "C": "Investigate",
        "D": "Investigate",
        "E": "Investigate",
        "F": "Investigate — verify before proceeding",
        "G": "Hold",
        "H": "No-Go",
    }.get(letter, "Hold")


def scientific_rationale(
    match_quality: str,
    target_provenance: str,
    evidence_hierarchy_detail: Optional[str],
    occurrence_corroboration: str,
    has_negative_evidence: bool,
) -> str:
    """Answers Gap 8's "WHY is this a better/valid candidate?" from the
    chemical-link and evidence-quality signals already computed."""
    parts = []

    if match_quality == "exact":
        parts.append("Shares the exact reference compound with the reference plant.")
    elif match_quality == "target_verified":
        note = f" ({target_provenance})" if target_provenance and "Not applicable" not in target_provenance else ""
        parts.append(f"Shares a validated biological target with the reference compound{note}.")
    elif match_quality == "class_only":
        parts.append(
            "Shares only a broad chemical class with the reference compound — "
            "no confirmed shared target; this link is a hypothesis, not evidence."
        )
    else:
        parts.append("No chemical or mechanistic link to the reference compound was established.")

    if evidence_hierarchy_detail and evidence_hierarchy_detail != "Unclassified":
        parts.append(f"Strongest evidence tier found: {evidence_hierarchy_detail}.")

    if occurrence_corroboration:
        parts.append(occurrence_corroboration + ".")

    if has_negative_evidence:
        parts.append("A negative or contradictory finding was also identified for this candidate — see Negative_Evidence_Types.")

    return " ".join(parts)


def commercial_regulatory_rationale(
    market_status: str,
    white_space_type: str,
    regulatory_barriers: Optional[str] = None,
) -> str:
    """Answers Gap 8's "WHY is this commercially interesting?" — one
    sentence combining Market_Status (Gap 2) and White_Space_Type
    (Gap 4).

    regulatory_barriers (architecture audit Q8, "what regulatory
    barriers exist?"): optional, defaults to None so every existing
    caller keeps working unchanged. Market_Status/White_Space_Type only
    ever describe whether regulatory RECOGNITION exists — a barrier
    (banned, prescription-only, novel-food status) is the opposite
    concept and can coexist with recognition (e.g. prescription-only
    AND monograph-recognized), so it's stated as its own sentence
    rather than folded into the market_status branches above.
    """
    base = f"Market status: {market_status}."
    if white_space_type == "Industrial R&D White Space":
        result = base + " Real scientific signal exists alongside an open commercial/regulatory space — the combination that most directly argues for R&D investment."
    elif white_space_type == "Commercial White Space":
        result = base + " A completed commercial search found no verified product — a genuine market gap, if the underlying science holds up."
    elif white_space_type == "Regulatory White Space":
        result = base + " No regulatory monograph or traditional-use recognition was found for this application."
    elif white_space_type == "Scientific White Space":
        result = base + " The market picture is secondary here — the more immediate gap is scientific, not commercial (see Scientific_Rationale)."
    elif white_space_type == "Data Gap":
        result = base + " Neither the scientific nor the commercial picture has actually been investigated yet — this is not a finding, just missing data."
    else:
        result = base

    if regulatory_barriers:
        result += f" Regulatory barrier(s) identified: {regulatory_barriers}."

    return result


def evidence_strengths(
    match_quality: str,
    evidence_confidence: float,
    occurrence_corroboration: str,
    market_status: str,
) -> list[str]:
    """Itemized, traceable reasons this candidate looks promising —
    each item corresponds to one specific column value, so it can be
    checked, not just asserted."""
    strengths = []
    if match_quality == "exact":
        strengths.append("Exact compound match to the reference")
    if evidence_confidence >= 65:
        strengths.append(f"High evidence confidence ({evidence_confidence})")
    if "Corroborated by" in (occurrence_corroboration or ""):
        strengths.append(occurrence_corroboration)
    if market_status in {"Regulatory monograph exists", "Traditional-use status"}:
        strengths.append(f"Regulatory recognition: {market_status}")
    return strengths


def evidence_weaknesses(
    evidence_confidence: float,
    occurrence_corroboration: str,
    has_negative_evidence: bool,
    negative_evidence_types: str,
    safety_flags: str,
    market_status: str,
    regulatory_barriers: Optional[str] = None,
) -> list[str]:
    """Itemized, traceable gaps — the counterpart to evidence_strengths,
    so a reviewer sees both sides in the same structured form instead
    of having to infer weaknesses from the absence of a strength."""
    weaknesses = []
    if evidence_confidence < 30:
        weaknesses.append(f"Low evidence confidence ({evidence_confidence})")
    if occurrence_corroboration and (
        "Single-source" in occurrence_corroboration or "No independent source" in occurrence_corroboration
    ):
        weaknesses.append(occurrence_corroboration)
    if has_negative_evidence:
        weaknesses.append(f"Negative/contradictory finding(s): {negative_evidence_types}")
    if safety_flags and safety_flags != "No explicit flag found":
        weaknesses.append(f"Safety flag(s): {safety_flags}")
    if market_status in {"Search not performed", "Search incomplete", "Unknown", "Source unavailable"}:
        weaknesses.append(f"Market picture not established: {market_status}")
    if market_status == "Conflicting market evidence":
        weaknesses.append("Market evidence conflicts and needs manual review")
    if regulatory_barriers:
        weaknesses.append(f"Regulatory barrier(s): {regulatory_barriers}")
    return weaknesses


def next_experiment_suggestion(
    decision_class_ah: str,
    evidence_weaknesses_list: list[str],
    alt_plant: str,
) -> str:
    """Answers Gap 8's "WHY does this deserve lab validation?" by
    stating what specific next step would resolve the weakest part of
    the current picture — templated from Decision_Class_AH plus
    whichever weaknesses are actually present, not generic advice."""
    letter = (decision_class_ah or "").strip()[:1].upper()

    if letter == "H":
        return f"Do not proceed without expert toxicological/safety review of {alt_plant} first."
    if letter == "G":
        return f"Insufficient evidence to propose a specific next experiment for {alt_plant} — expand evidence collection first."
    if letter == "F":
        return (
            f"Treat as hypothesis-generating only: commission a targeted literature review or "
            f"a small pilot study for {alt_plant} before further investment, given the opportunity "
            f"score is not yet backed by matching evidence confidence."
        )

    weakness_text = " ".join(evidence_weaknesses_list).lower()
    if "single-source" in weakness_text or "no independent source" in weakness_text:
        return f"Seek independent corroborating studies for {alt_plant} before proceeding further."
    if letter == "D":
        return f"Conduct in-vitro/in-vivo validation of the shared target mechanism in {alt_plant}."
    if letter in {"C", "A", "B"}:
        return (
            f"Quantify compound concentration and confirm extraction yield in {alt_plant} "
            f"to compare directly against the reference plant."
        )
    if letter == "E":
        return f"Confirm the commercial gap for {alt_plant} with a dedicated retail/patent search before investing further."

    return f"Review available evidence for {alt_plant} manually before deciding on next steps."
