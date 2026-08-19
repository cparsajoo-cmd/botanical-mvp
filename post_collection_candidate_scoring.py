"""Generic post-collection candidate evidence scoring.

This module deliberately contains no indication-specific vocabulary.  It scores
only the candidates that were actually sent through Step 2, using the evidence
returned by that same collection run.

The resulting 0-100 score is an *evidence maturity / retrieval support* score.
It is not an efficacy probability and it does not reward positive outcomes or
penalize adverse findings. Safety direction and GO/NO-GO logic remain the
responsibility of the downstream decision engine.
"""
from __future__ import annotations

import math
from typing import Iterable, Mapping

from evidence_quality_engine import assess_evidence_quality
from general_indication_relevance import build_indication_profile, score_record_relevance
from source_registry import get_source_config


_COVERAGE_SCORE = {
    "COMPLETE": 100.0,
    "COMPLETE_WITH_LIMITATIONS": 80.0,
    "INCOMPLETE": 35.0,
    "NOT_ASSESSABLE": 0.0,
}


def _txt(value: object) -> str:
    return "" if value is None else str(value).strip()


def _norm(value: object) -> str:
    return " ".join(_txt(value).lower().split())


def _unwrap(item: Mapping) -> dict:
    record = item.get("record") if isinstance(item, Mapping) else None
    return dict(record or item or {})


def _source_name(item: Mapping, record: Mapping) -> str:
    return _txt(
        item.get("source")
        or record.get("Source_Type")
        or record.get("source")
    )


def _record_key(item: Mapping, record: Mapping) -> tuple:
    """Stable dedupe key across connector wrappers and standardized rows."""
    identifiers = (
        record.get("PMID"), record.get("pmid"), item.get("pmid"),
        record.get("DOI"), record.get("doi"),
        record.get("NCT_ID"), record.get("nct_id"), item.get("nct_id"),
        record.get("Source_URL"), record.get("source_url"),
    )
    identifier = next((_norm(v) for v in identifiers if _norm(v)), "")
    if identifier:
        return ("id", identifier)
    title = _norm(record.get("Source_Title") or record.get("Title") or item.get("title"))
    return ("title", _norm(_source_name(item, record)), title)


def _record_text(record: Mapping) -> str:
    fields = (
        "Target_Indication", "Extracted_Indication", "Target_Indication_Detected",
        "Primary_Outcome", "Result_Direction", "Mechanism", "Target",
        "Source_Title", "Title", "Abstract", "Notes", "Raw_Text", "Evidence_Text",
        "Study_Type", "Evidence_Type",
    )
    return ". ".join(_txt(record.get(field)) for field in fields if _txt(record.get(field)))


def _relevance_parts(record: Mapping) -> tuple[str, str, str]:
    tier1 = " ".join(_txt(record.get(k)) for k in (
        "Target_Indication", "Extracted_Indication", "Target_Indication_Detected"
    ))
    tier2 = " ".join(_txt(record.get(k)) for k in (
        "Primary_Outcome", "Result_Direction", "Mechanism", "Target"
    ))
    tier3 = " ".join(_txt(record.get(k)) for k in (
        "Source_Title", "Title", "Abstract", "Notes", "Raw_Text", "Evidence_Text",
        "Study_Type", "Evidence_Type"
    ))
    return tier1, tier2, tier3


def _authority_score(source_name: str, record: Mapping) -> float:
    # Standardized records may already carry a 0-1 authority score.  Prefer it
    # when present, otherwise fall back to the central source registry.
    for key in ("Source_Authority_Score", "source_authority_score", "Source_Authority_Weight"):
        try:
            value = float(record.get(key))
            if value > 0:
                return max(0.0, min(100.0, value * 100.0 if value <= 1.0 else value))
        except (TypeError, ValueError):
            pass
    config = get_source_config(source_name) or {}
    try:
        return max(0.0, min(100.0, float(config.get("authority_weight", 0.5)) * 100.0))
    except (TypeError, ValueError):
        return 50.0


def _domain(source_name: str, item: Mapping, record: Mapping) -> str:
    category = _norm(item.get("category") or record.get("Source_Category"))
    source = _norm(source_name)
    text = f"{category} {source}"
    if "clinical" in text:
        return "clinical"
    if "regulatory" in text or "label" in text:
        return "regulatory"
    if any(x in text for x in ("safety", "pharmacovigilance", "livertox", "faers", "dailymed")):
        return "safety"
    if any(x in text for x in ("chemistry", "chemical", "mechanism", "bioactivity", "pubchem", "chembl", "chebi")):
        return "mechanism_chemistry"
    if "patent" in text or "commercial" in text:
        return "patent_commercial"
    return "scientific_literature"


def _quality_score(record: Mapping) -> float:
    # Use the repository's direction-neutral study-quality engine.  It does
    # not make positive/negative outcome wording alter methodological quality.
    try:
        existing = record.get("Evidence_Quality_Score")
        if existing not in (None, ""):
            return max(0.0, min(100.0, float(existing)))
    except (TypeError, ValueError):
        pass
    try:
        return float(assess_evidence_quality(dict(record))["Evidence_Quality_Score"])
    except Exception:
        return 0.0


def score_candidate_collection(
    saved_records: Iterable[Mapping],
    *,
    indication: str,
    coverage: Mapping | None = None,
) -> dict:
    """Return a transparent 0-100 post-collection score for one candidate."""
    unique = []
    seen = set()
    for item in saved_records or []:
        item = dict(item or {})
        record = _unwrap(item)
        key = _record_key(item, record)
        if key in seen:
            continue
        seen.add(key)
        unique.append((item, record))

    if not unique:
        cov_status = _txt((coverage or {}).get("status")) or "NOT_ASSESSABLE"
        return {
            "score": 0.0,
            "record_count": 0,
            "unique_source_count": 0,
            "domain_count": 0,
            "directly_relevant_records": 0,
            "relevance_score": 0.0,
            "methodological_quality_score": 0.0,
            "source_authority_score": 0.0,
            "source_diversity_score": 0.0,
            "evidence_volume_score": 0.0,
            "retrieval_coverage_score": _COVERAGE_SCORE.get(cov_status, 0.0),
            "coverage_status": cov_status,
            "interpretation": "No unique evidence records were returned in this Step 2 collection run.",
        }

    corpus = [_record_text(record) for _, record in unique]
    profile = build_indication_profile(indication, corpus)

    relevance_values = []
    quality_values = []
    authority_values = []
    sources = set()
    domains = set()
    direct_relevant = 0

    for item, record in unique:
        source = _source_name(item, record)
        if source:
            sources.add(source)
        domain = _domain(source, item, record)
        domains.add(domain)
        authority_values.append(_authority_score(source, record))

        # Methodological quality is meaningful primarily for literature and
        # clinical records. Regulatory/safety/chemistry documents contribute
        # through authority and domain breadth instead of being mis-scored as
        # poor clinical studies simply because they are not trials.
        if domain in {"scientific_literature", "clinical"}:
            quality_values.append(_quality_score(record))
            t1, t2, t3 = _relevance_parts(record)
            rel = score_record_relevance(profile, t1, t2, t3)
            rel_pct = max(0.0, min(100.0, float(rel.score) * 100.0))
            relevance_values.append(rel_pct)
            if rel.score >= 0.50:
                direct_relevant += 1

    # Use the strongest relevant scientific records rather than diluting an
    # indication score with generic safety or chemistry documents. Diminishing
    # returns prevent a large pile of near-duplicate publications from winning
    # on count alone.
    top_relevance = sorted(relevance_values, reverse=True)[:8]
    relevance_score = sum(top_relevance) / len(top_relevance) if top_relevance else 0.0

    nonzero_quality = sorted((q for q in quality_values if q > 0), reverse=True)[:8]
    methodological_quality = (
        sum(nonzero_quality) / len(nonzero_quality) if nonzero_quality else 0.0
    )

    authority_score = sum(authority_values) / len(authority_values) if authority_values else 0.0
    source_diversity = min(100.0, len(sources) / 6.0 * 100.0)
    domain_breadth = min(100.0, len(domains) / 5.0 * 100.0)
    # Combine source diversity and domain breadth so six literature mirrors do
    # not look as mature as genuinely multi-domain evidence.
    diversity_score = 0.55 * source_diversity + 0.45 * domain_breadth

    # 12 unique records is enough to saturate the volume component in a quick
    # exploratory run; extra records still matter elsewhere but do not linearly
    # inflate this score.
    volume_score = min(100.0, 100.0 * math.log1p(len(unique)) / math.log1p(12.0))

    cov_status = _txt((coverage or {}).get("status")) or "NOT_ASSESSABLE"
    coverage_score = _COVERAGE_SCORE.get(cov_status, 0.0)

    final = (
        0.25 * relevance_score
        + 0.25 * methodological_quality
        + 0.15 * authority_score
        + 0.15 * diversity_score
        + 0.10 * volume_score
        + 0.10 * coverage_score
    )

    return {
        "score": round(max(0.0, min(100.0, final)), 1),
        "record_count": len(unique),
        "unique_source_count": len(sources),
        "domain_count": len(domains),
        "directly_relevant_records": direct_relevant,
        "relevance_score": round(relevance_score, 1),
        "methodological_quality_score": round(methodological_quality, 1),
        "source_authority_score": round(authority_score, 1),
        "source_diversity_score": round(diversity_score, 1),
        "evidence_volume_score": round(volume_score, 1),
        "retrieval_coverage_score": round(coverage_score, 1),
        "coverage_status": cov_status,
        "interpretation": (
            "0-100 evidence maturity score derived from this Step 2 run. "
            "It measures indication relevance, methodological quality, source authority, "
            "cross-domain breadth, record volume and retrieval coverage; it is not an efficacy probability."
        ),
    }


def score_collected_candidates(
    plant_collection_results: Mapping[str, Mapping],
    *,
    indication: str,
    coverage_by_plant: Mapping[str, Mapping] | None = None,
) -> dict[str, dict]:
    """Score every collected plant using the same indication-agnostic logic."""
    out = {}
    for plant, result in (plant_collection_results or {}).items():
        out[plant] = score_candidate_collection(
            (result or {}).get("saved_records") or [],
            indication=indication,
            coverage=(coverage_by_plant or {}).get(plant) or {},
        )
    return out
