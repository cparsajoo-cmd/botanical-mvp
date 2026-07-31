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
from collections import Counter
from typing import Iterable

import pandas as pd

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
)

_APPLICABILITY_MISMATCH_TERMS = (
    "mismatch", "not applicable", "incompatible", "wrong dosage",
    "different dosage form", "not direct for selected product",
)


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
        # A specific source ID or human/clinical evidence can override a broad
        # low-information label attached elsewhere on the same row.
        specific_source = not _is_missing(row.get("Source_Record_IDs", ""))
        human_signal = any(
            term in combined
            for term in ("human", "clinical", "random", "meta-analysis", "systematic review")
        )
        return specific_source or human_signal
    return not _is_missing(row.get("Evidence_Source", "")) or not _is_missing(
        row.get("Source_Record_IDs", "")
    )


def _hard_stop(row: pd.Series) -> bool:
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

    raw = row.get("Applicability_Summary", "")
    # Applicability_Summary is normally JSON.  Parse the structured fields so
    # a harmless key such as 'Not applicable': 0 is never mistaken for an
    # actual dosage-form mismatch.
    try:
        payload = json.loads(raw) if isinstance(raw, str) and raw.strip().startswith("{") else {}
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
    if "meta-analysis" in text or "systematic review" in text:
        return 30.0
    if "random" in text or "clinical" in text or "human" in text:
        return 26.0
    if "animal" in text or "in vivo" in text:
        return 18.0
    if "in vitro" in text or "cell" in text:
        return 12.0
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
_INDICATION_CONCEPTS = {
    "glycemic_metabolic": {
        "triggers": (
            "blood sugar", "blood glucose", "glycemic", "glycaemic", "diabetes",
            "diabetic", "hyperglycemia", "hyperglycaemia", "hypoglycemia",
            "hypoglycaemia", "insulin", "metabolic syndrome", "metabolic",
        ),
        "direct": (
            "blood sugar", "blood glucose", "glycemic", "glycaemic", "hba1c",
            "diabetes", "diabetic", "antidiabetic", "anti-diabetic",
            "hyperglycemia", "hyperglycaemia", "hypoglycemic", "hypoglycaemic",
            "glucose tolerance", "insulin resistance", "insulin sensitivity",
            "insulin secretion", "fasting glucose", "postprandial glucose",
        ),
        "mechanistic": (
            "alpha-glucosidase", "α-glucosidase", "alpha glucosidase",
            "alpha-amylase", "α-amylase", "alpha amylase", "glut4", "ampk",
            "aldose-reductase", "aldose reductase", "ppar-gamma", "pparγ",
            "metabolic syndrome", "lipid metabolism", "dyslipidemia",
            "dyslipidaemia", "insulin receptor", "pancreatic beta cell",
            "pancreatic β-cell", "gluconeogenesis", "glycogen synthesis",
        ),
    },
    "sleep_anxiety": {
        "triggers": ("sleep", "insomnia", "anxiety", "anxiolytic", "sedative"),
        "direct": (
            "sleep quality", "sleep latency", "insomnia", "anxiety", "anxiolytic",
            "sedative", "sleep duration", "sleep onset",
        ),
        "mechanistic": ("gaba", "gabaergic", "benzodiazepine receptor", "melatonin"),
    },
    "wound_skin": {
        "triggers": ("wound", "healing", "skin repair", "burn"),
        "direct": ("wound healing", "wound closure", "skin repair", "burn healing"),
        "mechanistic": ("collagen synthesis", "fibroblast", "re-epithelialization", "angiogenesis"),
    },
    "cognition": {
        "triggers": ("cognition", "memory", "alzheimer", "dementia", "neuroprotect"),
        "direct": ("cognitive", "memory", "alzheimer", "dementia"),
        "mechanistic": ("acetylcholinesterase", "ache inhibitor", "neuroprotective", "bdnf"),
    },
    "constipation_digestive": {
        "triggers": ("constipation", "laxative", "bowel", "digestive"),
        "direct": ("constipation", "bowel movement", "stool frequency", "laxative"),
        "mechanistic": ("intestinal motility", "colonic transit", "peristalsis"),
    },
}

_GENERIC_MECHANISM_ONLY = (
    "antioxidant", "anti-oxidant", "anti-inflammatory", "antiinflammatory",
    "nf-kb", "nrf2", "cox-2", "il-6", "tnf-alpha", "free radical",
)

_NOVELTY_HIGH_TERMS = ("novel", "underexplored", "under-explored", "emerging", "white space", "white-space")
_NOVELTY_LOW_TERMS = ("common", "saturated", "well-known", "well known", "widely used", "generic")


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
    indication_norm = _norm(indication)
    best = None
    best_hits = 0
    for family in _INDICATION_CONCEPTS.values():
        hits = sum(1 for term in family["triggers"] if term in indication_norm)
        if hits > best_hits:
            best, best_hits = family, hits
    return best


def _indication_relevance_detail(
    group: pd.DataFrame,
    indication: str,
) -> tuple[float, str, str, int]:
    """Return points, tier, evidence mode, and supporting source count.

    Direct indication language must be supported by candidate-specific evidence.
    Mechanism-only links are deliberately capped and cannot, by themselves,
    create a final Shortlist recommendation.
    """
    if not _norm(indication):
        return 17.5, "Not evaluated (no indication specified)", "Not evaluated", 0

    family = _concept_family(indication)
    if not family:
        blob = _candidate_specific_blob(group, indication)
        tokens = _indication_tokens(indication)
        hits = [t for t in tokens if re.search(rf"\b{re.escape(t)}\b", blob)]
        supported_rows = group[group.apply(_row_has_candidate_specific_empirical_support, axis=1)]
        source_count = len(_split_values(supported_rows.get("Source_Record_IDs", [])))
        if len(hits) >= 2 and source_count >= 2:
            return 25.0, "Medium relevance", "Direct candidate-specific", source_count
        if len(hits) == 1 and source_count >= 1:
            return 10.0, "Low relevance", "Indirect candidate-specific", source_count
        return 0.0, "No relevance", "None", 0

    direct_source_ids: list[str] = []
    mechanism_source_ids: list[str] = []
    direct_hits_all: set[str] = set()
    mechanism_hits_all: set[str] = set()
    inferred_mechanism_hits: set[str] = set()

    for _, row in group.iterrows():
        row_blob = _candidate_specific_blob(pd.DataFrame([row]), indication)
        direct_hits = set(_matched_terms(row_blob, family["direct"]))
        mechanism_hits = set(_matched_terms(row_blob, family["mechanistic"]))
        traceable = _row_has_traceable_source(row)
        empirical = _row_has_candidate_specific_empirical_support(row)

        if direct_hits and traceable and not _row_is_inferred_or_generic(row):
            direct_hits_all.update(direct_hits)
            direct_source_ids.extend(_split_values([row.get("Source_Record_IDs", "")]))
        if mechanism_hits:
            if empirical:
                mechanism_hits_all.update(mechanism_hits)
                mechanism_source_ids.extend(_split_values([row.get("Source_Record_IDs", "")]))
            else:
                inferred_mechanism_hits.update(mechanism_hits)

    direct_sources = len(set(map(_norm, direct_source_ids)))
    mechanism_sources = len(set(map(_norm, mechanism_source_ids)))
    human, preclinical = _evidence_context(group)

    if direct_hits_all:
        if human and direct_sources >= 1:
            return 35.0, "High relevance", "Direct human/clinical", direct_sources
        if preclinical and (direct_sources >= 2 or len(direct_hits_all) >= 2):
            return 27.0, "Medium relevance", "Direct preclinical", direct_sources
        return 22.0, "Medium relevance", "Direct but limited", direct_sources

    if mechanism_hits_all:
        if len(mechanism_hits_all) >= 2 and mechanism_sources >= 2:
            return 18.0, "Low relevance", "Mechanistic empirical", mechanism_sources
        return 12.0, "Low relevance", "Mechanistic empirical", mechanism_sources

    if inferred_mechanism_hits:
        return 6.0, "Low relevance", "Mechanistic inference only", 0

    return 0.0, "No relevance", "None", 0


def _indication_relevance(group: pd.DataFrame, indication: str) -> tuple[float, str]:
    points, tier, _, _ = _indication_relevance_detail(group, indication)
    return points, tier


def _evidence_quality(
    group: pd.DataFrame,
    sources: list[str],
    references: list[str],
) -> tuple[float, str]:
    """Score evidence quality, down-weighting inferred and non-specific rows."""
    empirical = group[group.apply(_row_has_candidate_specific_empirical_support, axis=1)]
    traceable = group[group.apply(_row_has_traceable_source, axis=1)]
    evidence_group = empirical if not empirical.empty else traceable

    if evidence_group.empty:
        return 0.0, "None"

    hierarchy_text = " | ".join(
        _norm(v)
        for col in (
            "Evidence_Level", "Evidence_Hierarchy_Detail",
            "Candidate_Evidence_Strength_Tier", "GRADE_Certainty",
        )
        if col in evidence_group.columns
        for v in evidence_group[col].dropna().tolist()
    )
    if "systematic review" in hierarchy_text or "meta-analysis" in hierarchy_text:
        hierarchy_points = 20.0
    elif any(t in hierarchy_text for t in ("randomized", "randomised", "clinical trial", "human evidence")):
        hierarchy_points = 17.0
    elif any(t in hierarchy_text for t in ("in vivo", "animal", "validated ex vivo")):
        hierarchy_points = 12.0
    elif any(t in hierarchy_text for t in ("in vitro", "cell", "preclinical", "mechanistic")):
        hierarchy_points = 8.0
    elif "analytical chemistry" in hierarchy_text or "occurrence" in hierarchy_text:
        hierarchy_points = 3.0
    else:
        hierarchy_points = 4.0

    empirical_sources = _split_values(empirical.get("Source_Record_IDs", []))
    all_sources = _split_values(traceable.get("Source_Record_IDs", []))
    independent_count = len(set(map(_norm, empirical_sources or all_sources)))
    source_points = min(8.0, 2.5 * independent_count)

    direct_rows = int(empirical.shape[0])
    consistency_points = min(2.0, 0.5 * max(0, direct_rows - 1))
    total = round(min(30.0, hierarchy_points + source_points + consistency_points), 1)

    if total >= 23:
        tier = "Strong"
    elif total >= 15:
        tier = "Moderate"
    elif total > 0:
        tier = "Weak"
    else:
        tier = "None"
    return total, tier


def _compound_quality(group: pd.DataFrame, distinctive_compounds: list[str]) -> tuple[float, str]:
    """Supporting chemistry only; capped at 5% of the 100-point score."""
    best_by_name: dict[str, float] = {}
    linked_weight = 0.0
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


def _mechanism_support(group: pd.DataFrame) -> tuple[float, str]:
    supported = int(group["Supported_Target_or_Mechanism"].sum())
    total = min(10.0, 2.0 * supported)
    tier = "Strong" if total >= 7 else "Some" if total > 0 else "None"
    return total, tier


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


def _safety_regulatory(group: pd.DataFrame) -> tuple[float, str]:
    if _critical_plant_stop(group):
        return 0.0, "Plant-level hard stop"

    # Mixed row-level safety signals reduce confidence but do not erase a
    # scientifically relevant candidate unless they meet the plant-level rule.
    if group["Hard_Stop_Present"].any():
        safety_points = 5.0
        safety_tier = "Mixed safety signals"
    else:
        safety_points = 9.0
        safety_tier = "Clean"

    barriers = _norm(_join(group.get("Regulatory_Barriers", []), 5))
    if not barriers or barriers in _MISSING_MARKERS or "none identified" in barriers:
        reg_points = 6.0
    else:
        reg_points = 2.0
        safety_tier = "Regulatory review needed"
    return round(safety_points + reg_points, 1), safety_tier


def _novelty_market(group: pd.DataFrame) -> tuple[float, str]:
    novelty_text = _norm(_join(group.get("Novelty_Status", []), 5))
    market_text = _norm(_join(group.get("Market_Status", []), 5))
    combined = f"{novelty_text} {market_text}"
    if any(t in combined for t in _NOVELTY_HIGH_TERMS):
        return 5.0, "Novel / white-space"
    if any(t in combined for t in _NOVELTY_LOW_TERMS):
        return 1.0, "Saturated / common"
    if combined.strip():
        return 3.0, "Moderate"
    return 2.5, "Not reported"


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
# The 78-point "Strong/Go" threshold reuses the exact cut point already
# documented in decision_class_ah.py / scoring_sensitivity_report.py for
# the legacy row-level score, instead of inventing a new one.
_STRONG_SCORE_THRESHOLD = 78.0

# Evidence_Confidence's own ceiling: Indication Relevance + Evidence
# Quality's combined maximum in the current weighting (kept as a constant,
# not a hardcoded 55, so it stays correct if either weight ever changes).
_EVIDENCE_CONFIDENCE_MAX_POINTS = 65.0  # Indication Relevance(35) + Evidence Quality(30)


def _derive_evidence_confidence(indication_points: float, evq_points: float) -> float:
    raw = indication_points + evq_points
    return round(min(100.0, max(0.0, raw / _EVIDENCE_CONFIDENCE_MAX_POINTS * 100.0)), 1)


def _derive_go_call(status: str, overall_score: float, reason: str = "") -> str:
    if status == "Excluded":
        return "No-Go" if "safety" in _norm(reason) else "Hold"
    if status == "Exploratory":
        return "Investigate — verify before proceeding"
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
    """Keep one primary shortlisted representative per genus.

    Raw rows remain untouched in the audit/export. Other shortlisted congeners
    are demoted to Exploratory, which prevents a genus with many database rows
    from crowding out taxonomically distinct R&D candidates.
    """
    if summary.empty or "Alternative_Plant" not in summary.columns:
        return summary

    summary = summary.copy()
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
        winner = str(ranked.iloc[0]["Alternative_Plant"])
        for i, row in ranked.iloc[1:].iterrows():
            capped_score = min(float(row["Overall_Score"]), 74.0)
            summary.loc[i, "Scientific_Triage_Status"] = "Exploratory"
            summary.loc[i, "Overall_Score"] = capped_score
            # Phase 3 — Overall_Score is authoritative, so every field derived
            # from it (the R&D_Opportunity_Score alias, and the status/score
            # derived Go/Decision-Class outputs) must be refreshed here too,
            # not left pointing at the pre-demotion values.
            summary.loc[i, "R&D_Opportunity_Score"] = capped_score
            summary.loc[i, "Go_Investigate_Hold_NoGo"] = _derive_go_call("Exploratory", capped_score)
            summary.loc[i, "Decision_Class_AH"] = _derive_decision_class_ah("Exploratory", capped_score)
            note = (
                f"near-duplicate congener of the stronger representative '{winner}' "
                f"within genus {genus.capitalize()}"
            )
            summary.loc[i, "Why_Selected_or_Rejected"] = (
                "Kept for further investigation because: " + note
            )
            summary.loc[i, "Duplicate_Pruning_Note"] = note

    if "Duplicate_Pruning_Note" not in summary.columns:
        summary["Duplicate_Pruning_Note"] = ""
    return summary.drop(columns=["_genus", "_identity_quality"])

def build_plant_candidate_shortlist(
    raw_df: pd.DataFrame,
    *,
    indication: str = "",
    dosage_form: str = "",
    max_candidates: int = 50,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return ``(plant_summary, row_audit)`` for any indication.

    ``plant_summary`` contains one row per Alternative_Plant and is sorted by a
    transparent Scientific_Triage_Score.  ``row_audit`` retains every raw row
    plus its pass/explore/exclude classification and reasons, so no association
    is silently discarded.
    """
    if not isinstance(raw_df, pd.DataFrame) or raw_df.empty:
        return pd.DataFrame(), pd.DataFrame()
    if "Alternative_Plant" not in raw_df.columns:
        return pd.DataFrame(), raw_df.copy()

    audit = raw_df.copy()
    statuses: list[str] = []
    reasons: list[str] = []
    direct_values: list[bool] = []
    target_values: list[bool] = []
    generic_values: list[bool] = []
    dosage_values: list[str] = []
    hard_values: list[bool] = []
    negative_values: list[bool] = []

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

    audit["Scientific_Triage_Status"] = statuses
    audit["Scientific_Triage_Reasons"] = reasons
    audit["Direct_Evidence_Present"] = direct_values
    audit["Supported_Target_or_Mechanism"] = target_values
    audit["Generic_Compound_Only"] = generic_values
    audit["Dosage_Form_Compatibility"] = dosage_values
    audit["Hard_Stop_Present"] = hard_values
    audit["Negative_Evidence_Present"] = negative_values

    rows: list[dict[str, object]] = []
    for plant, group in audit.groupby("Alternative_Plant", sort=False, dropna=False):
        plant = str(plant or "").strip()
        if not plant or plant.lower() == "nan":
            continue

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
        (
            indication_points,
            indication_tier,
            indication_mode,
            indication_source_count,
        ) = _indication_relevance_detail(group, indication)
        evq_points, evq_tier = _evidence_quality(group, sources, references)
        cq_points, cq_tier = _compound_quality(group, distinctive_compounds)
        mech_points, mech_tier = _mechanism_support(group)
        safety_reg_points, safety_reg_tier = _safety_regulatory(group)
        novelty_points, novelty_tier = _novelty_market(group)

        # Final plant-level decision gates. Mechanism similarity is supporting
        # evidence only: it cannot create a Shortlist recommendation without
        # direct candidate-specific indication evidence and adequate evidence
        # quality/traceability.
        indication_requested = bool(_norm(indication))
        reasons_note = None
        base_plant_status = plant_status
        plant_hard_stop = _critical_plant_stop(group)
        empirical_rows = int(group.apply(_row_has_candidate_specific_empirical_support, axis=1).sum())
        traceable_count = len(set(map(_norm, sources)))

        if plant_hard_stop:
            plant_status = "Excluded"
            reasons_note = "a repeated or explicit plant-level safety/regulatory stop is present"
        elif not indication_requested:
            plant_status = base_plant_status
        elif indication_points == 0.0:
            plant_status = "Excluded"
            reasons_note = "no candidate-specific evidence was found for the requested indication"
        elif indication_mode == "Direct human/clinical":
            if evq_points >= 12.0 and empirical_rows >= 1 and traceable_count >= 1:
                plant_status = "Shortlist"
            else:
                plant_status = "Exploratory"
                reasons_note = "direct human relevance is present, but traceability or evidence quality is still limited"
        elif indication_mode in {"Direct preclinical", "Direct but limited", "Direct candidate-specific"}:
            if indication_points >= 22.0 and evq_points >= 10.0 and empirical_rows >= 1 and traceable_count >= 2:
                plant_status = "Shortlist"
            else:
                plant_status = "Exploratory"
                reasons_note = "direct indication relevance is present, but the evidence base is not yet sufficient"
        elif indication_mode == "Mechanistic empirical":
            # A strong, replicated mechanism can justify R&D prioritisation, but
            # only when it is candidate-specific and backed by multiple records.
            if (
                indication_points >= 18.0
                and evq_points >= 18.0
                and empirical_rows >= 2
                and traceable_count >= 2
            ):
                plant_status = "Shortlist"
            else:
                plant_status = "Exploratory"
                reasons_note = "the indication link is mechanistic and does not yet meet the replicated-evidence gate"
        else:
            plant_status = "Exploratory"
            reasons_note = "only weak, indirect, or inferred indication relevance was found"

        if safety_reg_points <= 0.0:
            plant_status = "Excluded"
            reasons_note = "safety/regulatory screening did not pass at plant level"

        overall_score = round(
            indication_points + evq_points + cq_points + mech_points
            + safety_reg_points + novelty_points,
            1,
        )

        score_components = {
            "indication": (indication_points, indication_tier),
            "evidence": (evq_points, evq_tier),
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
        score_breakdown = {
            "Indication Relevance": indication_points,
            "Evidence Quality": evq_points,
            "Compound Support": cq_points,
            "Mechanism Support": mech_points,
            "Safety & Regulatory": safety_reg_points,
            "Novelty & Market": novelty_points,
        }
        score_breakdown_display = _format_breakdown([
            ("Indication Relevance", indication_points, 35),
            ("Evidence Quality", evq_points, 30),
            ("Compound Support", cq_points, 5),
            ("Mechanism Support", mech_points, 10),
            ("Safety & Regulatory", safety_reg_points, 15),
            ("Novelty & Market", novelty_points, 5),
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
        evidence_confidence = _derive_evidence_confidence(indication_points, evq_points)
        go_call = _derive_go_call(plant_status, overall_score, explanation_reason)
        decision_class_ah = _derive_decision_class_ah(plant_status, overall_score, explanation_reason)

        rows.append({
            "Alternative_Plant": plant,
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
            "Compound_Quality_Score": cq_points,
            "Mechanism_Support_Score": mech_points,
            "Safety_Regulatory_Score": safety_reg_points,
            "Novelty_Market_Score": novelty_points,
            "Reference_Plants": _join(usable.get("Reference_Plant", []), 8),
            "Reference_Plant_Count": len(references),
            "Distinctive_Shared_Compounds": "; ".join(distinctive_compounds[:10]),
            "Distinctive_Compound_Count": len(distinctive_compounds),
            "Supportive_Common_Compounds": "; ".join(supportive_common_compounds[:10]),
            "Supportive_Common_Compound_Count": len(supportive_common_compounds),
            "All_Shared_Compounds": _join(usable.get("Shared_or_Similar_Compound", []), 12),
            "Supported_Targets_or_Mechanisms": _join(usable.get("Target_or_Mechanism", []), 10),
            "Supported_Target_Count": len(targets),
            "Evidence_Levels": _join(usable.get("Evidence_Level", []), 8),
            "Evidence_Sources": _join(usable.get("Evidence_Source", []), 8),
            "Traceable_Source_Count": len(sources),
            "Dosage_Form_Compatibility": (
                "Compatible" if "Compatible" in dosage_statuses
                else "Mismatch" if dosage_statuses == {"Mismatch"}
                else "Unknown"
            ),
            "Safety_Flags": _join(group.get("Safety_Flags", []), 8) or "No explicit flag found",
            "Interaction_Flags": _join(group.get("Interaction_Flags", []), 8) or "No explicit flag found",
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
        })

    summary = pd.DataFrame(rows)
    if summary.empty:
        return summary, audit

    summary = _prune_near_duplicate_congeners(summary)

    status_order = pd.Categorical(
        summary["Scientific_Triage_Status"],
        categories=["Shortlist", "Exploratory", "Excluded"],
        ordered=True,
    )
    summary = summary.assign(_status_order=status_order).sort_values(
        ["_status_order", "Overall_Score", "Traceable_Source_Count", "Distinctive_Compound_Count"],
        ascending=[True, False, False, False],
    ).drop(columns=["_status_order"]).reset_index(drop=True)

    if max_candidates and max_candidates > 0:
        # Keep all excluded candidates in the audit; cap only the primary
        # plant-centric decision table.
        primary = summary[summary["Scientific_Triage_Status"] != "Excluded"].head(max_candidates)
        excluded = summary[summary["Scientific_Triage_Status"] == "Excluded"]
        summary = pd.concat([primary, excluded], ignore_index=True)

    return summary, audit


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

    authoritative_fields = (
        "Overall_Score", "Score_Breakdown", "Score_Breakdown_Display",
        "Evidence_Confidence", "Decision_Class_AH", "Go_Investigate_Hold_NoGo",
        "Scientific_Triage_Status", "Why_Selected_or_Rejected",
    )

    merged_rows = []
    for _, plant_row in all_plants.iterrows():
        plant = plant_row[plant_col]
        if plant in best_raw_rows.index:
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
        # Backward-compatible alias — same value as Overall_Score, not a
        # second computation.
        merged["R&D_Opportunity_Score"] = plant_row["Overall_Score"]
        merged_rows.append(merged)

    result = pd.DataFrame(merged_rows)
    result = result.sort_values("Overall_Score", ascending=False).reset_index(drop=True)
    return result
