"""Structured body-of-evidence assessment for final scientific decisions.

The module separates effect direction from certainty/readiness.  It uses
structured evidence fields when available and never treats a missing
methodological domain as evidence that the domain is satisfactory.

This is GRADE-informed, not formal GRADE: full GRADE requires outcome-specific
human methodological judgments and often full-text data that the platform may
not possess.  The purpose here is narrower and conservative: prevent
unassessed or weakly characterized evidence from being promoted to a
high-certainty autonomous GO.
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
    structured_domain_coverage: float
    unassessed_domains: tuple[str, ...]
    serious_methodological_concerns: tuple[str, ...]
    directness_concerns: tuple[str, ...]
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

_METHOD_DOMAINS = ("outcome", "comparator", "risk_of_bias", "directness")


def _norm_source_type(rec: Mapping) -> str:
    source = str(rec.get("source_type") or "").strip().upper().replace("-", "_").replace(" ", "_")
    design = str(rec.get("study_design") or "").strip().lower()
    text = str(rec.get("assertion_text") or rec.get("text") or "").strip().lower()
    signal = f"{design} {text}"
    if "systematic review" in signal or "meta-analysis" in signal or "meta analysis" in signal:
        return "SYSTEMATIC_REVIEW"
    if "randomized controlled trial" in signal or "randomised controlled trial" in signal or design == "rct":
        return "CLINICAL_TRIAL"
    if "clinical trial" in signal or "placebo-controlled trial" in signal or "placebo controlled trial" in signal:
        return "CLINICAL_TRIAL"
    if "observational" in signal or "cohort" in signal:
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


def _present(v) -> bool:
    return bool(str(v or "").strip())


def _structured_domain_state(rec: Mapping, source_type: str) -> tuple[dict[str, bool], list[str], list[str]]:
    """Return assessed-domain flags, methodological concerns and directness concerns.

    Systematic reviews/monographs are not penalized merely because a short
    connector record lacks a single-study comparator/sample-size field.
    However missing outcome/directness characterization caps certainty later.
    """
    outcome = _present(rec.get("primary_outcome") or rec.get("outcome"))
    comparator = _present(rec.get("comparator"))
    rob = str(rec.get("risk_of_bias") or "").strip().lower()
    applicability = str(rec.get("applicability_classification") or "").strip().lower()
    missing = str(rec.get("applicability_missing_dimensions") or "").strip()
    mismatches = str(rec.get("applicability_detected_mismatches") or "").strip()

    is_synthesis_or_monograph = source_type in {
        "SYSTEMATIC_REVIEW", "META_ANALYSIS", "SYSTEMATIC_REVIEW_META_ANALYSIS",
        "EMA_HMPC", "WHO_MONOGRAPH", "ESCOP_MONOGRAPH", "COMMISSION_E",
        "REGULATORY_MONOGRAPH",
    }

    assessed = {
        "outcome": outcome,
        "comparator": comparator or is_synthesis_or_monograph,
        "risk_of_bias": bool(rob) or is_synthesis_or_monograph,
        "directness": bool(applicability) or (not missing and not mismatches),
    }

    methodological = []
    if rob and any(x in rob for x in ("high", "serious", "critical")):
        methodological.append("risk_of_bias")
    if _present(rec.get("sample_size")):
        try:
            n = int(float(str(rec.get("sample_size")).replace(",", "").strip()))
        except Exception:
            n = None
        if n is not None and source_type == "CLINICAL_TRIAL" and n < 100:
            methodological.append("small_direct_trial")

    directness = []
    if applicability in {"partially applicable", "indirectly relevant", "not applicable"}:
        directness.append(applicability.replace(" ", "_"))
    if mismatches:
        directness.append("detected_applicability_mismatch")
    return assessed, methodological, directness


def assess_evidence_body(
    records: Iterable[Mapping],
    *,
    direction_fn: Callable[[str], str],
    limitation_fn: Callable[[str], str],
    explicit_conflict_fn: Callable[[str], bool] | None = None,
) -> EvidenceBodyAssessment:
    rows = []
    seen = set()
    for rec in records:
        ident = _identity(rec)
        if ident in seen:
            continue
        seen.add(ident)
        text = str(rec.get("assertion_text") or rec.get("text") or "")
        stype = _norm_source_type(rec)
        assessed, meth, directness = _structured_domain_state(rec, stype)
        rows.append({
            "identity": ident,
            "source_type": stype,
            "rank": _SOURCE_RANK.get(stype),
            "direction": str(direction_fn(text)),
            "limitation": str(limitation_fn(text)),
            "explicit_conflict": bool(explicit_conflict_fn(text)) if explicit_conflict_fn else False,
            "year": _year(rec),
            "domains": assessed,
            "methodological": meth,
            "directness": directness,
        })

    recognized = [r for r in rows if r["rank"] is not None]
    if not recognized:
        return EvidenceBodyAssessment(
            BodyDirection.UNRESOLVED, BodyCertainty.NOT_ASSESSABLE,
            (), (), 0, len(rows), 0, None, False, False, 0.0,
            _METHOD_DOMAINS, (), (),
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

    # Body-level domain coverage: a domain is considered assessed when at least
    # one governing source supplies it. Missing domains are never scored as clean.
    domain_assessed = {d: any(r["domains"][d] for r in top) for d in _METHOD_DOMAINS}
    unassessed = tuple(d for d, ok in domain_assessed.items() if not ok)
    coverage = sum(domain_assessed.values()) / len(_METHOD_DOMAINS)
    methodological = tuple(sorted({x for r in top for x in r["methodological"]}))
    directness = tuple(sorted({x for r in top for x in r["directness"]}))

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

    if direction == BodyDirection.UNRESOLVED and limitation_count:
        lower_support = any(
            r["rank"] is not None and r["rank"] > best_rank
            and r["direction"] in {"positive", "mixed"}
            for r in recognized
        )
        if lower_support:
            direction = BodyDirection.MIXED

    newer_contradiction = False
    if newest_top is not None and direction == BodyDirection.SUPPORTIVE:
        for r in recognized:
            if r["rank"] <= best_rank or r["year"] is None or r["year"] <= newest_top:
                continue
            if r["direction"] in {"negative", "null"}:
                newer_contradiction = True
                direction = BodyDirection.MIXED
                break

    # Starting certainty is based on governing tier and independent synthesis count.
    if best_rank in {1, 2, 3, 4}:
        base = BodyCertainty.HIGH
    elif best_rank == 0:
        base = BodyCertainty.HIGH if len(top) >= 2 else BodyCertainty.MODERATE
    elif best_rank == 5:
        base = BodyCertainty.MODERATE if len(top) >= 2 else BodyCertainty.LOW
    else:
        base = BodyCertainty.LOW

    order = [BodyCertainty.VERY_LOW, BodyCertainty.LOW, BodyCertainty.MODERATE, BodyCertainty.HIGH]
    idx = order.index(base)
    downgrade = 0
    if limitation_count:
        downgrade += 1
    if firm_count:
        downgrade += 1
    if direction in {BodyDirection.MIXED, BodyDirection.UNRESOLVED}:
        downgrade += 1
    if methodological:
        downgrade += 1
    if directness:
        downgrade += 1

    # Crucial validity guard: if core structured domains are substantially
    # unassessed, certainty cannot be "High".  This avoids interpreting
    # absence of methodological information as absence of methodological risk.
    certainty = order[max(0, idx - downgrade)]
    if coverage < 0.75 and certainty == BodyCertainty.HIGH:
        certainty = BodyCertainty.MODERATE
    if coverage < 0.50 and certainty in {BodyCertainty.HIGH, BodyCertainty.MODERATE}:
        certainty = BodyCertainty.LOW

    reason = (
        f"Governing tier={best_rank}; governing sources={len(top)}; "
        f"directions={sorted(dirs)}; material limitations={limitation_count}; "
        f"structured domain coverage={coverage:.2f}; unassessed={list(unassessed)}; "
        f"methodological concerns={list(methodological)}; directness concerns={list(directness)}; "
        f"explicit top-tier conflict={explicit_top_conflict}; newer contradiction={newer_contradiction}; "
        f"body certainty={certainty.value}."
    )
    return EvidenceBodyAssessment(
        direction=direction,
        certainty=certainty,
        governing_source_types=tuple(sorted({r["source_type"] for r in top})),
        governing_directions=tuple(sorted(dirs)),
        governing_source_count=len(top),
        total_source_count=len(rows),
        limitation_count=limitation_count,
        newest_governing_year=newest_top,
        has_newer_contradiction=newer_contradiction,
        has_explicit_conflict=explicit_top_conflict,
        structured_domain_coverage=coverage,
        unassessed_domains=unassessed,
        serious_methodological_concerns=methodological,
        directness_concerns=directness,
        reason=reason,
    )
