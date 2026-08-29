"""Rank a plant's candidate indications by how often each one is actually
cited across that plant's own compound/evidence records -- not by
alphabetical order.

Extracted from pages/Bulk evidence.py::_all_plants_with_indications() (2026-
08-29 session): that function grouped plant_compounds_df by scientific_name,
collected every distinct indication string attached to any compound record
for that plant, ALPHABETICALLY sorted the resulting set, and kept only the
first MAX_INDICATIONS_PER_PLANT. Because many unrelated plants share common
phytochemicals (and therefore share the same broad, compound-level
indication vocabulary), this consistently picked whichever indications
happened to start with an early letter (observed in production: "AIDS/HIV;
BPH; Cancer; Dermatitis/Dermatoses; Diabetes" -- identical across dozens of
otherwise unrelated plants) instead of the indications that were actually
most strongly/frequently associated with that specific plant. Downstream,
that alphabetically-arbitrary indication list is what drives the bulk
evidence-gathering search queries for the plant, so a plant with a genuine,
well-documented traditional/clinical use (e.g. Tripterygium wilfordii for
rheumatoid arthritis/autoimmune conditions) could be searched almost
entirely for unrelated topics, while its actual safety-relevant literature
was never queried at all.
"""
from __future__ import annotations

from collections import Counter
from typing import Iterable


def rank_plant_indications(indication_texts: Iterable[str], max_indications: int = 5) -> list[str]:
    """Return up to ``max_indications`` indication strings for one plant,
    ranked by how many of the plant's own compound/evidence records cite
    each one -- most-cited first. Ties are broken alphabetically, only for
    a deterministic, reproducible order (not as the primary ranking
    criterion, unlike the alphabetical-only approach this replaces).

    ``indication_texts`` is any iterable of raw indication strings, each
    possibly semicolon-separated (e.g. "Diabetes; Metabolic syndrome") --
    the same raw shape already stored in plant_compounds_df's indication
    column. Blank/whitespace-only entries are ignored. Never raises on
    malformed input; worst case returns an empty list.
    """
    counts: Counter[str] = Counter()
    for text in indication_texts or []:
        if not text:
            continue
        for part in str(text).split(";"):
            clean = part.strip()
            if clean:
                counts[clean] += 1

    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [name for name, _count in ranked[: max(0, int(max_indications))]]
