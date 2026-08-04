"""Phase 1 — Evidence Direction / Study Design separation.

WHAT THIS FIXES
_evidence_level() in botanical_rd_candidate_engine.py classifies a piece
of evidence text purely by which STUDY-DESIGN phrases it contains
("clinical trial", "randomized controlled trial", ...). It has no
concept at all of what that study actually FOUND. As a result, a
negative RCT ("failed to demonstrate efficacy"), a null RCT ("no
significant difference from placebo"), a merely-planned/future trial
("a clinical trial is needed to evaluate efficacy"), and a trial
protocol/registration record all currently classify identically to a
genuinely positive completed RCT and contribute the SAME "Clinical /
human evidence" weight to R&D_Opportunity_Score (24 points, at the
scoring_config default) — see the Phase 1 audit that produced this
module for direct proof runs against the real code path.

This module introduces two independent concepts for a piece of
evidence text:

  Study_Design       -- WHAT KIND of study/record this is (RCT, generic
                         clinical trial, trial protocol, review/
                         secondary-source mention, animal study, in
                         vitro study, or unspecified).
  Evidence_Direction  -- WHAT THE STUDY FOUND, independent of design:
                         "positive", "negative", "null", "mixed", or
                         "unclear".

It also derives:
  Evidence_Quality        -- a coarse methodological-strength signal
                              ("high" / "moderate" / "low" / "unknown"),
                              used only to SCALE (never invert) a
                              contribution.
  Evidence_Applicability  -- "direct_reported" for a completed study
                              actually being reported, or
                              "contextual_or_future" for a future/
                              planned/protocol/registration-only
                              mention that is NOT completed clinical
                              evidence.
  is_completed_study      -- convenience bool, True iff applicability
                              is "direct_reported".
  contribution             -- the points this evidence should contribute
                              to the "Clinical / human evidence" tier of
                              R&D_Opportunity_Score, computed from a
                              single, documented, testable table (see
                              DIRECTION_CONTRIBUTION_RATIO below) rather
                              than scattered literals.

WHAT THIS MODULE DOES NOT DO
- It does not decide Evidence_Level (the engine's existing coarse
  study-TYPE tier: "Clinical / human evidence" / "Regulatory /
  monograph evidence" / "Preclinical / mechanistic evidence" /
  "General literature signal" / "No direct evidence") — that
  classification is untouched and still lives in
  botanical_rd_candidate_engine.py::_evidence_level(). This module only
  supplies the DIRECTION-aware contribution that the engine applies on
  top of that tier when the tier is "Clinical / human evidence".
- It does not deduplicate evidence, build a unified Evidence Object, or
  touch anything about Regulatory / Preclinical / General-literature
  tier weights — explicitly out of scope for Phase 1.
- It is a bounded, transparent keyword/phrase heuristic, not an NLP
  model. Like every other free-text classifier already in this
  codebase (evidence_hierarchy_classifier.py,
  negative_evidence_classifier.py, regulatory_barrier_classifier.py),
  it is reasoned and documented, not validated against an
  expert-reviewed corpus.
- Standard library only (re, dataclasses, typing) — no new dependency.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

# ---------------------------------------------------------------------
# Study_Design values
# ---------------------------------------------------------------------
STUDY_DESIGN_RCT = "randomized_controlled_trial"
STUDY_DESIGN_CLINICAL_TRIAL_PROTOCOL = "clinical_trial_protocol"
STUDY_DESIGN_CLINICAL_TRIAL = "clinical_trial"
STUDY_DESIGN_REVIEW = "review"
STUDY_DESIGN_ANIMAL_STUDY = "animal_study"
STUDY_DESIGN_IN_VITRO_STUDY = "in_vitro_study"
STUDY_DESIGN_UNSPECIFIED = "unspecified"

# ---------------------------------------------------------------------
# Evidence_Direction values (the only five allowed)
# ---------------------------------------------------------------------
DIRECTION_POSITIVE = "positive"
DIRECTION_NEGATIVE = "negative"
DIRECTION_NULL = "null"
DIRECTION_MIXED = "mixed"
DIRECTION_UNCLEAR = "unclear"

# ---------------------------------------------------------------------
# Evidence_Quality / Evidence_Applicability values
# ---------------------------------------------------------------------
QUALITY_HIGH = "high"
QUALITY_MODERATE = "moderate"
QUALITY_LOW = "low"
QUALITY_UNKNOWN = "unknown"

APPLICABILITY_DIRECT = "direct_reported"
APPLICABILITY_CONTEXTUAL_OR_FUTURE = "contextual_or_future"

# ---------------------------------------------------------------------
# Single, documented, testable contribution table (audit requirement:
# "این مقادیر را در یک محل مشخص و قابل تست تعریف کن؛ نه به‌صورت اعداد
# پراکنده در چند تابع"). Expressed as a RATIO of the engine's existing
# Clinical-evidence base weight (scoring_config.evidence_clinical,
# default 24) rather than a hardcoded 24/6/0/-12, so this stays correct
# if that base weight is ever recalibrated:
#
#   positive -> 1.00  (24 at the default weight)
#   mixed    -> 0.25  ( 6 at the default weight)
#   null     -> 0.00  ( 0 )
#   unclear  -> 0.00  ( 0 )
#   negative -> -0.50 (-12 at the default weight)
# ---------------------------------------------------------------------
DEFAULT_CLINICAL_WEIGHT = 24.0

DIRECTION_CONTRIBUTION_RATIO = {
    DIRECTION_POSITIVE: 1.00,
    DIRECTION_MIXED: 0.25,
    DIRECTION_NULL: 0.00,
    DIRECTION_UNCLEAR: 0.00,
    DIRECTION_NEGATIVE: -0.50,
}

# Quality/applicability are only allowed to SCALE the magnitude of a
# contribution toward zero — never to change its sign, and never to
# turn a zero (null/unclear) or a future/contextual mention positive.
QUALITY_FACTOR = {
    QUALITY_HIGH: 1.0,
    QUALITY_MODERATE: 1.0,
    QUALITY_LOW: 0.6,
    QUALITY_UNKNOWN: 1.0,
}

APPLICABILITY_FACTOR = {
    APPLICABILITY_DIRECT: 1.0,
    # Belt-and-suspenders: even if a future/protocol/registration-only
    # mention were ever misdetected as having a direction, this factor
    # alone still forces its Clinical-evidence contribution to zero.
    APPLICABILITY_CONTEXTUAL_OR_FUTURE: 0.0,
}


def _norm(text: Optional[str]) -> str:
    if not text:
        return ""
    return str(text).lower()


def _find(text: str, phrases: List[str]) -> Optional[str]:
    """Return the first phrase (word-boundary safe, simple-plural
    tolerant) found in `text`, or None. Order of `phrases` is the match
    priority."""
    for phrase in phrases:
        words = phrase.split(" ")
        if len(words) == 1:
            body = re.escape(words[0]) + "s?"
        else:
            body = r"\s+".join(re.escape(w) for w in words[:-1]) + r"\s+" + re.escape(words[-1]) + "s?"
        if re.search(r"\b" + body + r"\b", text):
            return phrase
    return None


def _has(text: str, phrases: List[str]) -> bool:
    return _find(text, phrases) is not None


# A short, local negation-cue list (deliberately NOT imported from
# scientific_phrase_matcher.py — this module must stay dependency-free
# and standard-library only per Phase 1 scope). Used only to stop a
# NEGATED positive-outcome phrase ("did not demonstrate significant
# improvement") from being counted as positive.
_NEGATION_CUES = ("did not ", "does not ", "was not ", "were not ", "no ", "not ", "failed to ")
_NEGATION_LOOKBACK = 30


def _negated_positive_hits(text: str, phrases: List[str]) -> List[str]:
    """Positive-cue phrases that occur but are immediately preceded (in
    a short word window) by a negation cue — e.g. "did not demonstrate
    significant improvement". These are excluded from the positive
    bucket and instead treated as a null-direction signal."""
    hits = []
    for phrase in phrases:
        words = phrase.split(" ")
        if len(words) == 1:
            body = re.escape(words[0]) + "s?"
        else:
            body = r"\s+".join(re.escape(w) for w in words[:-1]) + r"\s+" + re.escape(words[-1]) + "s?"
        pattern = re.compile(r"\b" + body + r"\b")
        for match in pattern.finditer(text):
            window_start = max(0, match.start() - _NEGATION_LOOKBACK)
            preceding = text[window_start:match.start()]
            if any(cue in preceding for cue in _NEGATION_CUES):
                hits.append(phrase)
    return hits


def _positive_hits(text: str, phrases: List[str]) -> List[str]:
    """Positive-cue phrases that are present and NOT negated."""
    negated = set(_negated_positive_hits(text, phrases))
    hits = []
    for phrase in phrases:
        words = phrase.split(" ")
        if len(words) == 1:
            body = re.escape(words[0]) + "s?"
        else:
            body = r"\s+".join(re.escape(w) for w in words[:-1]) + r"\s+" + re.escape(words[-1]) + "s?"
        pattern = re.compile(r"\b" + body + r"\b")
        for match in pattern.finditer(text):
            if phrase in negated:
                continue
            window_start = max(0, match.start() - _NEGATION_LOOKBACK)
            preceding = text[window_start:match.start()]
            if any(cue in preceding for cue in _NEGATION_CUES):
                continue
            hits.append(phrase)
            break
    return hits


# ---------------------------------------------------------------------
# Phrase tables
# ---------------------------------------------------------------------

POSITIVE_PHRASES = [
    "demonstrated significant improvement",
    "significantly improved",
    "was effective",
    "were effective",
    "superior to placebo",
    "clinically meaningful benefit",
    "showed significant improvement",
    "significant improvement",
    "outcomes improved",
    "outcome improved",
    "symptoms improved",
    "symptom improved",
    "improved significantly",
]

# Bounded regex catch-all for the common "found/showed/demonstrated
# significant <outcome noun> effects/benefit/..." phrasing, which is
# not expressible as one of the fixed multi-word POSITIVE_PHRASES above
# (the outcome noun in between varies — "hepatoprotective effects",
# "anti-inflammatory benefit", etc.). Bounded to at most 6 words between
# "significant" and the outcome word, none of which may be "no"/"not",
# so this cannot accidentally match "found no significant difference"
# (already handled, correctly, by NULL_PHRASES) or any other negated
# span.
_POSITIVE_OUTCOME_REGEX = re.compile(
    r"\b(?:found|showed|demonstrated|reported)\s+significant\s+"
    r"(?:(?!\b(?:no|not)\b)\S+\s+){0,6}"
    r"(?:effects?|benefits?|improvements?|efficacy|response|responses)\b"
)


def _positive_regex_hit(text: str) -> Optional[str]:
    """Returns the matched span if _POSITIVE_OUTCOME_REGEX fires and is
    not itself preceded by a negation cue in a short window; else
    None."""
    match = _POSITIVE_OUTCOME_REGEX.search(text)
    if not match:
        return None
    window_start = max(0, match.start() - _NEGATION_LOOKBACK)
    preceding = text[window_start:match.start()]
    if any(cue in preceding for cue in _NEGATION_CUES):
        return None
    return match.group(0)

NULL_PHRASES = [
    "no significant difference",
    "no statistically significant difference",
    "not statistically significant",
    "failed to reach statistical significance",
    "comparable to placebo",
    "no meaningful change",
    "no significant improvement",
    "no difference from placebo",
    "not significant",
]

NEGATIVE_PHRASES = [
    "failed to demonstrate efficacy",
    "failed to demonstrate benefit",
    "trial failed",
    "worsened outcomes",
    "inferior to placebo",
    "associated with harm",
    "increased adverse outcomes",
    "evidence against efficacy",
    "did not meet the primary endpoint",
    "failed to meet its primary endpoint",
]

# Study-design phrase tables, checked in priority order (protocol and
# review are checked before RCT/clinical-trial so that a protocol
# record or a review-of-another-trial is never misclassified as the
# trial itself — per the required "review mentioning another trial"
# behavior).
_PROTOCOL_PHRASES = [
    "clinical trial protocol",
    "study protocol",
    "trial protocol",
    "protocol paper",
    "protocol article",
    "registered protocol",
    "registered clinical trial protocol",
    "registration-only record",
    "registered on clinicaltrials.gov",
    "trial registration",
    "study registration",
    "protocol for a randomized controlled trial",
    "protocol for a randomised controlled trial",
    "protocol for a randomized trial",
    "protocol for a randomised trial",
    "protocol for an rct",
    "protocol for a trial",
]

_REVIEW_PHRASES = [
    "systematic review",
    "literature review",
    "narrative review",
    "this review discusses",
    "this review",
    "meta-analysis",
]

_RCT_PHRASES = [
    "randomized controlled trial",
    "randomised controlled trial",
    "randomized placebo-controlled trial",
    "randomised placebo-controlled trial",
    "randomized double-blind trial",
    "randomised double-blind trial",
    "double-blind placebo-controlled trial",
    "double-blind randomized trial",
    "double-blind randomised trial",
    "double blind randomized trial",
    "double blind randomised trial",
    "double-blind randomized clinical trial",
    "double-blind randomised clinical trial",
    "randomized trial",
    "randomised trial",
]

_CLINICAL_TRIAL_PHRASES = [
    "clinical trial",
    "clinical study",
    "human trial",
    "human study",
    "the trial",
    "primary endpoint",
    "secondary outcome",
    "secondary outcomes",
    "one trial",
    "another trial",
    "a trial",
    "trial",
]

_ANIMAL_PHRASES = [
    "animal model", "animal study", "mouse model", "rat model",
    "murine model",
]

_IN_VITRO_PHRASES = [
    "in vitro", "in-vitro", "cell culture study",
]

# Future / not-yet-conducted / recommendation-only phrasing. Any of
# these anywhere in the text forces Evidence_Applicability to
# "contextual_or_future" regardless of which study-design phrase also
# matched, and forces the Clinical-evidence contribution to zero via
# APPLICABILITY_FACTOR.
_FUTURE_OR_PLANNED_PHRASES = [
    "trial is needed", "trials are needed", "study is needed",
    "studies are needed", "clinical trial is needed",
    "future clinical trial", "future trial", "future study",
    "planned randomized trial", "planned clinical trial",
    "planned trial", "is planned", "are planned",
    "will be conducted", "to be conducted",
    "recommend conducting", "recommended to conduct",
    "recommendation to conduct",
    "further clinical trials are needed",
    "additional trials are needed",
    "more research is needed", "further research is needed",
    "warrants further investigation", "warrants investigation",
]

_ONGOING_NO_RESULT_PHRASES = [
    "ongoing trial", "trial is ongoing", "currently underway",
    "study is ongoing", "is currently recruiting",
]

_PROTOCOL_APPLICABILITY_PHRASES = _PROTOCOL_PHRASES + [
    "study protocol", "trial registration",
]

# A sentence that only says clinical evidence is insufficient/lacking,
# without reporting any actual study, is not completed clinical
# evidence either.
_NO_EVIDENCE_SENTENCE_PHRASES = [
    "clinical evidence is insufficient",
    "clinical evidence is currently insufficient",
    "insufficient clinical evidence",
    "clinical evidence is limited",
    "clinical evidence remains limited",
    "lack of clinical evidence",
    "no clinical evidence",
]

_LOW_QUALITY_PHRASES = [
    "small sample size", "small sample", "pilot study",
    "case report", "preliminary", "underpowered", "anecdotal",
    "open-label", "uncontrolled", "single case",
]

_HIGH_QUALITY_PHRASES = [
    "double-blind", "double blind", "placebo-controlled",
    "placebo controlled", "multi-center", "multicenter",
    "large sample", "randomized controlled",
]


@dataclass
class EvidenceInterpretation:
    study_design: str
    evidence_direction: str
    evidence_quality: str
    evidence_applicability: str
    is_completed_study: bool
    contribution: float
    contribution_ratio: float
    matched_positive: List[str] = field(default_factory=list)
    matched_null: List[str] = field(default_factory=list)
    matched_negative: List[str] = field(default_factory=list)


def classify_study_design(text: str) -> str:
    """WHAT kind of study/record this text is — independent of
    Evidence_Direction. Checked in priority order: protocol > review >
    RCT > generic clinical trial > animal > in vitro > unspecified."""
    norm = _norm(text)
    if not norm:
        return STUDY_DESIGN_UNSPECIFIED
    if _has(norm, _PROTOCOL_PHRASES):
        return STUDY_DESIGN_CLINICAL_TRIAL_PROTOCOL
    if _has(norm, _REVIEW_PHRASES):
        return STUDY_DESIGN_REVIEW
    if _has(norm, _RCT_PHRASES):
        return STUDY_DESIGN_RCT
    if _has(norm, _CLINICAL_TRIAL_PHRASES):
        return STUDY_DESIGN_CLINICAL_TRIAL
    if _has(norm, _ANIMAL_PHRASES):
        return STUDY_DESIGN_ANIMAL_STUDY
    if _has(norm, _IN_VITRO_PHRASES):
        return STUDY_DESIGN_IN_VITRO_STUDY
    return STUDY_DESIGN_UNSPECIFIED


def classify_evidence_direction(text: str):
    """Returns (direction, positive_hits, null_hits, negative_hits)."""
    norm = _norm(text)
    if not norm:
        return DIRECTION_UNCLEAR, [], [], []

    positive_hits = _positive_hits(norm, POSITIVE_PHRASES)
    negated_positive = _negated_positive_hits(norm, POSITIVE_PHRASES)

    regex_hit = _positive_regex_hit(norm)
    if regex_hit and regex_hit not in positive_hits:
        positive_hits = positive_hits + [regex_hit]

    null_hits = [p for p in NULL_PHRASES if _has(norm, [p])]
    negative_hits = [p for p in NEGATIVE_PHRASES if _has(norm, [p])]

    # A negated positive-outcome statement ("did not demonstrate
    # significant improvement") reads as a null finding for direction
    # purposes, unless an explicit negative phrase also independently
    # fired.
    if negated_positive and not null_hits and not negative_hits:
        null_hits = list(negated_positive)

    has_positive = bool(positive_hits)
    has_null = bool(null_hits)
    has_negative = bool(negative_hits)

    if has_positive and (has_null or has_negative):
        return DIRECTION_MIXED, positive_hits, null_hits, negative_hits
    if has_positive:
        return DIRECTION_POSITIVE, positive_hits, null_hits, negative_hits
    if has_negative:
        return DIRECTION_NEGATIVE, positive_hits, null_hits, negative_hits
    if has_null:
        return DIRECTION_NULL, positive_hits, null_hits, negative_hits
    return DIRECTION_UNCLEAR, positive_hits, null_hits, negative_hits


def classify_evidence_applicability(text: str, study_design: str) -> str:
    """"direct_reported" for a completed study actually being reported;
    "contextual_or_future" for a future/planned/protocol/registration-
    only/recommendation-only mention, or a sentence that only laments
    insufficient clinical evidence without reporting a study."""
    norm = _norm(text)
    if not norm:
        return APPLICABILITY_CONTEXTUAL_OR_FUTURE
    if study_design == STUDY_DESIGN_CLINICAL_TRIAL_PROTOCOL:
        return APPLICABILITY_CONTEXTUAL_OR_FUTURE
    if _has(norm, _FUTURE_OR_PLANNED_PHRASES):
        return APPLICABILITY_CONTEXTUAL_OR_FUTURE
    if _has(norm, _ONGOING_NO_RESULT_PHRASES):
        return APPLICABILITY_CONTEXTUAL_OR_FUTURE
    if _has(norm, _NO_EVIDENCE_SENTENCE_PHRASES):
        return APPLICABILITY_CONTEXTUAL_OR_FUTURE
    return APPLICABILITY_DIRECT


def classify_evidence_quality(text: str, study_design: str) -> str:
    norm = _norm(text)
    if not norm or study_design == STUDY_DESIGN_UNSPECIFIED:
        return QUALITY_UNKNOWN
    if _has(norm, _LOW_QUALITY_PHRASES):
        return QUALITY_LOW
    if _has(norm, _HIGH_QUALITY_PHRASES):
        return QUALITY_HIGH
    return QUALITY_MODERATE


def interpret_evidence(
    text: Optional[str],
    clinical_weight: float = DEFAULT_CLINICAL_WEIGHT,
) -> EvidenceInterpretation:
    """Single entry point: interprets one evidence text and returns a
    Study_Design / Evidence_Direction / Evidence_Quality /
    Evidence_Applicability / contribution bundle, all independent of
    each other except that `contribution` is derived FROM direction,
    quality, and applicability.

    `clinical_weight` is the base "Clinical / human evidence" weight
    (scoring_config.evidence_clinical in the engine, default 24) that
    `contribution` is scaled from via DIRECTION_CONTRIBUTION_RATIO.
    Callers outside the Clinical tier (Regulatory / Preclinical /
    General literature) are unaffected by this module — Phase 1 is
    scoped to the Clinical-evidence tier only.
    """
    study_design = classify_study_design(text)
    direction, pos_hits, null_hits, neg_hits = classify_evidence_direction(text)
    applicability = classify_evidence_applicability(text, study_design)
    quality = classify_evidence_quality(text, study_design)
    is_completed = applicability == APPLICABILITY_DIRECT

    ratio = DIRECTION_CONTRIBUTION_RATIO.get(direction, 0.0)
    quality_factor = QUALITY_FACTOR.get(quality, 1.0)
    applicability_factor = APPLICABILITY_FACTOR.get(applicability, 1.0)

    contribution = clinical_weight * ratio * quality_factor * applicability_factor

    return EvidenceInterpretation(
        study_design=study_design,
        evidence_direction=direction,
        evidence_quality=quality,
        evidence_applicability=applicability,
        is_completed_study=is_completed,
        contribution=round(contribution, 2),
        contribution_ratio=ratio,
        matched_positive=pos_hits,
        matched_null=null_hits,
        matched_negative=neg_hits,
    )
