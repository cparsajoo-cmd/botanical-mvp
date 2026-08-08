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

from dataclasses import dataclass, field
from typing import Optional

from scientific_phrase_matcher import find_phrase_matches, find_verb_aware_phrase_matches

# Root-cause fix (Reference-Grounded Validation v1, Problem C): these are
# the single-word regulatory-action VERBS whose base/present-tense forms
# ("prohibit", "prohibits", "ban", "bans") were previously invisible to
# the classifier — only their past-participle/adjectival form ("banned",
# "prohibited", "outlawed") was in the phrase list, so real regulatory
# text phrased as "EU rules prohibit X" or "the law bans Y" produced zero
# matches. Matched via find_verb_aware_phrase_matches (verb-conjugation
# aware), separately from the plain phrase list below (which still
# covers the non-verb, adjective/adverb-phrase entries "illegal in",
# "not permitted for sale", "not permitted").
_BARRIER_VERB_TERMS = [
    ("Prohibited / banned", ["prohibit", "ban", "outlaw"]),
]

_BARRIER_TYPES = [
    ("Prohibited / banned", [
        "illegal in", "not permitted for sale", "not permitted",
    ]),
    ("Restricted access (prescription/controlled)", [
        "prescription only", "prescription-only", "controlled substance",
        "restricted to licensed practitioners", "requires a prescription",
        "schedule i", "schedule ii", "schedule iii",
        "restricted supply", "restricts supply",
        "restricted to registered pharmacies", "under pharmacist supervision",
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

# Negation handling ("not banned", "no import restriction" must not be
# flagged as the barrier they mention) now lives in the shared
# scientific_phrase_matcher module (NEGATION_CUES there), used by
# _matches below.


@dataclass
class RegulatoryBarrierResult:
    has_barrier: bool
    barrier_types: list = field(default_factory=list)
    matched_phrases: list = field(default_factory=list)


def _matches(text: str, terms: list) -> list:
    # Delegates to the shared scientific_phrase_matcher utility instead
    # of a local \bTERM\b-only regex. Fix for the proven plural-form bug
    # (e.g. \bcontrolled substance\b did not match "controlled
    # substances") — see scientific_phrase_matcher.py. Word-boundary
    # behavior and negation-aware behavior are otherwise unchanged from
    # before; the lookback window narrows from 40/25 to 30/25 chars here,
    # same as the original local implementation.
    return find_phrase_matches(text, terms, lookback=30, negation_window=25)


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

    for label, verb_terms in _BARRIER_VERB_TERMS:
        hits = find_verb_aware_phrase_matches(lowered, verb_terms, lookback=30, negation_window=25)
        if hits:
            if label not in barrier_types:
                barrier_types.append(label)
            matched_phrases.extend(hits)

    return RegulatoryBarrierResult(
        has_barrier=bool(barrier_types),
        barrier_types=barrier_types,
        matched_phrases=matched_phrases,
    )
