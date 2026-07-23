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

import re
from typing import Optional


def go_investigate_hold_no_go(decision_class_ah: str, fallback_occurred: bool = False) -> str:
    """Explicit Go/Investigate/Hold/No-Go call, mapped from
    Decision_Class_AH (Phase 6) — the audit asked for this exact label
    set; Decision_Class_AH already carries the information, it was
    just never rendered in these terms.

    fallback_occurred (external review #17): True when one or more of
    the engine's core Supabase loads (plant_compounds, compound_profiles,
    scientific_evidence) actually FAILED this run — not merely returned
    few rows — and the engine fell back to whatever local/seed data it
    had. A "Go" call must never rest on data that may not have actually
    loaded; when this is True, "Go" is capped down to "Investigate".
    Hold and No-Go are already conservative enough not to need capping.
    """
    letter = (decision_class_ah or "").strip()[:1].upper()
    call = {
        "A": "Go",
        "B": "Go",
        "C": "Investigate",
        "D": "Investigate",
        "E": "Investigate",
        "F": "Investigate — verify before proceeding",
        "G": "Hold",
        "H": "No-Go",
    }.get(letter, "Hold")

    if fallback_occurred and call == "Go":
        return "Investigate — data source reliability could not be confirmed this run"

    return call


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
        result += (
            f" Regulatory barrier(s) identified (screening signal from keyword "
            f"matching, not a verified legal determination — confirm jurisdiction, "
            f"date, and whether the restriction applies to the whole plant or a "
            f"specific extract/preparation before relying on it): {regulatory_barriers}."
        )

    return result


def regulatory_rationale(market_status: str, regulatory_barriers: Optional[str] = None) -> str:
    """The REGULATORY dimension alone (audit Task 1's decision card asks
    for Scientific/Clinical/Regulatory/Commercial/Safety as five DISTINCT
    rationales, not one combined market sentence). Split out rather than
    changing commercial_regulatory_rationale() itself, since that
    function's combined behavior is already depended on elsewhere."""
    regulatory_state = {
        "Regulatory monograph exists": "A regulatory monograph exists for this application.",
        "Traditional-use status": "Only traditional-use recognition exists — no formal regulatory monograph.",
        "Search not performed": "No regulatory search has been performed for this candidate.",
        "Search incomplete": "A regulatory search was attempted but did not resolve a clear status.",
        "Conflicting market evidence": "Regulatory signals conflict and require manual review.",
    }.get(market_status, f"Regulatory status: {market_status}.")

    if regulatory_barriers and regulatory_barriers != "None identified":
        regulatory_state += (
            f" Regulatory barrier(s) identified (screening signal, not a verified "
            f"legal determination — confirm jurisdiction, effective date, and "
            f"whether the restriction applies to the whole plant or a specific "
            f"extract/preparation before relying on it): {regulatory_barriers}."
        )
    else:
        regulatory_state += " No regulatory barrier was identified in the available evidence text."

    return regulatory_state


def commercial_rationale(market_status: str, white_space_type: str) -> str:
    """The COMMERCIAL dimension alone (audit Task 1)."""
    base = f"Market status: {market_status}."
    if white_space_type == "Industrial R&D White Space":
        return base + (
            " Real scientific signal exists alongside an open commercial space — "
            "the strongest commercial argument for R&D investment this platform "
            "can make."
        )
    if white_space_type == "Commercial White Space":
        return base + (
            " A completed commercial search found no verified competing product — "
            "a genuine market gap, if the underlying science holds up."
        )
    if white_space_type == "Data Gap":
        return base + " Commercial opportunity cannot yet be assessed — no market search has actually been performed."
    return base


def safety_rationale(safety_flags: str, interaction_flags: str) -> str:
    """The SAFETY dimension alone (audit Task 1)."""
    flags = safety_flags if safety_flags and safety_flags != "No explicit flag found" else None
    interactions = interaction_flags if interaction_flags and interaction_flags != "No explicit flag found" else None

    if not flags and not interactions:
        return "No explicit safety flag or drug-interaction concern was identified in the available evidence text."

    parts = []
    if flags:
        parts.append(f"Safety flag(s) identified: {flags}")
    if interactions:
        parts.append(f"Interaction flag(s) identified: {interactions}")

    return (
        "; ".join(parts) + ". These are screening signals extracted from evidence "
        "text, not a completed toxicological review."
    )


def clinical_rationale(
    evidence_hierarchy_detail: Optional[str],
    evidence_confidence: float,
    has_negative_evidence: bool,
) -> str:
    """The CLINICAL dimension alone (audit Task 1) — distinct from
    scientific_rationale(), which covers the chemical/mechanistic link;
    this covers whether clinical-grade evidence (as opposed to
    in-vitro/mechanistic/traditional-use evidence) actually exists."""
    tier = evidence_hierarchy_detail or "Unclassified"
    clinical_tiers = {
        "Systematic review / meta-analysis", "Clinical trial", "Observational human evidence",
    }

    if tier in clinical_tiers:
        note = f"Clinical-grade evidence exists: {tier} (Evidence_Confidence {evidence_confidence})."
    else:
        note = (
            f"No clinical-grade evidence was found — the strongest evidence tier "
            f"identified is {tier}, which is preclinical/mechanistic or weaker."
        )

    if has_negative_evidence:
        note += " A negative/contradictory clinical finding is also on record — see Evidence_Conflict_Reasoning."

    return note


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


CONFLICT_REASON_HINTS = {
    "Population differences": [
        "different population", "elderly population", "pediatric population",
        "healthy volunteers", "patient population", "different age group",
    ],
    "Dose differences": [
        "different dose", "higher dose", "lower dose", "dose-dependent",
        "dose-response",
    ],
    "Extraction/preparation differences": [
        "different extract", "different preparation", "standardized extract",
        "crude extract", "different formulation",
    ],
    "Study design differences": [
        "open-label", "uncontrolled study", "randomized controlled",
        "observational design", "retrospective design", "prospective design",
    ],
    "Endpoint differences": [
        "different endpoint", "primary endpoint", "surrogate endpoint",
        "different outcome measure",
    ],
}


def _hypothesize_conflict_reason(raw_evidence_text: Optional[str]) -> Optional[str]:
    """Honest, keyword-based hint at WHY two findings might conflict —
    population/dose/extraction/study-design/endpoint differences, per
    audit Task 4. Returns None (never a guess) when the evidence text
    doesn't actually mention any of these — a missing reason is
    reported as missing, not filled in with a plausible-sounding
    fabrication."""
    if not raw_evidence_text:
        return None
    lowered = raw_evidence_text.lower()
    hits = [label for label, terms in CONFLICT_REASON_HINTS.items() if any(t in lowered for t in terms)]
    return "; ".join(hits) if hits else None


def evidence_conflict_reasoning(
    occurrence_corroboration: str,
    has_negative_evidence: bool,
    negative_evidence_types: str,
    evidence_confidence: float,
    raw_evidence_text: Optional[str] = None,
) -> str:
    """A CSO doesn't want "Has_Negative_Evidence: True" as a bare flag —
    they want to know whether the evidence base is POSITIVE, MIXED, or
    NEGATIVE (audit Task 4), and how much that should temper trust.
    Built from signals already computed elsewhere (Occurrence_Corroboration's
    source count, Has_Negative_Evidence, Negative_Evidence_Types) plus,
    optionally, the raw evidence text for the WHY-hint — no new evidence
    collection, this is a reasoning layer over what already exists.

    Audit Task 5's exact requirement — never confuse these three
    situations — is enforced explicitly here, since an earlier version
    of this function collapsed the first two into one identical message:
      "No evidence exists"              -> source_count == 0, no negative finding
      "Evidence exists but insufficient" -> source_count == 1, no negative finding
      "Evidence exists and is negative"  -> has_negative_evidence == True
    These are different scientific conclusions and must read as
    different sentences, not the same templated line with a number
    swapped in.
    """
    source_count = 0
    match = re.search(r"Corroborated by (\d+)", occurrence_corroboration or "")
    if match:
        source_count = int(match.group(1))
    elif occurrence_corroboration and "Single-source" in occurrence_corroboration:
        source_count = 1

    if source_count == 0 and not has_negative_evidence:
        return (
            "NO EVIDENCE FOUND: no supporting or contradicting evidence was "
            "identified for this candidate. This is a data gap, not a scientific "
            "finding — it says nothing about whether the candidate is good or bad."
        )

    if not has_negative_evidence:
        if source_count >= 2:
            return (
                f"POSITIVE, CONSISTENT: {source_count} independent sources were "
                f"found and none contradicts the finding."
            )
        return (
            f"POSITIVE BUT INSUFFICIENT: {source_count} source found, no "
            f"contradiction on record, but too little independent corroboration "
            f"to be conclusive on its own."
        )

    reason = _hypothesize_conflict_reason(raw_evidence_text)
    reason_text = (
        f" Possible reason for the conflict: {reason}."
        if reason else
        " Reason for the conflict is not determinable from the available evidence text."
    )

    if source_count >= 3:
        return (
            f"MIXED (mostly positive, one contradiction): {source_count} "
            f"independent sources support this candidate, but a negative/contradictory "
            f"finding ({negative_evidence_types}) was also identified.{reason_text} "
            f"With this many corroborating sources, the contradiction more likely "
            f"reflects a specific study limitation than an invalid overall signal — "
            f"but read it before treating this as settled."
        )

    if source_count >= 1:
        return (
            f"NEGATIVE, GENUINELY CONFLICTING: only {source_count} source(s) support "
            f"this candidate, and a negative/contradictory finding "
            f"({negative_evidence_types}) was also identified.{reason_text} With this "
            f"little corroboration, the contradiction carries real weight — it must "
            f"be resolved, not just noted, before this recommendation can be trusted."
        )

    return (
        f"NEGATIVE ONLY: no supporting source was found, but a negative/contradictory "
        f"finding ({negative_evidence_types}) was identified.{reason_text} This "
        f"candidate should not be recommended without further investigation."
    )


def recommendation_confidence_statement(
    go_call: str,
    candidate_evidence_strength_tier: str,
    evidence_confidence: float,
    has_negative_evidence: bool,
) -> str:
    """ALWAYS present — unlike Confidence_Note (which only fires for the
    specific high-opportunity/low-confidence mismatch case), this
    translates the Go/Investigate/Hold/No-Go call itself into an
    explicit statement of how much to trust THAT CALL, not just the
    underlying evidence. An R&D director reading a GO needs to know
    immediately whether it's well-supported or borderline — the call
    alone doesn't say that.
    """
    tier = candidate_evidence_strength_tier or "Preliminary"
    contested_note = (
        " A contradictory finding is on record for this candidate — see "
        "Evidence_Conflict_Reasoning."
        if has_negative_evidence else ""
    )

    letter = (go_call or "").strip()[:1].upper()

    if go_call == "Go":
        if tier in {"Broad Evidence", "High-priority evidence tier"} and not has_negative_evidence:
            return f"This GO recommendation is well-supported: {tier}, no contradictory findings.{contested_note}"
        return (
            f"This GO recommendation rests on {tier} — review the underlying "
            f"evidence directly before committing resources.{contested_note}"
        )

    if go_call and go_call.startswith("Investigate"):
        return (
            f"This INVESTIGATE recommendation reflects real uncertainty: {tier}."
            f"{contested_note} Treat as a lead worth pursuing, not a validated conclusion."
        )

    if go_call == "Hold":
        return (
            f"This HOLD reflects insufficient evidence ({tier}) to recommend action "
            f"either way — a request for more data, not a rejection."
        )

    if go_call == "No-Go":
        return (
            "This NO-GO reflects an identified safety concern — do not proceed "
            "without expert toxicological/safety review, regardless of scientific "
            "opportunity."
        )

    return f"Confidence in this recommendation: {tier}.{contested_note}"


def competitive_positioning_statement(
    market_status: str,
    candidate_evidence_strength_tier: str,
    regulatory_barriers: Optional[str],
    white_space_type: str,
) -> str:
    """Synthesizes market maturity + scientific maturity + regulatory
    maturity into ONE competitive-positioning statement. Market_Status,
    Candidate_Evidence_Strength_Tier, and Regulatory_Barriers already
    exist as separate columns — a CSO comparing candidates wants this
    as a single read, not three columns to mentally combine themselves
    every time.
    """
    scientific_maturity = {
        "High-priority evidence tier": "scientifically mature (strong, corroborated evidence)",
        "Broad Evidence": "scientifically developing (solid, multi-source evidence)",
        "Partial Evidence": "scientifically early-stage (limited evidence)",
        "Preliminary": "scientifically nascent (little to no evidence)",
    }.get(candidate_evidence_strength_tier, "scientific maturity not established")

    market_maturity = {
        "Regulatory monograph exists": "regulatorily established (monograph recognition)",
        "Traditional-use status": "regulatorily semi-established (traditional-use recognition only)",
        "Commercial evidence reported, not independently verified": "commercially present but unverified",
        "No verified product found": "commercially open (no verified competing product)",
        "Conflicting market evidence": "commercially ambiguous (conflicting signals)",
    }.get(market_status, "commercial/regulatory maturity not established")

    barrier_note = (
        f" Regulatory barrier(s) on record: {regulatory_barriers}."
        if regulatory_barriers and regulatory_barriers != "None identified"
        else ""
    )

    positioning = f"Competitive position: {scientific_maturity}; {market_maturity}.{barrier_note}"

    if white_space_type == "Industrial R&D White Space":
        positioning += (
            " This combination — real science, open market — is the strongest "
            "competitive position an alternative-source candidate can have."
        )
    elif white_space_type == "Data Gap":
        positioning += (
            " Competitive position cannot yet be assessed — neither the science "
            "nor the market has actually been investigated."
        )

    return positioning


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


# =====================================================================
# Sprint 1 (post-review corrections) — the Explainable Recommendation
# Card, and the missing-data/confidence-basis machinery it needs.
#
# SCOPE NOTE, per reviewer feedback: an earlier version of this card
# lived in pharma_report_generator.py and imported a shared parser from
# comparative_rationale.py. Both of those files pre-date Sprint 1 and
# belong to earlier work (Gap 9 / the "why were the others rejected"
# work respectively) — reusing/expanding them inside Sprint 1 blurred
# sprint boundaries. Both files have been reverted to their exact
# pre-Sprint-1 state (verified byte-identical). Everything below is
# self-contained within this file, which IS Sprint 1's correct home —
# it only assembles OTHER functions already defined in this same file.
# The cost of this: _local_parse_score_breakdown() below duplicates
# ~15 lines already present in comparative_rationale.py. That
# duplication is intentional and accepted here specifically to avoid
# crossing sprint boundaries, not an oversight.
# =====================================================================

def _local_parse_score_breakdown(breakdown: Optional[str]) -> dict:
    """Self-contained copy of the Score_Breakdown parser (see
    comparative_rationale.py's _parse_score_breakdown — intentionally
    NOT imported from there; see the scope note above). Reverses
    _format_score_breakdown()'s "Name: +12.3; Other: -4.0" format back
    into a dict."""
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


# Maps botanical_rd_candidate_engine.py's actual Score_Breakdown
# component names onto the dimensions this card reports on.
#
# CORRECTION (review point 2): an earlier version mapped "Market
# signal" to BOTH Commercial and Regulatory. That was wrong — market
# evidence and regulatory evidence are not the same thing, and
# _score_candidate() genuinely does not compute any independent
# regulatory score contribution (its "Market signal" component is
# built entirely from Market_Status, which conflates commercial and
# regulatory signals into one bucket — see botanical_rd_candidate_engine.py).
# "Regulatory" is deliberately NOT a value anywhere in this mapping;
# regulatory_top_contributor() below always returns the honest
# unavailable message rather than ever attributing a score to it.
_COMPONENT_TO_DIMENSIONS = {
    "Chemical/mechanistic link": ["Scientific"],
    "Novelty": ["Scientific"],
    "Multi-compound match bonus": ["Scientific"],
    "Evidence quality": ["Clinical"],
    "Product-development fit": ["Commercial"],
    "Market signal": ["Commercial"],
    "Safety/interaction/self-row penalty": ["Safety"],
}

NO_REGULATORY_SCORE_CONTRIBUTION_MESSAGE = (
    "No independent regulatory score contribution is available in the current "
    "scoring model. Market_Status/regulatory signals are folded into a single "
    "\"Market signal\" component in Score_Breakdown that does not separate "
    "commercial from regulatory effects — see Regulatory_Rationale for "
    "contextual (non-scored) regulatory evidence instead."
)


def _top_contributor_for_dimension(components: dict, dimension: str) -> str:
    """Largest-magnitude Score_Breakdown component that maps to
    `dimension`. Returns an explicit "not identified" message — never a
    guess — when no component in this row's actual breakdown touches
    that dimension."""
    if dimension == "Regulatory":
        return NO_REGULATORY_SCORE_CONTRIBUTION_MESSAGE
    relevant = {
        name: value for name, value in components.items()
        if dimension in _COMPONENT_TO_DIMENSIONS.get(name, [])
    }
    if not relevant:
        return f"No {dimension.lower()} factor identified in the score breakdown for this candidate."
    top_name = max(relevant, key=lambda n: abs(relevant[n]))
    return f"{top_name}: {relevant[top_name]:+.1f}"


# ---------------------------------------------------------------------
# Missing-data semantics (review point 5). One consistent vocabulary,
# applied wherever this card has to say whether something is known:
#   "available"              — a real value/finding is present
#   "limited"                — some signal exists but is thin/partial
#   "searched but not found" — a search ran and genuinely found nothing
#   "not searched"           — no search was ever attempted
#   "connector unavailable"  — the specific data source is not wired in
#                               / not configured for this row
#   "unknown / legacy state" — the row doesn't carry enough information
#                               (e.g. an older/incomplete row) to tell
#                               which of the above applies
# An empty string or missing key is NEVER silently read as "no
# evidence" — every helper below is explicit about which of the six
# states it's reporting and why.
# ---------------------------------------------------------------------

_NO_SEARCH_MARKET_STATES = {"Search not performed", "Search incomplete", "Unknown", "Source unavailable"}
_POSITIVE_REGULATORY_STATES = {"Regulatory monograph exists", "Traditional-use status"}
_HUMAN_EVIDENCE_HIERARCHY_TIERS = {
    "Systematic review / meta-analysis", "Clinical trial", "Observational human evidence",
}
_NON_HUMAN_EVIDENCE_HIERARCHY_TIERS = {
    "Validated ex vivo / in vivo", "In vitro / mechanistic",
}


def _regulatory_data_availability(market_status: Optional[str]) -> str:
    if not market_status:
        return "unknown / legacy state"
    if market_status in _POSITIVE_REGULATORY_STATES:
        return "available"
    if market_status in _NO_SEARCH_MARKET_STATES:
        return "not searched"
    if market_status in {"Conflicting market evidence", "Commercial evidence reported, not independently verified"}:
        return "limited"
    return "unknown / legacy state"


def _human_evidence_availability(evidence_hierarchy_detail: Optional[str]) -> str:
    if not evidence_hierarchy_detail or evidence_hierarchy_detail == "Unclassified":
        return "unknown / legacy state"
    if evidence_hierarchy_detail in _HUMAN_EVIDENCE_HIERARCHY_TIERS:
        return "available"
    if evidence_hierarchy_detail in _NON_HUMAN_EVIDENCE_HIERARCHY_TIERS:
        return "searched but not found"  # a hierarchy WAS classified, just not a human one
    if evidence_hierarchy_detail == "Traditional-use / regulatory monograph":
        return "limited"
    if evidence_hierarchy_detail == "Occurrence / analytical chemistry only":
        return "searched but not found"
    return "unknown / legacy state"


def _safety_data_availability(evidence_level: Optional[str], safety_flags: Optional[str]) -> str:
    """"No explicit flag found" on its own does NOT mean "no safety
    data available" — it could mean a search ran over real evidence
    text and found nothing (searched but not found) or that there was
    no evidence text to search in the first place (not searched). This
    distinguishes the two using Evidence_Level as the signal for
    whether extraction actually had text to run over."""
    if not evidence_level:
        return "unknown / legacy state"
    if evidence_level == "No direct evidence":
        return "not searched"
    if safety_flags and safety_flags != "No explicit flag found":
        return "available"
    return "searched but not found"


def _connector_availability(row) -> dict:
    """Patent/retail connector status is only ever present on a row
    when enrich_candidates_with_market_landscape() (an OPT-IN,
    separate call — see botanical_rd_candidate_engine.py, not part of
    the default run()) was actually applied to this result. On a
    standard, non-enriched row, this is honestly reported as
    "connector unavailable" — not "not searched" and not a guess at
    what the status might be — since this card genuinely cannot tell
    whether a connector exists without that enrichment having run."""
    has_enrichment = any(
        key in row.index if hasattr(row, "index") else key in row
        for key in ("Market_Landscape_Patent_Search_Status", "Market_Landscape_Retail_Search_Status")
    )
    if not has_enrichment:
        return {
            "patent_connector": "connector unavailable — market/patent landscape enrichment was not run for this result",
            "retail_connector": "connector unavailable — market/patent landscape enrichment was not run for this result",
        }
    return {
        "patent_connector": row.get("Market_Landscape_Patent_Search_Status", "unknown / legacy state"),
        "retail_connector": row.get("Market_Landscape_Retail_Search_Status", "unknown / legacy state"),
    }


def _fallback_or_default_values_used(go_call: Optional[str]) -> str:
    """Fallback/data-reliability status (see
    BotanicalRDCandidateEngine.data_source_reliable and
    go_investigate_hold_no_go()'s fallback_occurred parameter) is
    tracked at the RUN level, not per-candidate — this is the only
    signal visible on an individual row, and is reported as such
    rather than implying a per-row check was made."""
    if go_call and "data source reliability could not be confirmed" in go_call:
        return (
            "YES — this run's Go_Investigate_Hold_NoGo call was capped because core "
            "data reliability could not be confirmed this run (see "
            "BotanicalRDCandidateEngine.data_source_reliable). This is a run-level "
            "signal, not independently verified per candidate."
        )
    return (
        "Not detected on this row (no fallback-capping language in "
        "Go_Investigate_Hold_NoGo) — but fallback status is only tracked at the "
        "run level; this is the best available per-row signal, not an independent "
        "per-candidate check."
    )


def build_confidence_basis(row) -> dict:
    """Review point 4 — structured confidence basis, distinguishing
    every piece the review named explicitly. No arbitrary thresholds
    are introduced anywhere here; every value below is read directly
    from an existing categorical column."""
    evidence_hierarchy_detail = row.get("Evidence_Hierarchy_Detail")
    evidence_level = row.get("Evidence_Level")
    market_status = row.get("Market_Status")

    return {
        "confidence_level": row.get("Evidence_Confidence", None),
        "confidence_tier": row.get("Candidate_Evidence_Strength_Tier", None),
        "evidence_completeness": (
            "Not distinctly tracked as its own field in the current repository — "
            "Candidate_Evidence_Strength_Tier is the closest available proxy "
            "(combines source count, confidence, and hierarchy tier)."
        ),
        "human_evidence_availability": _human_evidence_availability(evidence_hierarchy_detail),
        "regulatory_data_availability": _regulatory_data_availability(market_status),
        "safety_data_availability": _safety_data_availability(evidence_level, row.get("Safety_Flags")),
        "critical_missing_information": build_missing_information(row),
        "fallback_or_default_values_used": _fallback_or_default_values_used(row.get("Go_Investigate_Hold_NoGo")),
    }


def build_missing_information(row) -> list:
    """Itemized, traceable list of what's genuinely absent for this
    candidate — each item traces to a specific column's documented
    "nothing found"/"not reported" sentinel value, never inferred from
    a bare empty string."""
    missing = []

    if row.get("Evidence_Level") == "No direct evidence":
        missing.append("No direct evidence text was found for this candidate.")

    corroboration = str(row.get("Occurrence_Corroboration", "") or "")
    if "No independent source identified" in corroboration:
        missing.append("No independent corroborating source was identified.")

    if str(row.get("Concentration_Info", "")) in {"", "Not clearly reported"}:
        missing.append("Compound concentration was not clearly reported.")

    if str(row.get("Extraction_Method", "")) in {"", "Not clearly reported"}:
        missing.append("Extraction method was not clearly reported.")

    market_status = row.get("Market_Status")
    if market_status in _NO_SEARCH_MARKET_STATES:
        missing.append(f"Market/regulatory picture not established: {market_status}.")

    return missing


def build_not_searched(row) -> list:
    """Review point 3's not_searched field — states that were
    genuinely NEVER searched, distinct from a search that ran and
    found nothing (see build_missing_information for the latter)."""
    not_searched = []
    market_status = row.get("Market_Status")
    if market_status in {"Search not performed", "Search incomplete"}:
        not_searched.append(f"Commercial/regulatory market search: {market_status}.")

    connectors = _connector_availability(row)
    if "not run for this result" in connectors["patent_connector"]:
        not_searched.append("Patent search: enrichment not run for this result (opt-in step not applied).")
    if "not run for this result" in connectors["retail_connector"]:
        not_searched.append("Retail product search: enrichment not run for this result (opt-in step not applied).")

    return not_searched


def build_recommendation_card(row) -> dict:
    """Sprint 1 (post-review corrections) — the Explainable
    Recommendation Card. Every field below is required by the review
    and populated ONLY from data that already exists on a run() output
    row — nothing here is invented, and every "not available"/"not
    searched"/"connector unavailable" state is stated explicitly
    rather than inferred from an empty string.
    """
    components = _local_parse_score_breakdown(row.get("Score_Breakdown"))
    positive_drivers = {name: value for name, value in components.items() if value > 0}
    negative_drivers = {name: value for name, value in components.items() if value < 0}
    connectors = _connector_availability(row)

    return {
        "botanical": row.get("Alternative_Plant", "Unknown plant"),
        "final_recommendation": row.get("Go_Investigate_Hold_NoGo", "Unknown"),

        # Q1: why selected
        "scientific_rationale": row.get("Scientific_Rationale", ""),
        "top_scientific_contributor": _top_contributor_for_dimension(components, "Scientific"),

        # Q3 (audit numbering): which clinical evidence contributed most
        "clinical_rationale": row.get("Clinical_Rationale", ""),
        "top_clinical_contributor": _top_contributor_for_dimension(components, "Clinical"),
        "mechanism_of_action": row.get("Target_or_Mechanism", "Not clearly extracted"),

        # Q4: regulatory — CORRECTED, never a fabricated score contribution
        "regulatory_rationale": row.get("Regulatory_Rationale", ""),
        "top_regulatory_contributor": _top_contributor_for_dimension(components, "Regulatory"),

        # Q5: commercial
        "commercial_rationale": row.get("Commercial_Rationale", ""),
        "top_commercial_contributor": _top_contributor_for_dimension(components, "Commercial"),

        # Q6: safety
        "safety_profile": row.get("Safety_Rationale", ""),
        "top_safety_factor": _top_contributor_for_dimension(components, "Safety"),

        # Review point 3's required fields, verbatim names:
        "positive_drivers": positive_drivers if positive_drivers else "None — no component increased the score.",
        "negative_drivers": negative_drivers if negative_drivers else "None — no component reduced the score.",
        "limitations": row.get("Evidence_Weaknesses", "None identified"),
        "missing_information": build_missing_information(row),
        "not_searched": build_not_searched(row),
        "connector_unavailable": connectors,
        "recommended_next_step": row.get("Next_Experiment_Suggestion", ""),
        "traceability": {
            "source_record_ids": row.get("Source_Record_IDs", "No specific source record identified"),
            "corroboration": row.get("Occurrence_Corroboration", ""),
        },
        "confidence_basis": build_confidence_basis(row),

        # Retained from the pre-correction version, still valid:
        "evidence_conflict_reasoning": row.get("Evidence_Conflict_Reasoning", ""),
    }
