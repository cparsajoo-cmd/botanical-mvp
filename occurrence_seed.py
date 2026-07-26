"""
Task 7 — Populating data_contracts.PlantCompoundOccurrence.

WHAT THIS IS
An import mechanism only — no new botanical claims are made anywhere
in this file. Every PlantCompoundOccurrence this module produces is
mechanically DERIVED from data already curated in seed_data.py:
seed_data.PLANT_COMPOUNDS already carries a per-compound extraction
hint as the third element of each (name, class, extraction) tuple, and
seed_data.PLANTS already carries a per-plant part. This module simply
joins those two already-existing, already-reviewed sources into the
compound-level, occurrence-granular shape data_contracts.py's
PlantCompoundOccurrence dataclass was designed for — nothing here is
looked up externally, hand-typed as a new claim, or independently
asserted.

THE GAP THIS CLOSES (verified in the engine's own code, not assumed)
botanical_rd_candidate_engine.py's _richer_candidate_plants-adjacent
candidate-building code (the `for plant, compounds in
PLANT_COMPOUNDS.items()` loop) takes `next((ext for _name, _cls, ext
in compounds if ext), "")` — i.e. only the FIRST compound's extraction
hint survives as that PLANT's single Extraction_Method value; every
other compound's own, possibly quite different, extraction hint is
silently discarded once flattened to plant level. A plant with three
compounds extracted by infusion, steam distillation, and infusion
respectively ends up reporting only "infusion" for all three. This
module restores the compound-specific information seed_data.py already
had, so _best_extraction() can report the ACTUAL matched compound's
own extraction method instead of whichever compound happened to be
listed first for that plant.

CONFIDENCE / VERIFICATION HONESTY
Every record's verification_status is UNKNOWN (the dataclass default)
and confidence is None — this is a structural re-derivation of an
internal curated seed dataset, not an independently verified or
confidence-scored claim. study_or_source names the seed dataset
plainly rather than implying a literature citation that doesn't exist
here.

HOW TO USE
    from occurrence_seed import build_occurrence_lookup
    lookup = build_occurrence_lookup()
    occurrence = lookup.get((_norm(plant_name), _norm(compound_name)))
"""

from __future__ import annotations

import re

from data_contracts import PlantCompoundOccurrence, VerificationStatus
from seed_data import PLANTS, PLANT_COMPOUNDS

SOURCE_LABEL = "seed_data.PLANT_COMPOUNDS (internal curated seed)"


def _norm(value) -> str:
    """Mirrors botanical_rd_candidate_engine.BotanicalRDCandidateEngine._norm()'s
    algorithm exactly (lowercase, collapsed whitespace, blank for
    nan/none/null) — duplicated here (six lines) rather than imported,
    to avoid a two-way import between this module and the engine
    module; the two must stay algorithmically identical, which is why
    this docstring says so explicitly rather than leaving it implicit.
    """
    if value is None:
        return ""
    value = str(value).strip().lower()
    if value in {"nan", "none", "null"}:
        return ""
    return re.sub(r"\s+", " ", value)


def _plant_part_lookup() -> dict:
    """plant_scientific_name -> plant_part, read directly from
    seed_data.PLANTS's existing 5-tuple (name, common_name, family,
    region, plant_part) — no new data."""
    return {plant[0]: plant[4] for plant in PLANTS if len(plant) >= 5 and plant[4]}


def load_occurrence_records() -> list:
    """Returns one PlantCompoundOccurrence per (plant, compound) pair
    in seed_data.PLANT_COMPOUNDS that has a non-empty extraction hint
    — every field traceable to seed_data.py's own existing tuples, see
    module docstring."""
    plant_parts = _plant_part_lookup()
    records = []

    for plant, compounds in PLANT_COMPOUNDS.items():
        plant_part = plant_parts.get(plant)
        for compound_name, _compound_class, extraction_hint in compounds:
            if not extraction_hint:
                continue
            records.append(PlantCompoundOccurrence(
                plant_scientific_name=plant,
                accepted_taxonomic_name=plant,
                plant_synonym_used=None,
                compound_id=compound_name,
                plant_part=plant_part,
                detection_method=None,
                concentration_value=None,
                concentration_unit=None,
                extract_basis=None,
                dry_fresh_basis=None,
                extraction_solvent=extraction_hint,
                study_or_source=SOURCE_LABEL,
                confidence=None,
                verification_status=VerificationStatus.UNKNOWN,
                source_record_ids=[],
            ))

    return records


def build_occurrence_lookup() -> dict:
    """Returns {(norm_plant_name, norm_compound_id): PlantCompoundOccurrence}.
    If the same (plant, compound) pair appears more than once in
    seed_data.PLANT_COMPOUNDS (not expected, but not structurally
    impossible), the LAST one wins — callers needing every occurrence
    for a pair should use load_occurrence_records() directly instead.
    """
    lookup = {}
    for occurrence in load_occurrence_records():
        key = (_norm(occurrence.plant_scientific_name), _norm(occurrence.compound_id))
        lookup[key] = occurrence
    return lookup
