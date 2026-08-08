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

# Root-cause fix (Targeted Generalization Fix, Blocker 2, part 2):
# different limit phrasings have different INCLUSIVE/EXCLUSIVE boundary
# semantics, and treating them all as the same ">=" comparison silently
# mislabels a compliant candidate as a violation (or vice versa) at the
# exact boundary value:
#   - "less than X"                              -> X itself is NOT
#     compliant; violation is actual >= X (strict/exclusive limit).
#   - "no more than X" / "not more than X" /
#     "maximum (of) X" / "must not exceed X" /
#     "shall not exceed X" / "may not exceed X" /
#     "up to X" / "not exceeding X"               -> X itself IS
#     compliant; violation is actual > X (inclusive limit).
#   - "more than X ... prohibited"                -> same as the
#     inclusive-limit family: X itself is compliant, violation is
#     actual > X.
# Each family is its own regex group below so the comparator used at
# evaluation time is read directly off of which phrasing matched,
# instead of being assumed.
_STRICT_LIMIT_CUE_RE = re.compile(
    r"\bless than\s+" + _NUMBER_UNIT_RE.pattern
)
_INCLUSIVE_LIMIT_CUE_RE = re.compile(
    r"\b(?:no more than|not more than|maximum(?:\s+of)?|must not exceed|"
    r"shall not exceed|may not exceed|up to|not exceeding)\s+" + _NUMBER_UNIT_RE.pattern
)
_MORE_THAN_PROHIBITED_RE = re.compile(
    r"\bmore than\s+" + _NUMBER_UNIT_RE.pattern + r"\b(?:(?!\.).){0,40}?\b(?:prohibited|banned|not permitted)\b"
)

_UNIT_TO_MG = {"mg": 1.0, "mcg": 0.001, "g": 1000.0}


def _to_mg(value: float, unit: str) -> Optional[float]:
    canon = _UNIT_ALIASES.get(unit.lower())
    if canon is None:
        return None
    return value * _UNIT_TO_MG[canon]


# Words that can follow a number+unit before the constituent name itself
# ("less than 800 mg **of** Compound-X") and must be skipped rather than
# captured as part of the name.
_CONSTITUENT_LEAD_WORDS = {"of", "the", "a", "an"}
# Words that can trail a captured constituent name and must be trimmed
# (the same closed-class stopword set used for regulatory qualifiers,
# plus a few dose-clause-specific connectors).
_CONSTITUENT_TRAIL_STOPWORDS = _NON_QUALIFIER_CONTINUATION_WORDS | {
    "per", "daily", "portion", "portions", "serving", "servings", "day",
}


def _clean_constituent_phrase(raw: str) -> str:
    """Normalize a short constituent noun phrase without knowing its identity."""
    s=(raw or "").strip(" \t,;:.()")
    # Remove generic regulatory scaffolding that can precede the actual entity.
    s=re.sub(
        r"^(?:the\s+)?(?:amount|content|level|quantity|concentration)\s+of\s+",
        "", s,
    )
    s=re.sub(r"^(?:the|a|an)\s+", "", s)
    words=[w.strip(" ,;:.()") for w in s.split() if w.strip(" ,;:.()")]
    while words and words[0] in _CONSTITUENT_LEAD_WORDS:
        words.pop(0)
    while words and words[-1] in _CONSTITUENT_TRAIL_STOPWORDS:
        words.pop()
    return " ".join(words[-5:])


def _extract_constituent_aliases(
    text: str, number_unit_match: "re.Match"
) -> tuple[str, ...]:
    """Return generic aliases for the constituent governed by a numeric limit.

    Supports both common regulatory grammars:
      * ``less than 800 mg of Compound-X``
      * ``Compound-X shall not exceed 800 mg``

    Parenthetical aliases are preserved generically, e.g.
    ``epigallocatechin-3-gallate (EGCG)`` yields both the long name and
    ``egcg``.  No constituent name is hard-coded.
    """
    aliases=[]

    # Grammar A: entity follows number+unit.
    tail=text[number_unit_match.end(2):number_unit_match.end(2)+120]
    tail=re.sub(r"^\s*(?:of\s+)?", "", tail)
    # Token-by-token parsing is deliberately used instead of a greedy noun-
    # phrase regex: regulatory prose commonly continues immediately with
    # "per daily portion", "is permitted", "are prohibited", etc.
    tokens=re.findall(r"\([a-z0-9\-]{2,24}\)|[a-z0-9][a-z0-9\-]*", tail)
    phrase_tokens=[]
    alias_token=None
    hard_stops=_CONSTITUENT_TRAIL_STOPWORDS | {
        "is", "are", "was", "were", "shall", "must", "may", "should",
        "permitted", "allowed", "prohibited", "banned", "restricted",
        "required", "require", "requires", "provided", "provide", "provides",
    }
    for tok in tokens:
        if tok.startswith("(") and tok.endswith(")"):
            if phrase_tokens:
                alias_token=tok[1:-1]
            break
        if tok in hard_stops:
            break
        phrase_tokens.append(tok)
        if len(phrase_tokens) >= 5:
            break
    phrase=_clean_constituent_phrase(" ".join(phrase_tokens))
    if phrase:
        aliases.append(phrase)
    if alias_token:
        aliases.append(alias_token.lower())

    # Grammar B: entity precedes the comparator phrase.
    prefix=text[max(0, number_unit_match.start()-140):number_unit_match.start()]
    # Keep the final clause segment, not an earlier unrelated sentence.
    prefix=re.split(r"[.;:]|\b(?:and|but|whereas|while)\b", prefix)[-1].strip()
    # Remove the comparator's auxiliary wording if it lies in the prefix.
    prefix=re.sub(
        r"\b(?:shall|must|may)\s+not\s+exceed\s*$|"
        r"\b(?:not exceeding|no more than|not more than|maximum(?:\s+of)?|"
        r"up to|less than)\s*$",
        "", prefix,
    ).strip()
    # Capture an optional parenthetical alias at the end of the entity phrase.
    pm=re.search(
        r"((?:the\s+)?(?:amount|content|level|quantity|concentration)\s+of\s+)?"
        r"([a-z][a-z0-9\-]*(?:\s+[a-z0-9\-]+){0,5})"
        r"(?:\s*\(([a-z0-9\-]{2,24})\))?\s*$",
        prefix,
    )
    if pm:
        phrase=_clean_constituent_phrase(pm.group(2))
        if phrase:
            aliases.append(phrase)
        if pm.group(3):
            aliases.append(pm.group(3).strip().lower())

    # Stable dedup; reject generic words that are not usable constituent identities.
    generic={
        "", "daily", "portion", "serving", "product", "extract", "preparation",
        "amount", "content", "level", "quantity", "concentration",
    }
    return tuple(dict.fromkeys(a for a in aliases if a not in generic))


def _extract_constituent_name(text: str, number_unit_match: "re.Match") -> str:
    """Backward-compatible primary constituent name."""
    aliases=_extract_constituent_aliases(text, number_unit_match)
    return aliases[0] if aliases else ""


def _find_constituent_amount(
    ctx: str, constituent: str | tuple[str, ...]
) -> Optional["re.Match"]:
    """Find the amount adjacent to the regulated entity, not the first number.

    ``constituent`` may be a primary name or a tuple of generic aliases.
    Both ``900 mg Compound-X`` and ``Compound-X: 900 mg`` are supported.
    """
    aliases=(constituent,) if isinstance(constituent, str) else tuple(constituent)
    for alias in aliases:
        if not alias:
            continue
        const_pattern=re.escape(alias)
        before_re=re.compile(
            _NUMBER_UNIT_RE.pattern + r"\s*(?:of\s+)?" + const_pattern + r"\b"
        )
        m=before_re.search(ctx)
        if m:
            return m
        after_re=re.compile(
            r"\b" + const_pattern + r"\b[\s:(=-]{0,8}" + _NUMBER_UNIT_RE.pattern
        )
        m=after_re.search(ctx)
        if m:
            return m
    return None


@dataclass(frozen=True)
class DoseThresholdFinding:
    limit_value: float
    limit_unit: str
    constituent: str
    actual_value: Optional[float]
    actual_unit: Optional[str]
    violates: Optional[bool]  # None when no candidate value could be found


def detect_dose_threshold_violation(
    finding_text: str,
    candidate_context_text: str = "",
) -> Optional[DoseThresholdFinding]:
    """Detect a "must contain less than X <unit> <constituent>" style
    regulatory dose limit in ``finding_text`` and, if the candidate's
    own declared context states a numeric amount FOR THAT SAME
    CONSTITUENT, determine whether it violates the limit.

    Deliberately generic: it does not know about EGCG, green tea, or
    any other specific compound — it only looks for a generic
    limit-cue-phrase-plus-number-and-unit pattern, reads whichever
    constituent name follows the number in the source text, and
    compares against the number+unit adjacent to that SAME constituent
    name in the candidate's own context (never merely the first
    number+unit anywhere in either text — see
    ``_find_constituent_amount``). Returns None if no limit clause is
    found in ``finding_text`` at all (the ordinary case — most
    regulatory findings are not dose-based).
    """
    text = (finding_text or "").lower()
    if not text:
        return None

    limit_match = None
    comparator = None  # "strict" (actual >= limit) or "inclusive" (actual > limit)
    for regex, kind in (
        (_STRICT_LIMIT_CUE_RE, "strict"),
        (_INCLUSIVE_LIMIT_CUE_RE, "inclusive"),
        (_MORE_THAN_PROHIBITED_RE, "inclusive"),
    ):
        m = regex.search(text)
        if m:
            limit_match = m
            comparator = kind
            break
    if limit_match is None:
        return None

    limit_value = float(limit_match.group(1).replace(",", "."))
    limit_unit = limit_match.group(2)
    limit_mg = _to_mg(limit_value, limit_unit)
    constituent_aliases = _extract_constituent_aliases(text, limit_match)
    constituent = constituent_aliases[0] if constituent_aliases else ""

    ctx = (candidate_context_text or "").lower()
    actual_value = None
    actual_unit = None
    violates = None
    if ctx and limit_mg is not None:
        amount_match = _find_constituent_amount(ctx, constituent_aliases)
        if amount_match is not None:
            actual_value = float(amount_match.group(1).replace(",", "."))
            actual_unit = amount_match.group(2)
            actual_mg = _to_mg(actual_value, actual_unit)
            if actual_mg is not None:
                violates = (
                    actual_mg >= limit_mg if comparator == "strict"
                    else actual_mg > limit_mg
                )

    return DoseThresholdFinding(
        limit_value=limit_value,
        limit_unit=limit_unit,
        constituent=constituent,
        actual_value=actual_value,
        actual_unit=actual_unit,
        violates=violates,
    )
