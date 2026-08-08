"""Canonical scientific assertion resolution.

One evidence record may carry a source-reported result direction, an LLM-
extracted result direction, legacy platform interpretation, and raw prose.
This module defines one precedence/order and one normalization vocabulary so
downstream body-of-evidence code never re-invents scientific direction.

Precedence:
1. Source/connector Result_Direction (structured source assertion)
2. LLM_Result_Direction (structured extraction)
3. reported_direction carried by an adapter, when provenance is unknown
4. Text classifier fallback

The fallback exists for legacy records only. New records should acquire a
structured direction during standardization whenever extraction is available.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

CANONICAL_POSITIVE="positive"
CANONICAL_NEGATIVE="negative"
CANONICAL_NULL="null"
CANONICAL_MIXED="mixed"
CANONICAL_UNCLEAR="unclear"

_ALLOWED={
    CANONICAL_POSITIVE,CANONICAL_NEGATIVE,CANONICAL_NULL,
    CANONICAL_MIXED,CANONICAL_UNCLEAR,
}

@dataclass(frozen=True)
class CanonicalDirection:
    direction: str
    provenance: str
    raw_value: str = ""


def normalize_direction(value) -> str | None:
    n=str(value or "").strip().lower().replace("_"," ").replace("-"," ")
    n=" ".join(n.split())
    if not n:
        return None

    # Exact/controlled values first.
    exact={
        "positive":CANONICAL_POSITIVE,
        "supportive":CANONICAL_POSITIVE,
        "beneficial":CANONICAL_POSITIVE,
        "benefit":CANONICAL_POSITIVE,
        "negative":CANONICAL_NEGATIVE,
        "harm":CANONICAL_NEGATIVE,
        "harmful":CANONICAL_NEGATIVE,
        "null":CANONICAL_NULL,
        "neutral":CANONICAL_NULL,
        "no effect":CANONICAL_NULL,
        "no difference":CANONICAL_NULL,
        "mixed":CANONICAL_MIXED,
        "conflicting":CANONICAL_MIXED,
        "inconsistent":CANONICAL_MIXED,
        "unclear":CANONICAL_UNCLEAR,
        "unknown":CANONICAL_UNCLEAR,
        "inconclusive":CANONICAL_UNCLEAR,
        "insufficient":CANONICAL_UNCLEAR,
    }
    if n in exact:
        return exact[n]

    # Controlled values sometimes arrive with explanatory suffixes.
    if n.startswith(("positive ", "supportive ", "beneficial ")):
        return CANONICAL_POSITIVE
    if n.startswith(("negative ", "harmful ")):
        return CANONICAL_NEGATIVE
    if n.startswith(("neutral ", "null ", "no effect ")):
        return CANONICAL_NULL
    if n.startswith(("mixed ", "conflicting ", "inconsistent ")):
        return CANONICAL_MIXED
    if n.startswith(("unknown ", "unclear ", "inconclusive ")):
        return CANONICAL_UNCLEAR
    return None


def resolve_record_direction(
    record: Mapping,
    *,
    fallback_fn: Callable[[str], str],
    allow_text_fallback: bool = False,
) -> CanonicalDirection:
    """Resolve one evidence record to exactly one canonical direction."""
    candidates=(
        ("source_result_direction", record.get("source_result_direction")),
        ("llm_result_direction", record.get("llm_result_direction")),
        ("reported_direction", record.get("reported_direction")),
    )
    for provenance,raw in candidates:
        normalized=normalize_direction(raw)
        if normalized is not None and normalized != CANONICAL_UNCLEAR:
            return CanonicalDirection(normalized,provenance,str(raw or ""))
        # Explicit Unknown/Unclear is meaningful: do not pretend it was a
        # positive/negative source statement merely because fallback regex can
        # find a keyword elsewhere in the record.
        if normalized == CANONICAL_UNCLEAR:
            return CanonicalDirection(CANONICAL_UNCLEAR,provenance,str(raw or ""))

    if allow_text_fallback:
        text=str(record.get("assertion_text") or record.get("text") or "")
        fallback=normalize_direction(fallback_fn(text)) or CANONICAL_UNCLEAR
        return CanonicalDirection(fallback,"text_fallback","")

    # Fail-safe production rule: raw prose is not an authoritative scientific
    # assertion. A record without structured direction must not be promoted.
    return CanonicalDirection(CANONICAL_UNCLEAR,"missing_structured_direction","")


CANONICAL_SAFETY_SERIOUS="serious"
CANONICAL_SAFETY_MODERATE="moderate"
CANONICAL_SAFETY_REASSURING="reassuring"
CANONICAL_SAFETY_NONE="none"
CANONICAL_SAFETY_UNKNOWN="unknown"


def normalize_safety_signal(value) -> str | None:
    """Normalize structured safety signals into a tiny controlled severity set.

    This is intentionally not a free-text hazard detector. It is the adapter
    for fields that are already asserted as Safety_Signal by a connector or
    the structured extractor.
    """
    n=" ".join(str(value or "").strip().lower().replace("_"," ").split())
    if not n:
        return None
    exact={
        "serious":CANONICAL_SAFETY_SERIOUS,
        "serious risk":CANONICAL_SAFETY_SERIOUS,
        "severe":CANONICAL_SAFETY_SERIOUS,
        "severe risk":CANONICAL_SAFETY_SERIOUS,
        "high risk":CANONICAL_SAFETY_SERIOUS,
        "moderate":CANONICAL_SAFETY_MODERATE,
        "moderate risk":CANONICAL_SAFETY_MODERATE,
        "caution":CANONICAL_SAFETY_MODERATE,
        "safety caution detected":CANONICAL_SAFETY_MODERATE,
        "reassuring":CANONICAL_SAFETY_REASSURING,
        "no serious risk":CANONICAL_SAFETY_REASSURING,
        "positive safety signal":CANONICAL_SAFETY_REASSURING,
        "none":CANONICAL_SAFETY_NONE,
        "no signal":CANONICAL_SAFETY_NONE,
        "unknown":CANONICAL_SAFETY_UNKNOWN,
    }
    if n in exact:
        return exact[n]
    # Structured fields sometimes carry a brief explanatory suffix.
    if n.startswith(("serious ", "severe ", "life threatening ", "life-threatening ")):
        return CANONICAL_SAFETY_SERIOUS
    if n.startswith(("moderate ", "caution ")):
        return CANONICAL_SAFETY_MODERATE
    if n.startswith(("reassuring ", "no serious adverse", "well tolerated")):
        return CANONICAL_SAFETY_REASSURING
    return None
