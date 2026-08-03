"""General, extensible registry of therapeutic-area concepts.

WHY THIS MODULE EXISTS
research_engine.py used to hard-code two module-level dictionaries
(``_DISCOVERY_QUERY_TERMS`` and ``_DISCOVERY_CANDIDATE_POOLS``) covering a
handful of therapeutic areas. Every new indication required a new
if-statement somewhere in research_engine.py. This module replaces that
pattern with a structured, data-driven registry plus a generic fallback for
indications the registry has never seen.

IMPORTANT — THIS IS NOT EVIDENCE
Everything returned by this module (query terms, mechanism terms, candidate
hypotheses) is search/discovery *support*. None of it may be treated as
clinical evidence, and no caller should label a plant "validated" or
"evidence-backed" merely because it appears in a candidate-hypothesis pool
here. Only live literature/regulatory validation (see
``candidate_selection.py`` and ``research_engine.py``) may assign a
``validated_*`` evidence status.

DESIGN
- Canonical concepts are sourced from ``indication_semantics.py``, which is
  already the platform's single curated source of truth for indication
  aliases, direct terms and mechanism terms (used by Step 5 discovery).
  This module does not duplicate that vocabulary; it wraps it.
- Candidate-hypothesis pools (curated example plant lists per area) are
  migrated as-is from the previous research_engine.py hard-coded pools, but
  are attached to canonical concepts instead of being matched by ad hoc
  substring rules.
- "Related concepts" (e.g. Sleep <-> Anxiety <-> Stress) are derived from
  shared mechanism-term vocabulary rather than hand-written per-indication
  if-statements, so a newly-added area automatically participates in
  relatedness once it declares its own mechanism terms.
- Unknown/unregistered indications are still supported via
  ``get_query_terms`` / ``get_candidate_hypotheses``: the former falls back
  to safe lexical normalization of the user's own text, the latter simply
  returns an empty hypothesis list (there is nothing to fabricate).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import indication_semantics as _semantics
from general_indication_relevance import normalize_text as _norm


# ---------------------------------------------------------------------------
# Candidate-hypothesis pools migrated from research_engine.py's previous
# hard-coded ``_DISCOVERY_CANDIDATE_POOLS``. Keys are canonical
# indication_semantics.py concept names. Membership here is only a search
# hypothesis -- see module docstring.
# ---------------------------------------------------------------------------
_LEGACY_CANDIDATE_HYPOTHESES: Dict[str, Tuple[str, ...]] = {
    "Metabolic & blood sugar support": (
        "Gymnema sylvestre", "Momordica charantia", "Morus alba",
        "Salacia reticulata", "Syzygium cumini", "Camellia sinensis",
        "Olea europaea", "Vaccinium myrtillus", "Galega officinalis",
        "Gynostemma pentaphyllum", "Panax ginseng", "Curcuma longa",
        "Allium sativum", "Nigella sativa", "Aloe vera",
        "Ocimum tenuiflorum", "Zingiber officinale", "Silybum marianum",
        "Cichorium intybus", "Phaseolus vulgaris", "Plantago ovata",
        "Urtica dioica", "Taraxacum officinale", "Arctium lappa",
    ),
    "Energy / fatigue": (
        "Rhodiola rosea", "Panax ginseng", "Eleutherococcus senticosus",
        "Withania somnifera", "Schisandra chinensis", "Lepidium meyenii",
        "Ilex paraguariensis", "Camellia sinensis", "Cordyceps sinensis",
    ),
    "Sleep and relaxation": (
        "Valeriana officinalis", "Melissa officinalis",
        "Passiflora incarnata", "Humulus lupulus",
        "Lavandula angustifolia", "Matricaria chamomilla",
        "Tilia cordata", "Ziziphus jujuba",
    ),
    "Anxiety": (
        "Withania somnifera", "Rhodiola rosea", "Melissa officinalis",
        "Passiflora incarnata", "Lavandula angustifolia",
        "Valeriana officinalis", "Matricaria chamomilla",
    ),
}


@dataclass(frozen=True)
class TherapeuticArea:
    """One canonical therapeutic concept.

    ``candidate_hypotheses`` is search-hypothesis support only, never
    evidence -- see module docstring.
    """
    canonical_name: str
    aliases: Tuple[str, ...] = ()
    query_terms: Tuple[str, ...] = ()
    mechanism_terms: Tuple[str, ...] = ()
    candidate_hypotheses: Tuple[str, ...] = ()


def _build_registry() -> "Dict[str, TherapeuticArea]":
    areas: Dict[str, TherapeuticArea] = {}
    for name, semantics in _semantics.INDICATION_SEMANTICS.items():
        aliases = tuple(dict.fromkeys(semantics.get("aliases", ())))
        query_terms = tuple(dict.fromkeys(
            [*semantics.get("aliases", ()), *semantics.get("direct", ())]
        ))
        mechanism_terms = tuple(semantics.get("mechanistic", ()))
        hypotheses = _LEGACY_CANDIDATE_HYPOTHESES.get(name, ())
        areas[name] = TherapeuticArea(
            canonical_name=name,
            aliases=aliases,
            query_terms=query_terms,
            mechanism_terms=mechanism_terms,
            candidate_hypotheses=hypotheses,
        )
    return areas


# The registry may be extended freely (new keys in indication_semantics.py,
# or additional entries added here) without touching any matching logic
# elsewhere in the codebase -- see lookup_therapeutic_area().
THERAPEUTIC_AREAS: Dict[str, TherapeuticArea] = _build_registry()


def lookup_therapeutic_area(indication: object) -> Optional[TherapeuticArea]:
    """Find the best-matching registered therapeutic area for free text.

    Match strength, in order: exact/alias substring match (strong), then
    canonical-name token overlap (weaker, requires >=2 shared tokens to
    avoid one-word coincidental matches). Returns ``None`` for indications
    the registry has never seen -- callers must use the generic fallback
    path in that case, not fabricate a match.
    """
    indication_norm = _norm(indication)
    if not indication_norm:
        return None

    for area in THERAPEUTIC_AREAS.values():
        alias_terms = {_norm(area.canonical_name), *(_norm(a) for a in area.aliases)}
        for term in alias_terms:
            if not term:
                continue
            if term == indication_norm or term in indication_norm or indication_norm in term:
                return area

    indication_tokens = set(indication_norm.split())
    best_area = None
    best_overlap = 0
    for area in THERAPEUTIC_AREAS.values():
        name_tokens = set(_norm(area.canonical_name).split())
        overlap = len(name_tokens & indication_tokens)
        if overlap >= 2 and overlap > best_overlap:
            best_area = area
            best_overlap = overlap
    return best_area


def _generic_lexical_variants(indication: object) -> List[str]:
    """Safe, disease-agnostic query expansion for an unregistered indication.

    Uses only the user's own text: the normalized phrase plus its individual
    significant tokens. No curated vocabulary, no guessing.
    """
    norm = _norm(indication)
    if not norm:
        return []
    variants = [norm]
    variants.extend(token for token in norm.split() if len(token) > 2)
    return list(dict.fromkeys(variants))


def get_query_terms(indication: object) -> List[str]:
    """Return search-query terms for an indication (known or unknown)."""
    terms = [str(indication or "").strip()]
    area = lookup_therapeutic_area(indication)
    if area is not None:
        terms.extend(area.query_terms)
    else:
        terms.extend(_generic_lexical_variants(indication))
    return list(dict.fromkeys(term for term in terms if term))


def get_mechanism_terms(indication: object) -> List[str]:
    area = lookup_therapeutic_area(indication)
    return list(area.mechanism_terms) if area is not None else []


def get_candidate_hypotheses(indication: object) -> List[str]:
    """Return curated candidate-hypothesis plants for a KNOWN indication only.

    Returns an empty list for unregistered indications -- there is nothing
    safe to fabricate, per the architecture's non-goal of inserting
    irrelevant plants merely to reach a requested count.
    """
    area = lookup_therapeutic_area(indication)
    return list(area.candidate_hypotheses) if area is not None else []


def get_related_concepts(indication: object, max_hops: int = 2) -> List[str]:
    """Return canonical names of OTHER areas related to ``indication``.

    Relatedness is derived from shared mechanism-term vocabulary (e.g. Sleep
    and Anxiety both mention "gaba"/"benzodiazepine receptor"), not from a
    hand-written table of indication pairs. A newly registered area
    participates in this automatically once it declares mechanism terms.
    Performs a small bounded breadth-first walk (``max_hops``) so that, for
    example, Sleep -> Anxiety -> Stress remains reachable even though Sleep
    and Stress share no mechanism token directly.
    """
    start = lookup_therapeutic_area(indication)
    if start is None:
        return []

    def _mechanism_tokens(area: TherapeuticArea) -> set:
        tokens = set()
        for term in area.mechanism_terms:
            tokens.update(_norm(term).split())
        return tokens

    visited = {start.canonical_name}
    frontier = [start]
    related: List[str] = []
    for _ in range(max(0, max_hops)):
        next_frontier = []
        for area in frontier:
            area_tokens = _mechanism_tokens(area)
            if not area_tokens:
                continue
            for other in THERAPEUTIC_AREAS.values():
                if other.canonical_name in visited:
                    continue
                other_tokens = _mechanism_tokens(other)
                if area_tokens & other_tokens:
                    visited.add(other.canonical_name)
                    related.append(other.canonical_name)
                    next_frontier.append(other)
        frontier = next_frontier
        if not frontier:
            break
    return related
