"""General taxonomic synonym canonicalization.

WHY THIS MODULE EXISTS
``Actaea racemosa`` and ``Cimicifuga racemosa`` are literal-text-different
strings naming the SAME accepted botanical taxon (black cohosh was
reclassified from genus Cimicifuga into Actaea). Plain text normalization
(``candidate_selection.canonicalize_plant_name`` / ``normalize_text``) only
handles casing/whitespace -- it has no way to know that these two strings
refer to one taxon, so without this module a candidate list can silently
contain the same plant twice under different names.

This module is a small, general taxonomic layer: given ANY submitted plant
name, it looks up the accepted scientific name plus every known alias, with
a curated internal mapping as the default source. The lookup interface is
deliberately pluggable (see ``register_taxon_source``) so a maintained
taxonomic catalogue or live service (GBIF backbone, World Flora Online,
POWO, etc.) can be substituted or layered on top later without changing any
caller.

NOTHING HERE IS EVIDENCE. This module only tells callers which strings name
the same taxon and what that taxon's accepted name is -- it makes no claim
about efficacy, safety, or indication relevance.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from general_indication_relevance import normalize_text as _norm


@dataclass(frozen=True)
class TaxonRecord:
    """One taxon: its accepted scientific name, known synonyms, and the
    provenance/source of the mapping."""
    accepted_name: str
    synonyms: Tuple[str, ...] = ()
    source: str = "internal_curated_mapping"


# ---------------------------------------------------------------------------
# Internal curated fallback mapping.
#
# This is intentionally small and general-purpose (not built to solve one
# indication or one plant). Entries can be added freely without touching any
# matching/lookup logic below. Cimicifuga racemosa -> Actaea racemosa is
# included per the reported production duplication, but the mechanism is
# general: any accepted_name/synonyms pair works the same way.
# ---------------------------------------------------------------------------
_CURATED_TAXA: Tuple[TaxonRecord, ...] = (
    TaxonRecord(
        accepted_name="Actaea racemosa",
        synonyms=("Cimicifuga racemosa", "Actaea racemosa var. racemosa"),
        source="internal_curated_mapping",
    ),
    TaxonRecord(
        accepted_name="Withania somnifera",
        synonyms=("Physalis somnifera",),
        source="internal_curated_mapping",
    ),
    TaxonRecord(
        accepted_name="Centella asiatica",
        synonyms=("Hydrocotyle asiatica",),
        source="internal_curated_mapping",
    ),
    TaxonRecord(
        accepted_name="Panax ginseng",
        synonyms=("Panax schinseng",),
        source="internal_curated_mapping",
    ),
)


def _build_index(records: "Tuple[TaxonRecord, ...] | list[TaxonRecord]") -> Dict[str, TaxonRecord]:
    index: Dict[str, TaxonRecord] = {}
    for record in records:
        for alias in (record.accepted_name, *record.synonyms):
            key = _norm(alias)
            if key:
                index[key] = record
    return index


_CURATED_INDEX: Dict[str, TaxonRecord] = _build_index(_CURATED_TAXA)

# Pluggable additional sources, consulted BEFORE the curated fallback so a
# live/maintained catalogue can override or extend it without editing this
# file. Each entry is a plain {normalized_alias: TaxonRecord} mapping.
_EXTRA_SOURCES: List[Dict[str, TaxonRecord]] = []


def register_taxon_source(index: Dict[str, TaxonRecord]) -> None:
    """Register an additional taxonomic lookup table.

    Intended integration point for a future taxonomic service or maintained
    catalogue: build a ``{normalized_alias: TaxonRecord}`` mapping from that
    source and register it here. Registered sources are checked in
    registration order, before the internal curated mapping.
    """
    _EXTRA_SOURCES.append(index)


def lookup_taxon(name: object) -> Optional[TaxonRecord]:
    """Return the TaxonRecord for ``name`` (accepted name or any known
    synonym), or None if the name is not in any registered/curated
    mapping."""
    key = _norm(name)
    if not key:
        return None
    for source in _EXTRA_SOURCES:
        if key in source:
            return source[key]
    return _CURATED_INDEX.get(key)


def accepted_name(name: object) -> str:
    """Return the accepted scientific name for ``name``.

    An unmapped name is returned unchanged (trimmed) -- this module never
    guesses at a taxon it doesn't have a record for.
    """
    raw = str(name or "").strip()
    if not raw:
        return ""
    record = lookup_taxon(raw)
    return record.accepted_name if record is not None else raw


def is_synonym(name: object) -> bool:
    """True when ``name`` is a known synonym (not itself the accepted name)."""
    record = lookup_taxon(name)
    if record is None:
        return False
    return _norm(name) != _norm(record.accepted_name)


def all_aliases(name: object) -> List[str]:
    """Every known alias for ``name`` (accepted name + synonyms), usable for
    literature-search query expansion. Always includes the submitted name
    itself, even when unmapped."""
    raw = str(name or "").strip()
    if not raw:
        return []
    record = lookup_taxon(raw)
    if record is None:
        return [raw]
    aliases = [record.accepted_name, *record.synonyms]
    if raw not in aliases:
        aliases.append(raw)
    return list(dict.fromkeys(a for a in aliases if a))


def taxon_provenance(name: object) -> dict:
    """Structured provenance for one submitted name -- submitted/original
    name, accepted name, synonym status, and mapping source."""
    raw = str(name or "").strip()
    record = lookup_taxon(raw)
    return {
        "submitted_name": raw,
        "accepted_name": record.accepted_name if record is not None else raw,
        "is_synonym": is_synonym(raw),
        "source": record.source if record is not None else "unmapped",
    }


def taxon_match_key(name: object) -> str:
    """Return a stable matching key for a scientific botanical name.

    The key resolves known taxonomic synonyms first, then removes only
    nomenclatural author citations (e.g. ``L.``, ``(L.) Moench``) while
    preserving an infraspecific rank and epithet when one is present.
    It is for identity matching only; display/provenance names remain
    untouched.
    """
    raw = accepted_name(name)
    text = str(raw or "").strip()
    if not text:
        return ""

    # Normalize hybrid markers and punctuation around tokens without
    # guessing at taxonomic synonymy.
    tokens = text.replace("×", " x ").split()
    if not tokens:
        return ""

    # A botanical species identity minimally consists of genus + specific
    # epithet.  Author citations begin after that in the ordinary binomial
    # forms seen in EMA/Kew/PubMed records.  Preserve explicit
    # infraspecific ranks because varieties/subspecies need not be treated
    # as identical to the parent species.
    keep = tokens[:2]
    rank_tokens = {"subsp.", "subsp", "ssp.", "ssp", "var.", "var", "f.", "f", "nothosubsp.", "nothosubsp"}
    if len(tokens) >= 4 and tokens[2].lower() in rank_tokens:
        keep = tokens[:4]

    return _norm(" ".join(keep))
