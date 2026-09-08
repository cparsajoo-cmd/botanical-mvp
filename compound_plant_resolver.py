"""CompoundPlantResolver -- a single, data-backed source of compound ->
plant occurrence facts for every discovery-adjacent module in this
platform.

WHY THIS EXISTS (architecture note, external review, 2026-09-08):

Before this module, "which plants contain compound X" was answered by
small, hard-coded dictionaries duplicated across botanical_brain_engine.py,
compound_occurrence_map.py, and (unused/orphaned) target_knowledge_base.py
-- at most ~60 compounds each, always resolving to the same handful of
famous, already-well-known plants (valerenic acid -> Valeriana officinalis,
curcumin -> Curcuma longa, ...). Any "discovery engine" built on top of
those maps could only ever rediscover plants a human already knows about.

The platform's real compound-occurrence data is much larger and already
live: the plant_compounds Supabase table (Dr. Duke's phytochemical data,
~2,000+ plants -- see botanical_rd_candidate_engine.py's
_candidates_from_plant_compounds() docstring) already carries
scientific_name / compound_name / compound_class / target / mechanism /
plant_part / evidence_level / confidence_score / source / source_year /
reference_title / reference_url per row. This module turns that table into
a proper compound -> [occurrence record, ...] reverse index, so "which
plants contain X" is answered from real data with real provenance, not a
lookup table someone typed by hand.

WHAT THIS MODULE DOES NOT DO:
  - It does not fetch data itself. Callers pass in an already-loaded
    plant_compounds_df (dependency injection, matching every other engine
    in this codebase -- see BotanicalRDCandidateEngine's own constructor
    pattern). No network/Supabase call lives here.
  - It does not decide which candidates enter Stage 5 discovery. That
    decision belongs to indication_candidate_discovery.py's prescreen; this
    module only supplies the compound-occurrence facts and a specificity
    signal that prescreen (or any other caller) can use.
  - It does not attempt identifier-level (ChEMBL ID / PubChem CID /
    InChIKey) canonicalization. Matching here is a normalized-text lookup
    (case/whitespace-insensitive, plus a conservative substring fallback
    for compound-derivative names like "quercetin 3-O-glucoside" vs
    "quercetin"). Identifier-based canonicalization would need a compound
    identity service this platform does not yet have; documented here as a
    known limitation rather than silently pretended away.

Legacy hard-coded maps (botanical_brain_engine.COMPOUND_PLANT_MAP,
compound_occurrence_map.COMPOUND_PLANT_MAP) are NOT deleted by this module.
A caller may still pass one in as ``legacy_fallback_map`` -- used ONLY when
the real index has no match at all, and every record built from it is
tagged ``origin=SOURCE_LEGACY_FALLBACK_MAP`` so nothing downstream can
mistake a hand-typed fallback fact for a database-verified one.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Any, Mapping

import pandas as pd

SOURCE_PLANT_COMPOUNDS_DATABASE = "plant_compounds_database"
SOURCE_LEGACY_FALLBACK_MAP = "legacy_fallback_map"

_WHITESPACE_RE = re.compile(r"\s+")

# The plant_compounds columns this module reads (see module docstring for
# where each is documented in botanical_rd_candidate_engine.py). Every
# column is optional except compound_name/scientific_name, which are
# required for a row to produce an occurrence record at all.
_OPTIONAL_COLUMNS = (
    "common_name", "compound_class", "plant_part", "target", "mechanism",
    "evidence_level", "confidence_score", "source", "source_year",
    "reference_title", "reference_url",
)


def normalize_compound_name(name: Any) -> str:
    """Case/whitespace-insensitive normalization -- the same convention
    (lowercase, collapsed whitespace) used throughout this codebase's own
    ``_norm`` helpers, kept local here so this module has no import
    coupling to any single engine's private normalizer.
    """
    if name is None:
        return ""
    text = str(name).strip().lower()
    if text in ("nan", "none", "null"):
        return ""
    return _WHITESPACE_RE.sub(" ", text)


def build_compound_plant_index(
    plant_compounds_df: pd.DataFrame,
) -> dict[str, list[dict[str, Any]]]:
    """Build a normalized-compound-name -> [occurrence record, ...] reverse
    index from the real plant_compounds table.

    Returns an empty dict (never raises) for a missing/empty/malformed
    input, so every caller can treat "no data available" and "no matches
    found" as the same safe, empty-result case.
    """
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if not isinstance(plant_compounds_df, pd.DataFrame) or plant_compounds_df.empty:
        return dict(index)
    if "compound_name" not in plant_compounds_df.columns or "scientific_name" not in plant_compounds_df.columns:
        return dict(index)

    for _, row in plant_compounds_df.iterrows():
        compound_norm = normalize_compound_name(row.get("compound_name"))
        plant = str(row.get("scientific_name") or "").strip()
        if not compound_norm or not plant:
            continue
        record: dict[str, Any] = {
            "scientific_name": plant,
            "compound": str(row.get("compound_name") or "").strip(),
            "origin": SOURCE_PLANT_COMPOUNDS_DATABASE,
        }
        for column in _OPTIONAL_COLUMNS:
            value = row.get(column) if column in plant_compounds_df.columns else None
            record[column] = "" if value is None or (isinstance(value, float) and pd.isna(value)) else value
        index[compound_norm].append(record)

    return dict(index)


def find_plants_for_compound(
    compound: Any,
    index: Mapping[str, list[dict[str, Any]]],
    *,
    legacy_fallback_map: Mapping[str, list[str]] | None = None,
) -> list[dict[str, Any]]:
    """Return every known occurrence record for ``compound``.

    Lookup order (first non-empty result wins -- never blended, so a
    caller can always tell which tier answered):
      1. Exact normalized-name match against the real index.
      2. Conservative substring match against the real index (handles a
         compound derivative name, e.g. a specific glycoside, against its
         parent compound entry, or vice versa) -- still real,
         database-backed records, just matched more loosely.
      3. ``legacy_fallback_map`` (if supplied), producing minimal records
         with no provenance beyond "legacy curated MVP occurrence map" and
         origin=SOURCE_LEGACY_FALLBACK_MAP -- explicitly the lowest-trust
         tier, never silently equated with a real database record.

    Returns an empty list (never raises) if nothing matches at any tier.
    """
    compound_norm = normalize_compound_name(compound)
    if not compound_norm:
        return []

    exact = list(index.get(compound_norm, []))
    if exact:
        return exact

    substring_matches: list[dict[str, Any]] = []
    for key, records in index.items():
        if key == compound_norm:
            continue
        if compound_norm in key or key in compound_norm:
            substring_matches.extend(records)
    if substring_matches:
        return substring_matches

    if legacy_fallback_map:
        legacy_records: list[dict[str, Any]] = []
        for key, plants in legacy_fallback_map.items():
            key_norm = normalize_compound_name(key)
            if not key_norm:
                continue
            if compound_norm == key_norm or compound_norm in key_norm or key_norm in compound_norm:
                for plant in plants or []:
                    plant_name = str(plant).strip()
                    if not plant_name:
                        continue
                    legacy_records.append({
                        "scientific_name": plant_name,
                        "compound": str(compound).strip(),
                        "common_name": "", "compound_class": "", "plant_part": "",
                        "target": "", "mechanism": "", "evidence_level": "",
                        "confidence_score": None,
                        "source": "legacy curated MVP occurrence map (not database-verified)",
                        "source_year": "", "reference_title": "", "reference_url": "",
                        "origin": SOURCE_LEGACY_FALLBACK_MAP,
                    })
        if legacy_records:
            return legacy_records

    return []


def compound_plant_count(compound: Any, index: Mapping[str, list[dict[str, Any]]]) -> int:
    """Distinct plant count for ``compound`` in the real index only (never
    the legacy fallback -- the fallback map's own coverage is not a
    meaningful specificity signal). 0 if the compound has no real-index
    entry at all, including when it would only be found via
    find_plants_for_compound()'s substring or legacy tiers.
    """
    records = index.get(normalize_compound_name(compound), [])
    return len({r["scientific_name"] for r in records if r.get("scientific_name")})


def compound_specificity_score(plant_count: int) -> float:
    """0-1 specificity score: 1.0 for a compound reported in zero or one
    plant, decreasing smoothly as plant_count grows, via 1 / log2(1 + n).
    A continuous curve (rather than hard tier cutoffs) so a compound in 2
    plants and one in 3 plants are not treated identically.

    PROVISIONAL -- an engineering heuristic for ranking/throttling, not a
    statistically calibrated measure of biological specificity, matching
    the documented status of every other score in this scoring layer (see
    rd_discovery_classification.py's own PROVISIONAL caveats).
    """
    n = max(0, int(plant_count))
    if n <= 1:
        return 1.0
    return round(1.0 / math.log2(1 + n), 4)


def compound_specificity_tier(plant_count: int) -> str:
    """Human-readable specificity tier for display/explanation text,
    using the same plant_count input as compound_specificity_score() --
    kept as a separate function so a caller that only needs the label
    does not have to reverse-engineer it from the numeric score.
    """
    n = max(0, int(plant_count))
    if n <= 0:
        return "Unknown occurrence"
    if n <= 3:
        return "Rare / mechanism-specific"
    if n <= 15:
        return "Moderate occurrence"
    return "Common / non-specific"
