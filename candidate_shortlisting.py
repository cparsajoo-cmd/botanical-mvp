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
#   Indication Relevance ........ 30 pts   (Target_or_Mechanism, Evidence_Source,
#                                            Applicability_Summary, *_Rationale text)
#   Evidence Quality ............ 25 pts   (Evidence_Level/Hierarchy/GRADE,
#                                            Source_Record_IDs, Reference_Plant)
#   Compound Quality ............ 15 pts   (non-generic Shared_or_Similar_Compound,
#                                            bonus when linked to a supported target)
#   Mechanism/Target Support .... 10 pts   (Supported_Target_or_Mechanism rows)
#   Safety & Regulatory .......... 10 pts   (Hard_Stop_Present, Regulatory_Barriers)
#   Novelty & Market ............. 10 pts   (Novelty_Status, Market_Status)
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
    human = any(term in text for term in ("human", "clinical", "random", "meta-analysis", "systematic review"))
    preclinical = human or any(term in text for term in ("animal", "in vivo", "in vitro", "cell", "preclinical"))
    return human, preclinical


def _concept_family(indication: str) -> dict[str, tuple[str, ...]] | None:
    indication_norm = _norm(indication)
    best = None
    best_hits = 0
    for family in _INDICATION_CONCEPTS.values():
        hits = sum(1 for term in family["triggers"] if term in indication_norm)
        if hits > best_hits:
            best, best_hits = family, hits
    return best


def _indication_relevance(group: pd.DataFrame, indication: str) -> tuple[float, str]:
    """Conservatively score candidate-specific indication evidence.

    Generated narrative fields are excluded, the user-entered indication is
    stripped before matching, and generic antioxidant/anti-inflammatory text
    alone can never establish relevance.
    """
    if not _norm(indication):
        return 15.0, "Not evaluated (no indication specified)"

    blob = _candidate_specific_blob(group, indication)
    if not blob:
        return 0.0, "No relevance"

    family = _concept_family(indication)
    human, preclinical = _evidence_context(group)

    if family:
        direct_hits = _matched_terms(blob, family["direct"])
        mechanism_hits = _matched_terms(blob, family["mechanistic"])
        if direct_hits:
            # High requires a direct indication concept plus human evidence, or
            # multiple direct concepts with at least preclinical support.
            if human or (preclinical and len(direct_hits) >= 2):
                return 30.0, "High relevance"
            return 20.0, "Medium relevance"
        if len(mechanism_hits) >= 2:
            return 20.0, "Medium relevance"
        if len(mechanism_hits) == 1:
            return 10.0, "Low relevance"
        return 0.0, "No relevance"

    # Generic fallback for indications not covered by the small lexicon. Require
    # meaningful multi-token overlap; one broad token is only Low relevance.
    tokens = _indication_tokens(indication)
    hits = [t for t in tokens if re.search(rf"\b{re.escape(t)}\b", blob)]
    if any(term in blob for term in _GENERIC_MECHANISM_ONLY) and not hits:
        return 0.0, "No relevance"
    if len(hits) >= max(2, len(tokens)) and human:
        return 30.0, "High relevance"
    if len(hits) >= 2:
        return 20.0, "Medium relevance"
    if len(hits) == 1:
        return 10.0, "Low relevance"
    return 0.0, "No relevance"

def _evidence_quality(group: pd.DataFrame, sources: list[str], references: list[str]) -> tuple[float, str]:
    level_points = _evidence_points(group) / 30.0 * 15.0
    source_points = min(7.0, 1.4 * len(sources))
    reference_points = min(3.0, 1.5 * len(references))
    total = round(level_points + source_points + reference_points, 1)
    tier = "Strong" if total >= 18 else "Moderate" if total >= 10 else "Weak" if total > 0 else "None"
    return total, tier


def _compound_quality(group: pd.DataFrame, distinctive_compounds: list[str]) -> tuple[float, str]:
    """Score compounds by transparent specificity tiers rather than raw count."""
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

    base = min(11.0, 3.0 * weighted_sum)
    bonus = min(4.0, 0.8 * linked_weight)
    total = round(min(15.0, base + bonus), 1)
    tier = "High" if total >= 11 else "Moderate" if total >= 5 else "Low"
    return total, tier


def _mechanism_support(group: pd.DataFrame) -> tuple[float, str]:
    supported = int(group["Supported_Target_or_Mechanism"].sum())
    total = min(10.0, 2.5 * supported)
    tier = "Strong" if total >= 7.5 else "Some" if total > 0 else "None"
    return total, tier


def _safety_regulatory(group: pd.DataFrame) -> tuple[float, str]:
    if group["Hard_Stop_Present"].any():
        return 0.0, "Hard stop present"
    safety_points = 6.0
    barriers = _norm(_join(group.get("Regulatory_Barriers", []), 5))
    if not barriers or barriers in _MISSING_MARKERS or "none identified" in barriers:
        reg_points = 4.0
        tier = "Clean"
    else:
        reg_points = 1.0
        tier = "Barriers flagged"
    return round(safety_points + reg_points, 1), tier


def _novelty_market(group: pd.DataFrame) -> tuple[float, str]:
    novelty_text = _norm(_join(group.get("Novelty_Status", []), 5))
    market_text = _norm(_join(group.get("Market_Status", []), 5))
    combined = f"{novelty_text} {market_text}"
    if any(t in combined for t in _NOVELTY_HIGH_TERMS):
        return 10.0, "Novel / white-space"
    if any(t in combined for t in _NOVELTY_LOW_TERMS):
        return 2.0, "Saturated / common"
    if combined.strip():
        return 6.0, "Moderate"
    return 5.0, "Not reported"


def _format_breakdown(components: list[tuple[str, float, int]]) -> str:
    lines = []
    for label, points, max_points in components:
        dots = "." * max(3, 26 - len(label))
        lines.append(f"{label} {dots} {points:g}/{max_points}")
    return "\n".join(lines)


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
    if distinctive_count:
        bullets.append(f"{distinctive_count} differentiating shared compound(s)")
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
            summary.loc[i, "Scientific_Triage_Status"] = "Exploratory"
            summary.loc[i, "Overall_Score"] = min(float(row["Overall_Score"]), 74.0)
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
        indication_points, indication_tier = _indication_relevance(group, indication)
        evq_points, evq_tier = _evidence_quality(group, sources, references)
        cq_points, cq_tier = _compound_quality(group, distinctive_compounds)
        mech_points, mech_tier = _mechanism_support(group)
        safety_reg_points, safety_reg_tier = _safety_regulatory(group)
        novelty_points, novelty_tier = _novelty_market(group)

        # An indication was requested but nothing in the collected evidence is
        # specific to it: this candidate is a chemical-similarity artifact for
        # this indication and must not surface as a recommendation, even if it
        # passed the generic per-row gates (Requirement 1 / Requirement 8).
        indication_requested = bool(_norm(indication))
        reasons_note = None
        if indication_requested and plant_status != "Excluded":
            if indication_points == 0.0:
                plant_status = "Excluded"
                reasons_note = "no candidate-specific evidence was found for the requested indication"
            elif indication_points == 10.0:
                plant_status = "Exploratory"
                reasons_note = "only indirect indication-related mechanistic evidence was found"
            elif indication_points >= 20.0 and plant_status == "Exploratory":
                # Relevance cannot repair missing traceability/target gates, but
                # it may keep the candidate exploratory rather than excluded.
                plant_status = "Exploratory"

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
        score_breakdown = _format_breakdown([
            ("Indication Relevance", indication_points, 30),
            ("Evidence Quality", evq_points, 25),
            ("Compound Quality", cq_points, 15),
            ("Mechanism Support", mech_points, 10),
            ("Safety & Regulatory", safety_reg_points, 10),
            ("Novelty & Market", novelty_points, 10),
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

        rows.append({
            "Alternative_Plant": plant,
            "Scientific_Triage_Status": plant_status,
            "Scientific_Triage_Score": round(triage_score, 1),
            "Overall_Score": overall_score,
            "Score_Breakdown": score_breakdown,
            "Indication_Relevance": indication_tier,
            "Indication_Relevance_Score": indication_points,
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
