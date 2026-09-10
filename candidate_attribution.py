"""General, plant-agnostic verification that an evidence record's OWN text
actually concerns the candidate botanical, rather than trusting whatever
plant name a search connector happened to stamp onto the record.

ROOT CAUSE THIS MODULE ADDRESSES
Evidence connectors (clinicaltrials_connector.py, evidence_collector.py's
PubMed path) set a record's ``Scientific_Name`` field from the SEARCH QUERY
CONTEXT -- the plant that was being searched for -- not from anything
verified in the record's own content. External search APIs frequently
return records that only loosely match a free-text query (shared words,
MeSH-expanded terms, ranked "relevance" hits) and are not actually about
the queried botanical, or study a completely different outcome. Because
the queried plant's name is stamped onto every returned record
unconditionally, downstream consumers (evidence_adjudication_engine.py,
candidate_shortlisting.py) that trust ``Scientific_Name`` as ground truth
end up counting unrelated sources -- a congenital heart disease trial, a
tinnitus protocol, a sports-performance study -- as direct, plant-specific,
outcome-specific human evidence.

This module contains NO botanical-, indication-, compound-, or
dataset-specific vocabulary. It only tokenizes a candidate's own name
fields and checks for their whole-word presence in a record's own free
text (title, abstract, conditions, interventions, notes) -- the same kind
of general, corpus-independent check general_indication_relevance.py
already applies on the outcome side. It works for any species, any
indication, and any future dataset without code changes.
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


def verify_candidate_attribution(
    record_text: object,
    scientific_name: object = "",
    common_name: object = "",
) -> dict:
    """Check whether ``record_text`` (the record's OWN content -- title,
    abstract, conditions, interventions, notes -- never the search-query
    context) actually names the candidate botanical.

    Returns ``{"verified": bool, "basis": str}``. ``basis`` documents which
    signal established attribution, in descending order of strength:

    - "full_binomial": the complete "Genus species" phrase appears.
    - "genus_and_epithet_separately": both binomial words appear (not
      necessarily adjacent) -- covers text that names the genus in one
      sentence and the species epithet in another.
    - "genus_only": a single-word scientific name (e.g. already genus-level)
      appears as a whole word.
    - "common_name": every significant word of the stated common name
      appears as whole words. Whole-word matching (never substring) is
      required specifically to avoid a prior real production bug where a
      generic word like "lemon" false-matched inside "lemon verbena", a
      different species (see [[general_indication_relevance]] /
      research_engine.py).
    - "" (verified False): none of the above could be established from the
      available text -- the record must fail closed rather than being
      assumed relevant.
    """
    haystack = normalize_text(record_text)
    if not haystack:
        return {"verified": False, "basis": ""}

    sci_tokens = _name_tokens(scientific_name)
    if len(sci_tokens) >= 2:
        genus, epithet = sci_tokens[0], sci_tokens[1]
        binomial = f"{genus} {epithet}"
        if binomial in haystack:
            return {"verified": True, "basis": "full_binomial"}
        if _whole_word_present(genus, haystack) and _whole_word_present(epithet, haystack):
            return {"verified": True, "basis": "genus_and_epithet_separately"}
    elif len(sci_tokens) == 1:
        token = sci_tokens[0]
        if token not in _GENERIC_EPITHETS and _whole_word_present(token, haystack):
            return {"verified": True, "basis": "genus_only"}

    common_tokens = _name_tokens(common_name)
    if common_tokens and all(_whole_word_present(tok, haystack) for tok in common_tokens):
        return {"verified": True, "basis": "common_name"}

    return {"verified": False, "basis": ""}


def combined_record_text(*parts: object) -> str:
    """Join arbitrary record-owned text fields for a single attribution check.

    Callers pass only fields that originate from the SOURCE ITSELF (title,
    abstract, conditions, interventions, raw text) -- never fields that
    merely restate the search-query context (e.g. the requested plant name
    or requested indication), or this check would trivially always pass and
    stop meaning anything.
    """
    return " \n ".join(str(p) for p in parts if p)
