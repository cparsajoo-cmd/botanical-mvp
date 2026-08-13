"""
Phase 6 — Evidence Confidence, separated from R&D Opportunity (audit 4.16).

IMPORTANT SEMANTIC NOTE
The persisted column name ``Evidence_Confidence`` is retained for backward
compatibility, but the value is an Evidence Strength Index. It is NOT a
probability, calibrated posterior probability, confidence interval, or chance
that the recommendation is correct. User-facing surfaces should label it
"Evidence Strength Index".

WHY THIS IS A SEPARATE MODULE, NOT A CHANGE TO _score_candidate()
_score_candidate() in botanical_rd_candidate_engine.py already computes
one number (R&D_Opportunity_Score) that blends chemical-link strength,
evidence quality, product-development fit, novelty, market signal, and
safety penalties together. That formula is exercised by ~10 existing
regression tests that check both absolute thresholds (e.g. score >= 78
means "Strong") and relative orderings (e.g. a rare compound must
outscore a common one). Reworking that formula to also produce a
second number, in the same change, would mean re-deriving and
re-verifying every one of those tests' expectations at once — a much
bigger, riskier edit than one Phase-6 step should be.

Instead: this module computes Evidence_Confidence independently, from
signals the engine ALREADY computes per-row (Evidence_Hierarchy_Detail,
Evidence_Level, Has_Negative_Evidence — all wired in Phase 4). It's
wired into the engine as a new, additive column, exactly like
Evidence_Hierarchy_Detail and Has_Negative_Evidence were. R&D_Opportunity_Score
itself is untouched by this module.

WEIGHTS (documented here, not scattered across the file — audit 4.16:
"تمام weightها مستند شوند")

Base confidence by evidence hierarchy tier (0-100), following the
exact order audit 4.14 specified — including that traditional-use/
regulatory monograph evidence ranks BELOW in-vitro/mechanistic
evidence in that ordering, which is why its score here is lower too,
even though a regulatory monograph can feel more "official":
    Systematic review / meta-analysis          100
    Clinical trial                               85
    Observational human evidence                 65
    Validated ex vivo / in vivo                  50
    In vitro / mechanistic                       35
    Traditional-use / regulatory monograph       20
    Occurrence / analytical chemistry only       10
    (no tier classified)                          0

Fallback, when the fine-grained classifier found no tier but the
coarser Evidence_Level (Phase-1-era, 5-bucket) DID find something —
this keeps a text that only matched the coarser classifier's broader
terms from being scored as zero-confidence:
    Clinical / human evidence                    55
    Regulatory / monograph evidence               40
    Preclinical / mechanistic evidence            25
    General literature signal                     10
    No direct evidence                             0

Negative-evidence penalty: a documented negative/contradictory finding
(Phase 4, audit 4.15) multiplies the base score by 0.4 — substantially
undercutting confidence without zeroing it outright, since a single
negative finding can coexist with other, separately-positive evidence
about the same plant/compound in the same evidence pool. This is a
documented, named constant (NEGATIVE_EVIDENCE_CONFIDENCE_MULTIPLIER)
so it can be revisited/calibrated later rather than being a magic
number buried in a formula.

TASK 10.1 — METHODOLOGICAL-QUALITY MODIFIERS (additive, optional,
backward-compatible)
Three small, named, capped point additions on top of the base
hierarchy-tier score, detected from the same free-text evidence
string the engine already classifies for Evidence_Hierarchy_Detail —
no new data source, no new column, no second confidence score. These
answer a question the tier lookup above does NOT: two clinical trials
both classified as "Clinical trial" can differ hugely in methodological
strength (blinded/placebo-controlled/large N vs. none of those) — the
tier alone can't see that difference, these modifiers can.

Applied to `base` BEFORE the negative-evidence multiplier — a study's
methodological quality doesn't depend on whether its outcome was
positive or negative, so a well-blinded, placebo-controlled, large-N
trial that FAILED still earns these modifiers, and is then downweighted
overall for being a negative finding, exactly as before this task.

Only applied when base > 0 (i.e. only refines confidence for evidence
that already earned a real tier) — never used to manufacture
confidence out of a text with no classified evidence tier at all.

Sample-size modifier (SAMPLE_SIZE_CONFIDENCE_MODIFIERS): detected via
a plain-text pattern ("n = 200", "200 patients", "200 participants",
"sample size of 200") — same negation-agnostic phrase-matching style
already used by evidence_hierarchy_classifier.py/negative_evidence_classifier.py.
    >= 200 participants     +6
    >= 100 participants     +4
    >= 30 participants      +2
    (no size detected, or below 30)  +0

Blinding modifier (BLINDING_CONFIDENCE_MODIFIERS): detects the
strongest blinding level mentioned.
    Double-blind / triple-blind      +5
    Single-blind                     +3
    (no blinding mentioned)          +0

Placebo-control modifier (PLACEBO_CONTROL_CONFIDENCE_MODIFIER):
    Placebo-controlled mentioned     +4
    (not mentioned)                  +0

The three modifiers are summed and capped at
MAX_METHODOLOGICAL_MODIFIER_TOTAL (15) before being added to `base` —
a text that happens to match many keywords cannot let these modifiers
dominate the tier-based score they're meant to only refine. The final
result is still clamped to [0, 100], exactly as before this task.

THESE THREE MODIFIERS' POINT VALUES ARE A FIRST DRAFT, NOT VALIDATED
— same status as every other weight in this module (see WHAT THIS
MODULE DOES NOT DO below). They are reasoned, documented, and
reversible, not calibrated against expert-reviewed cases.

WHAT THIS MODULE DOES NOT DO (yet)
- Not calibrated against expert-reviewed use cases (audit 4.16's
  "score را با expert-reviewed use cases calibrate شود" and "sensitivity
  analysis انجام شود") — the numbers above, including the Task 10.1
  methodological-quality modifiers, are a first, documented,
  reversible starting point, not a validated model.
- Does not change Decision_Class. See
  confidence_adjusted_framing_note() for the one place this DOES
  surface in decision framing — as an additive note, not a change to
  the existing Decision_Class value.
- The sample-size/blinding/placebo detectors are plain-text pattern
  matches on the same evidence text already classified elsewhere in
  this pipeline — not a structured extraction of an actual reported
  N, and not a true GRADE-style risk-of-bias assessment (randomization
  adequacy, allocation concealment, selective reporting are NOT
  assessed here — see the Task 10 audit for that gap).
"""

from __future__ import annotations

import re
from typing import Optional

CONFIDENCE_BY_HIERARCHY_TIER: dict[Optional[str], float] = {
    "Systematic review / meta-analysis": 100,
    "Clinical trial": 85,
    "Observational human evidence": 65,
    "Validated ex vivo / in vivo": 50,
    "In vitro / mechanistic": 35,
    "Traditional-use / regulatory monograph": 20,
    "Occurrence / analytical chemistry only": 10,
}

CONFIDENCE_BY_EVIDENCE_LEVEL_FALLBACK: dict[str, float] = {
    "Clinical / human evidence": 55,
    "Regulatory / monograph evidence": 40,
    "Preclinical / mechanistic evidence": 25,
    "General literature signal": 10,
    "No direct evidence": 0,
}

NEGATIVE_EVIDENCE_CONFIDENCE_MULTIPLIER = 0.4

# Below this Evidence_Confidence, a high R&D_Opportunity_Score must not
# be presented as a strong recommendation without an explicit note —
# audit 4.16's "opportunity بالا ولی evidence پایین باید Exploratory
# باشد". Both thresholds are named constants, not magic numbers.
LOW_CONFIDENCE_THRESHOLD = 30
HIGH_OPPORTUNITY_THRESHOLD = 62

# ---------------------------------------------------------------------
# Phase 1 follow-up — Study_Design / Evidence_Direction /
# Evidence_Applicability / is_completed_study awareness
# (evidence_interpretation.py). Additive only: every constant below is
# used ONLY when a caller explicitly supplies the corresponding new
# keyword argument to compute_evidence_confidence(); a caller that
# doesn't (every pre-existing caller) gets the exact same return value
# as before this section existed.
#
# DIRECTION_NOT_POSITIVE_CONFIDENCE_MULTIPLIER: when the underlying
# evidence's reported outcome direction is "null", "negative", or
# "unclear", confidence must not be inflated purely because the text
# also contains a study-type phrase like "clinical trial" — this
# multiplier undercuts the tier-based base score the same way
# NEGATIVE_EVIDENCE_CONFIDENCE_MULTIPLIER already does for the older,
# coarser Has_Negative_Evidence signal. Only applied when
# has_negative_evidence hasn't already reduced this exact base score,
# so a genuinely negative finding is never double-penalized by two
# independent classifiers agreeing with each other.
DIRECTION_NOT_POSITIVE_CONFIDENCE_MULTIPLIER = 0.5

# CONTEXTUAL_OR_FUTURE_CONFIDENCE_CAP /
# NOT_COMPLETED_STUDY_CONFIDENCE_CAP / PROTOCOL_STUDY_DESIGN_CONFIDENCE_CAP:
# a future/planned mention, an incomplete study, or a trial
# protocol/registration record is not entitled to more confidence than
# the weakest hierarchy tier that actually reports real evidence
# ("Occurrence / analytical chemistry only" = 10 above) — these three
# checks are deliberately redundant (any one of
# Evidence_Applicability == "contextual_or_future",
# is_completed_study is False, or
# Study_Design == "clinical_trial_protocol" is sufficient on its own)
# so a contextual/future mention cannot slip past this cap via only
# one of the three signals being supplied.
CONTEXTUAL_OR_FUTURE_CONFIDENCE_CAP = 10.0
NOT_COMPLETED_STUDY_CONFIDENCE_CAP = 10.0
PROTOCOL_STUDY_DESIGN_CONFIDENCE_CAP = 10.0

_DIRECTION_NOT_POSITIVE_VALUES = {"null", "negative", "unclear"}

# Phase 1 follow-up — direct use of the already-interpreted
# Evidence_Quality value. These factors are intentionally small and only
# affect Evidence_Confidence; they never alter R&D_Opportunity_Score,
# evidence contribution, or Decision_Class. Unknown/unrecognised values
# preserve backward-compatible behaviour.
QUALITY_CONFIDENCE_MULTIPLIER = {
    "high": 1.0,
    "moderate": 0.95,
    "low": 0.85,
    "unknown": 1.0,
}


# =====================================================================
# Task 10.1 — methodological-quality modifiers. See the module
# docstring's "TASK 10.1" section for the full reasoning; this is the
# implementation of exactly the three modifiers documented there.
# =====================================================================

# Ordered largest to smallest, so the FIRST pattern that matches wins —
# same "strongest tier present wins" principle
# evidence_hierarchy_classifier.py already uses, applied here to
# sample-size bands instead of study-type tiers.
SAMPLE_SIZE_CONFIDENCE_MODIFIERS: list[tuple[int, float]] = [
    (200, 6),
    (100, 4),
    (30, 2),
]

# Matches "n = 200", "n=200", "200 patients", "200 participants",
# "200 subjects", "sample size of 200" — deliberately simple patterns
# (plain-text, not a structured Sample_Size field extraction) mirroring
# the phrase-matching style already used elsewhere in this pipeline
# (evidence_hierarchy_classifier.py, negative_evidence_classifier.py).
_SAMPLE_SIZE_PATTERNS = [
    re.compile(r"\bn\s*=\s*(\d+)\b", re.IGNORECASE),
    re.compile(r"\bsample size of (\d+)\b", re.IGNORECASE),
    re.compile(r"\b(\d+)\s*(?:patients|participants|subjects|volunteers)\b", re.IGNORECASE),
]

BLINDING_CONFIDENCE_MODIFIERS: dict[str, float] = {
    "double_or_triple_blind": 5,
    "single_blind": 3,
}

_DOUBLE_TRIPLE_BLIND_PATTERN = re.compile(
    r"\b(double|triple)[\s-]blind(?:ed)?\b", re.IGNORECASE,
)
_SINGLE_BLIND_PATTERN = re.compile(r"\bsingle[\s-]blind(?:ed)?\b", re.IGNORECASE)

PLACEBO_CONTROL_CONFIDENCE_MODIFIER = 4

_PLACEBO_CONTROL_PATTERN = re.compile(
    r"\bplacebo[\s-]controlled\b|\bvs\.?\s+placebo\b|\bplacebo[\s-]controlled\s+trial\b",
    re.IGNORECASE,
)

# All three modifiers together cannot outweigh the tier-based hierarchy
# score they're meant to only refine — see module docstring.
MAX_METHODOLOGICAL_MODIFIER_TOTAL = 15


def _detect_sample_size_modifier(evidence_text: Optional[str]) -> float:
    """Returns the largest sample-size band modifier a plain-text
    number match supports, or 0 if no pattern matches or the matched
    number is below the smallest band. Never raises on malformed text."""
    if not evidence_text:
        return 0

    largest_n = 0
    for pattern in _SAMPLE_SIZE_PATTERNS:
        for match in pattern.finditer(evidence_text):
            try:
                value = int(match.group(1))
            except (ValueError, IndexError):
                continue
            largest_n = max(largest_n, value)

    for threshold, modifier in SAMPLE_SIZE_CONFIDENCE_MODIFIERS:
        if largest_n >= threshold:
            return modifier
    return 0


def _detect_blinding_modifier(evidence_text: Optional[str]) -> float:
    """Returns the strongest blinding-level modifier mentioned in the
    text — double/triple-blind beats single-blind if both happen to
    appear (e.g. text describing more than one study)."""
    if not evidence_text:
        return 0
    if _DOUBLE_TRIPLE_BLIND_PATTERN.search(evidence_text):
        return BLINDING_CONFIDENCE_MODIFIERS["double_or_triple_blind"]
    if _SINGLE_BLIND_PATTERN.search(evidence_text):
        return BLINDING_CONFIDENCE_MODIFIERS["single_blind"]
    return 0


def _detect_placebo_control_modifier(evidence_text: Optional[str]) -> float:
    if not evidence_text:
        return 0
    if _PLACEBO_CONTROL_PATTERN.search(evidence_text):
        return PLACEBO_CONTROL_CONFIDENCE_MODIFIER
    return 0


def _methodological_quality_modifier(evidence_text: Optional[str]) -> float:
    """Sums the three Task 10.1 modifiers, capped at
    MAX_METHODOLOGICAL_MODIFIER_TOTAL. This is the ONLY entry point
    compute_evidence_confidence() calls — the three detector functions
    above are each independently testable, but this is what callers of
    this module beyond compute_evidence_confidence() itself should use
    if they ever need the combined modifier value."""
    total = (
        _detect_sample_size_modifier(evidence_text)
        + _detect_blinding_modifier(evidence_text)
        + _detect_placebo_control_modifier(evidence_text)
    )
    return min(total, MAX_METHODOLOGICAL_MODIFIER_TOTAL)


def compute_evidence_confidence(
    evidence_hierarchy_detail: Optional[str],
    evidence_level: str,
    has_negative_evidence: bool,
    evidence_text: Optional[str] = None,
    evidence_direction: Optional[str] = None,
    evidence_applicability: Optional[str] = None,
    is_completed_study: Optional[bool] = None,
    study_design: Optional[str] = None,
    evidence_quality: Optional[str] = None,
) -> float:
    """Returns a 0-100 confidence score. See module docstring for the
    documented weight tables this is built from.

    evidence_text (Task 10.1, optional, default None — no change to
    any existing caller's behavior): the same free-text evidence
    string already classified for Evidence_Hierarchy_Detail. When
    provided AND a real hierarchy/level tier was found (base > 0), the
    sample-size/blinding/placebo-control modifiers documented in the
    module docstring's "TASK 10.1" section are added before the
    negative-evidence multiplier. When omitted, or when no real tier
    was classified, this function's return value is unchanged from
    its pre-Task-10.1 behavior.

    evidence_direction / evidence_applicability / is_completed_study /
    study_design / evidence_quality (Phase 1 follow-up, all optional,
    default None — no
    change to any existing caller's behavior unless supplied): the
    matching fields from evidence_interpretation.interpret_evidence().
    When supplied, these stop Evidence_Confidence from being inflated
    by a bare study-type phrase ("clinical trial") when the underlying
    evidence's actual reported direction is null/negative/unclear, and
    cap confidence near the weakest real-evidence tier for any
    future/planned/protocol/registration-only mention. See the
    constants immediately above this function for the exact documented
    values.
    """
    base = CONFIDENCE_BY_HIERARCHY_TIER.get(evidence_hierarchy_detail)
    if base is None:
        base = CONFIDENCE_BY_EVIDENCE_LEVEL_FALLBACK.get(evidence_level, 0)

    if base > 0 and evidence_text:
        base += _methodological_quality_modifier(evidence_text)

    if has_negative_evidence:
        base = base * NEGATIVE_EVIDENCE_CONFIDENCE_MULTIPLIER
    elif evidence_direction in _DIRECTION_NOT_POSITIVE_VALUES:
        # Only reached when the older Has_Negative_Evidence classifier
        # didn't already reduce this base score — avoids double-
        # penalizing a finding both classifiers independently agree is
        # not positive.
        base = base * DIRECTION_NOT_POSITIVE_CONFIDENCE_MULTIPLIER

    if evidence_applicability == "contextual_or_future":
        base = min(base, CONTEXTUAL_OR_FUTURE_CONFIDENCE_CAP)
    if is_completed_study is False:
        base = min(base, NOT_COMPLETED_STUDY_CONFIDENCE_CAP)
    if study_design == "clinical_trial_protocol":
        base = min(base, PROTOCOL_STUDY_DESIGN_CONFIDENCE_CAP)

    if evidence_quality is not None:
        base *= QUALITY_CONFIDENCE_MULTIPLIER.get(
            str(evidence_quality).strip().lower(), 1.0
        )

    return round(min(100.0, max(0.0, base)), 1)


def methodological_quality_signals(evidence_text: Optional[str]) -> dict:
    """Task 2 (GRADE-style certainty grading) — exposes WHICH of the
    Task 10.1 methodological markers fired for `evidence_text`, not
    just their summed point total. Read-only wrapper around the same
    _detect_blinding_modifier()/_detect_placebo_control_modifier()/
    _detect_sample_size_modifier() detectors _methodological_quality_modifier()
    above already calls — no new pattern-matching, no change to
    compute_evidence_confidence()'s behavior or return value for any
    existing caller.

    Added so grade_certainty_classifier.py's risk-of-bias/imprecision
    domains can reuse these exact, already-tested detectors (rather
    than re-implementing similar-but-subtly-different regexes) without
    grade_certainty_classifier.py reaching into this module's
    underscore-prefixed internals directly.

    Returns a dict with three booleans:
      - "blinded": single- or double/triple-blind mentioned
      - "placebo_controlled": placebo-controlled design mentioned
      - "large_sample": a sample-size mention of >= 100 participants
        (the SAMPLE_SIZE_CONFIDENCE_MODIFIERS "100" band or above) was
        matched — deliberately the >=100 band, not >=30, since
        grade_certainty_classifier.py's imprecision domain treats
        anything below 100 as an imprecision concern per GRADE's own
        cautious-by-default convention for unclear/small samples.
    """
    return {
        "blinded": _detect_blinding_modifier(evidence_text) > 0,
        "placebo_controlled": _detect_placebo_control_modifier(evidence_text) > 0,
        "large_sample": _detect_sample_size_modifier(evidence_text) >= 4,
    }


def confidence_adjusted_framing_note(
    rd_opportunity_score: Optional[float],
    evidence_confidence: Optional[float],
) -> Optional[str]:
    """Returns an explicit warning string when a candidate has a high
    opportunity score but low evidence confidence — the exact mismatch
    audit 4.16 named. Returns None when no warning applies. This is
    surfaced as an ADDITIONAL column (Confidence_Note) alongside the
    existing Decision_Class, not a replacement for it — changing what
    Decision_Class itself means is a separate, larger migration."""
    if rd_opportunity_score is None or evidence_confidence is None:
        return None
    if (
        evidence_confidence < LOW_CONFIDENCE_THRESHOLD
        and rd_opportunity_score >= HIGH_OPPORTUNITY_THRESHOLD
    ):
        return (
            f"Exploratory — R&D_Opportunity_Score ({rd_opportunity_score}) is high, "
            f"but Evidence_Confidence ({evidence_confidence}) is low. Treat as an "
            f"exploratory hypothesis, not a strong recommendation, until stronger "
            f"evidence is available."
        )
    return None
