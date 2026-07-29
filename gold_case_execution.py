"""
Reference-Grounded Validation — GoldCase Execution.

WHY THIS DOES NOT ROUTE THROUGH validation_protocol_execution.py
validation_protocol_execution.execute_protocol_against_engine() requires
a LOCKED ValidationCaseProtocol, and ValidationCaseProtocol.lock_protocol()
hard-requires a real ExpertPanel — correct for a commercial validation
case, where a live expert panel is exactly what Appendix A demands. A
GoldCase is curated directly against authoritative references with NO
live expert panel required (Reference-Grounded Validation Principle —
see gold_case.CurationStatus). This module calls
BotanicalRDCandidateEngine directly, the same way
validation_protocol_execution.py itself does, without ever
constructing a ValidationCaseProtocol. validation_case_protocol.py is
untouched by this decision.

STRUCTURAL LEAKAGE BOUNDARY (v4 correction #1)
The ONLY evidence this function accepts is
list[engine_evidence_input.EngineEvidenceInput] — a frozen dataclass
with exactly three plain-string fields (scientific_name,
target_indication, notes). It is structurally impossible to pass a
ReferenceClaim or ResolvedExpectedOutcome through this parameter: no
such field exists on EngineEvidenceInput, so nothing about the
approved "reference truth" layer can reach the engine's actual
constructor call. This replaces the PRIOR (incorrect) design that
accepted a raw target= string as an ad hoc test-only trigger — that
parameter has been REMOVED entirely, not merely deprecated. Real
evidence must now flow as natural-language text in
EngineEvidenceInput.notes, exactly the way genuine evidence enters
production via evidence_df["Notes"] (see
botanical_rd_candidate_engine.py's _collect_raw_evidence()).

SINGLE-TAXON SCOPE, NEUTRAL ANCHOR (unchanged from the prior revision)
A GoldCase's ValidationUnit names exactly one taxon. This module runs
the engine with a fixed, neutral anchor taxon as the reference plant
and the GoldCase's real taxon as the alternative — NEVER a self-match
row, because botanical_rd_candidate_engine.py's same_plant exemption
would silently make the safety/regulatory gates NOT_EVALUABLE for a
self-matched row, defeating the entire point of a Safety-Serious
GoldCase. See test_gold_case_execution.py's
test_returned_row_uses_anchor_as_reference_and_taxon_as_alternative
for the regression lock on this.

WHAT THIS NEVER DOES
Never modifies botanical_rd_candidate_engine.py. Never computes a
metric itself (see evaluation_run.py). Never persists anything (see
gold_case_persistence.py / evaluation_run_persistence.py).
"""

from __future__ import annotations

import pandas as pd

from botanical_rd_candidate_engine import BotanicalRDCandidateEngine
from engine_evidence_input import EngineEvidenceInput
from gold_case import GoldCase


class GoldCaseNotExecutableError(Exception):
    """Raised when a GoldCase cannot be run — missing indication, or
    missing preparation/dosage_form."""


# A fixed, neutral placeholder scientific name used ONLY as the
# reference-plant anchor for GoldCase execution — see module
# docstring. Deliberately unrealistic so it can never collide with a
# genuine GoldCase taxon.
_GOLD_CASE_ANCHOR_TAXON = "GoldSetExecutionAnchorPlant__DoNotUseAsRealTaxon"


def _evidence_inputs_to_dataframe(evidence: list) -> pd.DataFrame:
    """The ONLY function that converts EngineEvidenceInput records
    into the DataFrame shape botanical_rd_candidate_engine.py's
    evidence_df parameter expects (Scientific_Name/Target_Indication/
    Notes). Reads exactly EngineEvidenceInput's three plain-string
    fields — nothing else can reach this conversion, by construction
    of that frozen dataclass."""
    if not evidence:
        return pd.DataFrame()
    return pd.DataFrame([
        {
            "Scientific_Name": item.scientific_name,
            "Target_Indication": item.target_indication,
            "Notes": item.notes,
        }
        for item in evidence
    ])


def execute_gold_case_against_engine(
    gold_case: GoldCase,
    evidence: list = None,
    compound_name: str = "primary_compound",
    compound_profiles_df: pd.DataFrame = None,
    scientific_evidence_df: pd.DataFrame = None,
    use_live_search: bool = False,
) -> pd.DataFrame:
    """Runs BotanicalRDCandidateEngine.run() for exactly the one taxon
    named in gold_case.validation_unit, against a neutral anchor
    reference plant. Raises GoldCaseNotExecutableError if the
    ValidationUnit lacks an indication or a dosage_form.

    evidence: list[EngineEvidenceInput] — the ONLY way real evidence
    text reaches the engine (see module docstring's leakage-boundary
    section). None/empty means the engine runs with no evidence at
    all for this taxon (a legitimate, meaningful case: it should
    produce NOT_EVALUABLE gates and a low-confidence/insufficient-
    evidence decision, not an error).

    compound_name is plumbing only (links the anchor and taxon rows
    via a shared compound so the engine treats them as comparable) —
    not part of ValidationUnit's approved 8-dimension schema, and
    never derived from anything in the reference-truth layer.

    Returns the engine's raw result_df, filtered to the single row
    where Reference_Plant is the anchor and Alternative_Plant is the
    GoldCase's own taxon (never the anchor's own self-match row).
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

    taxon_targets = []
    for item in (evidence or []):
        if item.scientific_name == unit.taxon:
            taxon_targets.extend(item.compound_activity_targets)
    target_value = "; ".join(dict.fromkeys(taxon_targets)) if taxon_targets else "unspecified"

    plant_compounds_df = pd.DataFrame([
        {
            "scientific_name": _GOLD_CASE_ANCHOR_TAXON,
            "compound_name": compound_name,
            "indication": unit.indication,
            "target": "unspecified",
            "common_name": "", "plant_part": "", "extraction_method": "",
        },
        {
            "scientific_name": unit.taxon,
            "compound_name": compound_name,
            "indication": unit.indication,
            "target": target_value,
            "common_name": "",
            "plant_part": unit.plant_part or "",
            "extraction_method": (unit.preparation.solvent if unit.preparation else "") or "",
        },
    ])

    evidence_df = _evidence_inputs_to_dataframe(evidence or [])

    engine = BotanicalRDCandidateEngine(
        plant_compounds_df=plant_compounds_df,
        compound_profiles_df=compound_profiles_df if compound_profiles_df is not None else pd.DataFrame(),
        scientific_evidence_df=scientific_evidence_df if scientific_evidence_df is not None else pd.DataFrame(),
        evidence_df=evidence_df,
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
    execute_gold_case_against_engine()'s result. Returns an empty dict
    (not None, not a fabricated default) if result_df is empty.
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
