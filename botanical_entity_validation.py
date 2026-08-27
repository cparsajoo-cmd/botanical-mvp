"""Open-world botanical entity extraction and validation.

WHY THIS MODULE EXISTS
Stage 2 (research_engine.py) used to be a closed-world literature search:
``_extract_catalogued_plants`` can only ever recognize a plant mention that
is already present in the internal alias catalogue (``plants`` /
``plant_compounds``). A scientifically real plant that has simply never
been manually loaded into Supabase could never be discovered, no matter how
strong its literature support.

This module adds the other half: given raw literature text, (1) extract
plausible botanical binomial mentions that are NOT already covered by the
internal catalogue, then (2) validate each unique candidate against a real
taxonomic/botanical source before it is ever allowed to become a candidate.

It deliberately does not decide anything about evidence, ranking, or
indication relevance -- see research_engine.py for how a validated novel
mention is turned into a scored discovery candidate, and candidate_selection.py
for how it competes against catalogue-known candidates.

VALIDATION SOURCES (checked in order, cheapest/most-authoritative first)
1. botanical_taxonomy.py -- the platform's own curated synonym mapping.
   A hit here means the name is already known to be an accepted botanical
   name or synonym; treated as the strongest signal.
2. kew_connector.py -- Kew Plants of the World Online (POWO) search.
3. gbif_connector.py -- GBIF species search, restricted to kingdom Plantae
   (already filtered inside gbif_connector.search_gbif_plants).

Both external connectors already degrade to ``[]`` on any network/HTTP
failure (see their own try/except), so a taxonomy-service outage here never
raises -- it simply leaves a candidate ``unresolved`` (rejected), per the
platform's fail-safe requirement that ambiguous/unverifiable candidates are
never silently promoted.

Each unique candidate string is validated at most once per call site (the
caller is expected to pass a shared ``cache`` dict across an entire Stage 2
run) so a taxonomy lookup is never repeated once per article mention.
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Set

import botanical_taxonomy as _taxonomy
from gbif_connector import search_gbif_plants
from kew_connector import search_kew_plants


# --- Validation status vocabulary -------------------------------------------
STATUS_VALIDATED_CURATED_SYNONYM = "validated_curated_synonym"
STATUS_VALIDATED_EXTERNAL_TAXONOMY = "validated_external_taxonomy"
STATUS_UNRESOLVED = "unresolved"
STATUS_REJECTED_FORMAT = "rejected_non_binomial_format"
# Part 19 (Stage 2 remediation) -- distinct from STATUS_UNRESOLVED (which
# means "we asked Kew/GBIF and got no match"): this means the remote
# lookup was never attempted at all because no Stage 2 budget remained.
# Kept separate for auditability -- a caller inspecting Stage 2 results
# can tell "genuinely not found" apart from "not checked due to time".
STATUS_SKIPPED_BUDGET_EXHAUSTED = "skipped_budget_exhausted"

# Confidence scores are deliberately modest and ordered, not calibrated
# probabilities -- callers compare them relatively (curated > external) and
# combine them with real literature-support signals; they are never the
# sole basis for a decision.
_SCORE_CURATED_SYNONYM = 1.0
_SCORE_EXTERNAL_TAXONOMY = 0.75
_SCORE_UNRESOLVED = 0.0


# --- Extraction --------------------------------------------------------------

# A conservative binomial-format matcher: "Genus species" where the genus
# is a single capitalized word and the species epithet is a single
# lowercase word. This is a FORMAT filter only -- it says nothing about
# whether the phrase is actually a plant; that is what validate_botanical_
# candidate() below is for. Requiring capitalization on the raw (non-
# lowercased) title/abstract text already rules out most ordinary English
# phrases, since sentences are not routinely capitalized mid-clause.
_BINOMIAL_RE = re.compile(r"\b([A-Z][a-z]{2,})\s+([a-z][a-z\-]{2,})\b")

# First-word (genus-position) stoplist: common sentence-initial / section-
# heading words that would otherwise pass the bare capitalization check.
# General-purpose, not tied to any indication or plant.
_GENUS_POSITION_STOPWORDS = {
    "the", "this", "these", "those", "that", "there", "here", "background",
    "objective", "objectives", "methods", "method", "results", "result",
    "conclusion", "conclusions", "introduction", "discussion", "abstract",
    "however", "because", "although", "therefore", "moreover", "furthermore",
    "additionally", "importantly", "notably", "overall", "finally", "first",
    "second", "third", "we", "our", "study", "studies", "trial", "trials",
    "patients", "participants", "subjects", "data", "figure", "table",
    "significant", "significantly", "compared", "treatment", "treatments",
    "group", "groups", "authors", "author", "article", "review", "journal",
    "current", "previous", "recent", "several", "various", "many", "some",
    "all", "each", "both", "either", "one", "two", "three", "four", "five",
}

# Species-position (second word) stoplist: ordinary English words that
# commonly follow a capitalized sentence-initial word but are never a
# botanical specific epithet in practice.
_SPECIES_POSITION_STOPWORDS = {
    "of", "and", "with", "were", "was", "are", "is", "for", "the", "in",
    "on", "to", "that", "this", "which", "study", "studies", "trial",
    "trials", "group", "groups", "dose", "doses", "effect", "effects",
    "level", "levels", "activity", "activities", "model", "models",
    "disease", "diseases", "patients", "cells", "cell", "receptor",
    "receptors", "protein", "proteins", "gene", "genes", "type", "based",
    "related", "associated", "induced", "mediated", "derived", "specific",
    "human", "humans", "animal", "animals", "clinical", "randomized",
    "randomised", "double", "blind", "controlled", "placebo",
}


def _looks_like_binomial(genus: str, species: str) -> bool:
    if genus.lower() in _GENUS_POSITION_STOPWORDS:
        return False
    if species.lower() in _SPECIES_POSITION_STOPWORDS:
        return False
    if genus.lower() == species.lower():
        return False
    return True


def extract_binomial_mentions(text: object) -> List[str]:
    """Return unique, format-plausible "Genus species" mentions from raw
    (non-lowercased) text, in first-seen order.

    This is a FORMAT-level extraction only -- see module docstring. Callers
    must still run each result through validate_botanical_candidate() (or
    filter it against the known internal alias catalogue) before treating
    it as a real candidate.
    """
    raw = str(text or "")
    seen: Set[str] = set()
    out: List[str] = []
    for match in _BINOMIAL_RE.finditer(raw):
        genus, species = match.group(1), match.group(2)
        if not _looks_like_binomial(genus, species):
            continue
        name = f"{genus} {species}"
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


# --- Validation ---------------------------------------------------------------

def _normalized_binomial_key(name: object) -> str:
    """First two whitespace-separated tokens, lowercased -- used only to
    compare a candidate string against an external source's returned
    scientific name, independent of author citations/infraspecific rank."""
    tokens = str(name or "").strip().split()
    return " ".join(t.lower() for t in tokens[:2])


def _external_source_confirms(candidate_key: str, results: Iterable[dict]) -> Optional[str]:
    for item in results or ():
        matched_name = item.get("Scientific_Name") or ""
        if _normalized_binomial_key(matched_name) == candidate_key:
            return str(matched_name).strip()
    return None


def validate_botanical_candidate(
    name: object, cache: Optional[Dict[str, dict]] = None, deadline_seconds: Optional[float] = None,
) -> dict:
    """Validate one candidate botanical name against real taxonomic sources.

    Returns a structured provenance dict:
        {
            "original_mention": <name as submitted>,
            "valid": bool,
            "botanical_validation_status": one of the STATUS_* constants,
            "botanical_validation_score": float,
            "taxonomic_source": str,
            "matched_scientific_name": str,
        }

    ``cache`` is an optional caller-provided dict keyed by normalized
    candidate name; when supplied, a candidate already validated earlier in
    the same run is never re-queried against a live service (see module
    docstring's performance requirement).

    ``deadline_seconds`` (Part 19, Stage 2 remediation): remaining stage
    budget, if the caller has one. When supplied, each remote connector's
    own network timeout is min(connector_default, remaining_seconds), so
    a candidate validated near the end of Stage 2's budget cannot itself
    consume the rest of it -- and if there is no budget left at all
    (<=0), the remote lookups are skipped entirely and the candidate is
    marked UNKNOWN/unresolved rather than silently validated (fail-closed
    -- an unverified name is never treated as confirmed just to save
    time). None (the default) preserves the exact prior behavior (the
    connectors' own 30s default).
    """
    raw = str(name or "").strip()
    cache_key = raw.lower()
    if cache is not None and cache_key in cache:
        return cache[cache_key]

    genus_species = raw.split()
    result: dict
    if len(genus_species) < 2 or not _looks_like_binomial(genus_species[0], genus_species[1]):
        result = {
            "original_mention": raw,
            "valid": False,
            "botanical_validation_status": STATUS_REJECTED_FORMAT,
            "botanical_validation_score": _SCORE_UNRESOLVED,
            "taxonomic_source": "",
            "matched_scientific_name": "",
        }
        if cache is not None:
            cache[cache_key] = result
        return result

    candidate_key = _normalized_binomial_key(raw)

    # 1. Curated internal taxonomy (accepted name or known synonym).
    taxon = _taxonomy.lookup_taxon(raw)
    if taxon is not None:
        result = {
            "original_mention": raw,
            "valid": True,
            "botanical_validation_status": STATUS_VALIDATED_CURATED_SYNONYM,
            "botanical_validation_score": _SCORE_CURATED_SYNONYM,
            "taxonomic_source": taxon.source,
            "matched_scientific_name": taxon.accepted_name,
        }
        if cache is not None:
            cache[cache_key] = result
        return result

    # 2. Kew POWO, then 3. GBIF. Each connector already fails closed
    # (returns []) on any network/HTTP error -- never raises here.
    # Part 19 -- if no Stage 2 budget remains at all, skip the remote
    # lookups entirely rather than spending the connectors' full default
    # timeout with nothing left to show for it; the candidate is marked
    # explicitly unverified (fail-closed), never silently validated.
    if deadline_seconds is not None and deadline_seconds <= 0:
        result = {
            "original_mention": raw,
            "valid": False,
            "botanical_validation_status": STATUS_SKIPPED_BUDGET_EXHAUSTED,
            "botanical_validation_score": _SCORE_UNRESOLVED,
            "taxonomic_source": "",
            "matched_scientific_name": "",
        }
        if cache is not None:
            cache[cache_key] = result
        return result

    connector_timeout = (
        min(30, deadline_seconds) if deadline_seconds is not None else None
    )
    matched = _external_source_confirms(
        candidate_key, search_kew_plants(raw, timeout=connector_timeout)
    )
    source = "Kew POWO" if matched else ""
    if not matched:
        matched = _external_source_confirms(
            candidate_key, search_gbif_plants(raw, timeout=connector_timeout)
        )
        source = "GBIF" if matched else source

    if matched:
        result = {
            "original_mention": raw,
            "valid": True,
            "botanical_validation_status": STATUS_VALIDATED_EXTERNAL_TAXONOMY,
            "botanical_validation_score": _SCORE_EXTERNAL_TAXONOMY,
            "taxonomic_source": source,
            "matched_scientific_name": matched,
        }
    else:
        result = {
            "original_mention": raw,
            "valid": False,
            "botanical_validation_status": STATUS_UNRESOLVED,
            "botanical_validation_score": _SCORE_UNRESOLVED,
            "taxonomic_source": "",
            "matched_scientific_name": "",
        }

    if cache is not None:
        cache[cache_key] = result
    return result
