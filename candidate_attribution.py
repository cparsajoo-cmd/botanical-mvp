"""General, plant-agnostic verification that an evidence record's candidate
botanical is actually the studied INTERVENTION/EXPOSURE, not merely a name
that appears somewhere in the record.

ARCHITECTURE NOTE (post-STOP-PATCHING pass)
This module previously also contained a PubMed/unstructured-literature
heuristic (first sentence-level administration-cue co-occurrence, later a
bounded token-distance local-relation check). Independent adversarial
testing showed that approach remains structurally brittle no matter how
many phrases/patterns are added -- "were NOT randomized to CANDIDATE",
"CANDIDATE intervention was considered but not administered", "CANDIDATE
treatment was prohibited" all defeat surface-pattern matching, while other
genuine constructions ("consumed", "ingested", "allocated to", "the
CANDIDATE arm received...") are missed by too narrow a cue vocabulary. That
heuristic has been REMOVED from this module (not merely patched again).

PubMed/unstructured-literature candidate attribution is now derived by
candidate_intervention_assertion.py, via the SAME structured LLM evidence
extraction already used for Result_Direction/Preparation/etc (see
llm_extractor.py's EVIDENCE_SCHEMA and evidence_standardizer.py), with a
verbatim-supporting-span check and a fail-closed default -- not a text
heuristic in this module. A very conservative, high-precision deterministic
fast path (two unambiguous constructions only) lives there too, used only
when LLM extraction is unavailable.

THIS MODULE keeps only what remains correct and explicitly NOT to be
redesigned: verification from text that is ITSELF a STRUCTURED source
field (e.g. a ClinicalTrials.gov intervention/exposure field) -- never
title, condition, or eligibility text. See clinicaltrials_connector.py,
which builds this text from armsInterventionsModule.interventions (or, for
observational designs lacking that module, armGroups descriptions as an
exposure proxy) and nothing else.

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

    UNCHANGED in this pass, per explicit instruction: this structured-field
    path is already substantially correct and is not being redesigned.
    """
    return _name_present_in_text(normalize_text(intervention_text), scientific_name, common_name)
