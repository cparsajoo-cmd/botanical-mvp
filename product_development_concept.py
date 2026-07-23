"""
Product Development Concept (external review, repeated across rounds:
"Candidate is still a Plant, not a Botanical Development Concept").

WHAT THIS IS
Reframes a candidate row from "Alternative_Plant shares a compound with
Reference_Plant" into a structured development concept: plant, plant
part, extraction method, dosage form, route, indication, target
population, target market, regulatory pathway, and commercial
positioning — the shape an industrial R&D team actually plans around,
not just a plant name.

WHY THIS IS A POST-PROCESSING ENRICHMENT, NOT A CHANGE TO run()
Every field this pulls in either already exists on the row (plant
part, extraction method, market status, white space type) or comes
from question_understanding_engine's Standardized Project Definition
(route, target population, regulatory focus) — which is built once per
session in step_inputs.py, not per candidate row. Merging it in as an
enrichment step (same pattern as
enrich_candidates_with_market_landscape) keeps run()'s core output and
signature untouched.

HONESTY ABOUT WHAT'S REAL VS NOT TRACKED
The review's full spec included: plant species, plant part, chemotype,
extract type, extraction solvent, DER, standardization marker, dosage
form, route, dose, indication, target population, target market,
regulatory pathway, commercial positioning. Of these, this engine
genuinely tracks: plant species, plant part (as of this session),
extraction method (free text, not cleanly split into type/solvent),
dosage form, route (via question_understanding_engine), indication,
target population (when provided via free-text parsing), target
market, and an approximation of regulatory pathway (Market_Status +
regulatory_focus) and commercial positioning (Commercial_Regulatory_Rationale
+ White_Space_Type). Chemotype, DER (drug-extract ratio), standardization
marker, and dose are NOT tracked anywhere in this pipeline — they are
explicitly labeled "Not tracked" below, never silently omitted or
guessed.
"""

from __future__ import annotations

import pandas as pd

NOT_TRACKED = "Not tracked in this pipeline"


def build_development_concept_text(row, standardized_project: dict = None) -> str:
    """Builds the human-readable development-concept summary for one
    candidate row. `row` can be a pandas Series or a dict-like with the
    same keys run() produces."""
    sp = standardized_project or {}

    plant = row.get("Alternative_Plant", "Unknown plant")
    plant_part = row.get("Alternative_Plant_Part") or "Not specified in database"
    extraction = row.get("Extraction_Method") or "Not clearly reported"
    dosage_form = sp.get("dosage_form") or row.get("dosage_form") or "Not specified"
    route = sp.get("route") or "Not specified"
    indication = sp.get("target_indication") or row.get("indication") or "Not specified"
    population = sp.get("target_population") or "Not specified (assume general adult population)"
    market = sp.get("target_market") or row.get("Target_Market") or "Not specified"
    regulatory_focus = sp.get("regulatory_focus") or []
    market_status = row.get("Market_Status", "Not specified")
    white_space = row.get("White_Space_Type", "")
    commercial_note = row.get("Commercial_Regulatory_Rationale", "")

    lines = [
        f"**{plant}** ({plant_part}) — {dosage_form}, {route} route",
        f"Extraction: {extraction}",
        f"Chemotype: {NOT_TRACKED} | DER: {NOT_TRACKED} | "
        f"Standardization marker: {NOT_TRACKED} | Dose: {NOT_TRACKED}",
        f"Indication: {indication} | Target population: {population} | Target market: {market}",
        f"Regulatory pathway: {market_status}"
        + (f" ({', '.join(regulatory_focus)})" if regulatory_focus else ""),
    ]
    if white_space:
        lines.append(f"Commercial positioning: {white_space}")
    elif commercial_note:
        lines.append(f"Commercial positioning: {commercial_note}")

    return "\n".join(lines)


def add_development_concept_column(result_df: pd.DataFrame, standardized_project: dict = None) -> pd.DataFrame:
    """Returns a COPY of result_df with a new Product_Development_Concept
    column. Does not mutate the input or touch run()'s own output."""
    if result_df is None or result_df.empty:
        return result_df.copy() if result_df is not None else result_df

    enriched = result_df.copy()
    enriched["Product_Development_Concept"] = enriched.apply(
        lambda row: build_development_concept_text(row, standardized_project), axis=1
    )
    return enriched
