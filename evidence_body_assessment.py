"""Structured body-of-evidence assessment for final scientific decisions.

This module intentionally separates:
1) WHAT the evidence says (direction), from
2) HOW CERTAIN the body of evidence is (certainty/limitations/coverage).

It does not contain plant names, PMIDs, indication-specific thresholds, or
benchmark labels.  It operates on structured evidence-record fields plus two
generic semantic callbacks supplied by final_decision_policy.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Iterable, Mapping


class BodyDirection(str, Enum):
    SUPPORTIVE = "supportive"
    NULL_OR_NEGATIVE = "null_or_negative"
    MIXED = "mixed"
    UNRESOLVED = "unresolved"


class BodyCertainty(str, Enum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    VERY_LOW = "very_low"
    NOT_ASSESSABLE = "not_assessable"


@dataclass(frozen=True)
class EvidenceBodyAssessment:
    direction: BodyDirection
    certainty: BodyCertainty
    governing_source_types: tuple[str, ...]
    governing_directions: tuple[str, ...]
    governing_source_count: int
    total_source_count: int
    limitation_count: int
    newest_governing_year: int | None
    has_newer_contradiction: bool
    has_explicit_conflict: bool
    reason: str


_SOURCE_RANK = {
    "SYSTEMATIC_REVIEW": 0,
    "META_ANALYSIS": 0,
    "SYSTEMATIC_REVIEW_META_ANALYSIS": 0,
    "EMA_HMPC": 1,
    "WHO_MONOGRAPH": 2,
    "ESCOP_MONOGRAPH": 3,
    "COMMISSION_E": 4,
    "REGULATORY_MONOGRAPH": 4,
    "CLINICAL_TRIAL": 5,
    "RANDOMIZED_CONTROLLED_TRIAL": 5,
    "RANDOMISED_CONTROLLED_TRIAL": 5,
    "RCT": 5,
    "OBSERVATIONAL": 6,
    "COHORT": 6,
}


def _norm_source_type(rec: Mapping) -> str:
    source = str(rec.get("source_type") or "").strip().upper().replace("-", "_").replace(" ", "_")
    design = str(rec.get("study_design") or "").strip().lower()
    text = str(rec.get("assertion_text") or rec.get("text") or "").strip().lower()
    design_signal = f"{design} {text}"
    if "systematic review" in design_signal or "meta-analysis" in design_signal or "meta analysis" in design_signal:
        return "SYSTEMATIC_REVIEW"
    if "randomized controlled trial" in design_signal or "randomised controlled trial" in design_signal or design == "rct":
        return "CLINICAL_TRIAL"
    if "clinical trial" in design_signal or "placebo-controlled trial" in design_signal or "placebo controlled trial" in design_signal:
        return "CLINICAL_TRIAL"
    if "observational" in design_signal or "cohort" in design_signal:
        return "OBSERVATIONAL"
    return source


def _year(rec: Mapping) -> int | None:
    for key in ("source_year", "publication_year", "year", "Source_Year", "Publication_Year", "Year"):
        v = rec.get(key)
        if v is None:
            continue
        s = str(v).strip()
        if len(s) >= 4 and s[:4].isdigit():
            y = int(s[:4])
            if 1800 <= y <= 2200:
                return y
    return None


def _identity(rec: Mapping) -> str:
    for key in ("evidence_record_id", "pmid", "doi", "source_url"):
        v = str(rec.get(key) or "").strip().lower()
        if v:
            return f"{key}:{v}"
    return f"text:{str(rec.get('assertion_text') or rec.get('text') or '').strip().lower()}"


def assess_evidence_body(
    records: Iterable[Mapping],
    *,
    direction_fn: Callable[[str], str],
    limitation_fn: Callable[[str], str],
    explicit_conflict_fn: Callable[[str], bool] | None = None,
) -> EvidenceBodyAssessment:
    """Assess one therapeutic body of evidence without benchmark-specific rules.

    `direction_fn` returns the production evidence-direction string.
    `limitation_fn` returns "none", "caution", or "firm_uncertainty".
    """
    rows = []
    seen = set()
    for rec in records:
        ident = _identity(rec)
        if ident in seen:
            continue
        seen.add(ident)
        text = str(rec.get("assertion_text") or rec.get("text") or "")
        stype = _norm_source_type(rec)
        rank = _SOURCE_RANK.get(stype)
        direction = str(direction_fn(text))
        limitation = str(limitation_fn(text))
        rows.append({
            "identity": ident,
            "source_type": stype,
            "rank": rank,
            "direction": direction,
            "limitation": limitation,
            "explicit_conflict": bool(explicit_conflict_fn(text)) if explicit_conflict_fn else False,
            "year": _year(rec),
        })

    recognized = [r for r in rows if r["rank"] is not None]
    if not recognized:
        return EvidenceBodyAssessment(
            BodyDirection.UNRESOLVED, BodyCertainty.NOT_ASSESSABLE,
            (), (), 0, len(rows), 0, None, False, False,
            "No recognized clinical synthesis, monograph, trial, or observational tier was available.",
        )

    best_rank = min(r["rank"] for r in recognized)
    top = [r for r in recognized if r["rank"] == best_rank]
    dirs = {r["direction"] for r in top}
    explicit_top_conflict = any(r["explicit_conflict"] for r in top)
    limitation_count = sum(r["limitation"] != "none" for r in top)
    firm_count = sum(r["limitation"] == "firm_uncertainty" for r in top)
    years = [r["year"] for r in top if r["year"] is not None]
    newest_top = max(years) if years else None

    pos = "positive" in dirs
    neg = bool(dirs & {"negative", "null"})
    mixed = "mixed" in dirs
    unresolved = "unclear" in dirs

    if (pos and neg) or (mixed and neg):
        direction = BodyDirection.MIXED
    elif neg and not pos and not mixed:
        direction = BodyDirection.NULL_OR_NEGATIVE
    elif pos and not neg:
        direction = BodyDirection.MIXED if (mixed or unresolved) else BodyDirection.SUPPORTIVE
    elif mixed:
        direction = BodyDirection.MIXED
    else:
        direction = BodyDirection.UNRESOLVED

    if explicit_top_conflict:
        direction = BodyDirection.MIXED

    # If the governing synthesis is explicitly limitation-qualified but cannot
    # itself state a firm direction, directly relevant lower-tier supportive
    # clinical evidence can rescue the body from "unresolved" to a cautious
    # supportive state.  It cannot create unconditional support.
    if direction == BodyDirection.UNRESOLVED and limitation_count:
        lower_support = any(
            r["rank"] is not None and r["rank"] > best_rank
            and r["direction"] in {"positive", "mixed"}
            for r in recognized
        )
        if lower_support:
            direction = BodyDirection.MIXED

    # Newer direct evidence may challenge an older governing synthesis.
    newer_contradiction = False
    if newest_top is not None and direction == BodyDirection.SUPPORTIVE:
        for r in recognized:
            if r["rank"] <= best_rank or r["year"] is None or r["year"] <= newest_top:
                continue
            if r["direction"] in {"negative", "null"}:
                newer_contradiction = True
                direction = BodyDirection.MIXED
                break

    # Certainty is body-level. It is intentionally conservative:
    # - authoritative monographs can be high-certainty for their stated indication;
    # - multiple clean syntheses can be high;
    # - a single clean synthesis is moderate;
    # - direct trials without a synthesis are low/moderate, never unconditional high;
    # - explicit limitations downgrade at least one level.
    top_types = {r["source_type"] for r in top}
    if best_rank in {1, 2, 3, 4}:  # authoritative monographs
        base = BodyCertainty.HIGH
    elif best_rank == 0:
        base = BodyCertainty.HIGH if len(top) >= 2 else BodyCertainty.MODERATE
    elif best_rank == 5:
        base = BodyCertainty.MODERATE if len(top) >= 2 else BodyCertainty.LOW
    else:
        base = BodyCertainty.LOW

    order = [
        BodyCertainty.VERY_LOW,
        BodyCertainty.LOW,
        BodyCertainty.MODERATE,
        BodyCertainty.HIGH,
    ]
    idx = order.index(base)
    downgrade = 0
    if limitation_count:
        downgrade += 1
    if firm_count:
        downgrade += 1
    if direction in {BodyDirection.MIXED, BodyDirection.UNRESOLVED}:
        downgrade += 1
    certainty = order[max(0, idx - downgrade)]

    reason = (
        f"Governing tier={best_rank}; governing sources={len(top)}; "
        f"directions={sorted(dirs)}; material limitations={limitation_count}; "
        f"explicit top-tier conflict={explicit_top_conflict}; newer contradiction={newer_contradiction}; body certainty={certainty.value}."
    )
    return EvidenceBodyAssessment(
        direction=direction,
        certainty=certainty,
        governing_source_types=tuple(sorted(top_types)),
        governing_directions=tuple(sorted(dirs)),
        governing_source_count=len(top),
        total_source_count=len(rows),
        limitation_count=limitation_count,
        newest_governing_year=newest_top,
        has_newer_contradiction=newer_contradiction,
        has_explicit_conflict=explicit_top_conflict,
        reason=reason,
    )
