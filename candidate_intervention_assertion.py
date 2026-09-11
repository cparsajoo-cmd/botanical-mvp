"""Canonical, evidence-grounded Candidate_Intervention_Assertion.

ARCHITECTURAL ROOT CAUSE THIS MODULE FIXES
Every prior pass at PubMed candidate attribution (sentence-level admin-cue
co-occurrence, then bounded token-distance relation checking) tried to
infer a SCIENTIFIC relation -- "is the candidate botanical the thing this
study actually administered?" -- from surface text patterns: administration
verb lists, connector-word whitelists, negation-phrase lists, bare
compound-noun shortcuts. That is an ever-expanding whack-a-mole problem:
"were NOT randomized to CANDIDATE", "CANDIDATE intervention was considered
but not administered", "CANDIDATE treatment was prohibited" all defeat a
token-adjacency check, while "consumed", "ingested", "allocated to", "the
CANDIDATE arm received..." are missed by too narrow a cue list. No amount
of regex vocabulary can substitute for actually understanding the sentence.

THE FIX
Represent the relation explicitly as a CanonicalIntervention Assertion with
four independent dimensions (candidate role, polarity, temporality,
provenance) instead of a single "does text near the name look
administration-y" boolean. This mirrors the project's existing
semantic-gate-assertion architecture for safety/regulatory claims (see
semantic_gate_assertions.py / llm_extractor.py's GATE_ASSERTION_SCHEMA):
structured, source-grounded LLM extraction is the general engine; a
verbatim-supporting-span check (validate_supporting_span, reused from that
same module) prevents the model from inventing an intervention; and a
tiny, high-precision deterministic fast path is kept ONLY for
unquestionably explicit constructions, never as the general semantic
engine.

Candidate_Attribution_Verified=True is produced ONLY when:
    candidate_role in {STUDIED_INTERVENTION, STUDIED_COMPARATOR}
    AND polarity == POSITIVE
    AND temporality == CURRENT_STUDY
    AND the assertion has a verbatim, source-grounded supporting span.
Anything else -- including extraction failure, an invalid/non-verbatim
span, or an ambiguous role/polarity/temporality -- fails closed to
UNVERIFIED. False negatives are accepted; false positives are not.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from general_indication_relevance import normalize_text
from semantic_gate_assertions import validate_supporting_span

CANDIDATE_INTERVENTION_ASSERTION_VERSION = "1.0.0"


class CandidateRole(str, Enum):
    STUDIED_INTERVENTION = "studied_intervention"
    STUDIED_COMPARATOR = "studied_comparator"
    CONCOMITANT_EXPOSURE = "concomitant_exposure"
    PRIOR_EXPOSURE = "prior_exposure"
    EXCLUDED_EXPOSURE = "excluded_exposure"
    BACKGROUND_MENTION = "background_mention"
    UNKNOWN = "unknown"


class InterventionPolarity(str, Enum):
    POSITIVE = "positive"
    NEGATED = "negated"
    UNKNOWN = "unknown"


class Temporality(str, Enum):
    CURRENT_STUDY = "current_study"
    PRIOR_OR_HISTORICAL = "prior_or_historical"
    UNKNOWN = "unknown"


# Roles that can ever contribute to verified direct/outcome-specific human
# evidence. A studied comparator is included deliberately: a head-to-head
# trial of CANDIDATE vs. an active comparator still studies CANDIDATE as
# one of its own arms even when it is not the primary/first-named arm.
_VERIFIABLE_ROLES = frozenset({CandidateRole.STUDIED_INTERVENTION, CandidateRole.STUDIED_COMPARATOR})


@dataclass(frozen=True)
class CandidateInterventionAssertion:
    candidate_role: CandidateRole = CandidateRole.UNKNOWN
    polarity: InterventionPolarity = InterventionPolarity.UNKNOWN
    temporality: Temporality = Temporality.UNKNOWN
    supporting_text: str = ""
    extraction_method: str = ""  # "structured_field" | "llm_semantic_extraction" | "deterministic_fast_path" | "unavailable"
    extraction_confidence: float = 0.0
    evidence_record_id: str = ""
    source_url: str = ""
    classifier_version: str = CANDIDATE_INTERVENTION_ASSERTION_VERSION

    @property
    def verified(self) -> bool:
        return (
            self.candidate_role in _VERIFIABLE_ROLES
            and self.polarity == InterventionPolarity.POSITIVE
            and self.temporality == Temporality.CURRENT_STUDY
            and bool(self.supporting_text)
        )


def _unverified(extraction_method: str, evidence_record_id: str = "", source_url: str = "") -> CandidateInterventionAssertion:
    return CandidateInterventionAssertion(
        candidate_role=CandidateRole.UNKNOWN,
        polarity=InterventionPolarity.UNKNOWN,
        temporality=Temporality.UNKNOWN,
        extraction_method=extraction_method,
        evidence_record_id=evidence_record_id,
        source_url=source_url,
    )


# ======================================================================
# 1. STRUCTURED SOURCES (e.g. ClinicalTrials.gov)
#
# This path is deliberately a thin wrapper: the structured intervention/
# exposure field IS the authoritative basis, exactly as before this
# pass -- candidate_attribution.verify_intervention_attribution() (whole-
# word/binomial matching against text that is ITSELF the source's own
# intervention/exposure field, never title/condition/eligibility text) is
# unchanged, per this task's explicit instruction not to redesign it.
# ======================================================================

def assertion_from_structured_field(
    intervention_text: str,
    scientific_name: str = "",
    common_name: str = "",
    evidence_record_id: str = "",
    source_url: str = "",
) -> CandidateInterventionAssertion:
    from candidate_attribution import verify_intervention_attribution

    result = verify_intervention_attribution(intervention_text, scientific_name, common_name)
    if not result["verified"]:
        return _unverified("structured_field", evidence_record_id, source_url)
    return CandidateInterventionAssertion(
        candidate_role=CandidateRole.STUDIED_INTERVENTION,
        polarity=InterventionPolarity.POSITIVE,
        temporality=Temporality.CURRENT_STUDY,
        supporting_text=str(intervention_text or "").strip(),
        extraction_method="structured_field",
        extraction_confidence=1.0,
        evidence_record_id=evidence_record_id,
        source_url=source_url,
    )


# ======================================================================
# 2. PUBMED / UNSTRUCTURED LITERATURE -- LLM-extracted assertion
#
# ``data`` is the SAME dict already returned by llm_extractor.py's
# extract_evidence_with_llm() (extended with candidate_intervention_role/
# polarity/temporality/supporting_text -- see llm_extractor.py's
# EVIDENCE_SCHEMA) -- not a second, parallel model call.
# ======================================================================

_ROLE_VALUES = {r.value for r in CandidateRole}
_POLARITY_VALUES = {p.value for p in InterventionPolarity}
_TEMPORALITY_VALUES = {t.value for t in Temporality}


def assertion_from_llm_extraction(
    data: dict,
    source_text: str,
    scientific_name: str = "",
    common_name: str = "",
    evidence_record_id: str = "",
    source_url: str = "",
) -> CandidateInterventionAssertion:
    """Build an assertion from one LLM structured-extraction result.

    FAIL-CLOSED: an assertion whose supporting_text is empty, does not
    exist verbatim in ``source_text``, does not explicitly anchor the candidate
    botanical in that exact span, has zero/invalid confidence, or whose
    role/polarity/temporality is missing/unrecognized/UNKNOWN can never verify -- see
    CandidateInterventionAssertion.verified.  The model is deliberately
    never trusted to have identified a real intervention unless its own
    quoted span can be found, character-for-character, in the real source
    text (validate_supporting_span, the same function this project already
    uses to gate safety/regulatory semantic assertions).
    """
    data = data or {}
    span = str(data.get("candidate_intervention_supporting_text") or "").strip()
    if not validate_supporting_span(source_text, span):
        return _unverified("llm_semantic_extraction", evidence_record_id, source_url)

    # Final deterministic provenance gate: verbatimness proves that the quoted
    # span exists in the source, but not that the span is ABOUT the candidate.
    # Reuse the existing high-precision botanical name matcher on the exact
    # supporting span.  The semantic role/polarity/temporality remain the
    # structured extractor's job; this check merely prevents an unrelated
    # verbatim sentence (e.g. "Participants received placebo") from being
    # accepted as candidate-specific evidence.  A reliable common-name mapping
    # may establish the anchor; without one, common-name-only text fails closed.
    from candidate_attribution import verify_intervention_attribution
    candidate_anchor = verify_intervention_attribution(
        span, scientific_name=scientific_name, common_name=common_name
    )
    if not candidate_anchor.get("verified"):
        return _unverified("llm_semantic_extraction", evidence_record_id, source_url)

    role_raw = str(data.get("candidate_intervention_role") or "unknown").strip().lower()
    polarity_raw = str(data.get("candidate_intervention_polarity") or "unknown").strip().lower()
    temporality_raw = str(data.get("candidate_intervention_temporality") or "unknown").strip().lower()

    role = CandidateRole(role_raw) if role_raw in _ROLE_VALUES else CandidateRole.UNKNOWN
    polarity = InterventionPolarity(polarity_raw) if polarity_raw in _POLARITY_VALUES else InterventionPolarity.UNKNOWN
    temporality = Temporality(temporality_raw) if temporality_raw in _TEMPORALITY_VALUES else Temporality.UNKNOWN

    try:
        confidence = max(0.0, min(1.0, float(data.get("candidate_intervention_confidence", 0.0))))
    except (TypeError, ValueError):
        confidence = 0.0

    # Confidence is diagnostic rather than a calibrated decision threshold.
    # We therefore do not invent an arbitrary cutoff.  An explicit/invalid zero,
    # however, is internally inconsistent with an affirmative verified semantic
    # assertion and fails closed.  Positive confidence does not override any of
    # the role/polarity/temporality/provenance gates above.
    if confidence <= 0.0:
        return _unverified("llm_semantic_extraction", evidence_record_id, source_url)

    return CandidateInterventionAssertion(
        candidate_role=role,
        polarity=polarity,
        temporality=temporality,
        supporting_text=span,
        extraction_method="llm_semantic_extraction",
        extraction_confidence=confidence,
        evidence_record_id=evidence_record_id,
        source_url=source_url,
    )


# ======================================================================
# 3. DETERMINISTIC FAST PATH -- a HIGH-PRECISION optimization only, never
# the general semantic engine. Used ONLY when LLM extraction is
# unavailable/disabled/failed. Deliberately restricted to the two
# unambiguous constructions this task explicitly allows retaining:
#
#   "Participants received CANDIDATE extract."
#   "CANDIDATE extract was administered to participants."
#
# NOT retained (previously present, now removed per this task's explicit
# instruction to demote/remove unsafe shortcuts): "treated with", "randomized/
# assigned to", "supplementation with", and -- most importantly -- the bare
# "CANDIDATE + treatment/intervention/supplementation" compound-noun
# shortcut, which is exactly what let "Ficticus alpinum intervention was
# considered but not administered" and "Ficticus alpinum treatment was
# prohibited" false-positive. This fast path never guesses: any sentence
# not matching one of the two patterns below -- including every negation,
# concomitant-use, historical, or prohibited/excluded-use construction --
# falls through to UNVERIFIED (fail closed), exactly as the cahier requires
# ("false negatives are acceptable ... false positives are not").
# ======================================================================

_GENERIC_EPITHETS = {"officinalis", "vulgaris", "communis", "sativa", "sativus", "spp"}
_FAST_PATH_CONNECTORS = {
    "of", "with", "to", "the", "a", "an",
    "standardized", "standardised", "dry", "aqueous", "ethanolic",
    "hydroalcoholic", "extract", "extracts", "daily", "twice", "once",
    "mg", "g", "ml", "mcg", "iu", "capsules", "capsule", "tablets",
    "tablet", "dose", "doses",
}
_FAST_PATH_NEGATORS = {"not", "never", "no"}


def _name_tokens(name: object) -> list[str]:
    return [t for t in normalize_text(name).split() if len(t) >= 3]


def _tokenize(text: object) -> list[str]:
    return normalize_text(text).split()


def _botanical_span(tokens: list[str], scientific_name: str) -> tuple[int, int] | None:
    sci_tokens = _name_tokens(scientific_name)
    if len(sci_tokens) >= 2:
        genus, epithet = sci_tokens[0], sci_tokens[1]
        for i in range(len(tokens) - 1):
            if tokens[i] == genus and tokens[i + 1] == epithet:
                return (i, i + 2)
    elif len(sci_tokens) == 1 and sci_tokens[0] not in _GENERIC_EPITHETS:
        for i, t in enumerate(tokens):
            if t == sci_tokens[0]:
                return (i, i + 1)
    return None


def _split_sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?;])\s+", str(text or "")) if s.strip()]


def assertion_from_deterministic_fast_path(
    raw_text: str,
    scientific_name: str = "",
    evidence_record_id: str = "",
    source_url: str = "",
) -> CandidateInterventionAssertion:
    for sentence in _split_sentences(raw_text):
        tokens = _tokenize(sentence)
        span = _botanical_span(tokens, scientific_name)
        if span is None:
            continue
        start, end = span

        # Pattern 1: "received" [connectors 0-2] BOTANICAL, with no
        # negator immediately before "received".
        idx = start
        skipped = 0
        while idx > 0 and skipped < 2 and tokens[idx - 1] in _FAST_PATH_CONNECTORS:
            idx -= 1
            skipped += 1
        if idx > 0 and tokens[idx - 1] == "received":
            if not (idx - 2 >= 0 and tokens[idx - 2] in _FAST_PATH_NEGATORS):
                return CandidateInterventionAssertion(
                    candidate_role=CandidateRole.STUDIED_INTERVENTION,
                    polarity=InterventionPolarity.POSITIVE,
                    temporality=Temporality.CURRENT_STUDY,
                    supporting_text=sentence.strip(),
                    extraction_method="deterministic_fast_path",
                    extraction_confidence=1.0,
                    evidence_record_id=evidence_record_id,
                    source_url=source_url,
                )

        # Pattern 2: BOTANICAL [connectors 0-2] "was"/"were" "administered",
        # with no negator between the auxiliary and the verb.
        jdx = end
        skipped = 0
        while jdx < len(tokens) and skipped < 2 and tokens[jdx] in _FAST_PATH_CONNECTORS:
            jdx += 1
            skipped += 1
        if (
            jdx < len(tokens) and tokens[jdx] in {"was", "were"}
            and jdx + 1 < len(tokens) and tokens[jdx + 1] == "administered"
        ):
            return CandidateInterventionAssertion(
                candidate_role=CandidateRole.STUDIED_INTERVENTION,
                polarity=InterventionPolarity.POSITIVE,
                temporality=Temporality.CURRENT_STUDY,
                supporting_text=sentence.strip(),
                extraction_method="deterministic_fast_path",
                extraction_confidence=1.0,
                evidence_record_id=evidence_record_id,
                source_url=source_url,
            )
        if (
            jdx < len(tokens) and tokens[jdx] in {"was", "were"}
            and jdx + 2 < len(tokens) and tokens[jdx + 1] in _FAST_PATH_NEGATORS
        ):
            # "CANDIDATE was not administered" -- explicit negation right at
            # the fast path's own pattern; never verify.
            continue

    return _unverified("deterministic_fast_path", evidence_record_id, source_url)
