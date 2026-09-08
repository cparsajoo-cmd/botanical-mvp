"""R&D Discovery Lane classification -- additive layer only.

WHY THIS FILE EXISTS (architecture note, Hamid, 2026-09-08):

candidate_shortlisting.py's plant-level gate
(build_plant_candidate_shortlist(), see the block that sets
`plant_status` / `Scientific_Triage_Status`) answers one question:
"is this plant good enough, on TODAY's evidence, to recommend building a
product around?" That is exactly the right question for evidence-backed
prioritisation, but it is a different question from "is this plant
scientifically interesting enough to invest R&D attention in, even with
zero human/clinical evidence today?" -- and the existing gate answers both
with the same three labels (Shortlist / Exploratory / Excluded):

  * A mechanistically-plausible, under-studied plant with no clinical
    trials gets capped at "Exploratory" (best case) or "Excluded" (if the
    mechanistic rationale is not judged "explicit enough"), the SAME
    labels used for a plant that has no scientific rationale at all.
  * A plant with a genuine regulatory prohibition gets "Excluded", the
    SAME label as a plant merely lacking evidence.

This module does not change any of that gate's decisions. It adds a
second, explicit classification computed from the exact same inputs the
existing gate already produced (plant_status, plant_hard_stop,
indication_points, mech_points, targets, novelty_points, ...) --
never re-deriving indication relevance, safety text, or mechanism
support with new logic, and never changing Scientific_Triage_Status,
Overall_Score, or any existing field. Every existing consumer of those
fields (tests, exports, the Streamlit UI) is completely unaffected by
importing or calling this module; nothing here is wired into any
decision that changes which plants reach the shortlist output or how it
is scored.

Call sites are responsible for recomputing `regulatory_prohibition_present`
and `explicit_mechanistic_rationale` from the SAME group-level text checks
already used by candidate_shortlisting.py's own gate (see
_critical_plant_stop() and the "Mechanistic empirical" / "Mechanistic
inference only" branch respectively) -- this module intentionally holds no
knowledge of the DataFrame/group shape so it stays a pure, independently
testable function of already-computed scalars.

If candidate_shortlisting.py's plant_status decision tree changes, the
branch conditions in classify_discovery_lane() below must be re-checked
against it; they mirror that tree, they do not own it.
"""

from __future__ import annotations

import math

# --- RD_Discovery_Lane vocabulary -------------------------------------
DISCOVERY_LANE_EVIDENCE_BACKED = "Evidence-Backed Candidate"
DISCOVERY_LANE_HYPOTHESIS = "R&D Discovery Hypothesis"
DISCOVERY_LANE_REGULATORY_STOP = "Regulatory Prohibition"
DISCOVERY_LANE_SAFETY_STOP = "Not Currently Developable (Safety)"
DISCOVERY_LANE_INSUFFICIENT = "Insufficient Signal"
DISCOVERY_LANE_EVIDENCE_GAP = "Established Plant — Evidence Gap for This Indication"
DISCOVERY_LANE_CATALOGUE_EVIDENCE_GAP = "Catalogue Plant — Evidence Gap for This Indication"
DISCOVERY_LANE_CATALOGUE_HYPOTHESIS = "Catalogue R&D Hypothesis — Market Novelty Unassessed"

ALL_DISCOVERY_LANES = (
    DISCOVERY_LANE_EVIDENCE_BACKED,
    DISCOVERY_LANE_HYPOTHESIS,
    DISCOVERY_LANE_REGULATORY_STOP,
    DISCOVERY_LANE_SAFETY_STOP,
    DISCOVERY_LANE_INSUFFICIENT,
    DISCOVERY_LANE_EVIDENCE_GAP,
    DISCOVERY_LANE_CATALOGUE_EVIDENCE_GAP,
    DISCOVERY_LANE_CATALOGUE_HYPOTHESIS,
)

# Novelty-market tiers (candidate_shortlisting.py::_novelty_market()) that
# indicate a plant already has real commercial/market presence -- i.e. it
# is not merely "in the catalogue" as a data-entry, it is a known,
# marketed botanical. Used only to route an Exploratory/mechanism-only
# candidate to DISCOVERY_LANE_EVIDENCE_GAP instead of
# DISCOVERY_LANE_HYPOTHESIS (see classify_discovery_lane() docstring).
# Intentionally NOT "Commercial white-space" / "Emerging commercial
# opportunity" / "Indication-repurposing opportunity" -- those describe a
# plant with LITTLE current market presence, which is exactly the
# discovery-hypothesis case, not the evidence-gap case.
_MARKET_ESTABLISHED_NOVELTY_TIERS = (
    "Established / commercially active",
    "Competitive / saturated market",
)


def classify_discovery_lane(
    *,
    plant_status: str,
    plant_hard_stop: bool,
    regulatory_prohibition_present: bool,
    explicit_mechanistic_rationale: bool,
    indication_points: float,
    dosage_mismatch: bool,
    already_in_catalogue: bool | None = None,
    novelty_tier: str = "",
    direct_evidence_count: int = 0,
) -> str:
    """Return the additive RD_Discovery_Lane label for one plant-level row.

    Mirrors candidate_shortlisting.py's plant_status decision tree
    exactly (see module docstring); does not alter it.

      Shortlist                                -> Evidence-Backed Candidate
      Exploratory / mechanism-only-Excluded,
        candidate genuinely novel-to-catalogue
        or has assessed white-space/repurposing   -> R&D Discovery Hypothesis
      Exploratory / mechanism-only-Excluded,
        catalogue plant + direct evidence         -> Catalogue Plant — Evidence
                                                       Gap for This Indication
      Exploratory / mechanism-only-Excluded,
        catalogue plant + market unassessed       -> Catalogue R&D Hypothesis —
                                                       Market Novelty Unassessed
      Exploratory / mechanism-only-Excluded,
        catalogue plant + established market      -> Established Plant — Evidence
                                                       Gap for This Indication
      Excluded, hard stop, regulatory ban text   -> Regulatory Prohibition
      Excluded, hard stop, no regulatory ban     -> Not Currently
                                                     Developable (Safety)
      Excluded, dosage/preparation mismatch      -> Insufficient Signal
      Excluded, no evidence AND no mechanism     -> Insufficient Signal

    ``already_in_catalogue`` (external review, 2026-09-08): True/False when
    known (from candidate_shortlisting.py's Candidate_Origin/
    Already_In_Internal_Catalogue columns -- see
    indication_candidate_discovery.py's _RD_ORIGIN_COLUMNS), None when
    unknown (e.g. an older raw_df that predates those columns, or the
    compound-substitution discovery path, which does not tag origin at
    all). ``novelty_tier`` is candidate_shortlisting.py::_novelty_market()'s
    own tier string, read verbatim, never re-derived.

    WHY THIS DISTINCTION EXISTS: a plant with 500 marketed products and
    merely-insufficient evidence for a NEW indication is a genuinely
    different situation from an unfamiliar, under-studied species with an
    interesting mechanism -- both could previously only ever reach
    "R&D Discovery Hypothesis" once their status was Exploratory or
    mechanism-only-Excluded, collapsing two different R&D questions
    ("should we investigate repositioning an established plant?" vs.
    "should we investigate an unknown one at all?") into one label. When
    the catalogue/market signal is unavailable (None / unrecognised tier),
    this function falls back to the original, broader "R&D Discovery
    Hypothesis" behavior -- it never invents novelty it cannot confirm.
    """
    if plant_status == "Shortlist":
        return DISCOVERY_LANE_EVIDENCE_BACKED

    _known_established_catalogue_plant = (
        already_in_catalogue is True and novelty_tier in _MARKET_ESTABLISHED_NOVELTY_TIERS
    )
    _catalogue_with_direct_evidence = (
        already_in_catalogue is True and max(0, int(direct_evidence_count or 0)) > 0
    )
    _catalogue_market_unassessed = (
        already_in_catalogue is True and novelty_tier == _NOVELTY_MARKET_UNASSESSED_TIER
    )

    def _research_lane_for_non_shortlist() -> str:
        # Direct evidence on a plant already present in the internal catalogue is
        # an evidence-maturity/repositioning question, not a novel botanical
        # discovery claim. Market verification may refine that to the stronger
        # "Established" label, but missing market search must never silently turn
        # a known catalogue plant with direct evidence into "R&D Discovery".
        if _known_established_catalogue_plant:
            return DISCOVERY_LANE_EVIDENCE_GAP
        if _catalogue_with_direct_evidence:
            return DISCOVERY_LANE_CATALOGUE_EVIDENCE_GAP
        # A catalogue entry can still be genuinely under-explored (the Dr Duke
        # import contains thousands of plants), so do not hide it. When market
        # novelty was never assessed, surface it with a deliberately non-claiming
        # catalogue-hypothesis label instead of pretending it is novel.
        if _catalogue_market_unassessed:
            return DISCOVERY_LANE_CATALOGUE_HYPOTHESIS
        return DISCOVERY_LANE_HYPOTHESIS

    if plant_status == "Exploratory":
        return _research_lane_for_non_shortlist()
    # plant_status == "Excluded" from here -- distinguish WHY, since the
    # existing gate collapses several different reasons into one label.
    if plant_hard_stop:
        return (
            DISCOVERY_LANE_REGULATORY_STOP if regulatory_prohibition_present
            else DISCOVERY_LANE_SAFETY_STOP
        )
    if dosage_mismatch:
        return DISCOVERY_LANE_INSUFFICIENT
    if explicit_mechanistic_rationale:
        return _research_lane_for_non_shortlist()
    if indication_points == 0.0:
        return DISCOVERY_LANE_INSUFFICIENT
    return DISCOVERY_LANE_INSUFFICIENT


# Novelty-market tier (candidate_shortlisting.py::_novelty_market()) that
# means "the market was never actually checked" -- as opposed to every
# other tier, which reflects a real (even if weak) market assessment.
# discovery_potential_score() below must not let this specific neutral
# prior read as evidence of novelty (external review, 2026-09-08: "we
# don't know" is not "this looks unclaimed").
_NOVELTY_MARKET_UNASSESSED_TIER = "Commercial novelty not assessed"


def discovery_potential_score(
    *,
    mech_points: float,
    target_count: int,
    mechanistic_evidence_count: int,
    novelty_points: float,
    novelty_tier: str = "",
    linked_target_count: int | None = None,
    linked_compound_count: int = 0,
    compound_specificity: float = 0.0,
) -> float:
    """Return a 0-100 R&D-interest score that avoids hard-cap saturation.

    This score is deliberately independent of clinical evidence maturity. The
    previous implementation used four linear components with low hard caps
    (e.g. 10 mechanism points -> 40/40; four targets -> 20/20). In real Stage-6
    output many unrelated candidates therefore collapsed to the exact same 70
    points and alphabetical ordering became the effective ranking.

    The revised model keeps the same scientific intent but uses smooth,
    diminishing-return curves and, when the Stage-5 mechanistic entry path
    provides row-level provenance, rewards compound specificity ONLY for the
    compound(s) actually linked to an indication-relevant target/mechanism.

    Components (PROVISIONAL engineering heuristic, not clinically calibrated):
      * mechanistic support strength .......... 30 points
      * indication-linked target breadth ...... 20 points
      * mechanistic evidence depth ............ 20 points
      * linked-compound specificity ........... 15 points
      * assessed commercial novelty ........... 15 points

    ``linked_target_count`` is authoritative when supplied, including zero.
    Older callers that do not have row-level linkage may omit it and retain the
    historical ``target_count`` fallback. ``compound_specificity`` is expected
    on a 0-1 scale from compound_plant_resolver.compound_specificity_score();
    unknown/unavailable specificity contributes zero rather than a neutral prior.

    As before, the special market tier ``Commercial novelty not assessed``
    contributes zero novelty points: unknown market status is not evidence of
    novelty.
    """
    def _sat(value: float, scale: float, cap: float) -> float:
        value = max(0.0, float(value or 0.0))
        if value <= 0.0:
            return 0.0
        return cap * (1.0 - math.exp(-value / scale))

    mechanism_component = _sat(mech_points, 5.0, 30.0)

    effective_target_count = (
        max(0, int(linked_target_count))
        if linked_target_count is not None
        else max(0, int(target_count or 0))
    )
    target_component = _sat(effective_target_count, 2.5, 20.0)
    preclinical_component = _sat(max(0, int(mechanistic_evidence_count or 0)), 3.0, 20.0)

    specificity = min(1.0, max(0.0, float(compound_specificity or 0.0)))
    # A specificity value without any linked compound is not actionable
    # provenance and must not contribute.
    specificity_component = 15.0 * specificity if max(0, int(linked_compound_count or 0)) > 0 else 0.0

    effective_novelty_points = (
        0.0 if novelty_tier == _NOVELTY_MARKET_UNASSESSED_TIER
        else max(0.0, float(novelty_points or 0.0))
    )
    novelty_component = min(15.0, effective_novelty_points * 3.0)

    return round(
        min(
            100.0,
            mechanism_component + target_component + preclinical_component
            + specificity_component + novelty_component,
        ),
        1,
    )

def evidence_maturity_score(
    *,
    evq_points: float,
    direct_evidence_count: int,
    outcome_specific_human_evidence_count: int,
    indication_points: float,
) -> float:
    """0-100 measure of how clinically/scientifically mature the existing
    evidence base already is -- the evidence-backed-prioritisation axis.

    All inputs are pre-computed elsewhere (evq_points from
    _scientific_evidence_components(), direct_evidence_count /
    outcome_specific_human_evidence_count from the same primary-tier row
    accounting already used for Direct_Evidence_Count /
    Outcome_Specific_Human_Evidence_Count, indication_points from
    _indication_relevance_detail()) -- nothing is re-derived here.

    PROVISIONAL bucket weights, matching the rest of this scoring layer --
    not a calibrated instrument.
    """
    evidence_component = min(40.0, max(0.0, evq_points) * 2.0)
    direct_component = min(25.0, max(0, direct_evidence_count) * 5.0)
    human_component = min(25.0, max(0, outcome_specific_human_evidence_count) * 8.0)
    relevance_component = min(10.0, max(0.0, indication_points) * 0.33)
    return round(
        min(
            100.0,
            evidence_component + direct_component
            + human_component + relevance_component,
        ),
        1,
    )
