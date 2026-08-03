"""General candidate merge / dedupe / rank / select pipeline.

This module is deliberately indication-agnostic: nothing in it knows what a
"sleep" or "diabetes" candidate is. It only knows how to merge candidates
that arrive tagged with an *origin* and an *evidence status*, deduplicate
them by canonical plant name, rank them, and select up to a requested count
-- recording exactly why any shortfall remains.

ORIGINS (where a candidate came from)
    validated_literature  - passed live literature/regulatory validation for
                             THIS indication (see research_engine.py)
    reference_seed        - platform reference/database plant, not yet
                             validated for this indication
    candidate_hypothesis  - a search hypothesis (e.g. from
                             therapeutic_area_registry.py); never evidence
    ranked_fallback       - globally ranked catalogue candidate

EVIDENCE STATUSES (what we're actually allowed to claim about a candidate)
    validated_direct      - direct literature/regulatory support found for
                             this plant AND this indication
    validated_indirect     - literature support found, but weaker (no
                             clinical/systematic-review signal)
    pending_validation     - has not yet been checked against literature for
                             this indication; MUST NOT be called
                             "evidence-backed"
    fallback_hypothesis     - has no indication-specific support at all; pure
                             discovery/ranking hypothesis

A dedupe merge NEVER upgrades a candidate past what its best contributing
origin actually earned -- appearing in a reference_seed list and a
candidate_hypothesis list at the same time does not, by itself, create
validated evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from general_indication_relevance import normalize_text as _norm
import botanical_taxonomy as _taxonomy


# --- Origins ----------------------------------------------------------------
ORIGIN_VALIDATED_LITERATURE = "validated_literature"
ORIGIN_REFERENCE_SEED = "reference_seed"
ORIGIN_CANDIDATE_HYPOTHESIS = "candidate_hypothesis"
ORIGIN_RANKED_FALLBACK = "ranked_fallback"

ALL_ORIGINS = (
    ORIGIN_VALIDATED_LITERATURE,
    ORIGIN_REFERENCE_SEED,
    ORIGIN_CANDIDATE_HYPOTHESIS,
    ORIGIN_RANKED_FALLBACK,
)

# --- Evidence statuses --------------------------------------------------------
STATUS_VALIDATED_DIRECT = "validated_direct"
STATUS_VALIDATED_INDIRECT = "validated_indirect"
STATUS_PENDING_VALIDATION = "pending_validation"
STATUS_FALLBACK_HYPOTHESIS = "fallback_hypothesis"

_ORIGIN_DEFAULT_STATUS = {
    ORIGIN_VALIDATED_LITERATURE: STATUS_VALIDATED_INDIRECT,
    ORIGIN_REFERENCE_SEED: STATUS_PENDING_VALIDATION,
    ORIGIN_CANDIDATE_HYPOTHESIS: STATUS_PENDING_VALIDATION,
    ORIGIN_RANKED_FALLBACK: STATUS_FALLBACK_HYPOTHESIS,
}

# Base score contribution by origin. Deliberately modest relative to the
# score components callers attach for real evidence signals (supporting
# records, clinical/systematic-review counts, etc.) -- origin alone should
# never dominate a strong evidence-based score from a weaker-origin plant.
_ORIGIN_BASE_WEIGHT = {
    ORIGIN_VALIDATED_LITERATURE: 20.0,
    ORIGIN_REFERENCE_SEED: 8.0,
    ORIGIN_CANDIDATE_HYPOTHESIS: 2.0,
    ORIGIN_RANKED_FALLBACK: 5.0,
}

_STATUS_RANK = {
    STATUS_VALIDATED_DIRECT: 4,
    STATUS_VALIDATED_INDIRECT: 3,
    STATUS_PENDING_VALIDATION: 2,
    STATUS_FALLBACK_HYPOTHESIS: 1,
}

# --- Controlled shortfall_reason vocabulary ----------------------------------
SHORTFALL_NONE = "none"
SHORTFALL_INSUFFICIENT_HYPOTHESES = "insufficient_candidate_hypotheses"
SHORTFALL_NO_VALIDATED_LITERATURE = "no_validated_literature_candidates"
SHORTFALL_CATALOGUE_COVERAGE_GAP = "catalogue_coverage_gap"
SHORTFALL_CONNECTOR_FAILURE = "connector_failure"
SHORTFALL_QUALITY_THRESHOLD_NOT_MET = "quality_threshold_not_met"
SHORTFALL_DEDUPLICATION_REDUCED_COUNT = "deduplication_reduced_count"


def canonicalize_plant_name(name: object, alias_lookup: Optional[dict] = None) -> str:
    """Canonicalize a plant name string.

    Two steps:
    1. ``alias_lookup`` is an optional ``{normalized_alias: canonical_name}``
       mapping (e.g. built from the platform's plants table); when a match
       is found, that canonical name is used as the starting point.
    2. The result is then resolved through botanical_taxonomy.py's
       taxonomic synonym mapping (e.g. Cimicifuga racemosa -> Actaea
       racemosa), so deduplication always uses the ACCEPTED scientific
       name regardless of which synonym any individual origin submitted.
       This runs even when ``alias_lookup`` found nothing, so a raw
       taxonomic synonym is still canonicalized on its own.

    An input with no match anywhere is trimmed and returned as-is.
    """
    raw = str(name or "").strip()
    if not raw:
        return ""
    candidate = raw
    if alias_lookup:
        mapped = alias_lookup.get(_norm(raw))
        if mapped:
            candidate = str(mapped).strip()
    return _taxonomy.accepted_name(candidate)


@dataclass
class CandidateRecord:
    name: str
    origin: str
    evidence_status: str = ""
    score: float = 0.0
    score_components: dict = field(default_factory=dict)
    sources: Tuple[str, ...] = ()
    notes: str = ""
    # The name as originally submitted, before alias/taxonomic
    # canonicalization -- preserved so a synonym collapse (e.g. Cimicifuga
    # racemosa -> Actaea racemosa) never loses which original name each
    # contributing origin actually used. See merge_candidates().
    submitted_name: str = ""

    def __post_init__(self) -> None:
        if not self.evidence_status:
            self.evidence_status = _ORIGIN_DEFAULT_STATUS.get(
                self.origin, STATUS_PENDING_VALIDATION
            )
        if not self.submitted_name:
            self.submitted_name = self.name


def make_candidate(
    name: object,
    origin: str,
    score: float = 0.0,
    score_components: Optional[dict] = None,
    sources: Sequence[str] = (),
    evidence_status: Optional[str] = None,
    notes: str = "",
    alias_lookup: Optional[dict] = None,
) -> Optional[CandidateRecord]:
    """Build one CandidateRecord. Returns None for an empty/unusable name."""
    raw = str(name or "").strip()
    canonical = canonicalize_plant_name(name, alias_lookup)
    if not canonical:
        return None
    base_weight = _ORIGIN_BASE_WEIGHT.get(origin, 0.0)
    return CandidateRecord(
        name=canonical,
        origin=origin,
        evidence_status=evidence_status or _ORIGIN_DEFAULT_STATUS.get(origin, STATUS_PENDING_VALIDATION),
        score=round(base_weight + float(score or 0.0), 4),
        score_components=dict(score_components or {}),
        sources=tuple(sources or ()),
        notes=notes,
        submitted_name=raw,
    )


def _count_by_origin(records: Iterable[CandidateRecord]) -> Dict[str, int]:
    counts = {origin: 0 for origin in ALL_ORIGINS}
    for record in records:
        counts[record.origin] = counts.get(record.origin, 0) + 1
    return counts


def merge_candidates(candidates: Iterable[Optional[CandidateRecord]]) -> List[CandidateRecord]:
    """Deduplicate candidates by canonical (normalized) plant name.

    The strongest contributing evidence_status/score wins; other origins
    that also proposed the same plant are preserved as provenance and add a
    small, capped corroboration bonus -- never enough on their own to
    manufacture a validated status a plant did not actually earn.
    Deterministic: ties are broken by plant name.
    """
    grouped: Dict[str, List[CandidateRecord]] = {}
    order: List[str] = []
    for record in candidates:
        if record is None or not record.name:
            continue
        key = _norm(record.name)
        if not key:
            continue
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(record)

    merged: List[CandidateRecord] = []
    for key in order:
        group = sorted(
            grouped[key],
            key=lambda r: (-_STATUS_RANK.get(r.evidence_status, 0), -r.score, r.origin),
        )
        best = group[0]
        contributing_origins = sorted({r.origin for r in group})
        contributing_original_names = sorted({r.submitted_name for r in group if r.submitted_name})
        all_sources = tuple(dict.fromkeys(s for r in group for s in r.sources))
        combined_score = best.score
        if len(contributing_origins) > 1:
            combined_score += min(3.0, (len(contributing_origins) - 1) * 1.5)
        merged_components = dict(best.score_components)
        merged_components["contributing_origins"] = contributing_origins
        merged_components["contributing_original_names"] = contributing_original_names
        merged.append(CandidateRecord(
            name=best.name,
            origin=best.origin,
            evidence_status=best.evidence_status,
            score=round(combined_score, 4),
            score_components=merged_components,
            sources=all_sources,
            notes=best.notes,
            submitted_name=best.submitted_name,
        ))

    merged.sort(key=lambda r: (-_STATUS_RANK.get(r.evidence_status, 0), -r.score, r.name.lower()))
    return merged


def _shortfall_reason(
    requested_count: int,
    raw_candidates: List[CandidateRecord],
    deduped: List[CandidateRecord],
    connector_failure: bool,
) -> str:
    if not raw_candidates:
        return SHORTFALL_INSUFFICIENT_HYPOTHESES
    if connector_failure:
        return SHORTFALL_CONNECTOR_FAILURE
    counts = _count_by_origin(raw_candidates)
    if counts.get(ORIGIN_VALIDATED_LITERATURE, 0) == 0:
        return SHORTFALL_NO_VALIDATED_LITERATURE
    if len(deduped) < len(raw_candidates) and len(deduped) < requested_count:
        return SHORTFALL_DEDUPLICATION_REDUCED_COUNT
    if counts.get(ORIGIN_CANDIDATE_HYPOTHESIS, 0) == 0 and counts.get(ORIGIN_RANKED_FALLBACK, 0) == 0:
        return SHORTFALL_INSUFFICIENT_HYPOTHESES
    return SHORTFALL_CATALOGUE_COVERAGE_GAP


def select_candidates(
    candidates: Iterable[Optional[CandidateRecord]],
    requested_count: int,
    connector_failure: bool = False,
) -> Tuple[List[CandidateRecord], dict]:
    """Merge, rank and select up to ``requested_count`` candidates.

    Selection uses SOFT source-diversity: each already-selected origin
    receives a small, decaying bonus penalty for being picked again, so a
    strong single-origin pool is never blocked from filling the shortlist,
    but a shortlist that could draw from more than one origin tends to.
    This is a preference, not a hard per-origin quota.
    """
    requested_count = max(0, int(requested_count or 0))
    raw_candidates = [c for c in candidates if c is not None and c.name]
    deduped = merge_candidates(raw_candidates)

    remaining = list(deduped)
    selected: List[CandidateRecord] = []
    origin_counts: Dict[str, int] = {}

    while remaining and len(selected) < requested_count:
        def _selection_key(record: CandidateRecord):
            diversity_bonus = 2.0 / (1.0 + origin_counts.get(record.origin, 0))
            return (
                -_STATUS_RANK.get(record.evidence_status, 0),
                -(record.score + diversity_bonus),
                record.name.lower(),
            )
        remaining.sort(key=_selection_key)
        chosen = remaining.pop(0)
        selected.append(chosen)
        origin_counts[chosen.origin] = origin_counts.get(chosen.origin, 0) + 1

    rejected = remaining
    shortfall = max(0, requested_count - len(selected))
    reason = SHORTFALL_NONE
    if shortfall:
        reason = _shortfall_reason(requested_count, raw_candidates, deduped, connector_failure)

    raw_counts = _count_by_origin(raw_candidates)
    diagnostics = {
        "requested_candidate_count": requested_count,
        "available_reference_seed_count": raw_counts.get(ORIGIN_REFERENCE_SEED, 0),
        "validated_literature_count": raw_counts.get(ORIGIN_VALIDATED_LITERATURE, 0),
        "candidate_hypothesis_count": raw_counts.get(ORIGIN_CANDIDATE_HYPOTHESIS, 0),
        "ranked_fallback_count": raw_counts.get(ORIGIN_RANKED_FALLBACK, 0),
        "deduplicated_candidate_count": len(deduped),
        "selected_candidate_count": len(selected),
        "candidate_shortfall": shortfall,
        "shortfall_reason": reason,
        "rejected_candidates": [r.name for r in rejected],
        "rejection_reasons": [
            {"name": r.name, "origin": r.origin, "evidence_status": r.evidence_status, "score": r.score}
            for r in rejected
        ],
        "candidate_provenance": {
            r.name: {
                "origin": r.origin,
                "evidence_status": r.evidence_status,
                "sources": list(r.sources),
                "contributing_origins": r.score_components.get("contributing_origins", [r.origin]),
                "contributing_original_names": r.score_components.get(
                    "contributing_original_names", [r.submitted_name]
                ),
            }
            for r in deduped
        },
        "selection_score_components": {r.name: r.score_components for r in selected},
    }
    return selected, diagnostics
