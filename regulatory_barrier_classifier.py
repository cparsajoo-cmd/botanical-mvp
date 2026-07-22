"""
Architecture audit Q8 — "What regulatory barriers exist?"

WHAT THIS FIXES
Market_Status (Gap 2) only tracks whether regulatory RECOGNITION
exists ("Regulatory monograph exists", "Traditional-use status") — it
has no way to represent the OPPOSITE claim: an active restriction,
prohibition, or special-access requirement. "No monograph found" and
"explicitly banned in this market" are both currently invisible to
Market_Status in the same way (neither matches its positive-signal
patterns) — but they are completely different findings for an R&D
team to act on.

WHY A SEPARATE CLASSIFIER, NOT A CHANGE TO _market_status()
_market_status() already has six branches and a carefully-ordered
conflict-detection priority (Gap 2) — adding a seventh concept
(barriers, which can coexist with any of the existing six: a plant can
have a monograph AND a restriction, e.g. prescription-only) would mean
either overloading its single return string with two orthogonal ideas,
or picking an arbitrary priority between them. Keeping this as its own
column, built from the SAME evidence text `_market_status()` already
reads, lets both signals be reported independently instead of forcing
a false choice between them. This is the same reasoning that kept
Decision_Class_AH and White_Space_Type as separate columns rather than
folded into Decision_Class.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

_BARRIER_TYPES = [
    ("Prohibited / banned", [
        "banned", "prohibited", "illegal in", "not permitted for sale",
        "outlawed",
    ]),
    ("Restricted access (prescription/controlled)", [
        "prescription only", "prescription-only", "controlled substance",
        "restricted to licensed practitioners", "requires a prescription",
        "schedule i", "schedule ii", "schedule iii",
    ]),
    ("Novel food / pre-market approval required", [
        "novel food", "pre-market approval required", "premarket notification required",
        "not on the positive list", "requires novel food authorization",
    ]),
    ("Import / export restriction", [
        "import restricted", "export restricted", "cites-listed", "cites listed",
        "trade restricted", "customs restricted",
    ]),
    ("Withdrawn / recalled for regulatory reasons", [
        "regulatory withdrawal", "recalled by the regulator", "suspended by the regulator",
        "marketing authorization withdrawn", "marketing authorisation withdrawn",
    ]),
]

# Same negation-cue list already used throughout this codebase
# (evidence_hierarchy_classifier.py, negative_evidence_classifier.py) —
# "not banned", "no import restriction" must not be flagged as the
# barrier they mention.
_NEGATION_CUES = (
    "no ", "not ", "lack of ", "lacks ", "without ", "none found",
    "no evidence of ", "unproven", "unconfirmed", "no longer",
)


@dataclass
class RegulatoryBarrierResult:
    has_barrier: bool
    barrier_types: list = field(default_factory=list)
    matched_phrases: list = field(default_factory=list)


def _matches(text: str, terms: list) -> list:
    matched = []
    for term in terms:
        pattern = re.compile(r"\b" + re.escape(term) + r"\b")
        for match in pattern.finditer(text):
            window_start = max(0, match.start() - 30)
            preceding = text[window_start:match.start()]
            if not any(cue in preceding[-25:] for cue in _NEGATION_CUES):
                matched.append(term)
                break
    return matched


def classify_regulatory_barriers(text: Optional[str]) -> RegulatoryBarrierResult:
    """Scans `text` for the barrier categories above. A single text can
    match more than one category (e.g. both prescription-only AND a
    novel-food requirement) — all matches are returned, not just the
    first, same as negative_evidence_classifier.py's approach."""
    if not text:
        return RegulatoryBarrierResult(has_barrier=False)

    lowered = text.lower()
    barrier_types = []
    matched_phrases = []

    for label, terms in _BARRIER_TYPES:
        hits = _matches(lowered, terms)
        if hits:
            barrier_types.append(label)
            matched_phrases.extend(hits)

    return RegulatoryBarrierResult(
        has_barrier=bool(barrier_types),
        barrier_types=barrier_types,
        matched_phrases=matched_phrases,
    )
