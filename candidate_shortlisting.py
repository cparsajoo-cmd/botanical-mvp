"""Plant-centric scientific shortlisting for Step 5.

This module is deliberately post-processing only.  It never changes the raw
candidate network produced by :mod:`botanical_rd_candidate_engine`, never
changes the existing R&D_Opportunity_Score, and never turns a chemical
co-occurrence into an efficacy claim.  It converts the raw plant-compound
association rows into an auditable, one-row-per-alternative-plant triage view.
"""
from __future__ import annotations

import re
import json
import time
from collections import Counter
from typing import Any, Iterable, Mapping

import pandas as pd

from indication_semantics import resolve_indication_semantics
from evidence_authority import (
    classify_source_authority_from_row,
    source_authority_factor as _source_authority_factor,
    summarize_authority_distribution,
    weighted_evidence_strength,
    signed_evidence_contribution,
    AUTHORITY_UNKNOWN,
    DIRECTION_POSITIVE,
    DIRECTION_NEGATIVE,
    DIRECTION_NULL,
    DIRECTION_MIXED,
    DIRECTION_UNCLEAR,
)
from scientific_phrase_matcher import phrase_present
from standard_evidence_builder import (
    evaluate_applicability, preparation_from_product_form, canonical_preparation_identity,
)
from evidence_consistency import classify_evidence_consistency
from phase5_scoring_config import (
    SCORING_MODEL_VERSION,
    EVIDENCE_TIER_PRECEDENCE,
    HIERARCHY_LABEL_TO_TIER,
    DIRECTION_FACTORS,
    CONSISTENCY_FACTORS,
    APPLICABILITY_FACTORS,
    APPLICABILITY_FACTOR_WHEN_NOTHING_EVALUABLE,
    APPLICABILITY_CLASSIFICATION_WHEN_NOTHING_EVALUABLE,
    APPLICABILITY_CLASSIFICATION_PRECEDENCE,
    NOT_APPLICABLE,
    SCIENTIFIC_EVIDENCE_SCORE_FLOOR,
    SCIENTIFIC_EVIDENCE_SCORE_CEILING,
    RANKING_COMPONENT_BASE_WEIGHTS,
    RANKING_COMPONENT_ACTIVE_WEIGHTS,
    RANKING_STRONG_PRIORITY_THRESHOLD,
)
from ranking_score_model import reweight_score_breakdown, score_from_breakdown
from safety_interaction_attribution import extract_structured_safety_interactions

from general_indication_relevance import (
    ENGINE_VERSION as _RELEVANCE_ENGINE_VERSION,
    MATCH_EXACT_INDICATION,
    MATCH_EXPLICIT_FIELD_OVERLAP,
    MATCH_OUTCOME_OR_MECHANISM_SUPPORT,
    MATCH_CORPUS_DERIVED_SEMANTIC,
    MATCH_HYBRID_SEMANTIC,
    MATCH_EMBEDDING_SEMANTIC,
    MATCH_WEAK_LEXICAL,
    MATCH_CURATED_ASSIST_FALLBACK,
    MATCH_NO_MATCH,
)

# Same strength grouping used by indication_candidate_discovery.py's own
# gating (_MATCH_STRONG / _MATCH_SUPPORTIVE there). Duplicated as plain
# string-constant tuples rather than imported, to avoid a module-level
# import cycle with indication_candidate_discovery.py (which itself may be
# imported lazily elsewhere for that reason). The category names themselves
# come from general_indication_relevance.py, the single authoritative
# source -- this is not a second vocabulary, just the same categories
# grouped by strength for scoring weights below.
_MATCH_STRONG = (MATCH_EXACT_INDICATION, MATCH_EXPLICIT_FIELD_OVERLAP)
_MATCH_SUPPORTIVE = (
    MATCH_OUTCOME_OR_MECHANISM_SUPPORT, MATCH_CORPUS_DERIVED_SEMANTIC,
    MATCH_HYBRID_SEMANTIC, MATCH_EMBEDDING_SEMANTIC,
    MATCH_WEAK_LEXICAL, MATCH_CURATED_ASSIST_FALLBACK,
)

# Transparent compound-specificity tiers. Tier 0 compounds are chemically
# non-informative for alternative-source discovery. Tier 1 compounds are common
# phytochemicals: they can support a hypothesis, but must not dominate ranking.
# Everything else defaults to Tier 2 (more differentiating) unless the row itself
# explicitly labels the match common/non-specific. Exact-token matching avoids
# suppressing a specific compound merely because its name contains e.g. glucose.
_COMPOUND_TIER_0 = {
    "water", "glucose", "fructose", "sucrose", "cellulose", "starch",
    "choline", "fluoride", "calcium", "magnesium", "potassium", "sodium",
    "iron", "zinc", "copper", "manganese", "phosphorus", "phosphate",
    "chloride", "sulfate", "nitrate", "ammonia", "urea",
}

_COMPOUND_TIER_1 = {
    "lactic acid", "citric acid", "malic acid", "oxalic acid", "acetic acid",
    "formic acid", "palmitic acid", "stearic acid", "oleic acid",
    "linoleic acid", "beta-sitosterol", "β-sitosterol", "sitosterol",
    "campesterol", "stigmasterol", "quercetin", "kaempferol", "rutin",
    "gallic acid", "caffeic acid", "chlorogenic acid", "rosmarinic acid",
    "catechin",
}

_MISSING_MARKERS = {
    "", "nan", "none", "null", "unknown", "unclassified",
    "not clearly extracted", "not clearly reported", "not specified",
    "not specified in database", "no specific source record identified",
    "not applicable (no shared-target claim for this match type)",
    "no explicit flag found", "none identified",
}

_HARD_STOP_TERMS = (
    "safety concern", "not suitable", "no-go", "nogo", "prohibited",
    "regulatory prohibition", "contraindicated", "fatal", "severe toxicity",
)

_NO_DIRECT_EVIDENCE_TERMS = (
    "no direct evidence", "no evidence", "general literature signal",
    "not grade-applicable", "unclassified", "unknown",
    "registry record without reported results", "registry / protocol only",
    "results not reported", "await reported results",
)

_APPLICABILITY_MISMATCH_TERMS = (
    "mismatch", "not applicable", "incompatible", "wrong dosage",
    "different dosage form", "not direct for selected product",
)


# TEMPORARY DIAGNOSTIC INSTRUMENTATION (performance audit —
# build_plant_candidate_shortlist() runtime). Prints only; no behavior
# change. See build_plant_candidate_shortlist() below.
def _perf(msg):
    print(f"[PERF] {msg}", flush=True)


def _norm(value: object) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def _is_missing(value: object) -> bool:
    return _norm(value) in _MISSING_MARKERS


def _split_values(values: Iterable[object]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value is None:
            continue
        for item in re.split(r"[;|\n]+", str(value)):
            item = item.strip()
            key = _norm(item)
            if not item or key in _MISSING_MARKERS or key in seen:
                continue
            seen.add(key)
            output.append(item)
    return output


def _join(values: Iterable[object], limit: int = 10) -> str:
    items = _split_values(values)
    if not items:
        return ""
    shown = items[:limit]
    suffix = f" (+{len(items) - limit} more)" if len(items) > limit else ""
    return "; ".join(shown) + suffix


def _row_source_record_ids(row: pd.Series) -> list[str]:
    """Return deterministic source identifiers for one raw row."""
    ids = _split_values([row.get("Source_Record_IDs", "")])
    if ids:
        return ids
    fallback = str(row.get("Evidence_Source", "") or "").strip()
    return [fallback] if fallback and not _is_missing(fallback) else []


def _source_ids_for_rows(rows: Iterable[pd.Series]) -> list[str]:
    return sorted({source_id for row in rows for source_id in _row_source_record_ids(row)})


def _compound_names(compound: object) -> list[str]:
    """Return normalized compound names, stripping similarity annotations."""
    names: list[str] = []
    for item in re.split(r"[;|\n]+", str(compound or "")):
        item = re.sub(r"\s*\[.*?\]\s*$", "", item).strip()
        name = _norm(item)
        if name and name not in _MISSING_MARKERS:
            names.append(name)
    return names


def _compound_weight(compound: object, novelty_status: object = "") -> float:
    """Return the strongest transparent compound-specificity weight on a row."""
    novelty = _norm(novelty_status)
    weights: list[float] = []
    for name in _compound_names(compound):
        if name in _COMPOUND_TIER_0:
            weights.append(0.0)
        elif name in _COMPOUND_TIER_1:
            weights.append(0.35)
        else:
            weights.append(1.0)
    if not weights:
        return 0.0
    weight = max(weights)
    if "common" in novelty or "non-specific" in novelty or "nonspecific" in novelty:
        weight = min(weight, 0.35)
    return weight


def _compound_is_generic(compound: object, novelty_status: object = "") -> bool:
    """Backward-compatible row gate: only Tier 0 is wholly non-informative."""
    return _compound_weight(compound, novelty_status) <= 0.0


def _has_supported_target(row: pd.Series) -> bool:
    target = row.get("Target_or_Mechanism", "")
    provenance = _norm(row.get("Target_Provenance", ""))
    if _is_missing(target):
        return False
    return not (
        "not applicable" in provenance
        or "no shared-target" in provenance
        or "not clearly" in provenance
    )


def _has_direct_evidence(row: pd.Series) -> bool:
    """True only for traceable, candidate-specific direct evidence.

    In indication mode, a source ID alone is not evidence *for the requested
    indication*.  The authoritative upstream match type must be direct and the
    row must contain empirical candidate-specific support.  Legacy callers that
    predate Indication_Match_Type retain the historical compatibility path.
    """
    match_type = str(row.get("Indication_Match_Type", "") or "").strip()
    if match_type:
        return bool(
            match_type in _MATCH_STRONG
            and _row_has_traceable_source(row)
            and _row_has_candidate_specific_empirical_support(row)
            and not _row_is_inferred_or_generic(row)
        )

    combined = " | ".join(
        str(row.get(col, ""))
        for col in (
            "Evidence_Level", "Evidence_Hierarchy_Detail",
            "Candidate_Evidence_Strength_Tier", "Evidence_Source",
            "Source_Record_IDs", "GRADE_Certainty",
        )
    ).lower()
    if not combined.strip():
        return False
    if any(term in combined for term in _NO_DIRECT_EVIDENCE_TERMS):
        specific_source = not _is_missing(row.get("Source_Record_IDs", ""))
        human_signal = any(
            term in combined
            for term in ("human", "clinical", "random", "meta-analysis", "systematic review")
        )
        return specific_source and human_signal
    return _row_has_traceable_source(row)


def _hard_stop(row: pd.Series) -> bool:
    # Phase 4 — Eligibility Gate. The structured Eligibility_Status/
    # Eligible_For_Normal_Ranking fields (when present on the row) are
    # now the AUTHORITATIVE source for this check, not a substring
    # match over Decision_Class/Safety_Flags/Regulatory_Barriers text.
    #
    # WHY: the pre-Phase-4 text-only version of this function was
    # proven (Phase 4 audit) to MISS the exact same_plant bypass bug it
    # was meant to catch — a same_plant self-row with a severe hard
    # safety term (e.g. "teratogenic") produced Decision_Class =
    # "Promising candidate; verify safety and standardization" (no
    # _HARD_STOP_TERMS substring at all) while Safety_Flags still said
    # "teratogenic" (also not one of the _HARD_STOP_TERMS phrases,
    # which only cover human-readable Decision_Class-style wording like
    # "safety concern"/"prohibited"/"contraindicated") — so a text-only
    # check here could never have caught it regardless of what terms
    # were listed, because it depended on a Decision_Class string that
    # was itself already wrong. Reading Eligible_For_Normal_Ranking
    # directly closes that gap structurally instead of by adding more
    # keywords.
    #
    # Backward compatibility: a row produced before Phase 4 has neither
    # column at all — for that case only, fall back to the original
    # text-based check so historical rows/tests keep the same
    # (imperfect but pre-existing) behavior rather than silently
    # becoming eligible.
    if "Eligible_For_Normal_Ranking" in row.index and pd.notna(row.get("Eligible_For_Normal_Ranking")):
        return not bool(row.get("Eligible_For_Normal_Ranking"))
    if "Eligibility_Status" in row.index and pd.notna(row.get("Eligibility_Status")):
        return str(row.get("Eligibility_Status")) not in ("eligible", "eligible_with_restrictions")

    combined = " | ".join(
        str(row.get(col, ""))
        for col in (
            "Decision_Class", "Decision_Class_AH", "Go_Investigate_Hold_NoGo",
            "Safety_Flags", "Regulatory_Barriers", "Gate_Results",
        )
    ).lower()
    return any(term in combined for term in _HARD_STOP_TERMS)


def _dosage_compatibility(row: pd.Series, dosage_form: str) -> str:
    selected = _norm(dosage_form)
    if not selected:
        return "Not evaluated"

    explicit = _norm(row.get("Preparation_Applicability", ""))
    if explicit in {"compatible", "mismatch", "unknown", "not evaluated"}:
        return explicit.title() if explicit != "not evaluated" else "Not evaluated"

    raw = row.get("Applicability_Summary", "")
    # Applicability_Summary is normally JSON.  Parse the structured fields so
    # a harmless key such as 'Not applicable': 0 is never mistaken for an
    # actual dosage-form mismatch.
    try:
        if isinstance(raw, dict):
            payload = raw
        elif isinstance(raw, str) and raw.strip().startswith("{"):
            payload = json.loads(raw)
        else:
            payload = {}
    except Exception:
        payload = {}

    if isinstance(payload, dict):
        mismatches = payload.get("critical_mismatches") or []
        if isinstance(mismatches, list) and mismatches:
            mismatch_text = " | ".join(str(x) for x in mismatches).lower()
            if any(term in mismatch_text for term in ("dosage", "form", "preparation", "route", "extract")):
                return "Mismatch"
        evidence_items = payload.get("evidence_items") or []
        classifications = " | ".join(
            str(item.get("applicability_classification", ""))
            for item in evidence_items if isinstance(item, dict)
        ).lower()
        if "directly applicable" in classifications or "partially applicable" in classifications:
            return "Compatible"
        if "not applicable" in classifications:
            return "Mismatch"

    applicability = _norm(raw)
    extraction = _norm(row.get("Extraction_Method", ""))
    # Plain-text fallback only uses explicit mismatch phrases, not the generic
    # words 'not applicable' which may appear as a zero-valued JSON category.
    if any(term in applicability for term in (
        "dosage-form mismatch", "preparation mismatch", "route mismatch",
        "incompatible with selected", "wrong dosage form",
    )):
        return "Mismatch"
    if selected in extraction:
        return "Compatible"
    return "Unknown"


# ---------------------------------------------------------------------------
# General preparation-applicability distinction (additive to, not a
# replacement for, _dosage_compatibility() above -- that function's output
# stays untouched so every existing caller/test keeps working). This is a
# stricter, controlled four-value vocabulary that never treats a different
# preparation as automatically applicable to the requested dosage form.
# ---------------------------------------------------------------------------

PREP_DIRECT_MATCH = "direct_match"
PREP_COMPATIBLE_BUT_INDIRECT = "compatible_but_indirect"
PREP_INCOMPATIBLE = "incompatible"
PREP_NOT_REPORTED = "not_reported"

# Preparation "families". Two entries in the SAME family are treated as a
# direct match for each other (e.g. "infusion" evidence directly supports an
# "infusion" request; "tea" and "aqueous extract" evidence do too, since
# they are the same preparation type in practice). Two entries in
# DIFFERENT families are never automatically a direct match -- standardized
# extracts, isolated isoflavones, oils, capsules and foods must not be
# treated as automatically applicable to an infusion (or vice versa).
_PREPARATION_FAMILY_TERMS = {
    "infusion": ("infusion", "tea", "tisane", "aqueous extract", "water extract", "decoction"),
    "oil": ("essential oil", "volatile oil"),
    "capsule": ("capsule", "tablet", "softgel"),
    "extract": (
        "standardized extract", "standardised extract", "hydroalcoholic extract",
        "isolated isoflavone", "isoflavone extract", "extract",
    ),
    "food": ("food", "functional food", "fortified food"),
}


def _preparation_family(text: str) -> str:
    normalized = _norm(text)
    for family, terms in _PREPARATION_FAMILY_TERMS.items():
        if any(term in normalized for term in terms):
            return family
    return normalized  # unrecognized text is its own (unmatched) family


def _preparation_applicability_row(row: pd.Series, dosage_form: str) -> str:
    """Diagnostic preparation class, aligned with authoritative Phase-5 status.

    When the current-session ``Dimension_Status`` is present, it wins.  This
    prevents the older vocabulary-family heuristic from reporting a direct
    preparation match when the authoritative comparator says PARTIAL (for
    example infusion vs decoction) or MISMATCH (infusion vs dry extract).
    Legacy rows fall back conservatively: exact preparation text is direct;
    same normalized parent category is only indirect; dosage-form-only words
    such as capsule/tablet do not establish a botanical preparation.
    """
    dimension_status = row.get("Dimension_Status")
    if isinstance(dimension_status, Mapping):
        prep_status = str(dimension_status.get("preparation") or "").upper()
        if prep_status == "MATCH":
            return PREP_DIRECT_MATCH
        if prep_status == "PARTIAL":
            return PREP_COMPATIBLE_BUT_INDIRECT
        if prep_status == "MISMATCH":
            return PREP_INCOMPATIBLE
        if prep_status in {"UNKNOWN", "NOT_APPLICABLE"}:
            return PREP_NOT_REPORTED

    selected = _norm(dosage_form)
    if not selected:
        return PREP_NOT_REPORTED

    if _dosage_compatibility(row, dosage_form) == "Mismatch":
        return PREP_INCOMPATIBLE

    evidence_preparation = _norm(row.get("Evidence_Preparation", ""))
    if not evidence_preparation:
        evidence_preparation = _norm(row.get("Preparation", ""))
    if not evidence_preparation:
        evidence_preparation = _norm(row.get("Extraction_Method", ""))
    if not evidence_preparation:
        return PREP_NOT_REPORTED

    target_preparation = preparation_from_product_form(dosage_form)
    if not target_preparation:
        return PREP_NOT_REPORTED
    target_norm = _norm(target_preparation)
    if target_norm == evidence_preparation:
        return PREP_DIRECT_MATCH

    target_identity = canonical_preparation_identity(target_preparation)
    evidence_identity = canonical_preparation_identity(evidence_preparation)
    if target_identity and evidence_identity and target_identity == evidence_identity:
        return PREP_DIRECT_MATCH

    target_family = _preparation_family(target_norm)
    evidence_family = _preparation_family(evidence_preparation)
    if target_family and evidence_family and target_family == evidence_family:
        return PREP_COMPATIBLE_BUT_INDIRECT

    return PREP_COMPATIBLE_BUT_INDIRECT

def _explicit_preparation_applicability_row(row: Mapping[str, Any], dosage_form: str) -> str:
    """Preparation transferability from explicitly reported preparation only.

    Unlike the legacy compatibility adapter used by calibrated scoring, this
    reporting helper never converts a generic ``Compatible`` flag into a direct
    preparation match.  It requires an actual Evidence_Preparation/Preparation/
    Extraction_Method value.  This preserves historical scoring while keeping
    Stage-6 preparation claims scientifically literal.
    """
    selected = _norm(dosage_form)
    if not selected:
        return PREP_NOT_REPORTED
    evidence_preparation = _norm(row.get("Evidence_Preparation", ""))
    if not evidence_preparation:
        evidence_preparation = _norm(row.get("Preparation", ""))
    if not evidence_preparation:
        evidence_preparation = _norm(row.get("Extraction_Method", ""))
    if not evidence_preparation:
        return PREP_NOT_REPORTED
    target_preparation = preparation_from_product_form(dosage_form)
    if not target_preparation:
        return PREP_NOT_REPORTED
    target_norm = _norm(target_preparation)
    if target_norm == evidence_preparation:
        return PREP_DIRECT_MATCH
    target_identity = canonical_preparation_identity(target_preparation)
    evidence_identity = canonical_preparation_identity(evidence_preparation)
    if target_identity and evidence_identity and target_identity == evidence_identity:
        return PREP_DIRECT_MATCH
    target_family = _preparation_family(target_norm)
    evidence_family = _preparation_family(evidence_preparation)
    if target_family and evidence_family:
        # Different preparation families require translation/formulation work;
        # they are not automatically biologically incompatible.  Reserve the
        # hard INCOMPATIBLE label for the authoritative applicability engine's
        # explicit MISMATCH result above.
        return PREP_COMPATIBLE_BUT_INDIRECT
    return PREP_COMPATIBLE_BUT_INDIRECT


def _row_classification(row: pd.Series, dosage_form: str) -> tuple[str, list[str], dict[str, bool | str]]:
    direct = _has_direct_evidence(row)
    target = _has_supported_target(row)
    generic = _compound_is_generic(
        row.get("Shared_or_Similar_Compound", ""), row.get("Novelty_Status", "")
    )
    hard_stop = _hard_stop(row)
    dosage = _dosage_compatibility(row, dosage_form)
    negative = bool(row.get("Has_Negative_Evidence", False))

    reasons: list[str] = []
    if hard_stop:
        reasons.append("Hard safety or regulatory stop")
    if not direct:
        reasons.append("No direct, traceable evidence for the alternative plant")
    if not target:
        reasons.append("No supported target or mechanism claim")
    if generic:
        reasons.append("Match rests on a generic/non-specific compound")
    if dosage == "Mismatch":
        reasons.append("Selected dosage form is not applicable to this evidence")
    if negative:
        reasons.append("Negative or contradictory evidence is present")

    if hard_stop or dosage == "Mismatch":
        status = "Excluded"
    elif direct and target and not generic:
        status = "Shortlist"
    elif not direct and not target:
        status = "Excluded"
    else:
        status = "Exploratory"

    return status, reasons, {
        "direct": direct,
        "target": target,
        "generic": generic,
        "hard_stop": hard_stop,
        "dosage": dosage,
        "negative": negative,
    }


def _evidence_points(group: pd.DataFrame) -> float:
    text = " | ".join(
        str(v).lower()
        for col in ("Evidence_Level", "Evidence_Hierarchy_Detail", "Candidate_Evidence_Strength_Tier", "GRADE_Certainty")
        if col in group.columns
        for v in group[col].dropna().tolist()
    )
    # Word-boundary + simple-plural aware matching via the shared
    # scientific_phrase_matcher utility, replacing bare substring checks.
    # Fix for the proven false-positive bug: "clinical" as a plain
    # substring matched inside "preclinical" (itself a value
    # _evidence_level() produces), incorrectly triggering the 26-point
    # clinical/human branch for preclinical-only evidence. See
    # scientific_phrase_matcher.py. negation_aware=False preserves this
    # function's original behavior of not doing any negation handling —
    # only the substring/word-boundary mechanism changes here.
    if phrase_present(text, "meta-analysis") or phrase_present(text, "systematic review"):
        base = 30.0
    elif (
        phrase_present(text, "random")
        or phrase_present(text, "clinical")
        or phrase_present(text, "human")
    ):
        base = 26.0
    elif phrase_present(text, "animal") or phrase_present(text, "in vivo"):
        base = 18.0
    elif phrase_present(text, "in vitro") or phrase_present(text, "cell"):
        base = 12.0
    elif group["Direct_Evidence_Present"].any():
        base = 10.0
    else:
        return 0.0

    # Phase 1 follow-up (engine audit, "Study_Design vs Evidence_Direction"):
    # everything above says WHAT KIND of evidence this is; it says nothing
    # about what it actually FOUND. Without this, a negative/null-only
    # evidence pool earned the exact same Scientific_Triage_Score as a
    # genuinely positive one purely because it also contained the word
    # "clinical"/"randomized". This outcome_multiplier is local to
    # Scientific_Triage_Score (a separate, 0-100 triage/filtering score,
    # NOT Evidence_Quality_Score/Overall_Score/R&D_Opportunity_Score —
    # see build_plant_candidate_shortlist()). PHASE 3, problem 2 removed
    # the equivalent step from this function's sibling, _evidence_quality()
    # (which DOES drive Overall_Score/R&D_Opportunity_Score), because that
    # score must be independent of Evidence_Direction per the Phase 3
    # brief. Scientific_Triage_Score is a different, pre-existing
    # component the brief explicitly said not to redesign ("component های
    # دیگر ... را تغییر نده") — it intentionally keeps rewarding/penalizing
    # by outcome direction for triage purposes, so the two scores in this
    # module now deliberately differ on this point; they are not meant to
    # agree.
    outcomes = _outcome_profile(group)
    if outcomes["positive"] == 0 and (outcomes["null"] + outcomes["harmful"]) > 0:
        outcome_multiplier = 0.55
    elif outcomes["positive"] > 0 and (outcomes["null"] + outcomes["harmful"] + outcomes["mixed"]) > 0:
        outcome_multiplier = 0.80
    else:
        outcome_multiplier = 1.0
    return round(base * outcome_multiplier, 1)
    if group["Direct_Evidence_Present"].any():
        return 10.0
    return 0.0


# ---------------------------------------------------------------------------
# Transparent weighted scoring (Requirement 8).
#
# Overall_Score (0-100) is the explicit sum of six independently computed,
# independently capped components. Weights were chosen from what the raw
# association rows can actually support (see accompanying explanation), not
# fitted or hidden:
#
#   Indication Relevance ........ 35 pts   (candidate-specific direct or
#                                            mechanistically relevant evidence)
#   Evidence Quality ............ 30 pts   (evidence hierarchy, independent
#                                            traceable sources, evidence provenance)
#   Compound Support ............. 5 pts   (specificity-weighted overlap only)
#   Mechanism/Target Support .... 10 pts   (supporting role; cannot create a
#                                            shortlist recommendation by itself)
#   Safety & Regulatory .......... 15 pts   (hard stops and explicit barriers)
#   Novelty & Market .............. 5 pts   (secondary opportunity signal)
#                                 -------
#                                 100 pts
#
# Every component returns (points, short_tier_label) so the breakdown and the
# explanation text are generated from the same numbers that drive the rank —
# nothing is scored twice and nothing is invented.
# ---------------------------------------------------------------------------

_INDICATION_STOPWORDS = {
    "the", "and", "for", "with", "a", "an", "of", "in", "to", "or", "on",
    "related", "disorder", "disorders", "condition", "conditions", "syndrome",
    "support", "health", "target", "targeting", "selected", "indication",
    "product", "products", "botanical", "alternative", "adult", "adults",
}

# Only candidate-specific scientific fields are eligible. Generated narrative
# fields such as Rationale/Comparative_Rationale are deliberately excluded
# because they repeat the research question and previously caused leakage.
_INDICATION_TEXT_COLUMNS = (
    "Target_or_Mechanism", "Scientific_Rationale", "Clinical_Rationale",
    "GRADE_Certainty_Rationale", "Evidence_Strengths", "Evidence_Weaknesses",
    "Applicability_Summary",
)

# Conservative concept lexicon for common R&D indication families. The matcher
# also has a generic fallback, but broad words alone never create High relevance.
_INDICATION_CONCEPTS = None  # semantics are centralized in indication_semantics.py

_GENERIC_MECHANISM_ONLY = (
    "antioxidant", "anti-oxidant", "anti-inflammatory", "antiinflammatory",
    "nf-kb", "nrf2", "cox-2", "il-6", "tnf-alpha", "free radical",
)

# Commercial-opportunity terminology.  Chemical/source differentiation is
# carried separately in Novelty_Status/Chemical_Differentiation_Status and must
# NEVER create commercial white-space by itself.
_COMMERCIAL_WHITE_SPACE_TERMS = (
    "commercial white space", "commercial white-space",
    "no verified product found", "no verified commercial product",
)
_COMMERCIAL_REPURPOSING_TERMS = (
    "repurposing white space", "repurposing white-space",
    "indication-repurposing", "indication repurposing",
)
_COMMERCIAL_ESTABLISHED_TERMS = (
    "established commercial use", "verified marketed for indication",
    "commercially active for selected indication", "active commercial use",
)
_COMMERCIAL_UNASSESSED_TERMS = (
    "commercial novelty not assessed", "market data incomplete",
    "search not performed", "source unavailable", "market not covered",
    "connector not implemented",
)


def _indication_tokens(indication: str) -> list[str]:
    words = re.findall(r"[a-zA-Z]{3,}", _norm(indication))
    return [w for w in words if w not in _INDICATION_STOPWORDS]


def _strip_research_question_leakage(text: object, indication: str) -> str:
    cleaned = _norm(text)
    indication_norm = _norm(indication)
    # Remove common generated templates even when punctuation or dosage wording
    # differs slightly from the exact indication string.
    cleaned = re.sub(r"for\s+[^.;|]{0,80}?\s+targeting\s+[^.;|]+", " ", cleaned)
    cleaned = re.sub(r"(?:selected\s+)?(?:research\s+question|indication)\s*[:=-]\s*[^.;|]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _candidate_specific_blob(group: pd.DataFrame, indication: str) -> str:
    parts: list[str] = []
    for col in _INDICATION_TEXT_COLUMNS:
        if col not in group.columns:
            continue
        for value in group[col].dropna().tolist():
            cleaned = _strip_research_question_leakage(value, indication)
            if cleaned:
                parts.append(cleaned)
    return " | ".join(parts)


def _matched_terms(blob: str, terms: Iterable[str]) -> list[str]:
    return sorted({term for term in terms if _norm(term) in blob})


def _evidence_context(group: pd.DataFrame) -> tuple[bool, bool]:
    text = " | ".join(
        _norm(v)
        for col in (
            "Evidence_Level", "Evidence_Hierarchy_Detail",
            "Candidate_Evidence_Strength_Tier", "GRADE_Certainty",
        )
        if col in group.columns
        for v in group[col].dropna().tolist()
    )
    human = any(term in text for term in (
        "human", "clinical trial", "randomized", "randomised",
        "meta-analysis", "systematic review",
    ))
    preclinical = human or any(term in text for term in (
        "animal", "in vivo", "in vitro", "cell", "preclinical",
        "ex vivo", "validated",
    ))
    return human, preclinical


def _candidate_specific_blob_row(row: Mapping[str, Any], indication: str) -> str:
    """Row-level equivalent of _candidate_specific_blob() for exactly one
    record. Root-cause fix (2026-08-26): the per-row loops in
    _indication_relevance_detail_authoritative/_legacy_fallback used to
    wrap each row in a fresh pd.DataFrame([row]) (~2.7ms/call at this
    project's 90-column OUTPUT_COLUMNS width -- measured directly) just to
    call the group-level _candidate_specific_blob()/_evidence_context()
    below. For a single-row group, group[col].dropna().tolist() yields
    either [value] (value not NaN) or [] (value NaN) -- exactly what
    `if not pd.isna(row.get(col))` selects here. Same columns, same
    pd.isna() missingness test dropna() itself uses, same
    _strip_research_question_leakage() call -- output is identical to
    calling _candidate_specific_blob(pd.DataFrame([row]), indication),
    without constructing that DataFrame.
    """
    parts: list[str] = []
    for col in _INDICATION_TEXT_COLUMNS:
        value = row.get(col)
        if pd.isna(value):
            continue
        cleaned = _strip_research_question_leakage(value, indication)
        if cleaned:
            parts.append(cleaned)
    return " | ".join(parts)


def _evidence_context_row(row: Mapping[str, Any]) -> tuple[bool, bool]:
    """Row-level equivalent of _evidence_context() for exactly one record.
    See _candidate_specific_blob_row()'s docstring for the equivalence
    rationale -- same reasoning applies here.
    """
    text = " | ".join(
        _norm(row.get(col))
        for col in (
            "Evidence_Level", "Evidence_Hierarchy_Detail",
            "Candidate_Evidence_Strength_Tier", "GRADE_Certainty",
        )
        if not pd.isna(row.get(col))
    )
    human = any(term in text for term in (
        "human", "clinical trial", "randomized", "randomised",
        "meta-analysis", "systematic review",
    ))
    preclinical = human or any(term in text for term in (
        "animal", "in vivo", "in vitro", "cell", "preclinical",
        "ex vivo", "validated",
    ))
    return human, preclinical


def _row_has_traceable_source(row: pd.Series) -> bool:
    return not _is_missing(row.get("Source_Record_IDs", ""))


def _row_is_inferred_or_generic(row: pd.Series) -> bool:
    """Identify rows that do not provide candidate-specific efficacy evidence."""
    text = " | ".join(
        _norm(row.get(col, ""))
        for col in (
            "Scientific_Rationale", "Clinical_Rationale", "Evidence_Level",
            "Evidence_Hierarchy_Detail", "Evidence_Source", "Target_Provenance",
        )
    )
    return any(term in text for term in (
        "hardcoded knowledge base",
        "not a specific study",
        "seed candidate database",
        "general literature signal",
        "occurrence / analytical chemistry only",
        "no direct evidence",
        "no independent source identified",
        "class-only",
    ))


def _row_has_candidate_specific_empirical_support(row: pd.Series) -> bool:
    if not _row_has_traceable_source(row) or _row_is_inferred_or_generic(row):
        return False
    text = " | ".join(
        _norm(row.get(col, ""))
        for col in (
            "Evidence_Level", "Evidence_Hierarchy_Detail",
            "Scientific_Rationale", "Clinical_Rationale",
        )
    )
    return any(term in text for term in (
        "human", "clinical", "random", "systematic review", "meta-analysis",
        "animal", "in vivo", "in vitro", "ex vivo", "cell", "preclinical",
        "validated",
    ))


def _concept_family(indication: str) -> dict[str, tuple[str, ...]] | None:
    """Use the same semantic family as raw Step 5 candidate discovery."""
    return resolve_indication_semantics(indication)





def _row_has_indication_specific_outcome(row: pd.Series, indication: str) -> bool:
    """Whether this empirical row actually reports an outcome for the query.

    Relevance in a title/abstract is not by itself an efficacy outcome.  This
    generic guard uses the same indication semantic family as discovery and
    only promotes a record to *direct outcome evidence* when its own outcome
    field contains the requested indication (or one of its direct aliases).
    It does not change the calibrated Phase-5 score; it tightens the exported
    direct-evidence diagnostic and downstream scientific interpretation.
    """
    outcome = " | ".join(
        str(row.get(col, "") or "")
        for col in ("Primary_Outcome", "outcome", "Endpoint", "endpoint")
    ).strip()
    if not outcome:
        reason = str(row.get("Indication_Match_Reason", "") or "").lower()
        return "record's own reported outcome" in reason
    family = _concept_family(indication) or {}
    terms = list(dict.fromkeys([
        str(indication or "").strip(),
        *(family.get("direct", ()) or ()),
        *(family.get("aliases", ()) or ()),
    ]))
    for term in terms:
        term = str(term or "").strip()
        if not term:
            continue
        try:
            if phrase_present(outcome, term):
                return True
        except Exception:
            if re.search(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", outcome, flags=re.I):
                return True
    return False

def _result_category(row: pd.Series) -> str:
    """Classify a record's reported outcome without inventing missing results."""
    direction = _norm(row.get("Result_Direction", ""))
    negative_text = _norm(row.get("Negative_Evidence_Types", ""))
    narrative = " | ".join(
        _norm(row.get(col, ""))
        for col in ("Clinical_Rationale", "Scientific_Rationale", "Evidence_Conflict_Reasoning")
    )
    text = f"{direction} {negative_text} {narrative}"
    if any(t in text for t in (
        "worsened", "harm", "increased risk", "adverse direction", "negative effect",
    )):
        return "harmful"
    if bool(row.get("Has_Negative_Evidence", False)) or any(t in text for t in (
        "no significant", "no effect", "null", "not improved", "failed to improve",
    )):
        return "null"
    if any(t in text for t in (
        "positive", "improved", "improvement", "reduced", "reduction", "decreased",
        "benefit", "beneficial", "significant effect", "effective",
    )):
        return "positive"
    if "mixed" in text or "conflicting" in text or "inconsistent" in text:
        return "mixed"
    return "unreported"


def _outcome_profile(group: pd.DataFrame) -> dict[str, int | float | str]:
    """Summarise unique record-level efficacy directions for transparent gating."""
    empirical = group[group.apply(_row_has_candidate_specific_empirical_support, axis=1)].copy()
    if empirical.empty:
        return {"positive": 0, "null": 0, "harmful": 0, "mixed": 0, "unreported": 0, "total": 0, "label": "No empirical outcomes"}
    empirical["_source_key"] = empirical.apply(
        lambda row: _norm(row.get("Source_Record_IDs", ""))
        or _norm(row.get("Evidence_Source", ""))
        or f"row-{row.name}", axis=1,
    )
    empirical = empirical.drop_duplicates(subset=["_source_key"], keep="first")
    counts = {k: 0 for k in ("positive", "null", "harmful", "mixed", "unreported")}
    for _, row in empirical.iterrows():
        counts[_result_category(row)] += 1
    total = len(empirical)
    if counts["harmful"] > 0 and counts["positive"] == 0:
        label = "Adverse/negative evidence"
    elif counts["positive"] == 0 and counts["null"] > 0:
        label = "No demonstrated benefit"
    elif counts["positive"] > 0 and (counts["null"] + counts["harmful"] + counts["mixed"]) > 0:
        label = "Mixed/inconsistent results"
    elif counts["positive"] > 0:
        label = "Predominantly positive results"
    else:
        label = "Results not reported"
    return {**counts, "total": total, "label": label}


def _outcome_profile_from_row_records(row_records: list[dict]) -> dict[str, int | float | str]:
    """Build the standard outcome profile from already-deduplicated records."""
    counts = {k: 0 for k in ("positive", "null", "harmful", "mixed", "unreported")}
    for record in row_records:
        category = record.get("result_category") or _result_category(record["row"])
        counts[category if category in counts else "unreported"] += 1
    total = len(row_records)
    if total == 0:
        label = "No empirical outcomes"
    elif counts["harmful"] > 0 and counts["positive"] == 0:
        label = "Adverse/negative evidence"
    elif counts["positive"] == 0 and counts["null"] > 0:
        label = "No demonstrated benefit"
    elif counts["positive"] > 0 and (counts["null"] + counts["harmful"] + counts["mixed"]) > 0:
        label = "Mixed/inconsistent results"
    elif counts["positive"] > 0:
        label = "Predominantly positive results"
    else:
        label = "Results not reported"
    return {**counts, "total": total, "label": label}

def _row_authoritative_relevance(row: pd.Series) -> tuple[str, set[str]]:
    """Read the per-record relevance already computed upstream by the single
    authoritative engine, general_indication_relevance.py (attached to each
    row by indication_candidate_discovery.py as Indication_Match_Type /
    Indication_Match_Terms). This function performs no matching of its own --
    it only reads what discovery already decided, so shortlisting cannot
    disagree with discovery about which rows are direct vs. mechanistic
    evidence."""
    match_type = str(row.get("Indication_Match_Type", "") or "").strip()
    raw_terms = row.get("Indication_Match_Terms", "")
    terms = (
        {t.strip() for t in str(raw_terms).split(";") if t.strip()}
        if not _is_missing(raw_terms) else set()
    )
    return match_type, terms


def _group_has_authoritative_relevance(group: pd.DataFrame) -> bool:
    """True when this group's rows carry the authoritative Indication_Match_*
    columns produced by general_indication_relevance.py via
    indication_candidate_discovery.py. False for rows that never went
    through that engine (e.g. compound-source discovery mode, or any legacy
    caller) -- those use the one clearly-marked compatibility fallback
    below, per architecture requirement that indication_semantics.py is
    never required and never overrides the authoritative engine."""
    if "Indication_Match_Type" not in group.columns:
        return False
    return bool(group["Indication_Match_Type"].apply(lambda v: not _is_missing(v)).any())


def _indication_relevance_detail(
    group: pd.DataFrame, indication: str
) -> tuple[float, str, str, int]:
    """Score candidate-specific indication relevance for one plant's rows.

    Primary path: consume the authoritative per-record relevance already
    computed by general_indication_relevance.py (via
    indication_candidate_discovery.py's Indication_Match_* columns) -- see
    _indication_relevance_detail_authoritative(). This is what makes
    discovery and shortlisting share one relevance calculation instead of
    two that can disagree.

    Fallback path: only when those columns are entirely absent from this
    group (legacy/compound-source rows that never went through the
    authoritative engine) -- see
    _indication_relevance_detail_legacy_fallback(), which independently
    resolves indication_semantics.py the same way it always has. This path
    is clearly separated, not silently blended with the primary one.
    """
    if not _norm(indication):
        return 17.5, "Not evaluated (no indication specified)", "Not evaluated", 0

    if _group_has_authoritative_relevance(group):
        return _indication_relevance_detail_authoritative(group, indication)
    return _indication_relevance_detail_legacy_fallback(group, indication)


def _indication_relevance_detail_authoritative(
    group: pd.DataFrame, indication: str
) -> tuple[float, str, str, int]:
    """Score relevance using the upstream engine's per-row match_type/terms.

    Mirrors the scoring shape of the legacy fallback (human/preclinical
    source bonuses, concept breadth, outcome-profile adjustments), but the
    direct-vs-mechanistic classification of each row is read from
    Indication_Match_Type/Indication_Match_Terms -- computed once, upstream,
    by general_indication_relevance.py -- rather than recomputed here
    against indication_semantics.py. An indication with no curated
    indication_semantics.py entry scores exactly the same way as one that
    has one, because this function never consults that dictionary.
    """
    import math

    direct_source_ids: list[str] = []
    direct_human_source_ids: list[str] = []
    direct_preclinical_source_ids: list[str] = []
    mechanism_source_ids: list[str] = []
    direct_hits_all: set[str] = set()
    mechanism_hits_all: set[str] = set()
    inferred_mechanism_hits: set[str] = set()

    # Root-cause fix (2026-08-26): the old per-row pd.DataFrame([row])
    # (~2.7ms/call at this project's 90-column OUTPUT_COLUMNS width --
    # measured directly) to call the group-level
    # _candidate_specific_blob()/_evidence_context() was the dominant cost
    # of per-plant "scoring" in production (PERF log: 438s/2119 plants).
    # _evidence_context_row() below reads the row with .get(), which
    # pandas.Series already supports -- so group.iterrows() is kept
    # (measured faster than group.to_dict("records") at this function's
    # typical per-plant row count) and only the DataFrame construction is
    # removed.
    for _, row in group.iterrows():
        match_type, match_terms = _row_authoritative_relevance(row)
        # A qualifying match_type always counts as at least one "hit" for the
        # concept-breadth bonus below, even on the rare record whose matched
        # terms happen to be empty (e.g. an exact phrase match whose query
        # had no individually tokenizable words) -- the match_type itself is
        # the signal.
        direct_hits = (match_terms or {match_type}) if match_type in _MATCH_STRONG else set()
        mechanism_hits = (match_terms or {match_type}) if match_type in _MATCH_SUPPORTIVE else set()
        traceable = _row_has_traceable_source(row)
        empirical = _row_has_candidate_specific_empirical_support(row)
        row_sources = _split_values([row.get("Source_Record_IDs", "")])
        row_human, row_preclinical = _evidence_context_row(row)

        if direct_hits and traceable and empirical and not _row_is_inferred_or_generic(row):
            direct_hits_all.update(direct_hits)
            direct_source_ids.extend(row_sources)
            if row_human:
                direct_human_source_ids.extend(row_sources)
            elif row_preclinical:
                direct_preclinical_source_ids.extend(row_sources)
        if mechanism_hits:
            if empirical:
                mechanism_hits_all.update(mechanism_hits)
                mechanism_source_ids.extend(row_sources)
            else:
                inferred_mechanism_hits.update(mechanism_hits)

    direct_sources = len(set(map(_norm, direct_source_ids)))
    human_sources = len(set(map(_norm, direct_human_source_ids)))
    preclinical_sources = len(set(map(_norm, direct_preclinical_source_ids)))
    mechanism_sources = len(set(map(_norm, mechanism_source_ids)))

    # Relevance is not a binary 35/0 switch.  Within each evidence stratum,
    # independent direct sources and distinct indication-specific concepts add
    # modest, diminishing increments.  This preserves ranking resolution while
    # avoiding double-counting study quality, which belongs to Evidence Quality.
    if direct_hits_all:
        concept_bonus = min(3.0, 0.75 * len(direct_hits_all))
        if human_sources >= 1:
            source_bonus = min(4.0, 1.5 * math.log2(1 + human_sources))
            points = min(35.0, 28.0 + source_bonus + concept_bonus)
            # PHASE 5 (addendum §1/§9): Outcome Direction removed from
            # Indication_Relevance -- see the authoritative sibling
            # function's identical comment above. Direction/Consistency
            # now affect only Scientific_Evidence_Score.
            return round(points, 1), "High relevance", "Direct human/clinical", direct_sources
        if preclinical_sources >= 1:
            source_bonus = min(4.0, 1.5 * math.log2(1 + preclinical_sources))
            points = min(27.0, 21.0 + source_bonus + min(2.0, concept_bonus))
            return round(points, 1), "Medium relevance", "Direct preclinical", direct_sources
        source_bonus = min(3.0, math.log2(1 + direct_sources))
        points = min(22.0, 18.0 + source_bonus + min(1.0, concept_bonus))
        return round(points, 1), "Medium relevance", "Direct but limited", direct_sources

    if mechanism_hits_all:
        source_bonus = min(3.0, math.log2(1 + mechanism_sources))
        concept_bonus = min(2.0, 0.5 * len(mechanism_hits_all))
        if len(mechanism_hits_all) >= 2 and mechanism_sources >= 2:
            return round(min(18.0, 13.0 + source_bonus + concept_bonus), 1), "Low relevance", "Mechanistic empirical", mechanism_sources
        return round(min(12.0, 8.0 + source_bonus + concept_bonus), 1), "Low relevance", "Mechanistic empirical", mechanism_sources

    if inferred_mechanism_hits:
        return 6.0, "Low relevance", "Mechanistic inference only", 0

    return 0.0, "No relevance", "None", 0


def _indication_relevance_detail_legacy_fallback(
    group: pd.DataFrame, indication: str
) -> tuple[float, str, str, int]:
    """Compatibility-only path for rows that never went through
    general_indication_relevance.py (e.g. compound-source discovery mode).
    Independently resolves indication_semantics.py exactly as this module
    did before the authoritative engine existed. Never consulted when
    Indication_Match_Type is present -- see _indication_relevance_detail().
    """
    import math

    family = _concept_family(indication)
    if not family:
        blob = _candidate_specific_blob(group, indication)
        tokens = _indication_tokens(indication)
        hits = [t for t in tokens if re.search(rf"\b{re.escape(t)}\b", blob)]
        # Root-cause fix (2026-08-26): same iterrows/apply Series-construction
        # cost as the rest of this module (see _candidate_specific_blob_row()'s
        # docstring); _row_has_candidate_specific_empirical_support only ever
        # calls row.get(name, default), identical on a dict and a Series.
        supported_mask = [
            _row_has_candidate_specific_empirical_support(row)
            for row in group.to_dict("records")
        ]
        supported_rows = group[supported_mask]
        source_count = len(set(map(_norm, _split_values(supported_rows.get("Source_Record_IDs", [])))))
        if len(hits) >= 2 and source_count >= 2:
            points = min(27.0, 21.0 + min(4.0, math.log2(1 + source_count) * 1.5) + min(2.0, len(hits) * 0.5))
            return round(points, 1), "Medium relevance", "Direct candidate-specific", source_count
        if len(hits) == 1 and source_count >= 1:
            return 10.0, "Low relevance", "Indirect candidate-specific", source_count
        return 0.0, "No relevance", "None", 0

    direct_source_ids: list[str] = []
    direct_human_source_ids: list[str] = []
    direct_preclinical_source_ids: list[str] = []
    mechanism_source_ids: list[str] = []
    direct_hits_all: set[str] = set()
    mechanism_hits_all: set[str] = set()
    inferred_mechanism_hits: set[str] = set()

    # Root-cause fix (2026-08-26): same DataFrame-construction removal as
    # the authoritative sibling loop above (group.iterrows() kept -- it
    # measured faster than group.to_dict("records") here; the win is
    # entirely from removing the per-row pd.DataFrame([row]) construction).
    for _, row in group.iterrows():
        row_blob = _candidate_specific_blob_row(row, indication)
        direct_hits = set(_matched_terms(row_blob, family["direct"]))
        mechanism_hits = set(_matched_terms(row_blob, family["mechanistic"]))
        traceable = _row_has_traceable_source(row)
        empirical = _row_has_candidate_specific_empirical_support(row)
        row_sources = _split_values([row.get("Source_Record_IDs", "")])
        row_human, row_preclinical = _evidence_context_row(row)

        if direct_hits and traceable and empirical and not _row_is_inferred_or_generic(row):
            direct_hits_all.update(direct_hits)
            direct_source_ids.extend(row_sources)
            if row_human:
                direct_human_source_ids.extend(row_sources)
            elif row_preclinical:
                direct_preclinical_source_ids.extend(row_sources)
        if mechanism_hits:
            if empirical:
                mechanism_hits_all.update(mechanism_hits)
                mechanism_source_ids.extend(row_sources)
            else:
                inferred_mechanism_hits.update(mechanism_hits)

    direct_sources = len(set(map(_norm, direct_source_ids)))
    human_sources = len(set(map(_norm, direct_human_source_ids)))
    preclinical_sources = len(set(map(_norm, direct_preclinical_source_ids)))
    mechanism_sources = len(set(map(_norm, mechanism_source_ids)))

    if direct_hits_all:
        concept_bonus = min(3.0, 0.75 * len(direct_hits_all))
        if human_sources >= 1:
            source_bonus = min(4.0, 1.5 * math.log2(1 + human_sources))
            points = min(35.0, 28.0 + source_bonus + concept_bonus)
            # PHASE 5 (addendum §1/§9): Outcome Direction removed from
            # Indication_Relevance -- see the authoritative sibling
            # function's identical comment above. Direction/Consistency
            # now affect only Scientific_Evidence_Score.
            return round(points, 1), "High relevance", "Direct human/clinical", direct_sources
        if preclinical_sources >= 1:
            source_bonus = min(4.0, 1.5 * math.log2(1 + preclinical_sources))
            points = min(27.0, 21.0 + source_bonus + min(2.0, concept_bonus))
            return round(points, 1), "Medium relevance", "Direct preclinical", direct_sources
        source_bonus = min(3.0, math.log2(1 + direct_sources))
        points = min(22.0, 18.0 + source_bonus + min(1.0, concept_bonus))
        return round(points, 1), "Medium relevance", "Direct but limited", direct_sources

    if mechanism_hits_all:
        source_bonus = min(3.0, math.log2(1 + mechanism_sources))
        concept_bonus = min(2.0, 0.5 * len(mechanism_hits_all))
        if len(mechanism_hits_all) >= 2 and mechanism_sources >= 2:
            return round(min(18.0, 13.0 + source_bonus + concept_bonus), 1), "Low relevance", "Mechanistic empirical", mechanism_sources
        return round(min(12.0, 8.0 + source_bonus + concept_bonus), 1), "Low relevance", "Mechanistic empirical", mechanism_sources

    if inferred_mechanism_hits:
        return 6.0, "Low relevance", "Mechanistic inference only", 0

    return 0.0, "No relevance", "None", 0


    points, tier, _, _ = _indication_relevance_detail(group, indication)
    return points, tier


_DIRECTION_BY_RESULT_CATEGORY = {
    "positive": DIRECTION_POSITIVE,
    "harmful": DIRECTION_NEGATIVE,
    "null": DIRECTION_NULL,
    "mixed": DIRECTION_MIXED,
    "unreported": DIRECTION_UNCLEAR,
}

# PHASE 3 — dampened authority multiplier, not a direct multiply.
#
# evidence_authority.AUTHORITY_FACTORS spans 0.15 (Blog) to 1.00 (EMA HMPC
# Monograph), and AUTHORITY_UNKNOWN (the fallback for the large majority of
# today's evidence, which carries no Source_Organization/Source_URL at the
# candidate_shortlisting.py row shape — see PHASE3_SOURCE_AUTHORITY_AUDIT.md
# §1.3 and classify_source_authority_from_row()'s docstring) is 0.50.
# Multiplying `row_hierarchy_points` directly by that raw factor would cut
# the DEFAULT case's score roughly in half — a de facto redesign of this
# function's existing point scale, which the Phase 3 brief explicitly
# prohibits ("Ranking Logic = بدون بازطراحی"). Instead, the raw factor is
# compressed into a bounded [0.8725, 1.0] multiplier: an EMA/WHO/ESCOP/
# Cochrane source (factor ~0.93-1.00) is scored at ~98.95-100% of its
# unweighted hierarchy points; a genuinely low-authority source (Blog,
# factor 0.15) is scored at ~87.25%; the default Unknown case (factor 0.50)
# sits at 92.5% — a real, testable, direction-agnostic penalty/boost, but
# never large enough to flip this function's existing point scale for the
# common case where no organizational identity is available at all.
def _authority_hierarchy_multiplier(factor: float) -> float:
    return 0.85 + 0.15 * factor


def _row_hierarchy_points(row: pd.Series) -> tuple[float, str]:
    """Return the existing Phase-3 hierarchy points/label for one row.

    Kept module-level so the exact same classifier is reused when the
    authoritative Phase-5 path restricts Evidence Quality to the primary
    evidence tier.  No second study-design classifier is introduced.
    """
    text = " | ".join(
        _norm(row.get(col, ""))
        for col in (
            "Evidence_Level", "Evidence_Hierarchy_Detail",
            "Candidate_Evidence_Strength_Tier", "GRADE_Certainty",
        )
    )
    if any(t in text for t in ("registry record without reported results", "registry / protocol only")):
        return 0.0, "registry_no_results"
    if "systematic review" in text or "meta-analysis" in text:
        return 18.0, "review"
    if any(t in text for t in ("randomized", "randomised", "controlled trial", "rct")):
        return 16.0, "rct"
    if any(t in text for t in ("clinical trial", "human evidence", "human study", "clinical / human")):
        return 13.0, "human"
    if any(t in text for t in ("in vivo", "animal", "validated ex vivo")):
        return 9.0, "animal"
    if any(t in text for t in ("in vitro", "cell", "preclinical", "mechanistic")):
        return 6.0, "preclinical"
    if "analytical chemistry" in text or "occurrence" in text:
        return 2.0, "analytical"
    return 3.0, "unclassified"


def _build_evidence_row_records(group: pd.DataFrame) -> list[dict]:
    """Build one authority/hierarchy record per independent empirical source.

    Deduplication, Source Authority classification and hierarchy assignment
    happen exactly once here.  Both the legacy all-tier diagnostic score and
    the authoritative primary-tier score consume these same records.
    """
    # Root-cause fix (2026-08-26): the old code built a full pandas.Series
    # (block-manager machinery included) per row THREE separate times per
    # plant here (two group.apply(fn, axis=1) + one empirical.iterrows())
    # -- at this project's 90-column OUTPUT_COLUMNS width, that was
    # measured as a dominant cost of per-plant "scoring" in production
    # (PERF log: 438s across 2119 plants, ~89% of the plant-level
    # shortlist stage). group.to_dict("records") is called exactly ONCE
    # here (an earlier version of this fix called it three times, which
    # measured SLOWER than the original iterrows()/apply() at this
    # function's typical per-plant row count -- to_dict("records") only
    # wins when it replaces apply(axis=1) directly, or is called once
    # over a large frame, not when called repeatedly over small slices).
    # Filtering, the "_source_key" computation, and the
    # drop_duplicates(subset=["_source_key"], keep="first") dedup below
    # are then done in plain Python on that one materialized list --
    # keep="first" is exactly "skip if key already seen, else keep", in
    # original row order, which is what pandas' drop_duplicates does.
    # Every predicate/lambda here only ever calls row.get(name, default),
    # identical on a dict and a Series, so this is a pure speed-up, not a
    # behavior change. `idx` values match the original DataFrame index
    # labels the old apply(axis=1) lambda read via `row.name`.
    all_rows = list(zip(group.index, group.to_dict("records")))

    empirical_pairs = [
        (idx, row) for idx, row in all_rows
        if _row_has_candidate_specific_empirical_support(row)
    ]
    if not empirical_pairs:
        return []

    seen_source_keys: set[str] = set()
    deduped: list[tuple[object, dict, str]] = []
    for idx, row in empirical_pairs:
        source_key = (
            _norm(row.get("Source_Record_IDs", ""))
            or _norm(row.get("Evidence_Source", ""))
            or f"row-{idx}"
        )
        if source_key in seen_source_keys:
            continue
        seen_source_keys.add(source_key)
        deduped.append((idx, row, source_key))

    row_records: list[dict] = []
    for idx, row, source_key in deduped:
        base_points, label = _row_hierarchy_points(row)
        authority = classify_source_authority_from_row(row)
        authority_multiplier = _authority_hierarchy_multiplier(authority.score)
        weighted_points = base_points * authority_multiplier
        result_category = _result_category(row)
        direction = _DIRECTION_BY_RESULT_CATEGORY.get(result_category, DIRECTION_UNCLEAR)
        quality_factor_for_explain = min(1.0, base_points / 18.0) if base_points > 0 else 0.0
        strength = weighted_evidence_strength(quality_factor_for_explain, authority.score, 1.0)
        signed_contribution = signed_evidence_contribution(strength, direction)
        row_records.append({
            "row_id": idx,
            "row": row,
            "source_key": source_key or f"row-{idx}",
            "base_points": base_points,
            "label": label,
            "authority_label": authority.label,
            "authority_score": authority.score,
            "authority_reason": authority.reason,
            "weighted_points": weighted_points,
            "direction": direction,
            "result_category": result_category,
            "signed_contribution": signed_contribution,
            "source_record_ids": row.get("Source_Record_IDs", "") or row.get("Evidence_Source", ""),
        })
    return row_records


def _evidence_quality_from_row_records(row_records: list[dict]) -> tuple[float, str, dict]:
    """Apply the unchanged unsigned Evidence Quality formula to records."""
    if not row_records:
        return 0.0, "None", _empty_evidence_quality_explain()

    classified = [(r["weighted_points"], r["label"]) for r in row_records]
    positive_scores = [points for points, _ in classified if points > 0]
    if not positive_scores:
        return 0.0, "None", _build_evidence_quality_explain(row_records)

    ranked = sorted(positive_scores, reverse=True)
    best = ranked[0]
    top_mean = sum(ranked[:3]) / len(ranked[:3])
    hierarchy_points = 0.6 * best + 0.4 * top_mean

    import math
    independent_count = len(row_records)
    depth_points = min(7.0, 1.8 * math.log2(1 + independent_count))
    strata = {label for points, label in classified if points > 0}
    diversity_points = min(3.0, float(len(strata)))
    reproducibility_points = (
        min(2.0, 0.5 * (independent_count - 1)) if independent_count > 1 else 0.0
    )

    raw_total = hierarchy_points + depth_points + diversity_points + reproducibility_points
    total = round(min(30.0, raw_total), 1)
    if total >= 23:
        tier = "Strong"
    elif total >= 15:
        tier = "Moderate"
    elif total > 0:
        tier = "Weak"
    else:
        tier = "None"
    return total, tier, _build_evidence_quality_explain(row_records)


def _evidence_quality(
    group: pd.DataFrame,
    sources: list[str],
    references: list[str],
) -> tuple[float, str, dict]:
    """Score record-level evidence quality without collapsing every source.

    Phase 5/Step 5 now emits one raw row per evidence record.  This function
    therefore scores the actual hierarchy mix and depth rather than assigning
    the strongest label found anywhere to one synthetic plant row.  Duplicate
    identifiers are counted once and registry records without results do not
    earn efficacy points. (PHASE 3 FOLLOW-UP: contradictory/null findings no
    longer reduce the total here — see reproducibility_points/raw_total
    below and Evidence_Conflict/Outcome_Consistency in the explain dict for
    where that signal now lives instead.)

    PHASE 3 — Source Authority is now integrated INSIDE this function's
    existing 30.0 cap (never a new score component, per the brief's
    "Source Authority را ترجیحاً داخل همان سقف موجود Evidence Quality ادغام
    کن" instruction): each row's hierarchy points are scaled by a bounded
    authority multiplier (see _authority_hierarchy_multiplier) before being
    aggregated into `hierarchy_points`/`best`/`top_mean`. Authority never
    touches the direction/consistency logic below — it only adjusts the
    MAGNITUDE of each row's own quality contribution, exactly like the
    pre-existing hierarchy classification itself.

    PHASE 3, problem 2 — the `outcome_multiplier` step that previously
    scaled the final capped total down whenever the evidence pool was
    null/negative/mixed-heavy has been REMOVED: Evidence_Quality_Score
    must be independent of Evidence_Direction (unsigned strength =
    design x methodological quality x source authority x applicability
    x independence/depth; direction only ever applies to the signed
    per-row contribution surfaced in `explain`, never to this capped
    total). See the removal site (search `raw_total = hierarchy_points`)
    for the full rationale.

    Returns (total, tier, explain) where `explain` is an additive
    explainability dict (Phase 3 brief section 8) — never displayed by any
    existing UI/Dashboard code. PHASE 5: `explain["row_records"]` (already
    computed here) is now also reused by
    `_scientific_evidence_components()` below to build tier-aware
    Direction/Consistency/Applicability without re-deriving hierarchy
    classification in a second place — everything else in `explain`
    remains a pure diagnostic addition, as before.
    """
    row_records = _build_evidence_row_records(group)
    return _evidence_quality_from_row_records(row_records)


def _empty_evidence_quality_explain() -> dict:
    return {
        "authority_distribution": {},
        "quality_design_distribution": {},
        "positive_weighted_contribution": 0.0,
        "negative_weighted_contribution": 0.0,
        "null_weighted_contribution": 0.0,
        "unknown_authority_count": 0,
        "top_supporting_evidence": [],
        "top_contradicting_evidence": [],
        "evidence_direction_balance": {},
        "evidence_conflict": False,
        "outcome_consistency": 0.0,
        # PHASE 5 — the row_records this function already computed,
        # reused (not re-derived) by the tier-precedence/Direction/
        # Consistency/Applicability aggregation in
        # _scientific_evidence_components() below. Still never displayed
        # by any UI — only consumed inside this module.
        "row_records": [],
    }


def _build_evidence_quality_explain(row_records: list[dict]) -> dict:
    """PHASE 3 explainability (brief section 8) at the candidate-aggregate
    level: authority distribution, quality/study-design distribution,
    positive/negative/null weighted contribution, unknown-authority count,
    and the top supporting/contradicting evidence. Built from the SAME
    per-row numbers `_evidence_quality` actually computed above — never a
    separately-invented narrative (per the brief's "Explainability باید از
    همان اعدادی تولید شود که واقعاً scoring را اجرا کرده‌اند" instruction).

    PHASE 3 FOLLOW-UP: `evidence_direction_balance`/`evidence_conflict`/
    `outcome_consistency` are the diagnostics-only home for the outcome
    signal that used to live inside `_evidence_quality`'s scored total
    (first as `outcome_multiplier`, then as `consistency_points`). They
    are computed here, from the SAME row_records/`direction` values the
    positive/negative/null weighted contributions above already use —
    never fed back into `raw_total`/`total` in `_evidence_quality`.
    """
    if not row_records:
        return _empty_evidence_quality_explain()

    authority_distribution = summarize_authority_distribution(
        r["authority_label"] for r in row_records
    )
    quality_design_distribution: dict = {}
    for r in row_records:
        quality_design_distribution[r["label"]] = quality_design_distribution.get(r["label"], 0) + 1

    positive_weighted = sum(
        r["signed_contribution"] for r in row_records if r["signed_contribution"] > 0
    )
    negative_weighted = sum(
        r["signed_contribution"] for r in row_records if r["signed_contribution"] < 0
    )
    null_weighted = sum(
        r["signed_contribution"] for r in row_records if r["signed_contribution"] == 0
    )
    unknown_authority_count = sum(
        1 for r in row_records if r["authority_label"] == AUTHORITY_UNKNOWN
    )

    supporting = sorted(
        (r for r in row_records if r["signed_contribution"] > 0),
        key=lambda r: r["signed_contribution"],
        reverse=True,
    )
    contradicting = sorted(
        (r for r in row_records if r["signed_contribution"] < 0),
        key=lambda r: r["signed_contribution"],
    )

    def _summary(r: dict) -> dict:
        return {
            "source_record_ids": r["source_record_ids"],
            "study_design_label": r["label"],
            "authority_label": r["authority_label"],
            "authority_score": r["authority_score"],
            "direction": r["direction"],
            "signed_contribution": round(r["signed_contribution"], 4),
        }

    # PHASE 3 FOLLOW-UP — diagnostics-only outcome signal (never scored).
    direction_counts: dict = {}
    for r in row_records:
        direction_counts[r["direction"]] = direction_counts.get(r["direction"], 0) + 1
    positive_count = sum(
        1 for r in row_records if r["direction"] == DIRECTION_POSITIVE
    )
    negative_count = sum(
        1 for r in row_records if r["direction"] == DIRECTION_NEGATIVE
    )
    evidence_conflict = positive_count > 0 and negative_count > 0
    dominant_direction_count = max(direction_counts.values()) if direction_counts else 0
    outcome_consistency = (
        round(dominant_direction_count / len(row_records), 4) if row_records else 0.0
    )

    return {
        "authority_distribution": authority_distribution,
        "quality_design_distribution": quality_design_distribution,
        "positive_weighted_contribution": round(positive_weighted, 4),
        "negative_weighted_contribution": round(negative_weighted, 4),
        "null_weighted_contribution": round(null_weighted, 4),
        "unknown_authority_count": unknown_authority_count,
        "top_supporting_evidence": [_summary(r) for r in supporting[:3]],
        "top_contradicting_evidence": [_summary(r) for r in contradicting[:3]],
        "evidence_direction_balance": direction_counts,
        "evidence_conflict": evidence_conflict,
        "outcome_consistency": outcome_consistency,
        # PHASE 5 — reused by _scientific_evidence_components(); see
        # _empty_evidence_quality_explain()'s comment.
        "row_records": row_records,
    }

def _scientific_evidence_components(
    row_records: list[dict],
    resolved_target_context: Mapping[str, Any] | None,
    _compute_marginals: bool = True,
) -> dict:
    """PHASE 5 — tier-aware Direction/Consistency/Applicability
    aggregation and the resulting Scientific_Evidence_Score. Reuses
    `row_records` already computed by `_evidence_quality()` (same
    hierarchy classification, same de-duplication, same authority
    weighting) — no study-design detection is re-derived here.

    See PHASE5_SCORING_CALIBRATION_AUDIT_ADDENDUM.md §1.3-§1.5, §3.4-§3.7.
    PROVISIONAL. NOT CLINICALLY VALIDATED. NOT STATISTICALLY CALIBRATED.
    """
    tiers: dict[str, list[dict]] = {tier: [] for tier in EVIDENCE_TIER_PRECEDENCE}
    for record in row_records:
        tier = HIERARCHY_LABEL_TO_TIER.get(record["label"], "C")
        tiers[tier].append(record)

    primary_tier = next((t for t in EVIDENCE_TIER_PRECEDENCE if tiers[t]), None)
    primary_records = tiers[primary_tier] if primary_tier else []
    supporting_tiers_present = [
        t for t in EVIDENCE_TIER_PRECEDENCE if t != primary_tier and tiers[t]
    ]
    supporting_record_count = sum(len(tiers[t]) for t in supporting_tiers_present)

    # PHASE 5 (addendum §4/§11) — deterministic narrative provenance:
    # the SAME primary-tier records that establish Direction/Consistency/
    # Applicability are the ones eligible to supply narrative text, not
    # a separate, unrestricted raw-score ranking over ALL rows (the
    # confirmed provenance defect, main audit §4). Tie-broken by row_id
    # for determinism.
    scientific_source_record_ids = sorted({
        str(r["source_record_ids"] or r["row_id"]) for r in primary_records
    })
    authoritative_narrative_source_record_id = None
    authoritative_narrative_provenance = "no evidence records available"
    if primary_records:
        richest = max(
            primary_records,
            key=lambda r: (float(r["weighted_points"]), str(r["row_id"])),
        )
        authoritative_narrative_source_record_id = str(
            richest["source_record_ids"] or richest["row_id"]
        )
        authoritative_narrative_provenance = (
            f"selected: highest-weighted record ({richest['label']}, "
            f"weighted_points={round(float(richest['weighted_points']), 2)}) "
            f"within the primary evidence tier ({primary_tier})"
        )

    # --- Direction / Consistency (primary tier ONLY, per addendum §1.3) ---
    primary_outcome_profile = _outcome_profile_from_row_records(primary_records)
    consistency_class = classify_evidence_consistency(primary_outcome_profile)
    direction_factor = DIRECTION_FACTORS[consistency_class]
    consistency_factor = CONSISTENCY_FACTORS[consistency_class]

    # Evidence Quality uses the exact existing formula, but only over the
    # same primary-tier records that establish direction/consistency and
    # plant applicability. Lower tiers are diagnostic-only by contract.
    evidence_quality_score, evidence_quality_tier, evidence_quality_explain = (
        _evidence_quality_from_row_records(primary_records)
    )

    # --- Applicability (primary tier ONLY, quality-weighted mean) ---
    target_context = resolved_target_context or {}
    record_applicability_summary: dict[str, dict] = {}
    weighted_sum = 0.0
    weight_total = 0.0
    aggregate_dimension_status: dict[str, str] = {}
    any_incomplete = False
    for record in primary_records:
        source_id = str(record["source_record_ids"] or record["row_id"])
        result = evaluate_applicability(record["row"], target_context)
        record_applicability_summary[source_id] = result
        weight = max(0.0, float(record["weighted_points"]))
        weighted_sum += weight * float(result["Record_Applicability_Factor"])
        weight_total += weight
        if result["Applicability_Data_Completeness"] == "incomplete":
            any_incomplete = True
        for dim, status in result["Dimension_Status"].items():
            if status == NOT_APPLICABLE:
                continue
            existing = aggregate_dimension_status.get(dim)
            if existing is None:
                aggregate_dimension_status[dim] = status
            else:
                # worst-status-wins per dimension across primary-tier records
                existing_rank = APPLICABILITY_CLASSIFICATION_PRECEDENCE.index(existing)
                new_rank = APPLICABILITY_CLASSIFICATION_PRECEDENCE.index(status)
                if new_rank < existing_rank:
                    aggregate_dimension_status[dim] = status

    if not target_context:
        plant_applicability_factor = APPLICABILITY_FACTOR_WHEN_NOTHING_EVALUABLE
        applicability_classification = APPLICABILITY_CLASSIFICATION_WHEN_NOTHING_EVALUABLE
        applicability_completeness = "preliminary"
    elif weight_total <= 0.0 or not primary_records:
        plant_applicability_factor = APPLICABILITY_FACTOR_WHEN_NOTHING_EVALUABLE
        applicability_classification = APPLICABILITY_CLASSIFICATION_WHEN_NOTHING_EVALUABLE
        applicability_completeness = "incomplete"
    else:
        plant_applicability_factor = weighted_sum / weight_total
        applicability_classification = NOT_APPLICABLE
        for candidate_status in APPLICABILITY_CLASSIFICATION_PRECEDENCE:
            if candidate_status in aggregate_dimension_status.values():
                applicability_classification = candidate_status
                break
        applicability_completeness = "incomplete" if any_incomplete else "complete"

    raw_score = (
        evidence_quality_score * direction_factor * consistency_factor * plant_applicability_factor
    )
    scientific_evidence_score = round(
        min(SCIENTIFIC_EVIDENCE_SCORE_CEILING, max(SCIENTIFIC_EVIDENCE_SCORE_FLOOR, raw_score)), 2
    )

    evidence_direction_profile = {
        "Primary_Evidence_Tier": primary_tier,
        "Primary_Tier_Record_Count": len(primary_records),
        "Evidence_Consistency_Class": consistency_class,
        "Direction_Factor": direction_factor,
    }

    # PHASE 6 — exact, non-fabricated per-evidence score effect.  Because
    # Scientific_Evidence_Score is nonlinear, additive allocation across
    # records would be false precision.  Instead record the deterministic
    # leave-one-evidence-out marginal effect using the SAME scoring function.
    scientific_evidence_contributions = []
    if _compute_marginals and primary_records:
        for record in primary_records:
            reduced = [r for r in row_records if r is not record]
            counterfactual = _scientific_evidence_components(
                reduced, resolved_target_context, _compute_marginals=False
            )["Scientific_Evidence_Score"]
            source_id = str(record["source_record_ids"] or record["row_id"])
            scientific_evidence_contributions.append({
                "evidence_id": source_id,
                "entered_score": True,
                "marginal_score_effect": round(scientific_evidence_score - counterfactual, 4),
                "score_with_evidence": scientific_evidence_score,
                "score_without_evidence": counterfactual,
                "method": "leave_one_evidence_out",
                "study_design_label": record["label"],
                "authority_label": record["authority_label"],
                "authority_score": record["authority_score"],
                "direction": record["direction"],
                "applicability": record_applicability_summary.get(source_id),
            })

    return {
        "Scientific_Evidence_Score": scientific_evidence_score,
        "Direction_Factor": direction_factor,
        "Evidence_Consistency_Class": consistency_class,
        "Evidence_Consistency_Factor": consistency_factor,
        "Evidence_Direction_Profile": evidence_direction_profile,
        "Evidence_Quality_Score": evidence_quality_score,
        "Evidence_Quality_Tier": evidence_quality_tier,
        "Evidence_Quality_Explain": evidence_quality_explain,
        "Primary_Tier_Outcome_Profile": primary_outcome_profile,
        "Primary_Tier_Outcome_Label": primary_outcome_profile["label"],
        "Plant_Applicability_Factor": plant_applicability_factor,
        "Record_Applicability_Summary": record_applicability_summary,
        "Dimension_Status": aggregate_dimension_status,
        "Applicability_Classification": applicability_classification,
        "Applicability_Data_Completeness": applicability_completeness,
        "Primary_Evidence_Tier": primary_tier,
        "Supporting_Evidence_Tiers_Present": supporting_tiers_present,
        "Supporting_Evidence_Record_Count": supporting_record_count,
        "Scientific_Evidence_Source_Record_IDs": scientific_source_record_ids,
        "Scientific_Evidence_Contributions": scientific_evidence_contributions,
        "Authoritative_Narrative_Source_Record_ID": authoritative_narrative_source_record_id,
        "Authoritative_Narrative_Provenance": authoritative_narrative_provenance,
    }


def _compound_quality(group: pd.DataFrame, distinctive_compounds: list[str]) -> tuple[float, str]:
    """Supporting chemistry only; capped at 5% of the 100-point score."""
    best_by_name: dict[str, float] = {}
    linked_weight = 0.0
    # NOTE (2026-08-26): measured directly -- for this function's typical
    # per-plant row count, group.iterrows() is faster than
    # group.to_dict("records") (the fixed per-call conversion cost of
    # to_dict("records") only pays off when it replaces group.apply(...,
    # axis=1) specifically, or when called once over a large frame; see
    # _build_evidence_row_records()'s docstring for the case where it does
    # help). Every use of `row` below is row.get(name, default), so this
    # stays a pure iteration-mechanism choice either way.
    for _, row in group.iterrows():
        row_weight = _compound_weight(
            row.get("Shared_or_Similar_Compound", ""), row.get("Novelty_Status", "")
        )
        for name in _compound_names(row.get("Shared_or_Similar_Compound", "")):
            if name in _COMPOUND_TIER_0:
                weight = 0.0
            elif name in _COMPOUND_TIER_1:
                weight = min(0.35, row_weight)
            else:
                weight = row_weight
            best_by_name[name] = max(best_by_name.get(name, 0.0), weight)
        if bool(row.get("Supported_Target_or_Mechanism", False)):
            linked_weight += row_weight

    weighted_sum = sum(best_by_name.values())
    if weighted_sum <= 0:
        return 0.0, "Non-informative overlap only"

    base = min(4.0, 1.0 * weighted_sum)
    bonus = min(1.0, 0.2 * linked_weight)
    total = round(min(5.0, base + bonus), 1)
    tier = "High" if total >= 4 else "Moderate" if total >= 2 else "Low"
    return total, tier


def _split_mechanism_values(value: object) -> list[str]:
    if _is_missing(value):
        return []
    return [x.strip() for x in re.split(r"[;,|]", str(value)) if x.strip()]


def _indication_specific_mechanism_values(
    group: pd.DataFrame, indication: str, limit: int = 10
) -> list[str]:
    """Return only mechanism components grounded in the requested indication.

    Whole-plant phytochemical databases can attach hundreds of unrelated
    bioactivities (anticancer, pesticide, cytotoxic, etc.) to one row.  Those
    remain available upstream but must not be presented or scored as supported
    mechanisms for an unrelated indication.
    """
    family = resolve_indication_semantics(indication) if _norm(indication) else None
    indication_terms = set()
    if family:
        indication_terms.update(_norm(t) for t in family.get("mechanistic", ()) if _norm(t))
        indication_terms.update(_norm(t) for t in family.get("direct", ()) if _norm(t))
    kept: list[str] = []
    for _, row in group.iterrows():
        match_type, match_terms = _row_authoritative_relevance(row)
        if _group_has_authoritative_relevance(group) and match_type not in (*_MATCH_STRONG, *_MATCH_SUPPORTIVE):
            continue
        row_terms = {_norm(t) for t in match_terms if _norm(t)}
        for component in _split_mechanism_values(row.get("Target_or_Mechanism", "")):
            c_norm = _norm(component)
            if not c_norm:
                continue
            relevant = any(
                phrase_present(c_norm, term) or phrase_present(term, c_norm)
                for term in indication_terms | row_terms
                if term
            )
            if relevant and c_norm not in {_norm(x) for x in kept}:
                kept.append(component)
                if len(kept) >= limit:
                    return kept
    return kept


def _mechanism_support(group: pd.DataFrame, indication: str = "") -> tuple[float, str]:
    # IMPORTANT: keep the calibrated Phase-5 scoring semantics unchanged.
    # Indication-specific filtering is a reporting/traceability concern, not a
    # retroactive score recalibration.  Changing this support count would alter
    # Overall_Score and existing Go/Investigate thresholds for already-validated
    # primary-tier programmes.  The final report uses
    # _indication_specific_mechanism_values() separately to avoid displaying
    # unrelated whole-plant bioactivities.
    supported = int(group["Supported_Target_or_Mechanism"].sum())
    total = min(10.0, 2.0 * supported)
    tier = "Strong" if total >= 7 else "Some" if total > 0 else "None"
    return total, tier


def _latin_binomials(text: str) -> set[str]:
    return {
        f"{g.lower()} {sp.lower()}"
        for g, sp in re.findall(r"\b([A-Z][a-z]{2,})\s+([a-z][a-z-]{2,})\b", str(text or ""))
    }


def _clean_safety_flags_for_plant(group: pd.DataFrame, plant_name: str, limit: int = 8) -> str:
    """Keep only adverse signals attributable to the exact botanical species.

    Protective-toxicity studies and records about a different Latin species are
    not safety flags for the candidate being ranked.
    """
    target = _norm(plant_name)
    target_binomial = " ".join(target.split()[:2]) if len(target.split()) >= 2 else target
    adverse: list[str] = []
    for _, row in group.iterrows():
        value = row.get("Safety_Flags", "")
        if _is_missing(value):
            continue
        interpreted = extract_structured_safety_interactions(value, None, plant_name=plant_name)
        for flag in interpreted.get("adverse_events", []):
            binomials = _latin_binomials(flag)
            if binomials and target_binomial and target_binomial not in binomials:
                continue
            if _norm(flag) not in {_norm(x) for x in adverse}:
                adverse.append(flag)
                if len(adverse) >= limit:
                    return "; ".join(adverse)
    return "; ".join(adverse)


def _critical_plant_stop(group: pd.DataFrame) -> bool:
    """Return True only for a plant-level stop supported across the group.

    A single raw association marked No-Go must not automatically exclude the
    entire botanical candidate: one plant can have many compounds and mixed
    evidence rows.  We reserve plant-level exclusion for an explicit regulatory
    prohibition/contraindication or for repeated hard-stop rows that dominate
    the candidate record.
    """
    regulatory_text = " | ".join(
        _norm(v) for v in group.get("Regulatory_Barriers", pd.Series(dtype=object)).dropna().tolist()
    )
    if any(term in regulatory_text for term in (
        "prohibited", "prohibition", "banned", "regulatory ban", "contraindicated",
    )):
        return True

    hard_count = int(group["Hard_Stop_Present"].sum())
    row_count = max(1, len(group))
    if row_count == 1 and hard_count == 1:
        return True
    return hard_count >= 2 and (hard_count / row_count) >= 0.5


def _meaningful_group_values(group: pd.DataFrame, column: str) -> list[str]:
    """Return non-placeholder values without treating missingness as evidence."""
    if column not in group.columns:
        return []
    out: list[str] = []
    for value in group[column].dropna().tolist():
        text = str(value).strip()
        norm = _norm(text)
        if not norm or norm in _MISSING_MARKERS:
            continue
        if norm in {
            "not assessed", "search not performed", "requires product specific assessment",
            "requires product-specific assessment", "indication derived candidate",
            "indication-derived candidate",
        }:
            continue
        out.append(text)
    return out


def _safety_regulatory(group: pd.DataFrame) -> tuple[float, str]:
    """Score only explicit safety/regulatory information.

    Absence of a flag is not proof of safety.  Unknown safety and an unperformed
    regulatory search therefore receive a conservative neutral score rather than
    the previous optimistic 'clean' score.  Genuine reassuring, adverse, and
    prohibitive evidence still produce differentiated values.
    """
    if _critical_plant_stop(group):
        return 0.0, "Plant-level hard stop"

    safety_values = (
        _meaningful_group_values(group, "Safety_Flags")
        + _meaningful_group_values(group, "Interaction_Flags")
        + _meaningful_group_values(group, "Negative_Evidence_Types")
    )
    safety_text = _norm(" | ".join(safety_values))

    severe_terms = ("fatal", "severe toxicity", "hepatotoxic", "nephrotoxic", "teratogenic", "contraindicated")
    concern_terms = ("toxicity", "toxic", "adverse", "interaction", "bleeding", "allergic", "irritant")
    reassuring_terms = ("well tolerated", "no serious adverse", "no adverse event", "no safety signal")

    if any(term in safety_text for term in severe_terms):
        safety_points, tier = 1.0, "Major safety concern"
    elif any(term in safety_text for term in reassuring_terms):
        safety_points, tier = 8.0, "Explicit reassuring evidence"
    elif any(term in safety_text for term in concern_terms):
        safety_points, tier = 4.0, "Safety review needed"
    else:
        safety_points, tier = 5.0, "Safety not adequately assessed"

    regulatory_values = _meaningful_group_values(group, "Regulatory_Barriers")
    regulatory_text = _norm(" | ".join(regulatory_values))
    if any(term in regulatory_text for term in ("prohibited", "banned", "regulatory ban")):
        reg_points, tier = 0.0, "Regulatory prohibition"
    elif regulatory_values:
        if any(term in regulatory_text for term in ("approved", "authorized", "authorised", "monograph", "traditional use")):
            reg_points = 6.0
        else:
            reg_points = 2.0
            if tier == "Safety not adequately assessed":
                tier = "Regulatory review needed"
    else:
        reg_points = 3.0

    return round(min(15.0, safety_points + reg_points), 1), tier

def _novelty_market(group: pd.DataFrame) -> tuple[float, str]:
    """Score COMMERCIAL opportunity only; never infer it from chemistry.

    ``Novelty_Status`` is a legacy chemical/source-differentiation field.  It
    is intentionally NOT read here.  Commercial white-space/repurposing may be
    awarded only from an actually completed market assessment (preferably the
    Phase-8 Commercial_* fields).  Missing market data earns zero points rather
    than a half-score prior, because "not searched" is not an opportunity.
    """
    commercial_values = []
    for column in (
        "Commercial_Novelty_Status",
        "Commercial_Status_For_Indication",
        "Commercial_Status_Overall",
        "Commercial_Positioning",
        "Commercial_Market_Status",
        "Commercial_Search_Status",
        "Indication_Market_Search_Status",
    ):
        commercial_values.extend(_meaningful_group_values(group, column))

    # Backward-compatible fallback for historical rows that predate the
    # Commercial_* columns.  Market_Status may be used, but Novelty_Status may
    # not: the latter describes chemistry, not the market.
    if not commercial_values:
        commercial_values = _meaningful_group_values(group, "Market_Status")

    combined = _norm(" | ".join(commercial_values))
    if not combined or any(t in combined for t in _COMMERCIAL_UNASSESSED_TERMS):
        # Preserve the platform's historical neutral prior so legacy scientific
        # score contracts do not shift merely because commercial intelligence
        # was unavailable.  The LABEL is deliberately non-claiming: 2.5 is a
        # neutral scoring prior, not evidence of novelty or white-space.
        return 2.5, "Commercial novelty not assessed"

    if any(t in combined for t in _COMMERCIAL_ESTABLISHED_TERMS) or (
        "verified marketed product" in combined
    ):
        return 1.0, "Established / commercially active"

    if any(t in combined for t in _COMMERCIAL_REPURPOSING_TERMS):
        return 4.0, "Indication-repurposing opportunity"

    if any(t in combined for t in _COMMERCIAL_WHITE_SPACE_TERMS):
        return 5.0, "Commercial white-space"

    if any(t in combined for t in ("crowded", "many products", "high competition", "saturated")):
        return 1.0, "Competitive / saturated market"

    if any(t in combined for t in ("limited products", "emerging market", "moderate competition")):
        return 4.0, "Emerging commercial opportunity"

    if "commercial presence verified" in combined or "verified_marketed" in combined:
        return 1.5, "Commercial presence verified; indication status unclear"

    # Regulatory monographs/traditional-use recognition are not retail-product
    # evidence and therefore do not create commercial novelty points.
    if "regulatory monograph" in combined or "traditional-use" in combined or "traditional use" in combined:
        return 0.0, "Regulatory signal only; commercial novelty not assessed"

    return 0.0, "Commercial novelty not established"


def _first_group_value(group: pd.DataFrame, column: str, default: str = "") -> str:
    values = _meaningful_group_values(group, column)
    return values[0] if values else default


def _max_group_number(group: pd.DataFrame, column: str, default=0):
    if column not in group.columns:
        return default
    values = pd.to_numeric(group[column], errors="coerce").dropna()
    if values.empty:
        return default
    value = float(values.max())
    return int(value) if value.is_integer() else round(value, 2)


def _commercial_summary_fields(group: pd.DataFrame) -> dict:
    """Plant-level market summary, kept independent from chemical novelty."""
    chemical = _join(
        group.get(
            "Chemical_Differentiation_Status",
            group.get("Novelty_Status", pd.Series(dtype=object)),
        ),
        6,
    )
    commercial_market_status = _first_group_value(
        group, "Commercial_Market_Status", "Search not performed"
    )
    commercial_search_status = _first_group_value(
        group, "Commercial_Search_Status", "SEARCH_NOT_PERFORMED"
    )
    overall_status = _first_group_value(group, "Commercial_Status_Overall", "UNKNOWN")
    indication_status = _first_group_value(
        group, "Commercial_Status_For_Indication", "UNKNOWN"
    )
    commercial_novelty = _first_group_value(
        group, "Commercial_Novelty_Status", "Commercial novelty not assessed"
    )
    positioning = _first_group_value(
        group, "Commercial_Positioning",
        "Market data incomplete — do not classify as new commercial R&D",
    )
    indication_search_status = _first_group_value(
        group, "Indication_Market_Search_Status", "SEARCH_NOT_PERFORMED"
    )
    market_source_ids = sorted({
        source_id
        for _, row in group.iterrows()
        for source_id in _market_source_ids_from_row(row)
    })
    return {
        "Chemical_Differentiation_Status": chemical,
        "Commercial_Market_Status": commercial_market_status,
        "Commercial_Search_Status": commercial_search_status,
        "Commercial_Status_Overall": overall_status,
        "Commercial_Status_For_Indication": indication_status,
        "Commercial_Novelty_Status": commercial_novelty,
        "Commercial_Positioning": positioning,
        "Overall_Product_Hits": _max_group_number(group, "Overall_Product_Hits", 0),
        "Indication_Product_Hits": _max_group_number(group, "Indication_Product_Hits", 0),
        "Commercial_Market_Saturation": _first_group_value(
            group, "Commercial_Market_Saturation",
            _first_group_value(group, "Market_Saturation", "UNKNOWN"),
        ),
        "Indication_Market_Saturation": _first_group_value(
            group, "Indication_Market_Saturation", "UNKNOWN"
        ),
        "Indication_Market_Search_Status": indication_search_status,
        "Commercial_Market_Source_IDs": market_source_ids,
    }


def _indication_component_source_ids(
    group: pd.DataFrame,
    indication: str,
    indication_mode: str,
) -> list[str]:
    """Return rows actually consumed by the selected indication-score branch."""
    if not _norm(indication) or indication_mode in {"Not evaluated", "None"}:
        return []

    selected: list[pd.Series] = []
    if _group_has_authoritative_relevance(group):
        for _, row in group.iterrows():
            match_type, _ = _row_authoritative_relevance(row)
            empirical = _row_has_candidate_specific_empirical_support(row)
            if str(indication_mode).startswith("Direct"):
                if (
                    match_type in _MATCH_STRONG
                    and empirical
                    and _row_has_traceable_source(row)
                    and not _row_is_inferred_or_generic(row)
                ):
                    selected.append(row)
            elif indication_mode == "Mechanistic empirical":
                if match_type in _MATCH_SUPPORTIVE and empirical:
                    selected.append(row)
            elif indication_mode == "Mechanistic inference only":
                if match_type in _MATCH_SUPPORTIVE and not empirical:
                    selected.append(row)
    else:
        family = _concept_family(indication)
        for _, row in group.iterrows():
            empirical = _row_has_candidate_specific_empirical_support(row)
            if indication_mode in {"Direct candidate-specific", "Indirect candidate-specific"}:
                if empirical:
                    selected.append(row)
                continue
            if not family:
                continue
            row_blob = _candidate_specific_blob(pd.DataFrame([row]), indication)
            direct_hits = set(_matched_terms(row_blob, family["direct"]))
            mechanism_hits = set(_matched_terms(row_blob, family["mechanistic"]))
            if str(indication_mode).startswith("Direct"):
                if (
                    direct_hits
                    and empirical
                    and _row_has_traceable_source(row)
                    and not _row_is_inferred_or_generic(row)
                ):
                    selected.append(row)
            elif indication_mode == "Mechanistic empirical" and mechanism_hits and empirical:
                selected.append(row)
            elif indication_mode == "Mechanistic inference only" and mechanism_hits and not empirical:
                selected.append(row)
    return _source_ids_for_rows(selected)


def _compound_component_source_ids(group: pd.DataFrame) -> list[str]:
    selected: list[pd.Series] = []
    for _, row in group.iterrows():
        row_weight = _compound_weight(
            row.get("Shared_or_Similar_Compound", ""), row.get("Novelty_Status", "")
        )
        informative = any(
            name not in _COMPOUND_TIER_0 and row_weight > 0
            for name in _compound_names(row.get("Shared_or_Similar_Compound", ""))
        )
        linked_bonus = bool(row.get("Supported_Target_or_Mechanism", False)) and row_weight > 0
        if informative or linked_bonus:
            selected.append(row)
    return _source_ids_for_rows(selected)


def _mechanism_component_source_ids(group: pd.DataFrame) -> list[str]:
    return _source_ids_for_rows(
        row for _, row in group.iterrows() if bool(row.get("Supported_Target_or_Mechanism", False))
    )


def _safety_component_source_ids(group: pd.DataFrame) -> list[str]:
    selected: list[pd.Series] = []
    for _, row in group.iterrows():
        has_explicit_value = any(
            _meaningful_group_values(pd.DataFrame([row]), column)
            for column in (
                "Safety_Flags", "Interaction_Flags", "Negative_Evidence_Types",
                "Regulatory_Barriers",
            )
        )
        if has_explicit_value or bool(row.get("Hard_Stop_Present", False)):
            selected.append(row)
    return _source_ids_for_rows(selected)


def _market_source_ids_from_row(row: pd.Series) -> list[str]:
    """Extract Phase-8 market source IDs without attributing them to science."""
    value = row.get("Commercial_Market_Source_IDs", row.get("Market_Evidence_Source_IDs", []))
    if isinstance(value, (list, tuple, set)):
        return sorted({str(v).strip() for v in value if str(v).strip()})
    if isinstance(value, dict):
        return sorted({str(v).strip() for v in value.values() if str(v).strip()})
    text = str(value or "").strip()
    if not text:
        return []
    # Lists may have round-tripped through CSV as JSON/Python-ish text.
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return sorted({str(v).strip() for v in parsed if str(v).strip()})
    except Exception:
        pass
    text = text.strip("[]")
    return sorted({part.strip().strip("'\"") for part in re.split(r"[;,|]+", text) if part.strip().strip("'\"")})


def _novelty_component_source_ids(group: pd.DataFrame) -> list[str]:
    """Provenance for the COMMERCIAL opportunity component.

    Chemical-differentiation rows are deliberately excluded unless they also
    carry genuine market evidence.  This prevents a scientific source ID from
    being presented as if it supported a commercial-market claim.
    """
    ids = set()
    for _, row in group.iterrows():
        market_ids = _market_source_ids_from_row(row)
        ids.update(market_ids)
        if market_ids:
            continue
        # Legacy market rows may have their market observation and source ID on
        # the same row.  Only accept them when Market_Status itself contains a
        # real commercial signal; never because Novelty_Status is populated.
        market_text = _norm(row.get("Market_Status", ""))
        if any(term in market_text for term in (
            "verified marketed product", "commercial evidence reported",
            "no verified product found", "limited products", "emerging market",
            "crowded", "many products", "high competition",
        )):
            ids.update(_row_source_record_ids(row))
    return sorted(ids)


def _component_source_record_ids(
    group: pd.DataFrame,
    *,
    indication: str,
    indication_mode: str,
    scientific_source_ids: list[str],
) -> dict[str, list[str]]:
    """Structured provenance for every published score component."""
    return {
        "Indication Relevance": _indication_component_source_ids(group, indication, indication_mode),
        "Scientific Evidence": sorted(set(scientific_source_ids)),
        "Compound Support": _compound_component_source_ids(group),
        "Mechanism Support": _mechanism_component_source_ids(group),
        "Safety & Regulatory": _safety_component_source_ids(group),
        "Novelty & Market": _novelty_component_source_ids(group),
    }

def _format_breakdown(components: list[tuple[str, float, int]]) -> str:
    lines = []
    for label, points, max_points in components:
        dots = "." * max(3, 26 - len(label))
        lines.append(f"{label} {dots} {points:g}/{max_points}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Phase 3 (IMPLEMENTATION_PLAN.md) — Overall_Score becomes the ONE
# authoritative plant-level score. It stays decomposed into three SEPARATE,
# non-collapsed outputs rather than one opaque number:
#   - Evidence_Confidence   — how strong is the SCIENTIFIC evidence itself
#     (Indication Relevance + Evidence Quality only — the two components
#     that are directly about evidence, not opportunity/commercial fit).
#   - R&D_Opportunity_Score — the full Overall_Score (all six components):
#     the OPPORTUNITY question, which legitimately includes commercial/
#     novelty/market signal alongside the science.
#   - Decision_Class_AH / Go_Investigate_Hold_NoGo — the categorical CALL,
#     derived from Scientific_Triage_Status + Overall_Score, not
#     re-derived independently.
# These three answer three different questions and are kept as three
# separate fields for exactly that reason — collapsing them into one
# number would hide which one is doing the work in any given case.
#
# The current Strong/Go threshold is centralized in phase5_scoring_config.
# It remains an engineering prioritization cut-point until expert calibration.
_STRONG_SCORE_THRESHOLD = RANKING_STRONG_PRIORITY_THRESHOLD

# Legacy output field ``Evidence_Confidence`` is now explicitly an Evidence
# Strength Index. It combines indication relevance with the DIRECTION-,
# CONSISTENCY- and APPLICABILITY-aware Scientific_Evidence_Score, not unsigned
# Evidence_Quality_Score. This prevents a high-quality null/negative study from
# appearing as high "confidence" merely because the study design was strong.
_EVIDENCE_CONFIDENCE_MAX_POINTS = (
    RANKING_COMPONENT_BASE_WEIGHTS["Indication Relevance"]
    + RANKING_COMPONENT_BASE_WEIGHTS["Scientific Evidence"]
)


def _derive_evidence_confidence(indication_points: float, scientific_evidence_points: float) -> float:
    # Negative scientific contributions are evidence AGAINST efficacy, not
    # positive evidence strength. They therefore contribute zero to this
    # support-strength index; contradiction is surfaced separately in the
    # evidence-direction/consistency fields.
    raw = float(indication_points) + max(0.0, float(scientific_evidence_points))
    return round(min(100.0, max(0.0, raw / _EVIDENCE_CONFIDENCE_MAX_POINTS * 100.0)), 1)


def _derive_go_call(
    status: str,
    overall_score: float,
    reason: str = "",
    *,
    dosage_compatibility: str = "Unknown",
    safety_tier: str = "Safety not adequately assessed",
    outcome_label: str = "Results not reported",
) -> str:
    if status == "Excluded":
        return "No-Go" if "safety" in _norm(reason) else "Hold"
    if status == "Exploratory":
        return "Investigate — verify before proceeding"
    # A high numeric score alone cannot justify Go. Product-form applicability,
    # explicit safety information, and demonstrated benefit must all be present.
    if _norm(dosage_compatibility) != "compatible":
        return "Investigate — verify preparation applicability"
    if safety_tier != "Explicit reassuring evidence":
        return "Investigate — complete safety/interaction review"
    if outcome_label != "Predominantly positive results":
        return "Investigate — resolve efficacy consistency"
    return "Go" if overall_score >= _STRONG_SCORE_THRESHOLD else "Investigate"


def _derive_decision_class_ah(status: str, overall_score: float, reason: str = "") -> str:
    # Reuses the same A-H label vocabulary already established in
    # decision_class_ah.py, but computed here from the one authoritative
    # plant-level score rather than that module's row-level match_quality/
    # same_plant signals, which do not have a plant-level equivalent.
    if status == "Excluded":
        return "H — No-go / safety concern" if "safety" in _norm(reason) else "G — Hold / insufficient evidence"
    if status == "Exploratory":
        return "F — Exploratory hypothesis"
    if overall_score >= _STRONG_SCORE_THRESHOLD:
        return "B — Established scientific candidate"
    return "C — Alternative-source R&D candidate"


def _explain_candidate(
    status: str,
    components: dict[str, tuple[float, str]],
    distinctive_count: int,
    rejection_reason: str = "",
) -> str:
    if status == "Excluded":
        return "Excluded because: " + (rejection_reason or "scientific triage criteria were not met")

    bullets = []
    if components["indication"][0] > 0:
        bullets.append(components["indication"][1].lower())
    if components["mechanism"][0] >= 5:
        bullets.append("supported target/mechanism evidence")
    if components["evidence"][0] >= 10:
        bullets.append(f"{components['evidence'][1].lower()} evidence base")
    # Chemistry is supporting metadata only and is intentionally omitted from
    # the selection explanation; it cannot justify candidate entry or shortlist status.
    if components["safety"][1] == "Clean":
        bullets.append("clean safety/regulatory screen")
    if components["novelty"][1] == "Novel / white-space":
        bullets.append("novel / white-space opportunity")
    if not bullets:
        bullets.append("a limited but traceable scientific signal remains")

    prefix = "Selected because: " if status == "Shortlist" else "Kept for further investigation because: "
    return prefix + "; ".join(bullets)


def _genus(plant_name: str) -> str:
    first = re.split(r"\s+", str(plant_name or "").strip())[0]
    return _norm(first)


def _identity_quality(plant_name: str) -> int:
    name = _norm(plant_name)
    if not name or " sp." in f" {name}" or name.endswith(" sp") or "spp" in name:
        return 0
    parts = name.split()
    return 2 if len(parts) >= 2 else 1


def _prune_near_duplicate_congeners(summary: pd.DataFrame) -> pd.DataFrame:
    """Annotate same-genus shortlist candidates without changing science.

    Phase 7 correction: taxonomic diversity is a PRESENTATION concern, not a
    scientific-evidence rule. The previous implementation demoted every
    shortlisted congener except one to Exploratory and capped its score at 74,
    so a species could lose scientific status solely because another species
    shared its genus. That is no longer permitted.

    Scores, triage status and Go/Investigate calls are preserved byte-for-byte.
    ``Duplicate_Pruning_Note`` is retained as a backwards-compatible diagnostic
    column, but now only identifies which congener would be the primary display
    representative if a UI later chooses to diversify a top-N list.
    """
    if summary.empty or "Alternative_Plant" not in summary.columns:
        return summary

    summary = summary.copy()
    if "Duplicate_Pruning_Note" not in summary.columns:
        summary["Duplicate_Pruning_Note"] = ""
    summary["_genus"] = summary["Alternative_Plant"].map(_genus)
    summary["_identity_quality"] = summary["Alternative_Plant"].map(_identity_quality)

    for genus, idx in summary.groupby("_genus").groups.items():
        if not genus:
            continue
        shortlisted = summary.loc[idx]
        shortlisted = shortlisted[shortlisted["Scientific_Triage_Status"] == "Shortlist"]
        if len(shortlisted) <= 1:
            continue

        ranked = shortlisted.sort_values(
            [
                "Indication_Relevance_Score", "Evidence_Quality_Score",
                "Compound_Quality_Score", "Traceable_Source_Count",
                "Safety_Regulatory_Score", "_identity_quality", "Overall_Score",
            ],
            ascending=[False, False, False, False, False, False, False],
        )
        representative = str(ranked.iloc[0]["Alternative_Plant"])
        for i, row in ranked.iloc[1:].iterrows():
            summary.loc[i, "Duplicate_Pruning_Note"] = (
                f"same-genus candidate; primary diversity-display representative is "
                f"'{representative}' within genus {genus.capitalize()}. "
                "Scientific status and score are intentionally unchanged."
            )

    return summary.drop(columns=["_genus", "_identity_quality"])

def build_plant_candidate_shortlist(
    raw_df: pd.DataFrame,
    *,
    indication: str = "",
    dosage_form: str = "",
    max_candidates: int = 50,
    target_context: Mapping[str, Any] | None = None,
    progress_callback=None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return ``(plant_summary, row_audit)`` for any indication.

    ``plant_summary`` contains one row per Alternative_Plant and is sorted by a
    transparent Scientific_Triage_Score.  ``row_audit`` retains every raw row
    plus its pass/explore/exclude classification and reasons, so no association
    is silently discarded.

    PHASE 5 (addendum §3.8) — ``target_context`` is an explicit,
    keyword-only, backward-compatible addition: existing callers that
    never pass it keep every previously-existing field's behavior
    unchanged. When absent, a resolved context is still built from the
    legacy ``indication``/``dosage_form`` arguments (``indication`` ->
    ``Target_Indication``, ``dosage_form`` -> ``Target_Preparation``,
    only for non-empty values) so Applicability_* fields are still
    computed for legacy callers on whatever dimensions those two
    arguments cover — species/plant_part/route/dose stay NOT_APPLICABLE
    for such callers, since there is no legacy field to adapt them from.
    Explicit ``target_context`` values always take precedence over
    anything derived from the legacy arguments.

    ``progress_callback`` (2026-08-26, UX fix) -- optional, backward-
    compatible, presentation-only, mirroring the same-named hook already
    used by indication_candidate_discovery.discover_indication_candidates().
    It receives ``(current_plant_count, total_plant_count, message)`` and
    never feeds back into scoring, filtering, ranking, or scientific
    interpretation. Before this, the Streamlit progress bar had nothing to
    update during this function's entire runtime (measured in production
    at several minutes -- see the plant-loop PERF instrumentation below),
    which looked identical to a genuine hang. A caller that does not pass
    this argument gets byte-identical behavior to before.
    """
    def _progress(current: int = 0, total: int = 0, message: str = ""):
        if progress_callback is None:
            return
        try:
            progress_callback(current, total, message)
        except Exception:
            # UI telemetry must never be able to change or abort scientific
            # execution -- same guard as discover_indication_candidates()'s
            # own _progress() helper.
            pass

    if not isinstance(raw_df, pd.DataFrame) or raw_df.empty:
        return pd.DataFrame(), pd.DataFrame()
    if "Alternative_Plant" not in raw_df.columns:
        return pd.DataFrame(), raw_df.copy()

    # PHASE 5 (addendum §3.8, rules 2-4) — resolve target_context once,
    # up front: explicit values win; legacy indication/dosage_form only
    # fill in a key that's genuinely absent.
    explicit_target_context = target_context is not None
    resolved_target_context: dict[str, Any] = dict(target_context or {})
    if "Target_Indication" not in resolved_target_context and _norm(indication):
        resolved_target_context["Target_Indication"] = indication
    # Legacy direct callers historically used dosage_form as a preparation.
    # Keep that adapter only when no explicit transferability context was
    # supplied.  Production Step 5 now passes a context that deliberately
    # leaves Target_Preparation empty for dosage-form-only values such as
    # capsule/tablet/softgel; silently re-inserting "Capsule" here would undo
    # that distinction and recreate the source/target conflation this layer is
    # meant to prevent.
    if not explicit_target_context and "Target_Preparation" not in resolved_target_context and _norm(dosage_form):
        legacy_preparation = preparation_from_product_form(dosage_form)
        if legacy_preparation:
            resolved_target_context["Target_Preparation"] = legacy_preparation

    _t0 = time.perf_counter()
    _perf(f"build_plant_candidate_shortlist start rows={len(raw_df)}")

    _t = time.perf_counter()
    audit = raw_df.copy()
    _perf(f"dataframe_copy done elapsed={time.perf_counter() - _t:.3f} (cumulative={time.perf_counter() - _t0:.3f})")
    statuses: list[str] = []
    reasons: list[str] = []
    direct_values: list[bool] = []
    target_values: list[bool] = []
    generic_values: list[bool] = []
    dosage_values: list[str] = []
    hard_values: list[bool] = []
    negative_values: list[bool] = []

    _t = time.perf_counter()
    _row_classification_count = 0
    _ROW_PROGRESS_EVERY = 2000
    for _, row in audit.iterrows():
        status, row_reasons, flags = _row_classification(row, dosage_form)
        statuses.append(status)
        reasons.append("; ".join(row_reasons) if row_reasons else "Passed scientific triage gates")
        direct_values.append(bool(flags["direct"]))
        target_values.append(bool(flags["target"]))
        generic_values.append(bool(flags["generic"]))
        dosage_values.append(str(flags["dosage"]))
        hard_values.append(bool(flags["hard_stop"]))
        negative_values.append(bool(flags["negative"]))
        _row_classification_count += 1
        if _row_classification_count % _ROW_PROGRESS_EVERY == 0:
            _perf(
                f"row_classification loop {_row_classification_count}/{len(audit)} rows, "
                f"elapsed={time.perf_counter() - _t:.3f}"
            )
    _perf(
        f"row_classification loop done rows={_row_classification_count} "
        f"elapsed={time.perf_counter() - _t:.3f} (cumulative={time.perf_counter() - _t0:.3f})"
    )

    _t = time.perf_counter()
    audit["Scientific_Triage_Status"] = statuses
    audit["Scientific_Triage_Reasons"] = reasons
    audit["Direct_Evidence_Present"] = direct_values
    audit["Supported_Target_or_Mechanism"] = target_values
    audit["Generic_Compound_Only"] = generic_values
    audit["Dosage_Form_Compatibility"] = dosage_values
    audit["Hard_Stop_Present"] = hard_values
    audit["Negative_Evidence_Present"] = negative_values

    # Canonical row-level scientific context shared with downstream AI.
    # These fields are deliberately derived with the *same* deterministic
    # helpers used by the plant-level shortlist/count logic, so adjudication
    # cannot silently reinterpret a row's human/non-human status or whether
    # it actually measures an indication-specific outcome.
    canonical_context = []
    outcome_specific_direct = []
    outcome_specific_human = []
    for _, _row in audit.iterrows():
        _human, _preclinical = _evidence_context_row(_row)
        _ctx = "HUMAN" if _human else ("ANIMAL_OR_IN_VITRO" if _preclinical else "UNKNOWN")
        canonical_context.append(_ctx)
        if _group_has_authoritative_relevance(pd.DataFrame([_row])):
            _is_direct = (
                _row_authoritative_relevance(_row)[0] in _MATCH_STRONG
                and _row_has_traceable_source(_row)
                and _row_has_candidate_specific_empirical_support(_row)
                and _row_has_indication_specific_outcome(_row, indication)
                and not _row_is_inferred_or_generic(_row)
            )
        else:
            _is_direct = bool(_row.get("Direct_Evidence_Present", False)) and _row_has_indication_specific_outcome(_row, indication)
        outcome_specific_direct.append(bool(_is_direct))
        outcome_specific_human.append(bool(_is_direct and _ctx == "HUMAN"))
    audit["Canonical_Study_Context"] = canonical_context
    audit["Outcome_Specific_Direct_Evidence"] = outcome_specific_direct
    audit["Outcome_Specific_Human_Evidence"] = outcome_specific_human
    _perf(f"column_assign done elapsed={time.perf_counter() - _t:.3f} (cumulative={time.perf_counter() - _t0:.3f})")

    rows: list[dict[str, object]] = []

    # Narrowly-scoped per-plant-loop diagnostic pass (per-section
    # cumulative call counts and elapsed seconds), mirroring the
    # instrumentation already added to
    # indication_candidate_discovery.discover_indication_candidates().
    # Diagnostic-only: no thresholds, counts, or behavior are read from
    # these values anywhere.
    _PLANT_SECTION_ORDER = (
        "plant_row_filter", "aggregation", "scoring",
        "decision_gates", "row_append",
    )
    _plant_section_calls = {name: 0 for name in _PLANT_SECTION_ORDER}
    _plant_section_seconds = {name: 0.0 for name in _PLANT_SECTION_ORDER}

    def _plant_section_add(name, elapsed):
        _plant_section_calls[name] += 1
        _plant_section_seconds[name] += elapsed

    _plants_processed = 0
    _PLANT_PROGRESS_EVERY = 50

    def _print_plant_loop_profile(label, total_plants_label):
        detail_lines = [
            f"  plants_processed={_plants_processed}{total_plants_label}, "
            f"output_rows_so_far={len(rows)}, "
            f"elapsed={time.perf_counter() - _t_grouping_loop:.3f}"
        ]
        for name in _PLANT_SECTION_ORDER:
            calls = _plant_section_calls[name]
            total = _plant_section_seconds[name]
            avg_ms = (total / calls * 1000.0) if calls else 0.0
            detail_lines.append(
                f"  {name}: calls={calls} total={total:.3f} avg_ms={avg_ms:.2f}"
            )
        print(f"[PERF] plant loop profile {label}\n" + "\n".join(detail_lines), flush=True)

    _t = time.perf_counter()
    _grouped = audit.groupby("Alternative_Plant", sort=False, dropna=False)
    _perf(f"grouping (groupby call) done elapsed={time.perf_counter() - _t:.3f} (cumulative={time.perf_counter() - _t0:.3f})")
    _progress(0, audit["Alternative_Plant"].nunique(), "Scoring plant candidates…")

    _t_grouping_loop = time.perf_counter()
    for plant, group in _grouped:
        plant = str(plant or "").strip()
        if not plant or plant.lower() == "nan":
            continue
        _plants_processed += 1

        _t = time.perf_counter()
        shortlist_rows = group[group["Scientific_Triage_Status"] == "Shortlist"]
        exploratory_rows = group[group["Scientific_Triage_Status"] == "Exploratory"]
        usable = shortlist_rows if not shortlist_rows.empty else exploratory_rows
        if usable.empty:
            usable = group

        compounds = _split_values(usable.get("Shared_or_Similar_Compound", []))
        distinctive_compounds = [
            c for c in compounds if _compound_weight(c, "") >= 0.7
        ]
        supportive_common_compounds = [
            c for c in compounds if 0.0 < _compound_weight(c, "") < 0.7
        ]
        targets = _split_values(usable.get("Target_or_Mechanism", []))
        sources = _split_values(usable.get("Source_Record_IDs", []))
        references = _split_values(usable.get("Reference_Plant", []))
        statuses_count = Counter(group["Scientific_Triage_Status"].tolist())

        if statuses_count["Shortlist"] > 0:
            plant_status = "Shortlist"
        elif statuses_count["Exploratory"] > 0:
            plant_status = "Exploratory"
        else:
            plant_status = "Excluded"
        _plant_section_add("plant_row_filter", time.perf_counter() - _t)

        _t = time.perf_counter()
        evidence_points = _evidence_points(group)
        target_points = min(20.0, 5.0 * int(group["Supported_Target_or_Mechanism"].sum()))
        compound_points = min(15.0, 5.0 * len(distinctive_compounds))
        source_points = min(10.0, 2.0 * len(sources))
        dosage_statuses = set(group["Dosage_Form_Compatibility"].tolist())
        dosage_points = 10.0 if "Compatible" in dosage_statuses else (5.0 if "Unknown" in dosage_statuses else 0.0)
        safety_points = 0.0 if group["Hard_Stop_Present"].any() else 10.0
        reference_points = min(5.0, 2.5 * len(references))
        negative_penalty = 10.0 if group["Negative_Evidence_Present"].any() else 0.0
        generic_penalty = 10.0 if len(distinctive_compounds) == 0 else 0.0
        _plant_section_add("aggregation", time.perf_counter() - _t)

        triage_score = max(
            0.0,
            min(
                100.0,
                evidence_points + target_points + compound_points + source_points
                + dosage_points + safety_points + reference_points
                - negative_penalty - generic_penalty,
            ),
        )
        if plant_status == "Excluded":
            triage_score = min(triage_score, 39.0)
        elif plant_status == "Exploratory":
            # Preserve ranking differences while ensuring incomplete hypotheses
            # cannot outrank fully gate-passing shortlist candidates merely by
            # accumulating many weak associations.
            triage_score = min(74.0, round(triage_score * 0.75, 1))

        # --- Requirement 8: transparent weighted score (0-100) -------------
        _t = time.perf_counter()
        (
            indication_points,
            indication_tier,
            indication_mode,
            indication_source_count,
        ) = _indication_relevance_detail(group, indication)
        all_tier_evq_points, all_tier_evq_tier, all_tier_evq_explain = _evidence_quality(
            group, sources, references
        )
        sci_evidence = _scientific_evidence_components(
            all_tier_evq_explain["row_records"], resolved_target_context,
        )
        evq_points = sci_evidence["Evidence_Quality_Score"]
        evq_tier = sci_evidence["Evidence_Quality_Tier"]
        evq_explain = sci_evidence["Evidence_Quality_Explain"]
        cq_points, cq_tier = _compound_quality(group, distinctive_compounds)
        mech_points, mech_tier = _mechanism_support(group, indication)
        safety_reg_points, safety_reg_tier = _safety_regulatory(group)
        novelty_points, novelty_tier = _novelty_market(group)
        component_source_record_ids = _component_source_record_ids(
            group,
            indication=indication,
            indication_mode=indication_mode,
            scientific_source_ids=sci_evidence["Scientific_Evidence_Source_Record_IDs"],
        )
        authoritative_source_record_ids = sorted({
            source_id
            for source_ids in component_source_record_ids.values()
            for source_id in source_ids
        })
        authoritative_narrative_source_record_id = sci_evidence[
            "Authoritative_Narrative_Source_Record_ID"
        ]
        authoritative_narrative_provenance = sci_evidence[
            "Authoritative_Narrative_Provenance"
        ]
        if (
            authoritative_narrative_source_record_id is None
            and authoritative_source_record_ids
        ):
            authoritative_narrative_source_record_id = authoritative_source_record_ids[0]
            authoritative_narrative_provenance = (
                "selected: deterministic first score-contributing source because "
                "no primary-tier scientific narrative source was available"
            )
        _plant_section_add("scoring", time.perf_counter() - _t)

        # Final plant-level decision gates. Mechanism similarity is supporting
        # evidence only: it cannot create a Shortlist recommendation without
        # direct candidate-specific indication evidence and adequate evidence
        # quality/traceability.
        _t = time.perf_counter()
        indication_requested = bool(_norm(indication))
        reasons_note = None
        base_plant_status = plant_status
        plant_hard_stop = _critical_plant_stop(group)
        empirical_rows = int(group.apply(_row_has_candidate_specific_empirical_support, axis=1).sum())
        traceable_count = len(set(map(_norm, sources)))
        all_tier_outcome_profile = _outcome_profile(group)
        outcome_profile = sci_evidence["Primary_Tier_Outcome_Profile"]
        primary_record_count = int(sci_evidence["Evidence_Direction_Profile"]["Primary_Tier_Record_Count"])
        primary_traceable_count = len(set(sci_evidence["Scientific_Evidence_Source_Record_IDs"]))
        dosage_statuses = set(group["Dosage_Form_Compatibility"].tolist())
        dosage_summary = (
            "Compatible" if "Compatible" in dosage_statuses
            else "Mismatch" if dosage_statuses == {"Mismatch"}
            else "Unknown"
        )

        if plant_hard_stop:
            plant_status = "Excluded"
            reasons_note = "a repeated or explicit plant-level safety/regulatory stop is present"
        elif not indication_requested:
            plant_status = base_plant_status
        elif indication_points == 0.0:
            plant_status = "Excluded"
            reasons_note = "no candidate-specific evidence was found for the requested indication"
        elif str(indication_mode).startswith("Direct human/clinical") :
            if evq_points >= 12.0 and primary_record_count >= 1 and primary_traceable_count >= 1:
                plant_status = "Shortlist"
            else:
                plant_status = "Exploratory"
                reasons_note = "direct human relevance is present, but traceability or evidence quality is still limited"
        elif indication_mode in {"Direct preclinical", "Direct but limited", "Direct candidate-specific"}:
            if indication_points >= 22.0 and evq_points >= 10.0 and primary_record_count >= 1 and primary_traceable_count >= 2:
                plant_status = "Shortlist"
            else:
                plant_status = "Exploratory"
                reasons_note = "direct indication relevance is present, but the evidence base is not yet sufficient"
        elif indication_mode in {"Mechanistic empirical", "Mechanistic inference only"}:
            # PROBLEM 2 fix: indication relevance is a TRIAGE GATE, not
            # merely one additive score among several. Both of these modes
            # are "Low relevance" -- mechanism/target similarity without
            # direct candidate-specific indication evidence. However much
            # evidence volume or replication accumulates, that alone must
            # NEVER promote a Low-relevance candidate into the primary
            # shortlist (general fix, not menopause-specific). It may still
            # be surfaced as an exploratory hypothesis, but only when the
            # mechanistic rationale is explicit -- a real supported
            # target/mechanism is present, not merely an inferred or
            # generic one -- and the evidence gap is stated.
            explicit_mechanistic_rationale = mech_points > 0.0 or len(targets) > 0
            if explicit_mechanistic_rationale:
                plant_status = "Exploratory"
                reasons_note = (
                    f"indication relevance is Low ({indication_mode}); mechanism/target "
                    "similarity alone does not qualify for the primary shortlist -- "
                    "flagged as an exploratory hypothesis requiring direct, "
                    "indication-specific validation before further prioritisation"
                )
            else:
                plant_status = "Excluded"
                reasons_note = (
                    "indication relevance is Low and no explicit supported "
                    "target/mechanism is present, so even an exploratory "
                    "hypothesis is not justified"
                )
        else:
            plant_status = "Exploratory"
            reasons_note = "only weak, indirect, or inferred indication relevance was found"

        if safety_reg_points <= 0.0:
            plant_status = "Excluded"
            reasons_note = "safety/regulatory screening did not pass at plant level"
        elif outcome_profile["positive"] == 0 and (outcome_profile["null"] + outcome_profile["harmful"]) > 0:
            plant_status = "Exploratory"
            reasons_note = "human/clinical records did not demonstrate benefit or reported an adverse direction"
        elif dosage_summary == "Mismatch":
            plant_status = "Excluded"
            reasons_note = "available evidence uses a preparation that does not match the selected dosage form"
        _plant_section_add("decision_gates", time.perf_counter() - _t)

        _t = time.perf_counter()
        # --- Problem 2 additive diagnostics -------------------------------
        # Direct- vs mechanistic-support row counts, read from the same
        # authoritative per-row relevance used above wherever available, so
        # this reporting layer cannot disagree with the gate that already
        # decided plant_status.
        if _group_has_authoritative_relevance(group):
            direct_source_ids = {
                _norm(source_id)
                for _, r in group.iterrows()
                if (
                    _row_authoritative_relevance(r)[0] in _MATCH_STRONG
                    and _row_has_traceable_source(r)
                    and _row_has_candidate_specific_empirical_support(r)
                    and _row_has_indication_specific_outcome(r, indication)
                    and not _row_is_inferred_or_generic(r)
                )
                for source_id in _split_values([r.get("Source_Record_IDs", "")])
                if _norm(source_id)
            }
            # Report DIRECT evidence from the same primary evidence tier that
            # actually drives Scientific_Evidence_Score.  The old diagnostic
            # counted every direct-looking record across all evidence tiers,
            # including lower-tier projections that were deliberately excluded
            # from scoring.  That could produce misleading counts such as
            # dozens of "direct" records while the authoritative evidence body
            # was much smaller.  This remains indication-agnostic: it is an
            # evidence-lineage rule, not a disease-specific heuristic.
            primary_source_ids = {
                _norm(source_id)
                for value in (sci_evidence.get("Scientific_Evidence_Source_Record_IDs") or [])
                for source_id in _split_values([value])
                if _norm(source_id)
            }
            direct_evidence_count = len(direct_source_ids & primary_source_ids)
            mechanistic_source_ids = {
                _norm(source_id)
                for _, r in group.iterrows()
                if (
                    _row_authoritative_relevance(r)[0] in _MATCH_SUPPORTIVE
                    and _row_has_traceable_source(r)
                    and _row_has_candidate_specific_empirical_support(r)
                )
                for source_id in _split_values([r.get("Source_Record_IDs", "")])
                if _norm(source_id)
            }
            mechanistic_evidence_count = len(mechanistic_source_ids)
        else:
            direct_evidence_count = int(group["Direct_Evidence_Present"].sum())
            mechanistic_evidence_count = max(
                0, int(group["Supported_Target_or_Mechanism"].sum()) - direct_evidence_count
            )

        # Preparation applicability is determined by the same PRIMARY evidence
        # tier that drives the scientific score.  A single low-tier tea record
        # must not upgrade a body of capsule/extract evidence to a direct
        # infusion match.  Lower-tier rows may only provide an indirect hint
        # when the primary tier did not report preparation at all.
        primary_prep = str(sci_evidence.get("Dimension_Status", {}).get("preparation") or "").upper()
        primary_source_ids_for_prep = {
            _norm(source_id)
            for value in (sci_evidence.get("Scientific_Evidence_Source_Record_IDs") or [])
            for source_id in _split_values([value])
            if _norm(source_id)
        }
        primary_rows_for_prep = []
        for _, r in group.iterrows():
            row_ids = {_norm(x) for x in _split_values([r.get("Source_Record_IDs", "")]) if _norm(x)}
            if row_ids & primary_source_ids_for_prep:
                primary_rows_for_prep.append(r)
        explicit_primary_classes = {
            _explicit_preparation_applicability_row(r, dosage_form)
            for r in primary_rows_for_prep
        }
        # Scoring retains the calibrated legacy adapter, but the Stage-6 label
        # "direct_match" is stricter: it requires an explicitly reported
        # preparation in a primary-tier evidence record.  A generic legacy
        # "Compatible" flag is transferability support, not proof that the
        # studied preparation equals the requested product form.
        if primary_prep == "MATCH":
            if PREP_DIRECT_MATCH in explicit_primary_classes:
                preparation_applicability_class = PREP_DIRECT_MATCH
            elif PREP_INCOMPATIBLE in explicit_primary_classes:
                preparation_applicability_class = PREP_INCOMPATIBLE
            else:
                preparation_applicability_class = PREP_COMPATIBLE_BUT_INDIRECT
        elif primary_prep == "PARTIAL":
            preparation_applicability_class = PREP_COMPATIBLE_BUT_INDIRECT
        elif primary_prep == "MISMATCH":
            preparation_applicability_class = PREP_INCOMPATIBLE
        else:
            lower_classes = group.apply(lambda r: _explicit_preparation_applicability_row(r, dosage_form), axis=1)
            if PREP_INCOMPATIBLE in set(lower_classes.values):
                preparation_applicability_class = PREP_INCOMPATIBLE
            elif PREP_DIRECT_MATCH in set(lower_classes.values) or PREP_COMPATIBLE_BUT_INDIRECT in set(lower_classes.values):
                preparation_applicability_class = PREP_COMPATIBLE_BUT_INDIRECT
            else:
                preparation_applicability_class = PREP_NOT_REPORTED

        primary_app = sci_evidence.get("Record_Applicability_Summary", {}) or {}
        preparation_specific_evidence_count = sum(
            1 for rec in primary_app.values()
            if str((rec.get("Dimension_Status", {}) or {}).get("preparation") or "").upper() == "MATCH"
        )

        if plant_hard_stop or safety_reg_points <= 0.0:
            relevance_gate_result = "failed_safety"
        elif not indication_requested:
            relevance_gate_result = "not_applicable"
        elif indication_points == 0.0:
            relevance_gate_result = "failed_no_relevance"
        elif indication_tier in ("High relevance", "Medium relevance"):
            relevance_gate_result = "passed_direct"
        elif indication_tier == "Low relevance":
            relevance_gate_result = (
                "passed_indirect_exploratory_only" if plant_status != "Excluded"
                else "failed_no_relevance"
            )
        else:
            relevance_gate_result = "failed_no_relevance"

        _EVIDENCE_ROUTE_BY_MODE = {
            "Direct human/clinical": "direct_clinical",
            "Direct human/clinical; result direction unavailable": "direct_clinical",
            "Direct human mixed": "direct_clinical_mixed",
            "Direct human null/negative": "direct_clinical_null",
            "Direct preclinical": "direct_preclinical",
            "Direct but limited": "direct_limited",
            "Direct candidate-specific": "direct_candidate_specific",
            "Mechanistic empirical": "mechanistic_only",
            "Mechanistic inference only": "mechanistic_only",
            "Indirect candidate-specific": "indirect_candidate_specific",
            "Not evaluated": "not_evaluated",
            "None": "none",
        }
        evidence_route = _EVIDENCE_ROUTE_BY_MODE.get(str(indication_mode), "unclassified")

        triage_gate_reasons = (
            f"Relevance: {indication_tier} (route={evidence_route}); "
            f"Gate: {relevance_gate_result}; "
            f"Preparation: {preparation_applicability_class}; "
            + (reasons_note or "passed all scientific triage gates")
        )

        raw_score_breakdown = {
            "Indication Relevance": indication_points,
            "Scientific Evidence": sci_evidence["Scientific_Evidence_Score"],
            "Compound Support": cq_points,
            "Mechanism Support": mech_points,
            "Safety & Regulatory": safety_reg_points,
            "Novelty & Market": novelty_points,
        }
        # Phase 7 — production ranking now passes through the same explicit
        # weight model used by robustness/calibration. With today's active
        # weights (35/30/5/10/15/5), this is mathematically identical to the
        # historical sum, so no existing score changes merely because the
        # architecture became calibratable.
        score_breakdown = reweight_score_breakdown(
            raw_score_breakdown, RANKING_COMPONENT_ACTIVE_WEIGHTS
        )
        overall_score = score_from_breakdown(
            raw_score_breakdown, RANKING_COMPONENT_ACTIVE_WEIGHTS
        )

        score_components = {
            "indication": (indication_points, indication_tier),
            "evidence": (sci_evidence["Scientific_Evidence_Score"], evq_tier),
            "compound": (cq_points, cq_tier),
            "mechanism": (mech_points, mech_tier),
            "safety": (safety_reg_points, safety_reg_tier),
            "novelty": (novelty_points, novelty_tier),
        }
        # Phase 3 (IMPLEMENTATION_PLAN.md) — Score_Breakdown is now a plain
        # {name: value} dict (score_breakdown_schema.AUTHORITATIVE_CANONICAL_SECTIONS),
        # the same machine-parseable convention already used for the
        # indication-centric raw schema, so it round-trips through
        # score_breakdown_schema.parse_score_breakdown() and reconstructs
        # Overall_Score exactly. The dot-leader display string moves to its
        # own field for UI/report rendering, since that format was never
        # meant to be machine-parsed.
        # PHASE 5 — "Evidence Quality" renamed "Scientific Evidence",
        # backed by Scientific_Evidence_Score (replaces the raw,
        # direction/applicability-blind Evidence_Quality_Score
        # contribution — addendum §8/§1.5). Evidence_Quality_Score
        # itself remains available, unchanged and unsigned, as its own
        # separate authoritative field below.
        score_breakdown_display = _format_breakdown([
            (name, score_breakdown[name], RANKING_COMPONENT_ACTIVE_WEIGHTS[name])
            for name in RANKING_COMPONENT_ACTIVE_WEIGHTS
        ])

        if plant_status == "Excluded":
            explanation_reason = reasons_note or _join(group.get("Scientific_Triage_Reasons", []), 10)
        elif plant_status == "Exploratory" and reasons_note:
            explanation_reason = reasons_note
        else:
            explanation_reason = ""
        why_text = _explain_candidate(
            plant_status, score_components, len(distinctive_compounds), explanation_reason
        )

        # Phase 3 — the three separate, non-collapsed authoritative outputs.
        # R&D_Opportunity_Score is a backward-compatible ALIAS for
        # Overall_Score (same value, legacy field name every existing
        # report/UI/test already reads) — not a second, independently
        # computed number.
        evidence_confidence = _derive_evidence_confidence(
            indication_points, sci_evidence["Scientific_Evidence_Score"]
        )
        go_call = _derive_go_call(
            plant_status,
            overall_score,
            explanation_reason,
            dosage_compatibility=dosage_summary,
            safety_tier=safety_reg_tier,
            outcome_label=str(outcome_profile["label"]),
        )
        decision_class_ah = _derive_decision_class_ah(plant_status, overall_score, explanation_reason)
        commercial_summary = _commercial_summary_fields(group)

        rows.append({
            "Alternative_Plant": plant,
            **commercial_summary,
            "Scientific_Triage_Status": plant_status,
            "Scientific_Triage_Score": round(triage_score, 1),
            "Overall_Score": overall_score,
            "R&D_Opportunity_Score": overall_score,
            "Score_Breakdown": score_breakdown,
            "Score_Breakdown_Display": score_breakdown_display,
            "Evidence_Confidence": evidence_confidence,
            "Decision_Class_AH": decision_class_ah,
            "Go_Investigate_Hold_NoGo": go_call,
            "Indication_Relevance": indication_tier,
            "Indication_Relevance_Score": indication_points,
            "Indication_Evidence_Mode": indication_mode,
            "Indication_Supporting_Source_Count": indication_source_count,
            "Candidate_Specific_Empirical_Row_Count": empirical_rows,
            "Evidence_Quality_Score": evq_points,
            "All_Tier_Evidence_Quality_Diagnostic": {
                "Score": all_tier_evq_points,
                "Tier": all_tier_evq_tier,
            },
            # PHASE 5 — Scientific Score Calibration authoritative outputs
            # (addendum §1/§3/§8). Scientific_Evidence_Score replaces
            # Evidence_Quality_Score inside Overall_Score/Score_Breakdown
            # above; Evidence_Quality_Score itself remains unchanged and
            # unsigned. Scoring_Model_Version identifies which version of
            # phase5_scoring_config.py's weights/thresholds produced this
            # row.
            "Scientific_Evidence_Score": sci_evidence["Scientific_Evidence_Score"],
            "Scientific_Evidence_Contributions": sci_evidence["Scientific_Evidence_Contributions"],
            "Direction_Factor": sci_evidence["Direction_Factor"],
            "Evidence_Consistency_Class": sci_evidence["Evidence_Consistency_Class"],
            "Evidence_Consistency_Factor": sci_evidence["Evidence_Consistency_Factor"],
            "Evidence_Direction_Profile": sci_evidence["Evidence_Direction_Profile"],
            "Plant_Applicability_Factor": sci_evidence["Plant_Applicability_Factor"],
            # Backward-compat alias at plant level, mirroring evaluate_
            # applicability()'s own Applicability_Factor=Record_
            # Applicability_Factor alias (addendum §5).
            "Applicability_Factor": sci_evidence["Plant_Applicability_Factor"],
            "Record_Applicability_Summary": sci_evidence["Record_Applicability_Summary"],
            "Dimension_Status": sci_evidence["Dimension_Status"],
            "Applicability_Classification": sci_evidence["Applicability_Classification"],
            "Applicability_Data_Completeness": sci_evidence["Applicability_Data_Completeness"],
            "Primary_Evidence_Tier": sci_evidence["Primary_Evidence_Tier"],
            "Supporting_Evidence_Tiers_Present": sci_evidence["Supporting_Evidence_Tiers_Present"],
            "Supporting_Evidence_Record_Count": sci_evidence["Supporting_Evidence_Record_Count"],
            "Primary_Tier_Outcome_Profile": sci_evidence["Primary_Tier_Outcome_Profile"],
            "Primary_Tier_Outcome_Label": sci_evidence["Primary_Tier_Outcome_Label"],
            "Scoring_Model_Version": SCORING_MODEL_VERSION,
            "Component_Source_Record_IDs": component_source_record_ids,
            "Authoritative_Source_Record_IDs": authoritative_source_record_ids,
            "Authoritative_Narrative_Source_Record_ID": authoritative_narrative_source_record_id,
            "Authoritative_Narrative_Provenance": authoritative_narrative_provenance,
            # PHASE 3 — additive explainability (brief section 8). New
            # columns only; nothing above/below this line is renamed or
            # removed, and no existing column's value changes because of
            # these. UI/Dashboard are untouched per the brief's explicit
            # scope limit ("UI و Dashboard را تغییر نده").
            "Source_Authority_Distribution": evq_explain["authority_distribution"],
            "Evidence_Quality_Design_Distribution": evq_explain["quality_design_distribution"],
            "Positive_Weighted_Evidence_Contribution": evq_explain["positive_weighted_contribution"],
            "Negative_Weighted_Evidence_Contribution": evq_explain["negative_weighted_contribution"],
            "Null_Weighted_Evidence_Contribution": evq_explain["null_weighted_contribution"],
            "Unknown_Authority_Evidence_Count": evq_explain["unknown_authority_count"],
            "Top_Supporting_Evidence": evq_explain["top_supporting_evidence"],
            "Top_Contradicting_Evidence": evq_explain["top_contradicting_evidence"],
            "Compound_Quality_Score": cq_points,
            "Mechanism_Support_Score": mech_points,
            "Safety_Regulatory_Score": safety_reg_points,
            "Novelty_Market_Score": novelty_points,
            # Stage 5 candidate-funnel performance fix -- tiny additive,
            # backward-compatible fields (no existing field renamed or
            # removed). These let rescore_commercial_component() below
            # regenerate the Go/decision-class/explanation text after a
            # commercial-only update WITHOUT recomputing evidence quality
            # or safety/regulatory from scratch, so market enrichment can
            # never trigger a second full scientific scoring pass.
            "Scientific_Evidence_Tier": evq_tier,
            "Safety_Regulatory_Tier": safety_reg_tier,
            "Reference_Plants": _join(usable.get("Reference_Plant", []), 8),
            "Reference_Plant_Count": len(references),
            "Distinctive_Shared_Compounds": "; ".join(distinctive_compounds[:10]),
            "Distinctive_Compound_Count": len(distinctive_compounds),
            "Supportive_Common_Compounds": "; ".join(supportive_common_compounds[:10]),
            "Supportive_Common_Compound_Count": len(supportive_common_compounds),
            "All_Shared_Compounds": _join(usable.get("Shared_or_Similar_Compound", []), 12),
            "Supported_Targets_or_Mechanisms": "; ".join(_indication_specific_mechanism_values(group, indication, 10)),
            "Supported_Target_Count": len(_indication_specific_mechanism_values(group, indication, 20)),
            "Evidence_Levels": _join(usable.get("Evidence_Level", []), 8),
            "Evidence_Sources": _join(usable.get("Evidence_Source", []), 8),
            "Traceable_Source_Count": len(sources),
            "Dosage_Form_Compatibility": dosage_summary,
            "Outcome_Consistency": outcome_profile["label"],
            "All_Tier_Outcome_Consistency_Diagnostic": all_tier_outcome_profile["label"],
            "Positive_Result_Count": outcome_profile["positive"],
            "Null_Negative_Result_Count": outcome_profile["null"] + outcome_profile["harmful"],
            "Unreported_Result_Count": outcome_profile["unreported"],
            "Safety_Flags": _clean_safety_flags_for_plant(group, plant, 8) or "No explicit adverse event attributable to this plant found",
            "Interaction_Flags": _join(group.get("Interaction_Flags", []), 8) or "No explicit plant-drug interaction attributable to this plant found",
            "Safety_Reassurance": _join(group.get("Safety_Reassurance", []), 8),
            "Safety_Data_Status": _join(group.get("Safety_Data_Status", []), 4) or "not_assessed",
            "Negative_Evidence": _join(group.get("Negative_Evidence_Types", []), 8),
            "Best_Existing_R&D_Score": round(float(pd.to_numeric(group.get("R&D_Opportunity_Score", pd.Series([0])), errors="coerce").fillna(0).max()), 1),
            "Raw_Association_Row_Count": len(group),
            "Shortlist_Row_Count": statuses_count["Shortlist"],
            "Exploratory_Row_Count": statuses_count["Exploratory"],
            "Excluded_Row_Count": statuses_count["Excluded"],
            "Why_Selected_or_Rejected": why_text,
            "Row_Level_Reasons": _join(group.get("Scientific_Triage_Reasons", []), 10),
            "Selected_Indication": indication,
            "Selected_Dosage_Form": dosage_form,
            "Relevance_Gate_Result": relevance_gate_result,
            "Evidence_Route": evidence_route,
            "Direct_Indication_Evidence_Count": direct_evidence_count,
            "Mechanistic_Evidence_Count": mechanistic_evidence_count,
            "Preparation_Specific_Evidence_Count": preparation_specific_evidence_count,
            "Preparation_Applicability_Class": preparation_applicability_class,
            "Triage_Gate_Reasons": triage_gate_reasons,
        })
        _plant_section_add("row_append", time.perf_counter() - _t)

        if _plants_processed % _PLANT_PROGRESS_EVERY == 0:
            _total_plants_estimate = audit["Alternative_Plant"].nunique()
            _print_plant_loop_profile(
                f"{_plants_processed}", f"/~{_total_plants_estimate}"
            )
            _progress(
                _plants_processed, _total_plants_estimate,
                f"Scoring {_plants_processed} / {_total_plants_estimate} plant candidates…",
            )

    _perf(
        f"plant loop done plants_processed={_plants_processed}, output_rows={len(rows)} "
        f"elapsed={time.perf_counter() - _t_grouping_loop:.3f} (cumulative={time.perf_counter() - _t0:.3f})"
    )
    _print_plant_loop_profile("final", f"/~{_plants_processed}")

    summary = pd.DataFrame(rows)
    if summary.empty:
        return summary, audit

    _t = time.perf_counter()
    summary = _prune_near_duplicate_congeners(summary)
    _perf(f"prune_near_duplicate_congeners done rows={len(summary)} elapsed={time.perf_counter() - _t:.3f} (cumulative={time.perf_counter() - _t0:.3f})")

    _t = time.perf_counter()
    status_order = pd.Categorical(
        summary["Scientific_Triage_Status"],
        categories=["Shortlist", "Exploratory", "Excluded"],
        ordered=True,
    )
    summary = summary.assign(_status_order=status_order).sort_values(
        ["_status_order", "Overall_Score", "Traceable_Source_Count", "Distinctive_Compound_Count"],
        ascending=[True, False, False, False],
    ).drop(columns=["_status_order"]).reset_index(drop=True)
    _perf(f"sorting done elapsed={time.perf_counter() - _t:.3f} (cumulative={time.perf_counter() - _t0:.3f})")

    _t = time.perf_counter()
    if max_candidates and max_candidates > 0:
        # Keep all excluded candidates in the audit; cap only the primary
        # plant-centric decision table.
        primary = summary[summary["Scientific_Triage_Status"] != "Excluded"].head(max_candidates)
        excluded = summary[summary["Scientific_Triage_Status"] == "Excluded"]
        summary = pd.concat([primary, excluded], ignore_index=True)
    _perf(f"filtering_cap done rows={len(summary)} elapsed={time.perf_counter() - _t:.3f} (cumulative={time.perf_counter() - _t0:.3f})")

    _perf(f"build_plant_candidate_shortlist done total_elapsed={time.perf_counter() - _t0:.3f} output_rows={len(summary)}")

    return summary, audit


def rescore_commercial_component(
    plant_summary: pd.DataFrame,
    enriched_raw_df: pd.DataFrame,
    plants: Iterable[str],
) -> pd.DataFrame:
    """Update ONLY the Novelty & Market score component for ``plants`` after
    commercial enrichment, reusing every other already-computed scientific
    component -- never a second full ``build_plant_candidate_shortlist()``
    pass.

    Stage 5 candidate-funnel performance fix (see
    STAGE5_CANDIDATE_FUNNEL_ROOT_CAUSE_REPORT.md, part 8/9). Previously,
    Step 5 called ``build_plant_candidate_shortlist()`` a second time on the
    market-enriched subset to fold Commercial_* fields into the score, which
    recomputed indication relevance, scientific evidence, compound quality,
    mechanism support and safety/regulatory from scratch for those same
    plants -- work that had already been done identically in the first
    pass, since none of those five components depend on commercial data.

    ``Overall_Score`` is a fixed linear combination of six raw component
    points (see :func:`ranking_score_model.score_from_breakdown`):
    ``Indication Relevance``, ``Scientific Evidence``, ``Compound Support``,
    ``Mechanism Support``, ``Safety & Regulatory``, ``Novelty & Market``.
    Every one of the first five is already stored verbatim on
    ``plant_summary`` (Indication_Relevance_Score, Scientific_Evidence_Score,
    Compound_Quality_Score, Mechanism_Support_Score, Safety_Regulatory_Score)
    from the single authoritative scoring pass. Only ``Novelty & Market``
    (Novelty_Market_Score) can change from commercial enrichment, so this
    function recomputes ONLY that component -- via the same
    :func:`_novelty_market` the full pass would have called -- and folds it
    back into the existing breakdown with the same
    :func:`ranking_score_model.reweight_score_breakdown` /
    :func:`ranking_score_model.score_from_breakdown` the full pass uses, so
    the result is mathematically identical to what a full re-score would
    have produced for a plant whose scientific evidence did not change.

    A plant not present in ``plant_summary`` or with no rows in
    ``enriched_raw_df`` is left untouched.
    """
    if not isinstance(plant_summary, pd.DataFrame) or plant_summary.empty:
        return plant_summary
    plant_keys = {str(p).strip().lower() for p in (plants or []) if str(p).strip()}
    if not plant_keys:
        return plant_summary
    if not isinstance(enriched_raw_df, pd.DataFrame) or enriched_raw_df.empty:
        return plant_summary
    if "Alternative_Plant" not in enriched_raw_df.columns:
        return plant_summary

    out = plant_summary.copy()
    plant_col = out["Alternative_Plant"].fillna("").astype(str).str.strip()
    raw_by_plant = enriched_raw_df[
        enriched_raw_df["Alternative_Plant"].fillna("").astype(str).str.strip().str.lower().isin(plant_keys)
    ].groupby(
        enriched_raw_df["Alternative_Plant"].fillna("").astype(str).str.strip().str.lower(), sort=False
    )

    _t0 = time.perf_counter()
    updated = 0
    for idx, row in out.iterrows():
        key = str(row.get("Alternative_Plant", "")).strip().lower()
        if key not in plant_keys or key not in raw_by_plant.groups:
            continue
        group = raw_by_plant.get_group(key)
        new_novelty_points, new_novelty_tier = _novelty_market(group)

        raw_score_breakdown = {
            "Indication Relevance": row.get("Indication_Relevance_Score", 0.0),
            "Scientific Evidence": row.get("Scientific_Evidence_Score", 0.0),
            "Compound Support": row.get("Compound_Quality_Score", 0.0),
            "Mechanism Support": row.get("Mechanism_Support_Score", 0.0),
            "Safety & Regulatory": row.get("Safety_Regulatory_Score", 0.0),
            "Novelty & Market": new_novelty_points,
        }
        new_score_breakdown = reweight_score_breakdown(
            raw_score_breakdown, RANKING_COMPONENT_ACTIVE_WEIGHTS
        )
        new_overall_score = score_from_breakdown(
            raw_score_breakdown, RANKING_COMPONENT_ACTIVE_WEIGHTS
        )
        new_score_breakdown_display = _format_breakdown([
            (name, new_score_breakdown[name], RANKING_COMPONENT_ACTIVE_WEIGHTS[name])
            for name in RANKING_COMPONENT_ACTIVE_WEIGHTS
        ])

        status = str(row.get("Scientific_Triage_Status", ""))
        go_call = _derive_go_call(
            status, new_overall_score,
            dosage_compatibility=str(row.get("Dosage_Form_Compatibility", "Unknown")),
            safety_tier=str(row.get("Safety_Regulatory_Tier", "Safety not adequately assessed")),
            outcome_label=str(row.get("Outcome_Consistency", "Results not reported")),
        )
        decision_class_ah = _derive_decision_class_ah(status, new_overall_score)

        score_components = {
            "indication": (row.get("Indication_Relevance_Score", 0.0), str(row.get("Indication_Relevance", ""))),
            "evidence": (row.get("Scientific_Evidence_Score", 0.0), str(row.get("Scientific_Evidence_Tier", ""))),
            "compound": (row.get("Compound_Quality_Score", 0.0), ""),
            "mechanism": (row.get("Mechanism_Support_Score", 0.0), ""),
            "safety": (row.get("Safety_Regulatory_Score", 0.0), str(row.get("Safety_Regulatory_Tier", ""))),
            "novelty": (new_novelty_points, new_novelty_tier),
        }
        why_text = _explain_candidate(
            status, score_components,
            int(row.get("Distinctive_Compound_Count", 0) or 0),
            "" if status != "Excluded" else str(row.get("Why_Selected_or_Rejected", "")),
        )

        out.at[idx, "Novelty_Market_Score"] = new_novelty_points
        out.at[idx, "Overall_Score"] = new_overall_score
        out.at[idx, "R&D_Opportunity_Score"] = new_overall_score
        out.at[idx, "Score_Breakdown"] = new_score_breakdown
        out.at[idx, "Score_Breakdown_Display"] = new_score_breakdown_display
        out.at[idx, "Go_Investigate_Hold_NoGo"] = go_call
        out.at[idx, "Decision_Class_AH"] = decision_class_ah
        out.at[idx, "Why_Selected_or_Rejected"] = why_text
        updated += 1

    _perf(
        f"rescore_commercial_component done plants_updated={updated} "
        f"elapsed={time.perf_counter() - _t0:.3f}"
    )
    return out


def merge_authoritative_scores(raw_df: pd.DataFrame, plant_summary: pd.DataFrame) -> pd.DataFrame:
    """Phase 3 (IMPLEMENTATION_PLAN.md) — the ONE report-ready,
    one-row-per-plant frame that both the final recommendation block and
    the downloaded R&D report are built from.

    WHY THIS EXISTS
    Before Phase 3, three different places independently decided "what is
    this plant's score/ranking": the raw engine's row-level
    R&D_Opportunity_Score (compound-substitution or indication-centric,
    whichever produced raw_df), candidate_shortlisting's own plant-level
    Overall_Score, and step_rd_candidates.py's recommendation block doing
    its own drop_duplicates() over the raw rows sorted by the raw score.
    These could disagree — the report and the on-screen shortlist could
    show different top candidates for the exact same run. This function is
    the single reconciliation point: Overall_Score (plant_summary) is
    authoritative; every raw row's OWN score/classification fields are
    superseded by it here, once, rather than trusted wherever they
    happen to be read downstream.

    WHAT IS KEPT VS. OVERWRITTEN
    For EVERY plant in plant_summary — including Excluded ones, per the
    post-Phase-3-review correction below — the richest available raw row
    (by its OWN pre-Phase-3 score, purely as a tie-breaker for which row
    has the most complete narrative fields — never re-scored) supplies
    every narrative field the raw engine computes that plant_summary does
    NOT (Rationale, Evidence_Strengths, Evidence_Weaknesses,
    Next_Experiment_Suggestion, Gate_Results, Recommendation_Confidence_Statement,
    Competitive_Positioning, etc.). Only the score/classification fields
    are overwritten: R&D_Opportunity_Score, Overall_Score, Score_Breakdown,
    Evidence_Confidence, Decision_Class_AH, Go_Investigate_Hold_NoGo,
    Scientific_Triage_Status, Why_Selected_or_Rejected.

    EXCLUDED PLANTS ARE KEPT, NOT DROPPED (post-Phase-3-review correction)
    An earlier version of this function dropped every Excluded plant
    entirely — but a plant that was screened out and rejected is exactly
    what a reviewer needs to see the reason for, in the same report as
    everything else. Excluded plants stay in this frame, carrying their
    Scientific_Triage_Status="Excluded", a Hold/No-Go call, and their
    Why_Selected_or_Rejected explanation intact. It is the CALLER's job
    (step_rd_candidates.py's recommendation block) to bucket them into a
    "weak / not recommended" section — not this function's job to erase
    them from existence.
    """
    empty = pd.DataFrame()
    if not isinstance(raw_df, pd.DataFrame) or raw_df.empty:
        return empty
    if not isinstance(plant_summary, pd.DataFrame) or plant_summary.empty:
        return empty

    plant_col = "Alternative_Plant"
    if plant_col not in raw_df.columns or plant_col not in plant_summary.columns:
        return empty

    all_plants = plant_summary
    if all_plants.empty:
        return empty

    raw_indexed = raw_df.copy()
    raw_indexed["_raw_rank"] = pd.to_numeric(
        raw_indexed.get("R&D_Opportunity_Score", pd.Series([0] * len(raw_indexed), index=raw_indexed.index)),
        errors="coerce",
    ).fillna(0)
    best_raw_rows = (
        raw_indexed.sort_values("_raw_rank", ascending=False)
        .drop_duplicates(subset=[plant_col], keep="first")
        .drop(columns=["_raw_rank"])
        .set_index(plant_col, drop=False)
    )

    # PHASE 5 (addendum §4/§11) — deterministic narrative-row selection.
    # raw_df rows indexed by their own Source_Record_IDs, per plant, so a
    # plant_summary row's Authoritative_Narrative_Source_Record_ID can be
    # matched to the EXACT raw row it names — not merely any row whose ID
    # intersects a broader set, and not the highest raw, PRE-merge
    # R&D_Opportunity_Score (the confirmed provenance defect this
    # replaces). Falls back to the old best-raw-row selection, per plant,
    # only when no Authoritative_Narrative_Source_Record_ID is available
    # or it does not match any real raw row for that plant — a
    # deterministic, documented fallback, not a silent one.
    raw_by_plant_and_record: dict[tuple[str, str], pd.Series] = {}
    if "Source_Record_IDs" in raw_df.columns:
        for _, r in raw_df.iterrows():
            key = (str(r.get(plant_col, "")), str(r.get("Source_Record_IDs", "")))
            if key not in raw_by_plant_and_record:
                raw_by_plant_and_record[key] = r

    authoritative_fields = (
        "Overall_Score", "Score_Breakdown", "Score_Breakdown_Display",
        "Evidence_Confidence", "Decision_Class_AH", "Go_Investigate_Hold_NoGo",
        "Scientific_Triage_Status", "Why_Selected_or_Rejected",
        # Stage 6 scientific-gating fields.  These are plant-level outputs
        # from build_plant_candidate_shortlist() and must survive the merge
        # into rd_report_ready_df; otherwise the final recommendation layer
        # cannot distinguish direct indication evidence from exploratory
        # mechanism-only hypotheses.  Additive pass-through only: no score
        # or upstream triage logic is changed here.
        "Indication_Relevance", "Indication_Relevance_Score",
        "Indication_Evidence_Mode", "Indication_Supporting_Source_Count",
        "Relevance_Gate_Result", "Evidence_Route",
        "Direct_Indication_Evidence_Count", "Mechanistic_Evidence_Count",
        "Preparation_Specific_Evidence_Count", "Preparation_Applicability_Class",
        "Triage_Gate_Reasons", "Supported_Targets_or_Mechanisms",
        # Plant-level, attribution-cleaned safety fields must override the
        # narrative raw row; otherwise an unrelated/protective or different-
        # species safety sentence can leak back into the final report after
        # being correctly filtered during aggregation.
        "Safety_Flags", "Interaction_Flags", "Safety_Reassurance", "Safety_Data_Status",
        "Evidence_Quality_Score",
        "Compound_Quality_Score", "Mechanism_Support_Score",
        "Safety_Regulatory_Score", "Novelty_Market_Score",
        "Outcome_Consistency", "Positive_Result_Count",
        "Null_Negative_Result_Count", "Unreported_Result_Count",
        # PHASE 5 — authoritative Scientific Score outputs (addendum
        # §1/§3/§4/§11), always taken from plant_summary, never the raw row.
        "Scientific_Evidence_Score", "Scientific_Evidence_Contributions", "Direction_Factor", "Evidence_Consistency_Class",
        "Evidence_Consistency_Factor", "Evidence_Direction_Profile", "Plant_Applicability_Factor",
        "Record_Applicability_Summary", "Dimension_Status", "Applicability_Classification",
        "Applicability_Data_Completeness", "Applicability_Factor", "Primary_Evidence_Tier",
        "Supporting_Evidence_Tiers_Present", "Supporting_Evidence_Record_Count",
        "Primary_Tier_Outcome_Profile", "Primary_Tier_Outcome_Label",
        "All_Tier_Evidence_Quality_Diagnostic", "All_Tier_Outcome_Consistency_Diagnostic",
        "Scoring_Model_Version", "Component_Source_Record_IDs", "Authoritative_Source_Record_IDs",
        "Authoritative_Narrative_Source_Record_ID", "Authoritative_Narrative_Provenance",
        # Controlled AI evidence-adjudication layer (evidence_adjudication_engine.py).
        # Computed by step_rd_candidates.py as a post-processing pass over
        # plant_summary_df, AFTER build_plant_candidate_shortlist() returns and
        # BEFORE this function runs -- see that module's docstring for why it is
        # not called from inside build_plant_candidate_shortlist() itself. Listed
        # here only so these columns survive the merge into the report-ready
        # frame like every other plant-level field; this function does not
        # compute or interpret any of them.
        "Indication_Evidence_Direction", "Human_Evidence_Strength", "Evidence_Conflict_Level",
        "Negative_Evidence_Severity", "Preparation_Compatibility", "Plant_Part_Compatibility",
        "Route_Compatibility", "Scientific_Evidence_Confidence", "Positive_Evidence_IDs",
        "Negative_Evidence_IDs", "Key_Human_Evidence_IDs", "Preparation_Mismatch_Evidence_IDs",
        "Evidence_Adjudication_Status", "Evidence_Adjudication_Evidence_Count",
        "Evidence_Adjudication_Rationale", "Evidence_Adjudication_Fallback_Reason",
        "Evidence_Adjudication_Adjustment",
        "Negative_Human_Evidence_Adjustment", "Preparation_Adjustment", "Plant_Part_Adjustment",
        "Base_R&D_Opportunity_Score", "Final_R&D_Opportunity_Score", "Decision_Cap_Reason",
    )

    merged_rows = []
    for _, plant_row in all_plants.iterrows():
        plant = plant_row[plant_col]
        narrative_record_id = plant_row.get("Authoritative_Narrative_Source_Record_ID")
        base = None
        if narrative_record_id and not pd.isna(narrative_record_id):
            base = raw_by_plant_and_record.get((str(plant), str(narrative_record_id)))
        if base is not None:
            merged = base.to_dict()
        elif plant in best_raw_rows.index:
            # Deterministic, documented fallback (no matching
            # Authoritative_Narrative_Source_Record_ID for this plant —
            # e.g. a legacy caller that never populated it).
            base = best_raw_rows.loc[plant]
            if isinstance(base, pd.DataFrame):
                base = base.iloc[0]
            merged = base.to_dict()
        else:
            # No matching raw row (should not normally happen — every
            # plant_summary row is aggregated FROM raw_df) — build a
            # minimal row rather than fabricating narrative content that
            # was never actually computed for this plant.
            merged = {plant_col: plant}

        for field in authoritative_fields:
            if field in plant_row.index:
                merged[field] = plant_row[field]
        # PHASE 5 — every authoritative row is stamped with the current
        # central Scoring_Model_Version, regardless of whether the
        # caller's plant_summary fixture happened to include it (a
        # single, static value from phase5_scoring_config.py — safe to
        # guarantee unconditionally rather than only pass through).
        merged["Scoring_Model_Version"] = SCORING_MODEL_VERSION
        # Backward-compatible alias — same value as Overall_Score, not a
        # second computation.
        merged["R&D_Opportunity_Score"] = plant_row["Overall_Score"]
        merged_rows.append(merged)

    result = pd.DataFrame(merged_rows)
    result = result.sort_values("Overall_Score", ascending=False).reset_index(drop=True)
    return result
