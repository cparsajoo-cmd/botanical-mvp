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


def administration_context_text(raw_text: object) -> str:
    """Return only the sentences of ``raw_text`` that themselves contain a
    generic administration/exposure cue (see _ADMINISTRATION_CUES) -- used
    for unstructured literature (e.g. PubMed abstracts) that has no
    structured intervention field. A botanical named only in a sentence
    without such a cue (background, eligibility, discussion, a different
    arm, prior-treatment history) is excluded, so it cannot verify
    attribution merely by co-occurring somewhere in the abstract.

    Returns an empty string when no sentence in ``raw_text`` carries an
    administration cue at all -- the correct "cannot be established from
    the available record" signal for verify_pubmed_intervention_attribution
    to fail closed on, per the cahier's fail-safe requirement.
    """
    sentences = _split_sentences(str(raw_text or ""))
    lowered_cues = _ADMINISTRATION_CUES
    kept = []
    for sentence in sentences:
        low = sentence.lower()
        if any(cue in low for cue in lowered_cues):
            kept.append(sentence)
    return " ".join(kept)


def verify_pubmed_intervention_attribution(
    raw_text: object,
    scientific_name: object = "",
    common_name: object = "",
) -> dict:
    """Verify candidate attribution for unstructured literature (PubMed).

    PubMed abstracts carry no structured intervention field, so a
    deterministic, general, non-plant-specific heuristic is used instead of
    an unscoped full-text search: only sentences that themselves contain a
    generic administration/exposure cue (see _ADMINISTRATION_CUES) are
    considered, and the candidate's name must appear within THAT narrowed
    text. A record whose only botanical mention sits in a background,
    eligibility, discussion, or different-arm sentence -- with no
    administration-cue sentence naming the candidate -- fails closed.

    No LLM call. No fact is invented: this only re-scopes which existing
    text is eligible for the same whole-word/binomial matching already
    used for structured sources.
    """
    context_text = administration_context_text(raw_text)
    if not context_text:
        return {"verified": False, "basis": ""}
    return _name_present_in_text(normalize_text(context_text), scientific_name, common_name)


def combined_record_text(*parts: object) -> str:
    """Join arbitrary record-owned text fields.

    Retained as a general utility for callers that build free text for
    purposes OTHER than intervention/exposure attribution (e.g. general
    relevance diagnostics). Must NOT be used to build the text passed to
    verify_intervention_attribution / verify_pubmed_intervention_attribution
    -- those require intervention-scoped or administration-cue-scoped text
    specifically, not an arbitrary field blob (see module docstring).
    """
    return " \n ".join(str(p) for p in parts if p)
