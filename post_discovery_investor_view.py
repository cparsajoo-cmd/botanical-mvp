"""Post-discovery investor/R&D opportunity view (Sections 1, 2, 4, 5, 8, 13,
14, 24 of the 2026-09-09 "finish the missing parts" cahier des charges).

WHAT THIS IS
Every field here is built from columns already present on a Stage-5/6
report-ready row (RD_Discovery_Lane, Discovery_Linked_*, Direct_Indication_
Evidence_Count, Commercial_Status_*, Commercial_Opportunity_Class, safety/
regulatory flags, Overall_Score). NOTHING here calls generative AI and
nothing here recomputes an upstream scientific or commercial value --
this module only interprets and presents what already exists, exactly as
Section 2/18-21 require ("No generative AI call. No hallucination.").

WHY A SEPARATE MODULE
Investor-view construction is commercial/presentation logic (see
pipeline_fingerprint.py's docstring) -- it belongs in the COMMERCIAL
fingerprint, not the scientific one, so investor-view iteration never
forces a Stage-5 scientific rerun.

DOCUMENTED JUDGMENT CALLS (flagged, not hidden -- same convention as
commercial_opportunity_classification.py)
1. Commercial_Data_Completeness is computed over only the TWO commercial
   dimensions actually wired into this codebase today (retail/overall
   market status, indication-specific market status) -- see
   COMMERCIAL_ASSESSMENT_DIMENSIONS. Patent and regulatory assessment
   exist as separate, NOT-YET-INTEGRATED pipelines
   (botanical_rd_candidate_engine.py's market_landscape_df()/
   _search_patents()/_eu_regulatory_status()) that are not merged into
   the Stage-5/6 report-ready frame today. Rather than silently omit
   them or fabricate a status, they are reported explicitly as
   "NOT_INTEGRATED" (see Patent_Assessment_Status/
   Regulatory_Assessment_Status) so the gap is visible, not hidden.
2. REQUIRED_COMPLETENESS_THRESHOLD = 1.0 over those two wired dimensions
   (both must reflect a genuinely completed search, whether it found
   products or not) before a numeric Commercial_Opportunity_Score is
   produced.
3. Commercial_Opportunity_Score's band-per-class mapping
   (_OPPORTUNITY_CLASS_SCORE_BANDS) is an illustrative, documented
   judgment call, not derived from any dataset -- flagged for review
   exactly like the threshold in commercial_opportunity_classification.py.
"""

from __future__ import annotations

from typing import Optional

from evidence_id_parsing import normalize_evidence_ids
from rd_discovery_classification import (
    DISCOVERY_LANE_EVIDENCE_BACKED,
    DISCOVERY_LANE_HYPOTHESIS,
    DISCOVERY_LANE_REGULATORY_STOP,
    DISCOVERY_LANE_SAFETY_STOP,
    DISCOVERY_LANE_INSUFFICIENT,
    DISCOVERY_LANE_EVIDENCE_GAP,
    DISCOVERY_LANE_CATALOGUE_EVIDENCE_GAP,
    DISCOVERY_LANE_CATALOGUE_HYPOTHESIS,
)
from commercial_opportunity_classification import (
    OPP_SAFETY_DE_RISKING_REQUIRED,
    OPP_REGULATORY_CONSTRAINED,
    OPP_INSUFFICIENT_MARKET_DATA,
    OPP_CROWDED_MARKET,
    OPP_COMMERCIALLY_ESTABLISHED,
    OPP_ESTABLISHED_BOTANICAL_NEW_INDICATION,
    OPP_EMERGING_BOTANICAL_NEW_INDICATION,
    OPP_REPURPOSING_OPPORTUNITY,
    OPP_WHITE_SPACE_OPPORTUNITY,
)

_HYPOTHESIS_LANES = (DISCOVERY_LANE_HYPOTHESIS, DISCOVERY_LANE_CATALOGUE_HYPOTHESIS)
_EVIDENCE_GAP_LANES = (DISCOVERY_LANE_EVIDENCE_GAP, DISCOVERY_LANE_CATALOGUE_EVIDENCE_GAP)

_VERIFIED_FOR_INDICATION = "VERIFIED_MARKETED_FOR_INDICATION"
_USABLE_COMMERCIAL_STATUSES = {
    "VERIFIED_MARKETED_FOR_INDICATION",
    "NO_VERIFIED_PRODUCT_FOR_INDICATION_IN_COVERED_SOURCES",
    "VERIFIED_MARKETED",
    "NO_VERIFIED_PRODUCT_FOUND_IN_COVERED_SOURCES",
}

COMMERCIAL_ASSESSMENT_DIMENSIONS = (
    "Retail_Assessment_Status",
    "Indication_Market_Assessment_Status",
)
REQUIRED_COMPLETENESS_THRESHOLD = 1.0

# Section 5/15: illustrative score bands per already-classified opportunity
# type. A documented judgment call, not derived from data -- see module
# docstring. NaN classes (None/unrecognized) never get a numeric score.
_OPPORTUNITY_CLASS_SCORE_BANDS = {
    OPP_WHITE_SPACE_OPPORTUNITY: 85.0,
    OPP_ESTABLISHED_BOTANICAL_NEW_INDICATION: 75.0,
    OPP_REPURPOSING_OPPORTUNITY: 70.0,
    OPP_EMERGING_BOTANICAL_NEW_INDICATION: 65.0,
    OPP_COMMERCIALLY_ESTABLISHED: 50.0,
    OPP_CROWDED_MARKET: 25.0,
    OPP_REGULATORY_CONSTRAINED: 10.0,
    OPP_SAFETY_DE_RISKING_REQUIRED: 10.0,
    OPP_INSUFFICIENT_MARKET_DATA: None,
}


def _s(row, field, default="") -> str:
    value = row.get(field, default)
    if value is None:
        return default
    text = str(value).strip()
    return default if text.lower() in ("nan", "none", "null") else text


def _n(row, field) -> Optional[float]:
    value = row.get(field)
    if value is None:
        return None
    try:
        if isinstance(value, str) and not value.strip():
            return None
        f = float(value)
        return None if f != f else f  # NaN check without importing math/np
    except (TypeError, ValueError):
        return None


def _linked_counts(row):
    targets = int(_n(row, "Discovery_Linked_Target_Count") or 0)
    mechanisms = int(_n(row, "Discovery_Linked_Mechanism_Count") or 0)
    compounds = int(_n(row, "Discovery_Linked_Compound_Count") or 0)
    return targets, mechanisms, compounds


# ---------------------------------------------------------------------
# Section 8/22: Discovery_Admission_Path / Discovery_Admission_Rationale
# ---------------------------------------------------------------------

def has_defensible_admission(row) -> bool:
    """False exactly when no structured provenance at all supports this
    row appearing as a positive R&D hypothesis (Section 8/22: "If no
    defensible admission rationale can be reconstructed from structured
    provenance, it should not be shown as a positive Discovery hypothesis").
    """
    targets, mechanisms, compounds = _linked_counts(row)
    direct_evidence = int(_n(row, "Direct_Indication_Evidence_Count") or 0)
    if targets or mechanisms or compounds or direct_evidence:
        return True
    # A catalogue plant can still be legitimately admitted on catalogue
    # membership alone (an explicit, named admission path -- not "no
    # rationale"), but ONLY on the two lanes that say so.
    lane = _s(row, "RD_Discovery_Lane")
    if lane in _EVIDENCE_GAP_LANES and bool(row.get("Already_In_Internal_Catalogue")):
        return True
    return False


def discovery_admission_path(row) -> str:
    targets, mechanisms, compounds = _linked_counts(row)
    direct_evidence = int(_n(row, "Direct_Indication_Evidence_Count") or 0)
    lane = _s(row, "RD_Discovery_Lane")

    if targets or mechanisms or compounds:
        return "Profile-derived mechanistic linkage"
    if direct_evidence:
        return "Direct indication evidence record"
    if lane in _EVIDENCE_GAP_LANES and bool(row.get("Already_In_Internal_Catalogue")):
        return "Catalogue membership (no matched provenance)"
    return "No defensible admission provenance"


def discovery_admission_rationale(row) -> str:
    targets, mechanisms, compounds = _linked_counts(row)
    direct_evidence = int(_n(row, "Direct_Indication_Evidence_Count") or 0)
    lane = _s(row, "RD_Discovery_Lane")

    if targets or mechanisms or compounds:
        parts = []
        if targets:
            parts.append(f"{targets} linked target(s)")
        if mechanisms:
            parts.append(f"{mechanisms} linked mechanism(s)")
        if compounds:
            parts.append(f"{compounds} linked compound(s)")
        return (
            "Admitted via " + ", ".join(parts) +
            " matching the queried indication's relevance profile."
        )
    if direct_evidence:
        return (
            f"Admitted via {direct_evidence} direct evidence record(s) "
            "reporting an indication-specific outcome."
        )
    if lane in _EVIDENCE_GAP_LANES and bool(row.get("Already_In_Internal_Catalogue")):
        return (
            "No indication-specific target, mechanism, compound, or direct "
            "evidence was found for this indication; admitted only because "
            "the plant is already in the internal catalogue."
        )
    return (
        "No linked target, mechanism, compound, or direct evidence could be "
        "reconstructed for this candidate from structured provenance."
    )


# ---------------------------------------------------------------------
# Section 24: Opportunity_Type
# ---------------------------------------------------------------------

def opportunity_type(row) -> str:
    lane = _s(row, "RD_Discovery_Lane")
    already_catalogued = bool(row.get("Already_In_Internal_Catalogue"))
    commercial_class = _s(row, "Commercial_Opportunity_Class")

    if lane == DISCOVERY_LANE_SAFETY_STOP:
        return "Safety-De-Risking Research Lead"
    if lane == DISCOVERY_LANE_REGULATORY_STOP:
        return "Regulatory-Constrained Candidate"
    if commercial_class == OPP_CROWDED_MARKET:
        return "Commercially Crowded Candidate"
    if lane == DISCOVERY_LANE_EVIDENCE_BACKED:
        return "Novel Botanical Discovery" if not already_catalogued else "Evidence-Backed Validation Candidate"
    if lane in _HYPOTHESIS_LANES:
        return "Novel Botanical Discovery" if not already_catalogued else "Mechanistic Repurposing Hypothesis"
    if lane in _EVIDENCE_GAP_LANES:
        return "Known Botanical — New Indication Opportunity"
    return "Insufficient Signal"


# ---------------------------------------------------------------------
# Section 19: What_Is_New
# ---------------------------------------------------------------------

def what_is_new(row) -> str:
    lane = _s(row, "RD_Discovery_Lane")
    already_catalogued = bool(row.get("Already_In_Internal_Catalogue"))

    if not already_catalogued:
        return "Novel-to-catalogue botanical"
    if lane in _HYPOTHESIS_LANES:
        return "Mechanistic repurposing hypothesis"
    if lane in _EVIDENCE_GAP_LANES:
        return "Known botanical — new indication hypothesis"
    if lane == DISCOVERY_LANE_EVIDENCE_BACKED:
        if _s(row, "Commercial_Status_For_Indication") == _VERIFIED_FOR_INDICATION:
            return "Known same-indication botanical"
        return "Evidence-backed validation candidate"
    return "Commercial novelty not assessed"


# ---------------------------------------------------------------------
# Section 20: Key_Evidence_Gap (explicit rule precedence)
# ---------------------------------------------------------------------

def key_evidence_gap(row) -> str:
    lane = _s(row, "RD_Discovery_Lane")
    safety_level = _s(row, "Safety_Concern_Level").upper()
    safety_status = _s(row, "Safety_Assertion_Status").upper()
    if (
        lane == DISCOVERY_LANE_SAFETY_STOP
        or safety_level == "SERIOUS"
        or safety_status == "CONFLICTING_SAFETY_EVIDENCE"
    ):
        return "Safety characterization insufficient"

    human_evidence = has_confirmed_human_evidence(row)
    targets, mechanisms, compounds = _linked_counts(row)

    if not human_evidence and (targets or mechanisms or compounds):
        return "Mechanistic evidence only"
    if not human_evidence:
        return "No direct human evidence for queried indication"

    dosage_compat = _s(row, "Dosage_Form_Compatibility")
    if dosage_compat and dosage_compat != "Compatible / unspecified":
        return "Preparation transferability unresolved"

    outcome_consistency = _s(row, "Outcome_Consistency")
    if outcome_consistency and outcome_consistency not in ("Results not reported",):
        if "unresolved" in outcome_consistency.lower() or "unclear" in outcome_consistency.lower():
            return "Outcome-specific human evidence unresolved"

    if _s(row, "Commercial_Assessment_Status") != "ASSESSED":
        return "Commercial market not assessed"

    return "No significant evidence gap identified"


# ---------------------------------------------------------------------
# Section 21: Next_R&D_Step (explicit rule precedence)
# ---------------------------------------------------------------------

def next_rd_step(row) -> str:
    lane = _s(row, "RD_Discovery_Lane")
    safety_level = _s(row, "Safety_Concern_Level").upper()
    safety_status = _s(row, "Safety_Assertion_Status").upper()
    if (
        lane == DISCOVERY_LANE_SAFETY_STOP
        or safety_level == "SERIOUS"
        or safety_status == "CONFLICTING_SAFETY_EVIDENCE"
    ):
        return "Resolve toxicology/interaction risk before efficacy development."

    human_evidence = has_confirmed_human_evidence(row)
    targets, mechanisms, compounds = _linked_counts(row)
    if not human_evidence and (targets or mechanisms or compounds):
        return "Confirm indication-specific activity in a controlled preclinical model."

    dosage_compat = _s(row, "Dosage_Form_Compatibility")
    if human_evidence and dosage_compat and dosage_compat != "Compatible / unspecified":
        return "Validate preparation/exposure transferability."

    if _s(row, "Commercial_Assessment_Status") != "ASSESSED":
        return "Complete indication-specific market and IP assessment before development positioning."

    if human_evidence:
        return "Prioritize an early human feasibility study."

    return "Complete indication-specific market and IP assessment before development positioning."


# ---------------------------------------------------------------------
# Section 18: Why_Interesting (concise, structured-fact composition)
# ---------------------------------------------------------------------

def why_interesting(row) -> str:
    lane = _s(row, "RD_Discovery_Lane")
    targets, mechanisms, compounds = _linked_counts(row)
    human_evidence = has_confirmed_human_evidence(row)
    commercial_class = _s(row, "Commercial_Opportunity_Class")

    if lane == DISCOVERY_LANE_SAFETY_STOP:
        return "Flagged for safety de-risking before any further development."
    if lane == DISCOVERY_LANE_REGULATORY_STOP:
        return "Scientifically noted but currently regulatory-constrained for development."

    if targets or mechanisms or compounds:
        bits = []
        if targets:
            bits.append(f"{targets} linked target(s)")
        if mechanisms:
            bits.append(f"{mechanisms} linked mechanism(s)")
        if compounds:
            bits.append(f"{compounds} linked compound(s)")
        mechanism_clause = "Mechanistically supported by " + ", ".join(bits) + "."
    elif human_evidence:
        mechanism_clause = f"Supported by confirmed direct human evidence ({human_evidence_status(row)})."
    else:
        mechanism_clause = "Admitted on catalogue membership; no matched mechanistic or direct provenance yet."

    if not human_evidence and (targets or mechanisms or compounds):
        evidence_clause = "No confirmed direct human evidence for the queried indication has been identified yet."
    elif human_evidence:
        evidence_clause = "Confirmed direct human evidence is present for the queried indication."
    else:
        evidence_clause = "No direct or mechanistic evidence for the queried indication has been identified yet."

    commercial_clause_map = {
        OPP_WHITE_SPACE_OPPORTUNITY: "No verified commercial product was found for this indication or overall, suggesting a commercial white-space opportunity.",
        OPP_REPURPOSING_OPPORTUNITY: "The botanical is commercially established generally but not verified for this specific indication -- a possible repurposing opportunity.",
        OPP_EMERGING_BOTANICAL_NEW_INDICATION: "Limited existing commercial presence overall, not yet verified for this indication.",
        OPP_ESTABLISHED_BOTANICAL_NEW_INDICATION: "Substantial existing commercial presence overall, not yet verified for this indication.",
        OPP_CROWDED_MARKET: "The market for this indication already appears crowded.",
        OPP_COMMERCIALLY_ESTABLISHED: "Already commercially established for this indication.",
        OPP_INSUFFICIENT_MARKET_DATA: "Commercial positioning remains unassessed.",
    }
    commercial_clause = commercial_clause_map.get(commercial_class, "Commercial positioning remains unassessed.")

    return f"{mechanism_clause} {evidence_clause} {commercial_clause}".strip()


# ---------------------------------------------------------------------
# Sections 4/5/15/16: commercial assessment completeness/status/score
# ---------------------------------------------------------------------

def commercial_assessment_fields(row) -> dict:
    """Returns Retail_Assessment_Status, Indication_Market_Assessment_Status,
    Patent_Assessment_Status, Regulatory_Assessment_Status,
    Commercial_Data_Completeness, Commercial_Data_Sources,
    Commercial_Assessment_Status, Commercial_Assessment_Reason.
    """
    overall_status = _s(row, "Commercial_Status_Overall")
    indication_status = _s(row, "Commercial_Status_For_Indication")

    retail_assessed = overall_status in _USABLE_COMMERCIAL_STATUSES
    indication_assessed = indication_status in _USABLE_COMMERCIAL_STATUSES

    retail_status = "ASSESSED" if retail_assessed else "NOT_ASSESSED"
    indication_market_status = "ASSESSED" if indication_assessed else "NOT_ASSESSED"
    # Documented gap (see module docstring) -- not fabricated as assessed.
    patent_status = "NOT_INTEGRATED"
    regulatory_status = "NOT_INTEGRATED"

    assessed_count = sum([retail_assessed, indication_assessed])
    completeness = assessed_count / len(COMMERCIAL_ASSESSMENT_DIMENSIONS)

    sources = []
    if retail_assessed:
        sources.append("Structured market evidence (overall)")
    if indication_assessed:
        sources.append("Structured market evidence (indication-specific)")

    if completeness >= REQUIRED_COMPLETENESS_THRESHOLD:
        assessment_status = "ASSESSED"
        reason = "Retail and indication-specific market status were both genuinely assessed."
    elif completeness > 0:
        assessment_status = "PARTIALLY_ASSESSED"
        missing = []
        if not retail_assessed:
            missing.append("overall retail/market status")
        if not indication_assessed:
            missing.append("indication-specific market status")
        reason = "Not fully assessed -- missing: " + ", ".join(missing) + "."
    else:
        assessment_status = "NOT_ASSESSED"
        reason = "No commercial search has produced usable evidence for this candidate yet."

    return {
        "Retail_Assessment_Status": retail_status,
        "Indication_Market_Assessment_Status": indication_market_status,
        "Patent_Assessment_Status": patent_status,
        "Regulatory_Assessment_Status": regulatory_status,
        "Commercial_Data_Completeness": round(completeness, 4),
        "Commercial_Data_Sources": "; ".join(sources) if sources else "",
        "Commercial_Assessment_Status": assessment_status,
        "Commercial_Assessment_Reason": reason,
    }


def commercial_opportunity_score(row, *, commercial_assessment: Optional[dict] = None):
    """Returns a float 0-100, or None (-> NaN in a DataFrame) when
    completeness is below REQUIRED_COMPLETENESS_THRESHOLD, or the
    classified opportunity class itself has no defined band (e.g.
    INSUFFICIENT_MARKET_DATA). Never invents a neutral score for missing
    data (Section 5/15).
    """
    assessment = commercial_assessment or commercial_assessment_fields(row)
    if assessment["Commercial_Data_Completeness"] < REQUIRED_COMPLETENESS_THRESHOLD:
        return None
    commercial_class = _s(row, "Commercial_Opportunity_Class")
    return _OPPORTUNITY_CLASS_SCORE_BANDS.get(commercial_class)


# ---------------------------------------------------------------------
# Section 14: Development_Readiness_Score
# ---------------------------------------------------------------------

def development_readiness_score(row) -> Optional[float]:
    """Section 14: the existing R&D_Opportunity_Score/Overall_Score is
    scientific/development maturity, not a commercial score -- this is
    the same value under its correct, non-misleading name.
    R&D_Opportunity_Score itself is left completely untouched for
    backward compatibility (Section 30 of the prior pass).
    """
    value = _n(row, "Overall_Score")
    if value is None:
        value = _n(row, "R&D_Opportunity_Score")
    return value


# ---------------------------------------------------------------------
# Section 1/13/31: build_investor_opportunity_view
# ---------------------------------------------------------------------

INVESTOR_VIEW_COMPACT_COLUMNS = [
    "Candidate", "Opportunity_Type", "Discovery_Potential", "Evidence_Maturity",
    "Development_Readiness", "Commercial_Opportunity", "Commercial_Opportunity_Class",
    "Why_Interesting",
    "What_Is_New", "Key_Evidence_Gap", "Mechanistic_Rationale",
    "Human_Evidence_Status", "Human_Evidence_Source_Count",
    "Human_Evidence_Primary_Source_Title", "Human_Evidence_Primary_Source_URL",
    "Commercial_Whitespace", "Safety_Risk",
    "Regulatory_Status", "Patent_Status", "Key_Risk", "Next_R&D_Step",
]


# ---------------------------------------------------------------------
# Issue 2 (2026-09-09 second follow-up): authoritative human-evidence
# hierarchy. Direct_Indication_Evidence_Count is NOT necessarily human
# evidence (it can include animal/in-vitro rows with an indication-linked
# outcome) -- every function that makes a "human evidence" claim must go
# through this hierarchy instead, never through Direct_Indication_
# Evidence_Count directly.
# ---------------------------------------------------------------------

_HUMAN_EVIDENCE_COUNT_FIELDS_PRIORITY = (
    "AI_Direct_Human_Outcome_Evidence_Count",
    "Outcome_Specific_Human_Evidence_Count",
)
_HUMAN_EVIDENCE_STRENGTH_PRESENT_VALUES = {"STRONG", "MODERATE", "WEAK"}


def human_evidence_hierarchy(row):
    """The ONE authoritative human-evidence precedence for the whole
    application (Section 6, 2026-09-09 third follow-up):

        AI_Direct_Human_Outcome_Evidence_Count
            -> Direct_Human_Outcome_Evidence_IDs (via the canonical
               evidence_id_parsing.normalize_evidence_ids() -- Section 5's
               bug fix)
            -> Outcome_Specific_Human_Evidence_Count
            -> Human_Evidence_Strength
            -> UNRESOLVED

    Returns (tier, value): the FIRST tier that is actually PRESENT on the
    row wins outright -- once a tier resolves, lower tiers are never
    consulted, even if the resolved value is zero. This is deliberate:
    an authoritative zero from a higher tier (e.g. the AI adjudicator
    explicitly says 0) must not be silently overridden by a coincidental
    positive value in a lower-priority field -- that would hide a real
    disagreement rather than surface it (see
    validate_candidate_evidence_consistency() for the check that DOES
    surface such disagreements instead of picking one silently).

    tier is one of "AI_COUNT", "IDS", "OUTCOME_COUNT", "STRENGTH",
    "UNRESOLVED". value is an int for the three count-shaped tiers, the
    strength string for "STRENGTH", or None for "UNRESOLVED".
    """
    ai_count = _n(row, "AI_Direct_Human_Outcome_Evidence_Count")
    if ai_count is not None:
        return "AI_COUNT", int(ai_count)

    if "Direct_Human_Outcome_Evidence_IDs" in row:
        ids_count = len(normalize_evidence_ids(row.get("Direct_Human_Outcome_Evidence_IDs")))
        return "IDS", ids_count

    outcome_count = _n(row, "Outcome_Specific_Human_Evidence_Count")
    if outcome_count is not None:
        return "OUTCOME_COUNT", int(outcome_count)

    strength = _s(row, "Human_Evidence_Strength").upper()
    if strength in _HUMAN_EVIDENCE_STRENGTH_PRESENT_VALUES or strength == "NONE":
        return "STRENGTH", strength

    return "UNRESOLVED", None


def has_confirmed_human_evidence(row) -> bool:
    """True only when the authoritative hierarchy's resolved tier
    confirms it -- never derived from Direct_Indication_Evidence_Count.
    """
    tier, value = human_evidence_hierarchy(row)
    if tier in ("AI_COUNT", "IDS", "OUTCOME_COUNT"):
        return bool(value) and value > 0
    if tier == "STRENGTH":
        return value in _HUMAN_EVIDENCE_STRENGTH_PRESENT_VALUES
    return False


def human_evidence_status(row) -> str:
    tier, value = human_evidence_hierarchy(row)
    if tier in ("AI_COUNT", "IDS", "OUTCOME_COUNT"):
        if value and value > 0:
            return f"{value} direct human outcome record(s)"
        return "No verified direct human outcome evidence"
    if tier == "STRENGTH":
        if value in _HUMAN_EVIDENCE_STRENGTH_PRESENT_VALUES:
            return f"Human evidence present (strength: {value.title()}); verified record count unavailable"
        return "No verified direct human outcome evidence"
    # UNRESOLVED -- no authoritative human-specific signal exists at all;
    # the only honest thing left to say references non-human-specific
    # indication evidence, explicitly labelled as unresolved for humans.
    direct_evidence = int(_n(row, "Direct_Indication_Evidence_Count") or 0)
    if direct_evidence > 0:
        return "Direct indication evidence present; human outcome status unresolved"
    return "No verified direct human outcome evidence"


def _human_evidence_status(row) -> str:
    return human_evidence_status(row)


def _mechanistic_rationale(row) -> str:
    targets, mechanisms, compounds = _linked_counts(row)
    if not (targets or mechanisms or compounds):
        return "No matched mechanistic provenance"
    bits = []
    if targets:
        bits.append(f"{targets} target(s)")
    if mechanisms:
        bits.append(f"{mechanisms} mechanism(s)")
    if compounds:
        bits.append(f"{compounds} compound(s)")
    return ", ".join(bits)


def _safety_risk(row) -> str:
    lane = _s(row, "RD_Discovery_Lane")
    level = _s(row, "Safety_Concern_Level").upper()
    status = _s(row, "Safety_Assertion_Status").upper()
    if lane == DISCOVERY_LANE_SAFETY_STOP and level in {"", "NONE", "UNKNOWN"}:
        return "Safety stop — concern details unresolved"
    if level:
        return level.title()
    if status and status not in {"NO_SAFETY_EVIDENCE_RETRIEVED", "UNKNOWN", "NONE"}:
        return status.replace("_", " ").title()
    return "Unknown"


def _regulatory_status(row, assessment) -> str:
    """Issue 4 (2026-09-09 second follow-up): must never claim regulatory
    clearance from the mere absence of a prohibition flag when no genuine
    regulatory assessment was performed. Regulatory_Assessment_Status is
    "NOT_INTEGRATED" today (documented gap -- see module docstring), so
    this currently always returns "NOT ASSESSED"; it will start reflecting
    a real assessment automatically once that pipeline is integrated,
    without any further change here.
    """
    if assessment.get("Regulatory_Assessment_Status") != "ASSESSED":
        return "NOT ASSESSED"
    if bool(row.get("Regulatory_Prohibition_Present")):
        return "Regulatory prohibition present"
    return "No regulatory prohibition identified"


def _commercial_whitespace(row, commercial_class, assessment) -> str:
    """Issue 3: three-state, never collapses "unknown" into "No"."""
    if commercial_class == OPP_WHITE_SPACE_OPPORTUNITY:
        return "YES"
    if (
        assessment.get("Commercial_Assessment_Status") == "ASSESSED"
        and commercial_class
        and commercial_class != "NOT_ASSESSED"
    ):
        return "NO"
    return "NOT ASSESSED"


def _key_risk(row) -> str:
    lane = _s(row, "RD_Discovery_Lane")
    if lane == DISCOVERY_LANE_SAFETY_STOP:
        return "Safety"
    if lane == DISCOVERY_LANE_REGULATORY_STOP:
        return "Regulatory"
    commercial_class = _s(row, "Commercial_Opportunity_Class")
    if commercial_class == OPP_CROWDED_MARKET:
        return "Commercial (crowded market)"
    direct_evidence = int(_n(row, "Direct_Indication_Evidence_Count") or 0)
    if direct_evidence == 0:
        return "Scientific (no direct evidence)"
    return "Development"


# ---------------------------------------------------------------------
# Section 7 (2026-09-09 third follow-up): cross-layer consistency
# validator. Detects contradictions; NEVER silently repairs them.
# ---------------------------------------------------------------------

CONSISTENCY_COHERENT = "COHERENT"
CONSISTENCY_HUMAN_EVIDENCE_CONTRADICTION = "HUMAN_EVIDENCE_CONTRADICTION"
CONSISTENCY_COMMERCIAL_CONTRADICTION = "COMMERCIAL_CONTRADICTION"
CONSISTENCY_REGULATORY_CONTRADICTION = "REGULATORY_CONTRADICTION"
CONSISTENCY_SAFETY_CONTRADICTION = "SAFETY_CONTRADICTION"
CONSISTENCY_SOURCE_LINKAGE_INCOMPLETE = "SOURCE_LINKAGE_INCOMPLETE"
CONSISTENCY_MULTIPLE = "MULTIPLE_CONTRADICTIONS"


def _explicit_numeric(row, field):
    if field not in row:
        return False, None
    value = _n(row, field)
    return (value is not None), (int(value) if value is not None else None)


def validate_candidate_evidence_consistency(row):
    """Detect cross-layer contradictions without mutating scientific facts.

    Human evidence is checked pairwise across every explicitly-present tier.
    Source-linkage fields, when attached by evidence_source_resolver, are also
    checked so an evidence count can never look fully traceable when its IDs
    or evidence records are missing.
    """
    issues: list[str] = []

    # --- Human evidence: pairwise explicit-field consistency ---
    ai_present, ai_count = _explicit_numeric(row, "AI_Direct_Human_Outcome_Evidence_Count")
    ids_present = "Direct_Human_Outcome_Evidence_IDs" in row
    ids = normalize_evidence_ids(row.get("Direct_Human_Outcome_Evidence_IDs")) if ids_present else []
    ids_count = len(ids)
    outcome_present, outcome_count = _explicit_numeric(row, "Outcome_Specific_Human_Evidence_Count")
    strength = _s(row, "Human_Evidence_Strength").upper()
    strength_present = strength in (_HUMAN_EVIDENCE_STRENGTH_PRESENT_VALUES | {"NONE"})

    if ai_present and ids_present and ai_count != ids_count:
        issues.append(
            f"Human evidence mismatch: AI_Direct_Human_Outcome_Evidence_Count={ai_count} "
            f"but Direct_Human_Outcome_Evidence_IDs contains {ids_count} unique ID(s)."
        )
    if ids_present and outcome_present and ids_count != outcome_count:
        issues.append(
            f"Human evidence mismatch: Direct_Human_Outcome_Evidence_IDs contains {ids_count} "
            f"unique ID(s) but Outcome_Specific_Human_Evidence_Count={outcome_count}."
        )
    if strength in _HUMAN_EVIDENCE_STRENGTH_PRESENT_VALUES:
        explicit_counts = [count for present, count in ((ai_present, ai_count), (ids_present, ids_count), (outcome_present, outcome_count)) if present]
        if explicit_counts and max(explicit_counts) == 0:
            issues.append(
                f"Human_Evidence_Strength={strength} indicates human evidence, but every "
                "explicit authoritative human-evidence count/ID field is zero."
            )

    # --- Source linkage: only when traceability fields have been attached ---
    source_linkage_issue = False
    if "Human_Evidence_Unresolved_Source_Count" in row:
        unresolved = int(_n(row, "Human_Evidence_Unresolved_Source_Count") or 0)
        expected_positive = (ai_count or 0) > 0 if ai_present else (ids_count > 0 or ((outcome_count or 0) > 0 if outcome_present else False))
        if unresolved > 0 and expected_positive:
            source_linkage_issue = True
            issues.append(
                f"Human evidence source linkage incomplete: {unresolved} expected/identified "
                "human evidence source(s) are not fully linked to evidence records."
            )

    # --- Commercial ---
    commercial_class = _s(row, "Commercial_Opportunity_Class")
    assessment = commercial_assessment_fields(row)
    whitespace = _commercial_whitespace(row, commercial_class, assessment)
    if whitespace != "NOT ASSESSED" and assessment["Commercial_Assessment_Status"] != "ASSESSED":
        issues.append(
            f"Commercial_Whitespace={whitespace!r} was produced while "
            f"Commercial_Assessment_Status={assessment['Commercial_Assessment_Status']!r} "
            "(not ASSESSED)."
        )

    # --- Safety ---
    lane = _s(row, "RD_Discovery_Lane")
    safety_level = _s(row, "Safety_Concern_Level").upper()
    safety_status = _s(row, "Safety_Assertion_Status").upper()
    no_safety_assertion = safety_status in {
        "", "NONE", "UNKNOWN", "NO_SAFETY_EVIDENCE_RETRIEVED",
        "SAFETY_EVIDENCE_NOT_FOUND", "NO_SAFETY_SIGNAL_RETRIEVED",
    }
    if lane == DISCOVERY_LANE_SAFETY_STOP and safety_level in {"", "NONE", "UNKNOWN"} and no_safety_assertion:
        issues.append(
            "RD_Discovery_Lane is a safety-stop lane but the authoritative safety fields "
            "record no supporting concern/evidence state."
        )

    if not issues:
        return CONSISTENCY_COHERENT, []

    categories = set()
    for issue in issues:
        low = issue.lower()
        if "human" in low or "ai_direct" in low:
            categories.add(CONSISTENCY_HUMAN_EVIDENCE_CONTRADICTION)
        if "commercial" in low:
            categories.add(CONSISTENCY_COMMERCIAL_CONTRADICTION)
        if "safety" in low:
            categories.add(CONSISTENCY_SAFETY_CONTRADICTION)
    if source_linkage_issue:
        categories.add(CONSISTENCY_SOURCE_LINKAGE_INCOMPLETE)

    if len(categories) == 1:
        return next(iter(categories)), issues
    return CONSISTENCY_MULTIPLE, issues

def build_investor_opportunity_view_row(row) -> dict:
    """Builds ALL new explanatory/commercial fields for one report-ready
    row, plus the compact investor-facing column set. Every function
    called here is pure and AI-free (see module docstring).
    """
    assessment = commercial_assessment_fields(row)
    score = commercial_opportunity_score(row, commercial_assessment=assessment)
    commercial_class = _s(row, "Commercial_Opportunity_Class") or "NOT_ASSESSED"

    fields = {
        "Why_Interesting": why_interesting(row),
        "What_Is_New": what_is_new(row),
        "Key_Evidence_Gap": key_evidence_gap(row),
        "Next_R&D_Step": next_rd_step(row),
        "Opportunity_Type": opportunity_type(row),
        "Development_Readiness_Score": development_readiness_score(row),
        "Discovery_Admission_Path": discovery_admission_path(row),
        "Discovery_Admission_Rationale": discovery_admission_rationale(row),
        "Has_Defensible_Admission": has_defensible_admission(row),
        # Issue 5 (2026-09-09 second follow-up): the numeric score is an
        # explicitly documented, uncalibrated illustrative heuristic (see
        # module docstring) -- kept audit-only, never shown as investor-
        # grade evidence in the compact view. Tagged so a reader of the
        # full/audit export cannot mistake it for a calibrated figure.
        "Commercial_Opportunity_Score": score,
        "Commercial_Opportunity_Score_Status": (
            "UNCALIBRATED_HEURISTIC" if score is not None else "NOT_ASSESSED"
        ),
        **assessment,
    }

    fields["Candidate"] = _s(row, "Alternative_Plant")
    fields["Discovery_Potential"] = _n(row, "Discovery_Potential_Score")
    fields["Evidence_Maturity"] = _n(row, "Evidence_Maturity_Score")
    fields["Development_Readiness"] = fields["Development_Readiness_Score"]
    # Issue 5: the COMPACT "Commercial_Opportunity" column shows the
    # interpretable class/label (or "NOT ASSESSED"), never the uncalibrated
    # number -- Commercial_Opportunity_Class is also present verbatim
    # alongside it (added in the prior pass) for anyone who wants the raw
    # enum value specifically.
    fields["Commercial_Opportunity"] = (
        commercial_class if commercial_class and commercial_class != "NOT_ASSESSED"
        else "NOT ASSESSED"
    )
    fields["Mechanistic_Rationale"] = _mechanistic_rationale(row)
    fields["Human_Evidence_Status"] = human_evidence_status(row)
    fields["Commercial_Whitespace"] = _commercial_whitespace(row, commercial_class, assessment)
    fields["Safety_Risk"] = _safety_risk(row)
    fields["Regulatory_Status"] = _regulatory_status(row, assessment)
    fields["Patent_Status"] = assessment["Patent_Assessment_Status"]
    fields["Key_Risk"] = _key_risk(row)

    consistency_status, consistency_issues = validate_candidate_evidence_consistency(row)
    fields["Evidence_Consistency_Status"] = consistency_status
    fields["Evidence_Consistency_Issues"] = "; ".join(consistency_issues)

    return fields


def build_investor_opportunity_view(report_ready_df, *, exclude_non_defensible=True):
    """Section 1/13/31: builds the full investor/R&D opportunity view.

    Returns (full_df, compact_df):
      - full_df: report_ready_df with every new field from
        build_investor_opportunity_view_row() appended as columns
        (audit-rich, for the downloadable CSV -- Section 30).
      - compact_df: only INVESTOR_VIEW_COMPACT_COLUMNS, ranked by
        Discovery_Potential (Section 26: never rank solely by
        Overall_Score), for the visible Stage-6 table.

    exclude_non_defensible=True (default) drops rows without a
    defensible admission rationale (Has_Defensible_Admission is False)
    from the COMPACT view only -- Section 8/22: such a row must not be
    presented as a positive R&D hypothesis. The full audit frame still
    contains them (nothing is silently deleted), with
    Has_Defensible_Admission=False visible for audit.
    """
    import pandas as pd

    if not isinstance(report_ready_df, pd.DataFrame) or report_ready_df.empty:
        return report_ready_df, pd.DataFrame(columns=INVESTOR_VIEW_COMPACT_COLUMNS)

    new_fields = [build_investor_opportunity_view_row(row) for _, row in report_ready_df.iterrows()]
    new_fields_df = pd.DataFrame(new_fields, index=report_ready_df.index)

    full_df = report_ready_df.copy()
    for col in new_fields_df.columns:
        full_df[col] = new_fields_df[col]

    compact_source = full_df
    if exclude_non_defensible and "Has_Defensible_Admission" in compact_source.columns:
        compact_source = compact_source[compact_source["Has_Defensible_Admission"] != False]  # noqa: E712

    compact_df = compact_source[
        [c for c in INVESTOR_VIEW_COMPACT_COLUMNS if c in compact_source.columns]
    ].copy()
    if "Discovery_Potential" in compact_df.columns:
        compact_df = compact_df.sort_values(
            "Discovery_Potential", ascending=False, na_position="last"
        ).reset_index(drop=True)

    return full_df, compact_df
