"""
Validation Architecture v3 — Phase 2: GoldCase Execution.

WHY THIS DOES NOT ROUTE THROUGH validation_protocol_execution.py
validation_protocol_execution.execute_protocol_against_engine() requires
a LOCKED ValidationCaseProtocol, and ValidationCaseProtocol.lock_protocol()
hard-requires a real ExpertPanel (members, review_protocol,
independence_statement) — correct for a commercial validation case,
where a live expert panel is exactly what Appendix A demands. A
GoldCase, by contrast, is typically curated directly against an
authoritative monograph (Layer 1 of the validation architecture) with
NO live expert panel involved at all for the majority of cases (only
Layer 5's escalated cases ever see one). Fabricating a placeholder
ExpertPanel just to satisfy lock_protocol()'s gate would be exactly
the kind of dishonest workaround this whole pipeline exists to
prevent — so this module calls BotanicalRDCandidateEngine directly,
the same way validation_protocol_execution.py itself does, without
ever constructing a ValidationCaseProtocol. Both modules are
independent, honest consumers of the same unmodified engine.
validation_case_protocol.py is untouched by this decision.

SINGLE-TAXON SCOPE
A GoldCase's ValidationUnit names exactly one taxon. This module runs
the engine with that ONE taxon as both reference and alternative (a
self-match row) — the engine's own Decision_Class/Gate_Results/
GRADE_Certainty for that single preparation/indication combination is
the "platform output" a GoldCase's ExpectedOutput is compared against.
This is a narrower use of the engine than
validation_protocol_execution.py's multi-candidate comparison (which
answers "how does this candidate rank against others") — a GoldCase
answers "is the platform's own classification of THIS ONE candidate
correct," which does not need a comparison set.

WHAT THIS NEVER DOES
Never modifies botanical_rd_candidate_engine.py. Never computes a
metric itself (see evaluation_run.py for that). Never persists
anything (see gold_case_persistence.py / evaluation_run_persistence.py).
"""

from __future__ import annotations

import pandas as pd

from botanical_rd_candidate_engine import BotanicalRDCandidateEngine
from gold_case import GoldCase


class GoldCaseNotExecutableError(Exception):
    """Raised when a GoldCase cannot be run — missing indication, or
    missing preparation/dosage_form. Mirrors
    validation_protocol_execution.py's own ValueError cases, as a
    named exception type instead, since GoldCase execution has its own
    distinct failure modes worth naming (e.g. Phase 1's
    Preparation-Mismatch stratum cases are EXPECTED to be
    inexecutable, per their own correct_abstention_expected=True)."""


# A fixed, neutral placeholder scientific name used ONLY as the
# reference-plant anchor for GoldCase execution — see
# execute_gold_case_against_engine()'s own docstring for why a
# self-match row cannot be used here. This name is deliberately
# unrealistic (never a real botanical taxon) so it can never
# accidentally collide with a genuine GoldCase taxon.
_GOLD_CASE_ANCHOR_TAXON = "GoldSetExecutionAnchorPlant__DoNotUseAsRealTaxon"


def execute_gold_case_against_engine(
    gold_case: GoldCase,
    compound_name: str = "primary_compound",
    target: str = "unspecified",
    compound_profiles_df: pd.DataFrame = None,
    scientific_evidence_df: pd.DataFrame = None,
    evidence_df: pd.DataFrame = None,
    use_live_search: bool = False,
) -> pd.DataFrame:
    """Runs BotanicalRDCandidateEngine.run() for exactly the one taxon
    named in gold_case.validation_unit. Raises GoldCaseNotExecutableError
    if the ValidationUnit lacks an indication or a dosage_form — the
    two fields the engine's run() signature requires — rather than
    silently defaulting either.

    WHY A NEUTRAL ANCHOR REFERENCE PLANT, NOT A SELF-MATCH ROW
    An earlier version of this function ran the GoldCase's taxon
    against ITSELF (reference_plant == alternative_plant). That is a
    real bug, not a simplification: botanical_rd_candidate_engine.py's
    same_plant exemption (Task 4's hard safety/regulatory exclusion
    design) deliberately makes the safety and regulatory gates
    NOT_EVALUABLE for any self-matched row, precisely so a plant's own
    trace evidence can never trigger a false hard-stop against itself.
    That means a self-match execution can NEVER exercise a
    Safety-Serious or regulatory-prohibition GoldCase correctly — the
    hard gates this validation architecture most needs to check would
    silently never run. This function instead builds TWO rows sharing
    one compound: a fixed, neutral _GOLD_CASE_ANCHOR_TAXON as the
    reference plant, and the GoldCase's real taxon as the alternative
    — exactly mirroring how the engine's own existing tests exercise
    the hard safety/regulatory gates (see test_gate_layer.py's
    test_regulatory_prohibition_end_to_end_through_run, which uses a
    distinct RefPlant/AltPlant pair for the same reason). The returned
    row is the one where Alternative_Plant == the GoldCase's taxon,
    never the anchor's own self-match row.

    compound_name/target are NOT part of ValidationUnit (Validation
    Architecture v3's approved 8-dimension schema has no compound/
    target field — the engine needs one to build a minimal
    plant_compounds_df row) — passed explicitly by the caller with
    documented defaults, never invented by this function.

    Returns the engine's raw result_df, filtered to the single row
    where Alternative_Plant is the GoldCase's own taxon and
    Reference_Plant is the anchor (never the self-match row).
    """
    unit = gold_case.validation_unit

    if not unit.indication:
        raise GoldCaseNotExecutableError(
            f"GoldCase {gold_case.case_id!r}: validation_unit.indication is not set."
        )
    dosage_form = unit.preparation.dosage_form if unit.preparation else None
    if not dosage_form:
        raise GoldCaseNotExecutableError(
            f"GoldCase {gold_case.case_id!r}: validation_unit.preparation.dosage_form is not set."
        )

    shared_compound = compound_name
    plant_compounds_df = pd.DataFrame([
        {
            "scientific_name": _GOLD_CASE_ANCHOR_TAXON,
            "compound_name": shared_compound,
            "indication": unit.indication,
            "target": target,
            "common_name": "", "plant_part": "", "extraction_method": "",
        },
        {
            "scientific_name": unit.taxon,
            "compound_name": shared_compound,
            "indication": unit.indication,
            "target": target,
            "common_name": "",
            "plant_part": unit.plant_part or "",
            "extraction_method": (unit.preparation.solvent if unit.preparation else "") or "",
        },
    ])

    engine = BotanicalRDCandidateEngine(
        plant_compounds_df=plant_compounds_df,
        compound_profiles_df=compound_profiles_df if compound_profiles_df is not None else pd.DataFrame(),
        scientific_evidence_df=scientific_evidence_df if scientific_evidence_df is not None else pd.DataFrame(),
        evidence_df=evidence_df if evidence_df is not None else pd.DataFrame(),
        use_live_search=use_live_search,
    )

    result_df = engine.run(
        indication=unit.indication,
        dosage_form=dosage_form,
        market=unit.jurisdiction or "",
    )

    return result_df[
        (result_df["Reference_Plant"] == _GOLD_CASE_ANCHOR_TAXON)
        & (result_df["Alternative_Plant"] == unit.taxon)
    ]


def platform_output_for_gold_case(result_df: pd.DataFrame) -> dict:
    """Extracts the compact platform-output view from
    execute_gold_case_against_engine()'s result — the fields
    evaluation_run.py compares against ExpectedOutput. Returns an
    empty dict (not None, not a fabricated default) if result_df is
    empty — e.g. when the engine produced no row at all for this
    taxon, which is itself meaningful information the caller must not
    silently paper over.
    """
    if result_df is None or result_df.empty:
        return {}
    row = result_df.iloc[0]
    return {
        "decision_class": row.get("Decision_Class"),
        "decision_class_ah": row.get("Decision_Class_AH"),
        "gate_results": row.get("Gate_Results"),
        "grade_certainty": row.get("GRADE_Certainty"),
        "rd_opportunity_score": row.get("R&D_Opportunity_Score"),
    }
