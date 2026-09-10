"""General, plant-agnostic verification that an evidence record's candidate
botanical is actually the studied INTERVENTION/EXPOSURE, not merely a name
that appears somewhere in the record.

ROOT CAUSE (Problem 1, remaining defect 1)
The original version of this module verified attribution the moment the
candidate's name appeared anywhere in a blob of record text (title +
condition + notes, etc.). That over-verifies: a botanical is routinely
named in a study's background, eligibility criteria, discussion, a
different arm, or prior-treatment history WITHOUT being the thing that was
actually administered. For example:

    "Background: Ficticus alpinum is traditionally used for sleep. In this
    randomized trial, patients received cognitive behavioral therapy
    versus placebo."

names the candidate but studies something else entirely. Mere occurrence
is not intervention/exposure attribution.

WHAT THIS MODULE NOW REQUIRES
Verification must be established from text that is ITSELF scoped to the
intervention/exposure -- never a mention anywhere in the record:

- Structured sources (e.g. ClinicalTrials.gov) must pass ONLY their own
  intervention/exposure fields (name + description of what was actually
  administered/assigned) -- never title, condition, or eligibility text.
  See clinicaltrials_connector.py, which now builds this text from
  armsInterventionsModule.interventions (or, for observational designs
  lacking that module, armGroups descriptions as an exposure proxy) and
  nothing else.
- Unstructured literature (PubMed abstracts) has no structured
  intervention field. Rather than search the whole abstract for the
  plant's name, this module deterministically narrows the text to
  sentences that themselves contain a generic administration/exposure cue
  ("administered", "received", "supplementation", "mg of", "extract of",
  etc. -- see _ADMINISTRATION_CUES, which is intervention-vocabulary, not
  plant- or indication-specific) before checking for the candidate's name.
  A plant named only in a sentence with no such cue (background,
  eligibility, discussion, a different arm) does not verify attribution.
  This is a deterministic, general heuristic -- no LLM call, no invented
  facts, no plant-specific or indication-specific vocabulary -- and it
  fails closed (unverified) whenever no administration-context sentence
  exists at all, exactly the "insufficient metadata" case the cahier
  requires.

This module contains NO botanical-, indication-, or dataset-specific
vocabulary. It works for any species and any indication without code
changes.
"""
from __future__ import annotations

import re

from general_indication_relevance import normalize_text

# Botanical name particles that are too common across unrelated species to
# confirm attribution on their own (e.g. "officinalis" appears in dozens of
# medicinal-plant binomials). They still count when part of a full binomial
# match; they are excluded only from single-token confirmation.
_GENERIC_EPITHETS = {
    "officinalis", "vulgaris", "communis", "sativa", "sativus", "spp",
}

# Generic, species- and indication-agnostic cues that a sentence describes
# what was actually ADMINISTERED/ASSIGNED to participants, as opposed to
# background, eligibility, discussion, or a different study arm. Deliberately
# vocabulary about STUDY DESIGN/INTERVENTION MECHANICS only -- nothing here
# names any botanical, compound, or indication.
_ADMINISTRATION_CUES = (
    "administer", "administered", "administration of",
    "received", "receiving", "was given", "were given", "given daily",
    "supplementation", "supplemented with", "supplemented daily",
    "treated with", "treatment with", "treatment group",
    "intervention group", "intervention arm", "experimental group",
    "experimental arm", "assigned to", "randomized to", "randomised to",
    "participants took", "subjects took", "patients took",
    "dose of", "doses of", "dosage of", "mg of", "g of", "ml of",
    "capsules of", "tablets of", "extract of", "preparation of",
    "twice daily", "once daily", "daily for", "once a day", "twice a day",
    "orally", "oral administration",
)

# REMAINING DEFECT B FIX: an administration cue co-occurring with the
# candidate's name in one sentence is still not sufficient -- the same
# sentence (or one very like it) commonly says the candidate was NOT what
# was given (negation), was given historically/in a prior study rather
# than in the present one (background), or was actively excluded from the
# study population. Every phrase below describes SENTENCE STRUCTURE/STUDY-
# DESIGN CONTEXT only -- nothing here names a botanical, compound, or
# indication, so this stays general across arbitrary candidates and
# indications. A sentence matching any of these is disqualified outright
# and can never contribute to verification, regardless of what
# administration cues or candidate-name mentions it also contains.
_NEGATION_OR_EXCLUSION_CUES = (
    "rather than", "instead of", "in place of", "as opposed to",
    "not receive", "did not receive", "does not receive", "never received",
    "not administered", "not given", "without receiving",
    "no longer receiving", "discontinued",
    "excluded", "exclusion criteria", "were excluded", "was excluded",
    "ineligible", "not eligible",
)

_HISTORICAL_OR_BACKGROUND_CUES = (
    "prior treatment", "prior use", "prior exposure", "prior therapy",
    "prior studies", "prior trials",
    "previously treated", "previously used", "previously received",
    "previously administered", "previously prescribed",
    "history of", "previous use", "previous treatment", "previous therapy",
    "previous studies", "previous research", "previous trials",
    "earlier studies", "earlier research",
    "has previously", "have previously", "had previously",
    "was previously", "were previously", "previously been",
    "traditionally used", "traditionally administered", "traditionally applied",
    "is traditionally", "are traditionally", "has traditionally", "have traditionally",
    "in the past", "historically used", "historically administered",
)

# ======================================================================
# LOCAL INTERVENTION-RELATION CHECK (replaces "admin cue anywhere in
# sentence + name anywhere in sentence" as the actual verification basis
# for verify_pubmed_intervention_attribution -- see that function's
# docstring for the full rationale). _ADMINISTRATION_CUES/
# _NEGATION_OR_EXCLUSION_CUES/_HISTORICAL_OR_BACKGROUND_CUES/
# administration_context_text above remain as a coarse, sentence-level
# diagnostic helper other callers may still use, but are no longer the
# basis of verification by themselves.
#
# Every vocabulary set below is closed-class STUDY-DESIGN/GRAMMATICAL
# vocabulary -- prepositions, auxiliary verbs, dosage-form nouns, and a
# handful of administration-construction verbs -- never a botanical,
# compound, or indication name, and never an attempt to enumerate every
# way an administration statement could be negated or historicized. A
# bounded relation that requires ONLY these closed-class tokens between
# the cue and the candidate is what makes this general: any novel
# negation/concomitant-use/history phrasing already fails by inserting a
# non-whitelisted word into that gap, with no new phrase ever needed.
# ======================================================================

_CONNECTOR_WORDS = {
    "of", "with", "to", "the", "a", "an", "and", "or",
    "standardized", "standardised", "dry", "aqueous", "ethanolic",
    "hydroalcoholic", "extract", "extracts", "preparation",
    "daily", "twice", "once", "per", "day",
    "mg", "g", "ml", "mcg", "iu", "capsules", "capsule",
    "tablets", "tablet", "dose", "doses",
}

# Forward cues: CUE (+ up to 3 connector tokens) + BOTANICAL.
_FORWARD_CUES = (
    ("received",), ("receiving",), ("administered",), ("given",),
    ("treated", "with"),
    ("randomized", "to"), ("randomised", "to"),
    ("randomized", "to", "receive"), ("randomised", "to", "receive"),
    ("assigned", "to"), ("assigned", "to", "receive"),
    ("supplementation", "with"), ("supplemented", "with"),
)

# Reverse cues: BOTANICAL (+ up to 3 connector tokens) + AUX + VERB.
_REVERSE_AUX = {"was", "were"}
_REVERSE_VERBS = {"administered", "given"}

# Direct compound: BOTANICAL (+ up to 3 connector tokens) + this noun.
_DIRECT_COMPOUND_NOUNS = {"treatment", "intervention", "supplementation"}

# Pluperfect auxiliary immediately before a forward cue verb ("had
# received", "had administered") marks an action completed before the
# narrated reference point -- prior/historical exposure, not the present
# study's own arm. Closed-class grammar, not a phrase blacklist.
_PLUPERFECT_MARKER = "had"

# A review/meta-analysis describing what OTHER studies did ("Several
# trials administered CANDIDATE") is not this record's own participants.
# Closed, study-design-meta vocabulary -- the same category already used
# elsewhere in this codebase (evidence_extractor.py's Publication_Type
# classifier) to recognize review/meta-analysis language -- never
# botanical- or indication-specific.
_AGGREGATE_SUBJECT_WORDS = {
    "trials", "studies", "rcts", "reports", "papers", "articles", "reviews",
}

_MAX_CONNECTOR_SPAN = 3


# A forward match must also not be immediately undone by a trailing
# exclusion verb describing the SAME occurrence ("Participants receiving
# CANDIDATE were excluded.") -- closed-class study-design vocabulary,
# checked with the same bounded-connector-span logic as every other
# relation here, not a botanical/indication-specific phrase.
_EXCLUSION_VERBS = {"excluded", "ineligible"}


def _tokenize(text: object) -> list[str]:
    return normalize_text(text).split()


def _is_connector_token(token: str) -> bool:
    return token in _CONNECTOR_WORDS or token.isdigit()


def _botanical_token_spans(
    tokens: list[str], scientific_name: object, common_name: object
) -> list[tuple[int, int, str]]:
    """Every (start, end, basis) span where the candidate's name occurs in
    ``tokens`` as a contiguous whole-word run -- the anchor points the
    local-relation check scans outward from.
    """
    spans: list[tuple[int, int, str]] = []

    sci_tokens = _name_tokens(scientific_name)
    if len(sci_tokens) >= 2:
        genus, epithet = sci_tokens[0], sci_tokens[1]
        for i in range(len(tokens) - 1):
            if tokens[i] == genus and tokens[i + 1] == epithet:
                spans.append((i, i + 2, "full_binomial"))
    elif len(sci_tokens) == 1:
        token = sci_tokens[0]
        if token not in _GENERIC_EPITHETS:
            for i, t in enumerate(tokens):
                if t == token:
                    spans.append((i, i + 1, "genus_only"))

    common_tokens = _name_tokens(common_name)
    if common_tokens:
        n = len(common_tokens)
        for i in range(len(tokens) - n + 1):
            if tokens[i:i + n] == common_tokens:
                spans.append((i, i + n, "common_name"))

    return spans


def _forward_relation_at(tokens: list[str], start: int) -> bool:
    """True when a forward cue (CUE [+ connectors] + BOTANICAL) ends
    exactly at ``start``, and is not disqualified by a pluperfect
    auxiliary or an aggregate/review-level subject immediately before it.
    """
    for skip in range(0, _MAX_CONNECTOR_SPAN + 1):
        idx = start - skip
        if idx < 0:
            break
        if skip and not all(_is_connector_token(t) for t in tokens[idx:start]):
            continue
        for cue in _FORWARD_CUES:
            cue_start = idx - len(cue)
            if cue_start < 0:
                continue
            if tuple(tokens[cue_start:idx]) != cue:
                continue
            if cue_start > 0 and tokens[cue_start - 1] == _PLUPERFECT_MARKER:
                continue
            if cue_start > 0 and tokens[cue_start - 1] in _AGGREGATE_SUBJECT_WORDS:
                continue
            return True
    return False


def _reverse_relation_at(tokens: list[str], end: int) -> bool:
    """True when BOTANICAL (+ connectors) is followed by AUX+VERB
    (``was``/``were`` administered/given) or a direct treatment/
    intervention/supplementation compound, starting exactly at ``end``.
    """
    n = len(tokens)
    for skip in range(0, _MAX_CONNECTOR_SPAN + 1):
        idx = end + skip
        if idx >= n:
            break
        if skip and not all(_is_connector_token(t) for t in tokens[end:idx]):
            continue
        if tokens[idx] in _DIRECT_COMPOUND_NOUNS:
            return True
        if (
            idx + 1 < n
            and tokens[idx] in _REVERSE_AUX
            and tokens[idx + 1] in _REVERSE_VERBS
        ):
            return True
    return False


def _has_trailing_exclusion(tokens: list[str], end: int) -> bool:
    """True when BOTANICAL (+ connectors) is immediately followed by
    AUX + an exclusion verb (``were excluded`` / ``was ineligible``) --
    disqualifies an otherwise-matching relation for THIS occurrence
    (e.g. "Participants receiving CANDIDATE were excluded.", where
    "receiving" would otherwise satisfy the forward relation).
    """
    n = len(tokens)
    for skip in range(0, _MAX_CONNECTOR_SPAN + 1):
        idx = end + skip
        if idx >= n:
            break
        if skip and not all(_is_connector_token(t) for t in tokens[end:idx]):
            continue
        if (
            idx + 1 < n
            and tokens[idx] in _REVERSE_AUX
            and tokens[idx + 1] in _EXCLUSION_VERBS
        ):
            return True
    return False


def _has_local_intervention_relation(tokens: list[str], start: int, end: int) -> bool:
    if _has_trailing_exclusion(tokens, end):
        return False
    return _forward_relation_at(tokens, start) or _reverse_relation_at(tokens, end)


def _name_tokens(name: object) -> list[str]:
    """Whole-word tokens (>=3 chars) for a scientific or common name."""
    return [t for t in normalize_text(name).split() if len(t) >= 3]


def _whole_word_present(term: str, haystack_norm: str) -> bool:
    if not term or not haystack_norm:
        return False
    pattern = r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])"
    return re.search(pattern, haystack_norm) is not None


def _name_present_in_text(
    text_norm: str,
    scientific_name: object = "",
    common_name: object = "",
) -> dict:
    """Core, low-level name-matching primitive.

    Deliberately unaware of WHERE ``text_norm`` came from -- callers are
    responsible for scoping ``text_norm`` to intervention/exposure content
    before calling this (see module docstring). This function alone must
    never be treated as "verified candidate attribution"; that status
    requires both this AND intervention-scoped input text.
    """
    if not text_norm:
        return {"verified": False, "basis": ""}

    sci_tokens = _name_tokens(scientific_name)
    if len(sci_tokens) >= 2:
        genus, epithet = sci_tokens[0], sci_tokens[1]
        binomial = f"{genus} {epithet}"
        if binomial in text_norm:
            return {"verified": True, "basis": "full_binomial"}
        if _whole_word_present(genus, text_norm) and _whole_word_present(epithet, text_norm):
            return {"verified": True, "basis": "genus_and_epithet_separately"}
    elif len(sci_tokens) == 1:
        token = sci_tokens[0]
        if token not in _GENERIC_EPITHETS and _whole_word_present(token, text_norm):
            return {"verified": True, "basis": "genus_only"}

    common_tokens = _name_tokens(common_name)
    if common_tokens and all(_whole_word_present(tok, text_norm) for tok in common_tokens):
        return {"verified": True, "basis": "common_name"}

    return {"verified": False, "basis": ""}


def verify_intervention_attribution(
    intervention_text: object,
    scientific_name: object = "",
    common_name: object = "",
) -> dict:
    """Verify candidate attribution from TEXT THAT IS ITSELF THE
    INTERVENTION/EXPOSURE DESCRIPTION -- e.g. a ClinicalTrials.gov
    intervention name/description, or an arm-group exposure description.
    Never pass title, condition, eligibility, or background text here; a
    plant named only there is not evidence it was administered (see module
    docstring).

    Returns ``{"verified": bool, "basis": str}``, same shape/semantics as
    the module's other verification functions. Fails closed (verified
    False, basis "") when ``intervention_text`` is empty -- i.e. when no
    intervention/exposure field could be established from the source at
    all -- rather than falling back to any other part of the record.
    """
    return _name_present_in_text(normalize_text(intervention_text), scientific_name, common_name)


def _split_sentences(text: str) -> list[str]:
    # Deterministic, punctuation-based split. Good enough for identifying
    # which clause carries an administration cue; does not need to be a
    # full NLP sentence tokenizer for this bounded purpose.
    return [s for s in re.split(r"(?<=[.!?;])\s+", str(text or "")) if s.strip()]


def _is_disqualified_sentence(low: str) -> bool:
    """True when ``low`` (an already-lowercased sentence) describes
    negation, exclusion, or historical/background exposure rather than the
    present study's actual administered intervention (REMAINING DEFECT B).
    A disqualified sentence can never contribute to verification, even if
    it also contains an administration cue and the candidate's name --
    that combination is exactly the false-positive pattern being fixed
    (e.g. "rather than CANDIDATE", "prior treatment with CANDIDATE",
    "CANDIDATE... were excluded", "CANDIDATE has previously been
    administered").
    """
    return any(cue in low for cue in _NEGATION_OR_EXCLUSION_CUES) or any(
        cue in low for cue in _HISTORICAL_OR_BACKGROUND_CUES
    )


def administration_context_text(raw_text: object) -> str:
    """Return only the sentences of ``raw_text`` that themselves contain a
    generic administration/exposure cue (see _ADMINISTRATION_CUES) AND are
    not disqualified by a negation/exclusion/historical cue (see
    _is_disqualified_sentence) -- used for unstructured literature (e.g.
    PubMed abstracts) that has no structured intervention field. A
    botanical named only in a sentence without a genuine, non-disqualified
    administration cue (background, eligibility, discussion, a different
    arm, prior-treatment history, negated or excluded exposure) is
    excluded, so it cannot verify attribution merely by co-occurring
    somewhere in the abstract.

    Returns an empty string when no sentence in ``raw_text`` qualifies at
    all -- the correct "cannot be established from the available record"
    signal for verify_pubmed_intervention_attribution to fail closed on,
    per the cahier's fail-safe requirement.
    """
    sentences = _split_sentences(str(raw_text or ""))
    kept = []
    for sentence in sentences:
        low = sentence.lower()
        if _is_disqualified_sentence(low):
            continue
        if any(cue in low for cue in _ADMINISTRATION_CUES):
            kept.append(sentence)
    return " ".join(kept)


def verify_pubmed_intervention_attribution(
    raw_text: object,
    scientific_name: object = "",
    common_name: object = "",
) -> dict:
    """Verify candidate attribution for unstructured literature (PubMed).

    REMAINING DEFECT (this pass): the prior implementation kept a whole
    sentence the moment it contained ANY administration cue, then checked
    whether the candidate's name appeared anywhere in that sentence.
    "Administration word somewhere in sentence + botanical name somewhere
    in sentence" is not sufficient -- both still appear together in
    discontinuation ("received placebo after discontinuing CANDIDATE"),
    baseline/concomitant-use ("using CANDIDATE at baseline received CBT"),
    and pre-enrollment-history ("had received CANDIDATE before enrollment
    but received placebo during the study") sentences, none of which
    establish that the candidate was the actual STUDY intervention.

    THE FIX: a bounded, general, deterministic LOCAL RELATION check (see
    _has_local_intervention_relation) instead of sentence-wide
    co-occurrence. The candidate's name must sit immediately adjacent
    (allowing only a short run of closed-class connector/dosage tokens --
    see _CONNECTOR_WORDS) to one of a small, closed set of
    administration-construction cues (received/administered/treated
    with/randomized-assigned to/supplementation with, in either
    cue-then-botanical or botanical-then-was/were-administered order, or
    a direct "CANDIDATE treatment/intervention/supplementation" compound).
    Two further general (not botanical/indication-specific) checks
    disqualify an otherwise-matching local relation:

    - a pluperfect auxiliary ("had") immediately before the cue verb --
      the closed-class grammatical marker for an action completed before
      the narrated reference point, i.e. prior/historical exposure rather
      than the present study's own arm;
    - an aggregate/meta-vocabulary subject ("trials", "studies", "RCTs",
      "reports", "papers", "articles", "reviews") immediately before the
      cue verb -- a review/meta-analysis describing what OTHER studies did,
      not this record's own participants.

    This is a bounded relation check, not an ever-growing phrase
    blacklist: any novel negation/history/concomitant-use wording that
    inserts even one non-connector word between the cue and the candidate
    (or a "had" / aggregate-subject marker before the cue) already fails
    to establish the relation by construction, with no new phrase needed.

    No LLM call. No fact is invented. Fails closed (verified False, basis
    "") when the relation cannot be established from any sentence in
    ``raw_text`` at all.
    """
    scientific_tokens = _name_tokens(scientific_name)
    common_tokens = _name_tokens(common_name)
    if not scientific_tokens and not common_tokens:
        return {"verified": False, "basis": ""}

    for sentence in _split_sentences(str(raw_text or "")):
        tokens = _tokenize(sentence)
        for start, end, basis in _botanical_token_spans(tokens, scientific_name, common_name):
            if _has_local_intervention_relation(tokens, start, end):
                return {"verified": True, "basis": basis}

    return {"verified": False, "basis": ""}


def combined_record_text(*parts: object) -> str:
    """Join arbitrary record-owned text fields.

    Retained as a general utility for callers that build free text for
    purposes OTHER than intervention/exposure attribution (e.g. general
    relevance diagnostics). Must NOT be used to build the text passed to
    verify_intervention_attribution / verify_pubmed_intervention_attribution
    -- those require intervention-scoped text or the local relation check
    specifically, not an arbitrary field blob (see module docstring).
    """
    return " \n ".join(str(p) for p in parts if p)
