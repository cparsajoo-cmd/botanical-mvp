"""Regulatory scope/relevance and dose-threshold assessment.

WHAT THIS FIXES (Reference-Grounded Validation v1, Problem C)

``eligibility_gate.classify_regulatory_finding()`` previously had no way
to ever resolve a documented regulatory PROHIBITED/RESTRICTED finding to
a scope other than UNKNOWN in live production (see that module's own
docstring) — every prohibited finding therefore fell through to
EXPERT_REVIEW_REQUIRED, never an automatic NO_GO_REGULATORY, even for a
blanket whole-species food-supplement ban with no narrowing qualifier at
all. This mirrors, and is fixed the same way as, the equivalent gap that
was already closed for SAFETY findings via
``safety_assertion_engine``'s structured serious-assertion scope
inference (see ``eligibility_gate.classify_safety_finding``'s
``serious_assertions`` branch) — regulatory never received the
equivalent treatment.

The governing principle (identical to the safety-side fix, restated for
regulatory): a documented prohibition/restriction that carries no
candidate-limiting qualifier (a different plant part / preparation /
constituent / route than the one actually being evaluated) is broad for
the botanical record, not unknowable by default. If a qualifier IS
present, it only narrows the finding to the candidate when the
candidate's own declared context independently states the same
qualifier — this module never invents a match the source data does not
support.

Separately, Problem C's largest failure category — a dose-DEPENDENT
regulatory restriction ("must contain less than 800 mg X per daily
portion") — is not a keyword-presence question at all; no "banned/
prohibited/restricted" phrase is present in this kind of text. This
module also adds a small, plant/compound-agnostic numeric threshold
comparator for exactly this pattern.

Both capabilities are deliberately generic (no botanical name, PMID, or
holdout case id anywhere in this file) and are additive: neither
changes ``regulatory_barrier_classifier.py``'s own phrase-presence
detection, they only interpret the SCOPE of whatever it already found
(or, for the dose case, add one more narrowly-scoped detection path).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from scientific_phrase_matcher import find_phrase_matches

# ----------------------------------------------------------------------
# Qualifier-scope assessment
# ----------------------------------------------------------------------

# Generic (non-botanical-specific) plant-part and preparation-type nouns
# used only to detect WHETHER a regulatory finding names a narrowing
# qualifier at all — never to look up a specific plant.
_PLANT_PART_TERMS = (
    "leaf", "root", "bark", "seed", "flower", "fruit", "rhizome", "stem",
    "rind", "peel", "bulb", "berry",
)
_PREPARATION_TERMS = (
    "extract", "tincture", "essential oil", "powder", "tea", "decoction",
    "infusion", "tablet", "capsule",
)

# Capture a short (<=2 word) constituent phrase immediately following a
# "containing X"/"contains X" cue — kept deliberately short so the
# captured phrase is exactly the kind of short noun phrase a candidate's
# own indication/context text would plausibly restate verbatim (e.g.
# "hydroxyanthracene derivatives"), rather than accidentally swallowing
# trailing prepositional clauses ("...in foods").
_CONTAINING_RE = re.compile(
    r"\b(?:containing|contains)\b\s+([a-z0-9\-]+(?:\s+[a-z0-9\-]+)?)"
)
# "in which X is present" — captures just the constituent name itself.
_IN_WHICH_RE = re.compile(r"\bin which\s+([a-z0-9\-]+)\s+is\b")
# "prohibits X and ..." — captures a bare constituent name that is the
# direct object of the prohibition verb itself (as opposed to being
# introduced by "containing"), e.g. "prohibits emodin and all
# preparations...".
_DIRECT_OBJECT_RE = re.compile(
    r"\b(?:prohibits?|bans?|restricts?)\b\s+(?:the\s+use\s+of\s+)?"
    r"([a-z][a-z0-9\-]{2,})\s+(?:and|in|for|from|as)\b"
)


# Generic product-form nouns that are not, by themselves, a candidate-
# limiting qualifier — essentially every botanical candidate IS "a
# preparation"/"an extract"/"a product" of something, so capturing one
# of these as if it narrowed scope to a specific constituent would make
# every prohibition unmatchable (a real regression risk, not a
# hypothetical one — "prohibit preparations from X" grammatically has
# "preparations" as its direct object, but that word carries no
# distinguishing information).
_GENERIC_NON_QUALIFIER_NOUNS = {
    "preparation", "preparations", "product", "products", "substance",
    "substances", "ingredient", "ingredients", "material", "materials",
}


# Words that must never be swallowed into a captured qualifier phrase
# (copulas, prepositions, and other closed-class words that can follow
# a constituent name but are not part of it).
_NON_QUALIFIER_CONTINUATION_WORDS = {
    "is", "are", "was", "were", "being", "been", "in", "for", "and", "or",
    "because", "due", "present", "from", "per", "at", "to", "of", "the",
    "a", "an", "with", "without",
}


def _extract_constituent_phrases(finding_text: str) -> tuple:
    n = finding_text.lower()
    hits = []
    for regex in (_CONTAINING_RE, _IN_WHICH_RE, _DIRECT_OBJECT_RE):
        for m in regex.finditer(n):
            phrase = m.group(1).strip()
            words = [w for w in phrase.split() if w]
            # Trim any trailing closed-class word that leaked into the
            # capture (e.g. "xanthotoxin are" from "containing
            # xanthotoxin are prohibited" — the capture group's optional
            # second word should only ever extend a genuine multi-word
            # noun phrase like "hydroxyanthracene derivatives", never
            # swallow the next clause's verb).
            while words and words[-1] in _NON_QUALIFIER_CONTINUATION_WORDS:
                words.pop()
            phrase = " ".join(words)
            if phrase and phrase not in hits and phrase not in _GENERIC_NON_QUALIFIER_NOUNS:
                hits.append(phrase)
    return tuple(dict.fromkeys(hits))


@dataclass(frozen=True)
class RegulatoryScopeAssessment:
    scope: str  # "species_wide" | "plant_part_specific" | "preparation_specific"
                # | "constituent_specific" | "unknown"
    relevant: Optional[bool]  # True/False/None (cannot confirm)
    matched_qualifiers: tuple = ()


def assess_regulatory_scope(
    finding_text: str,
    candidate_context_text: str = "",
) -> RegulatoryScopeAssessment:
    """Determine how broadly a documented regulatory finding applies,
    and whether it is confirmed relevant to the specific candidate
    being evaluated.

    No qualifier detected at all in ``finding_text`` -> the finding is
    read as applying to the whole botanical record: scope="species_wide",
    relevant=True (mirrors the safety-side default — see module
    docstring).

    A qualifier IS detected (a named plant part, preparation type, or
    constituent) -> the finding only resolves to relevant=True if
    ``candidate_context_text`` independently states the SAME qualifier
    (i.e. the candidate's own declared indication/preparation text, not
    the regulatory source, confirms it applies). If the candidate
    context does not mention the qualifier at all, relevant=None
    (honestly unconfirmed, not guessed either way) — this keeps the
    EXPERT_REVIEW_REQUIRED safety net for genuinely ambiguous cases
    while letting an unambiguous match resolve automatically.
    """
    text = (finding_text or "").lower()
    ctx = (candidate_context_text or "").lower()
    if not text:
        return RegulatoryScopeAssessment(scope="unknown", relevant=None)

    matched_parts = find_phrase_matches(text, _PLANT_PART_TERMS, negation_aware=False)
    matched_preps = find_phrase_matches(text, _PREPARATION_TERMS, negation_aware=False)
    matched_constituents = _extract_constituent_phrases(text)

    qualifiers = list(matched_constituents) + list(matched_parts) + list(matched_preps)
    if not qualifiers:
        return RegulatoryScopeAssessment(scope="species_wide", relevant=True)

    if not ctx:
        # A qualifier exists but there is nothing to compare it against.
        scope = (
            "constituent_specific" if matched_constituents
            else "plant_part_specific" if matched_parts
            else "preparation_specific"
        )
        return RegulatoryScopeAssessment(scope=scope, relevant=None, matched_qualifiers=tuple(qualifiers))

    all_matched = True
    for q in qualifiers:
        # A qualifier "matches" the candidate context if its own phrase
        # (constituent name, plant part, or preparation noun) is present
        # in the candidate's own declared context text — simple,
        # explainable substring/plural-aware containment, not a semantic
        # model. Checked in both directions (singular source phrase
        # against a plural candidate mention, and vice versa) since
        # scientific_phrase_matcher's pluralizer only generates the
        # plural of whichever form it is GIVEN, not both.
        q_singular = q[:-1] if q.endswith("s") and len(q) > 3 else q
        if not (
            find_phrase_matches(ctx, [q], negation_aware=False)
            or find_phrase_matches(ctx, [q_singular], negation_aware=False)
        ):
            all_matched = False
            break

    scope = (
        "constituent_specific" if matched_constituents
        else "plant_part_specific" if matched_parts
        else "preparation_specific"
    )
    return RegulatoryScopeAssessment(
        scope=scope,
        relevant=True if all_matched else None,
        matched_qualifiers=tuple(qualifiers),
    )


# ----------------------------------------------------------------------
# Dose-threshold comparison
# ----------------------------------------------------------------------

_UNIT_ALIASES = {
    "mg": "mg", "milligram": "mg", "milligrams": "mg",
    "mcg": "mcg", "\u00b5g": "mcg", "ug": "mcg", "microgram": "mcg", "micrograms": "mcg",
    "g": "g", "gram": "g", "grams": "g",
}
_NUMBER_UNIT_RE = re.compile(
    r"([\d]+(?:[.,]\d+)?)\s*(mg|mcg|\u00b5g|ug|g|milligrams?|micrograms?|grams?)\b"
)
_LIMIT_CUE_RE = re.compile(
    r"\b(?:less than|no more than|not more than|maximum of|must not exceed|"
    r"shall not exceed|may not exceed|up to)\s+" + _NUMBER_UNIT_RE.pattern
)

_UNIT_TO_MG = {"mg": 1.0, "mcg": 0.001, "g": 1000.0}


def _to_mg(value: float, unit: str) -> Optional[float]:
    canon = _UNIT_ALIASES.get(unit.lower())
    if canon is None:
        return None
    return value * _UNIT_TO_MG[canon]


@dataclass(frozen=True)
class DoseThresholdFinding:
    limit_value: float
    limit_unit: str
    actual_value: Optional[float]
    actual_unit: Optional[str]
    violates: Optional[bool]  # None when no candidate value could be found


def detect_dose_threshold_violation(
    finding_text: str,
    candidate_context_text: str = "",
) -> Optional[DoseThresholdFinding]:
    """Detect a "must contain less than X <unit>" style regulatory dose
    limit in ``finding_text`` and, if the candidate's own declared
    context states a numeric amount, determine whether it violates that
    limit.

    Deliberately generic: it does not know about EGCG, green tea, or any
    other specific compound — it only looks for a generic
    limit-cue-phrase-plus-number-and-unit pattern, then compares against
    the first number-and-unit mentioned in the candidate's own context
    text. Returns None if no limit clause is found in ``finding_text``
    at all (the ordinary case — most regulatory findings are not
    dose-based).
    """
    text = (finding_text or "").lower()
    if not text:
        return None
    limit_match = _LIMIT_CUE_RE.search(text)
    if not limit_match:
        return None
    limit_value = float(limit_match.group(1).replace(",", "."))
    limit_unit = limit_match.group(2)
    limit_mg = _to_mg(limit_value, limit_unit)

    ctx = (candidate_context_text or "").lower()
    actual_value = None
    actual_unit = None
    violates = None
    if ctx and limit_mg is not None:
        # Prefer a candidate-declared amount that is NOT itself part of a
        # repeated limit clause (skip the same limit phrase if the
        # candidate context happens to also restate the regulatory
        # limit verbatim); take the first remaining number+unit.
        limit_span_text = limit_match.group(0)
        candidate_matches = [
            m for m in _NUMBER_UNIT_RE.finditer(ctx)
            if m.group(0) not in limit_span_text
        ]
        if candidate_matches:
            m = candidate_matches[0]
            actual_value = float(m.group(1).replace(",", "."))
            actual_unit = m.group(2)
            actual_mg = _to_mg(actual_value, actual_unit)
            if actual_mg is not None:
                violates = actual_mg >= limit_mg

    return DoseThresholdFinding(
        limit_value=limit_value,
        limit_unit=limit_unit,
        actual_value=actual_value,
        actual_unit=actual_unit,
        violates=violates,
    )
