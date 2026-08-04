"""Shared free-text phrase matching for scientific/regulatory evidence
classification.

WHAT THIS FIXES
Four call sites independently implemented their own version of "does this
evidence text mention phrase X":

  - botanical_rd_candidate_engine.py :: _evidence_level()
  - evidence_hierarchy_classifier.py :: _has_term()
  - regulatory_barrier_classifier.py :: _matches()
  - candidate_shortlisting.py :: _evidence_points()

The first three used ``re.compile(r"\\b" + re.escape(term) + r"\\b")`` against
a fixed list of SINGULAR-ONLY multi-word phrases (e.g. "clinical trial").
Because ``\\b`` is a boundary between a word character and a non-word
character, ``\\bclinical trial\\b`` does not match "clinical trials"
(plural) — real evidence text overwhelmingly uses plural forms, so genuine
evidence was silently falling through to a weaker classification tier.

The fourth site (``_evidence_points``) used plain substring matching with
no word-boundary and no negation handling at all, so the bare word
"clinical" matched inside "preclinical" (itself a value produced by
``_evidence_level``), causing a false positive in the opposite direction.

This module is a single, shared, well-tested matching primitive that all
four call sites now delegate to, so this bug class cannot recur
independently in a fifth place. It intentionally does NOT know about any
specific phrase list, tier ordering, or scoring weight — those all stay
in their original call sites, unchanged. This module only answers "is this
phrase present in this text, accounting for simple English plurals and
(optionally) negation," nothing more.
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Pattern

# Same negation-cue list already shared (informally, by copy-paste) across
# _evidence_level(), evidence_hierarchy_classifier.py, and
# regulatory_barrier_classifier.py, PLUS one addition: "further " /
# "additional " / "more " — a forward-looking hedge ("further clinical
# trials are needed to confirm this") is not a report of an existing
# trial and must not count as a positive match either, per the required
# test table for this fix (the "Forward-negated" case). This is the one
# place this fix intentionally widens negation coverage beyond a literal
# copy of the three call sites' original lists; it is additive only (it
# can only turn an old false positive into a correct non-match, never the
# reverse) and is exercised by test_scientific_phrase_matcher.py.
# candidate_shortlisting.py's _evidence_points() never had negation
# handling and is deliberately NOT switched to it here (see that call
# site's comment) — this constant is exposed for callers that want it,
# not force-applied to every caller.
NEGATION_CUES = (
    "no ", "not ", "lack of ", "lacks ", "insufficient ",
    "absence of ", "without ", "none found", "no evidence of ",
    "no direct ", "unproven", "unconfirmed", "no reported ", "no longer",
    "further ", "additional ", "more research",
)

_VOWELS = "aeiou"

# Compiled phrase patterns are cheap to build but this module is called on
# every row of every evidence table, so cache them by term.
_PATTERN_CACHE: Dict[str, Pattern] = {}


def _pluralize_pattern(word: str) -> str:
    """Return a regex fragment (no boundary anchors) matching `word` in
    either its singular or a simple regular-English plural form.

    This is deliberately a generic, indication-agnostic pluralization
    rule (drop trailing -y for -ies, add -es after a sibilant, otherwise
    add an optional -s) — not a per-word or per-disease dictionary. It
    covers every phrase family this bug fix was scoped against
    (clinical_trial -> trials, systematic_review -> reviews, cohort_study
    -> studies, animal_model -> models, monograph -> monographs,
    controlled_substance -> substances, novel_food -> foods) without
    hardcoding any of them individually.
    """
    if len(word) > 1 and word[-1] == "y" and word[-2] not in _VOWELS:
        stem = re.escape(word[:-1])
        return rf"{stem}(?:y|ies)"
    if word.endswith(("s", "x", "z")) or word.endswith(("ch", "sh")):
        return rf"{re.escape(word)}(?:es)?"
    return rf"{re.escape(word)}s?"


def _phrase_pattern(term: str) -> Pattern:
    cached = _PATTERN_CACHE.get(term)
    if cached is not None:
        return cached
    words = term.split(" ")
    if len(words) == 1:
        body = _pluralize_pattern(words[0])
    else:
        prefix = r"\s+".join(re.escape(w) for w in words[:-1])
        body = prefix + r"\s+" + _pluralize_pattern(words[-1])
    pattern = re.compile(r"\b" + body + r"\b")
    _PATTERN_CACHE[term] = pattern
    return pattern


def phrase_present(text: str, term: str) -> bool:
    """Word-boundary-aware, simple-plural-aware check for a single
    `term` in `text`. No negation handling — this is the base primitive
    every other function in this module builds on. `text` is expected to
    already be lowercased/normalized by the caller, matching the
    convention the original four call sites already used.
    """
    if not text:
        return False
    return _phrase_pattern(term).search(text) is not None


def find_phrase_matches(
    text: str,
    terms: Iterable[str],
    negation_aware: bool = True,
    lookback: int = 40,
    negation_window: int = 25,
) -> List[str]:
    """Return the subset of `terms` (in the order given, each term listed
    at most once) that are present in `text`.

    When `negation_aware` is True (the default, matching the behavior of
    the three original word-boundary call sites), a match immediately
    preceded by a negation cue within a short word window does not count
    — "no clinical trials have been conducted" is not a positive match
    for "clinical trial".
    """
    if not text:
        return []
    matched: List[str] = []
    for term in terms:
        pattern = _phrase_pattern(term)
        for match in pattern.finditer(text):
            if negation_aware:
                window_start = max(0, match.start() - lookback)
                preceding = text[window_start:match.start()]
                if any(cue in preceding[-negation_window:] for cue in NEGATION_CUES):
                    continue
            matched.append(term)
            break
    return matched


def has_phrase_match(text: str, terms: Iterable[str], negation_aware: bool = True, **kwargs) -> bool:
    """Convenience wrapper: True if any term in `terms` is matched."""
    return bool(find_phrase_matches(text, terms, negation_aware=negation_aware, **kwargs))
