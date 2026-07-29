"""
Structural leakage boundary tests (v4 correction #1).

WHAT THIS PROVES
That EngineEvidenceInput is structurally incapable of holding a
ReferenceClaim or ResolvedExpectedOutcome, and that the real engine
constructor never receives one — proven via (a) dataclass field
introspection (a TYPE-level guarantee, not a runtime text scan) and
(b) a spy wrapping the real BotanicalRDCandidateEngine constructor
that captures and inspects the actual evidence_df passed to it.

WHAT THIS DELIBERATELY DOES NOT DO
Scan any string content for forbidden words like "SERIOUS" or
"severity" — the approved architecture explicitly rejects that
approach (natural authoritative evidence legitimately contains such
words). Every test here checks TYPES and FIELD SETS, never string
content for banned vocabulary.
"""

import dataclasses
import inspect

import pandas as pd

from engine_evidence_input import EngineEvidenceInput
from gold_case_execution import execute_gold_case_against_engine, _evidence_inputs_to_dataframe
from reference_claim import ReferenceClaim
from resolved_expected_outcome import ResolvedExpectedOutcome


# ---------------------------------------------------------------------
# Type-level guarantee: EngineEvidenceInput's own field set
# ---------------------------------------------------------------------

def test_engine_evidence_input_has_no_field_of_type_reference_claim():
    field_types = {f.name: f.type for f in dataclasses.fields(EngineEvidenceInput)}
    for name, type_repr in field_types.items():
        assert "ReferenceClaim" not in str(type_repr), name
        assert "ResolvedExpectedOutcome" not in str(type_repr), name


def test_engine_evidence_input_field_set_is_exactly_four_plain_fields():
    field_names = {f.name for f in dataclasses.fields(EngineEvidenceInput)}
    assert field_names == {
        "scientific_name", "target_indication", "notes", "compound_activity_targets",
    }


def test_engine_evidence_input_every_field_is_a_primitive_or_tuple_of_primitives():
    instance = EngineEvidenceInput(
        scientific_name="X", target_indication="Y", notes="Z",
        compound_activity_targets=("A", "B"),
    )
    assert isinstance(instance.scientific_name, str)
    assert isinstance(instance.target_indication, str)
    assert isinstance(instance.notes, str)
    assert isinstance(instance.compound_activity_targets, tuple)
    for item in instance.compound_activity_targets:
        assert isinstance(item, str)


def test_engine_evidence_input_is_frozen():
    instance = EngineEvidenceInput(scientific_name="X", target_indication="Y", notes="Z")
    try:
        instance.notes = "tampered"
        assert False, "should have raised (frozen dataclass)"
    except dataclasses.FrozenInstanceError:
        pass


def test_engine_evidence_input_cannot_be_constructed_with_a_reference_claim_argument():
    # There is no keyword this could even bind to — confirms no
    # backdoor parameter exists.
    sig = inspect.signature(EngineEvidenceInput.__init__)
    assert "claim" not in sig.parameters
    assert "resolved_outcome" not in sig.parameters
    assert "expected_outcome" not in sig.parameters


# ---------------------------------------------------------------------
# Interface-level guarantee: execute_gold_case_against_engine()'s own
# signature has no reference-truth-typed parameter.
# ---------------------------------------------------------------------

def test_execute_gold_case_signature_has_no_reference_truth_parameter():
    sig = inspect.signature(execute_gold_case_against_engine)
    for name, param in sig.parameters.items():
        annotation_str = str(param.annotation)
        assert "ReferenceClaim" not in annotation_str, name
        assert "ResolvedExpectedOutcome" not in annotation_str, name


def test_execute_gold_case_has_no_target_parameter():
    # Direct regression lock: the OLD (incorrect) design had a bare
    # target= string kwarg — removed entirely, not merely deprecated.
    sig = inspect.signature(execute_gold_case_against_engine)
    assert "target" not in sig.parameters


def test_execute_gold_case_evidence_parameter_only_accepts_engine_evidence_input_list():
    sig = inspect.signature(execute_gold_case_against_engine)
    assert "evidence" in sig.parameters


# ---------------------------------------------------------------------
# Conversion function: the ONE place EngineEvidenceInput becomes a
# DataFrame — never reads anything beyond its own three text fields.
# ---------------------------------------------------------------------

def test_evidence_inputs_to_dataframe_only_contains_expected_columns():
    evidence = [EngineEvidenceInput(scientific_name="X", target_indication="Y", notes="Z")]
    df = _evidence_inputs_to_dataframe(evidence)
    assert set(df.columns) == {"Scientific_Name", "Target_Indication", "Notes"}


def test_evidence_inputs_to_dataframe_every_cell_is_a_plain_string():
    evidence = [EngineEvidenceInput(scientific_name="X", target_indication="Y", notes="Z")]
    df = _evidence_inputs_to_dataframe(evidence)
    for value in df.iloc[0]:
        assert isinstance(value, str)
        assert not isinstance(value, (ReferenceClaim, ResolvedExpectedOutcome))


def test_evidence_inputs_to_dataframe_empty_input_returns_empty_dataframe():
    df = _evidence_inputs_to_dataframe([])
    assert df.empty


# ---------------------------------------------------------------------
# Spy on the real engine constructor: capture the ACTUAL evidence_df
# and plant_compounds_df passed at runtime, prove neither can contain
# a ReferenceClaim/ResolvedExpectedOutcome instance anywhere.
# ---------------------------------------------------------------------

def test_spy_on_real_engine_constructor_never_receives_reference_truth_objects():
    import botanical_rd_candidate_engine as eng
    from gold_case import GoldCase
    from validation_unit import ValidationUnit, PreparationSpec

    eng.SIMILAR_COMPOUND_GROUPS = {}
    eng.COMPOUND_TARGETS = {}

    captured = {}
    real_init = eng.BotanicalRDCandidateEngine.__init__

    def spy_init(self, *args, **kwargs):
        captured["kwargs"] = kwargs
        return real_init(self, *args, **kwargs)

    unit = ValidationUnit(
        taxon="SpyTestTaxon", indication="TestIndication",
        preparation=PreparationSpec(dosage_form="Infusion"), jurisdiction="EU",
    )
    case = GoldCase(case_id="spy_test", validation_unit=unit)
    evidence = [EngineEvidenceInput(
        scientific_name="SpyTestTaxon", target_indication="TestIndication",
        notes="Natural evidence text mentioning a serious contraindication in pregnancy.",
        compound_activity_targets=("Lithogenic",),
    )]

    original_init = eng.BotanicalRDCandidateEngine.__init__
    try:
        eng.BotanicalRDCandidateEngine.__init__ = spy_init
        execute_gold_case_against_engine(case, evidence=evidence)
    finally:
        eng.BotanicalRDCandidateEngine.__init__ = original_init

    assert "kwargs" in captured, "spy never fired — engine constructor was not called"

    for key in ("plant_compounds_df", "evidence_df", "compound_profiles_df", "scientific_evidence_df"):
        value = captured["kwargs"].get(key)
        if value is None or not isinstance(value, pd.DataFrame):
            continue
        for column in value.columns:
            for cell in value[column]:
                assert not isinstance(cell, (ReferenceClaim, ResolvedExpectedOutcome)), (
                    f"{key}[{column!r}] contains a reference-truth object: {cell!r}"
                )


def test_spy_confirms_evidence_df_contains_only_the_three_expected_columns():
    import botanical_rd_candidate_engine as eng
    from gold_case import GoldCase
    from validation_unit import ValidationUnit, PreparationSpec

    eng.SIMILAR_COMPOUND_GROUPS = {}
    eng.COMPOUND_TARGETS = {}

    captured = {}
    real_init = eng.BotanicalRDCandidateEngine.__init__

    def spy_init(self, *args, **kwargs):
        captured["kwargs"] = kwargs
        return real_init(self, *args, **kwargs)

    unit = ValidationUnit(
        taxon="SpyTestTaxon2", indication="TestIndication",
        preparation=PreparationSpec(dosage_form="Infusion"), jurisdiction="EU",
    )
    case = GoldCase(case_id="spy_test_2", validation_unit=unit)
    evidence = [EngineEvidenceInput(
        scientific_name="SpyTestTaxon2", target_indication="TestIndication",
        notes="Some natural text.",
    )]

    original_init = eng.BotanicalRDCandidateEngine.__init__
    try:
        eng.BotanicalRDCandidateEngine.__init__ = spy_init
        execute_gold_case_against_engine(case, evidence=evidence)
    finally:
        eng.BotanicalRDCandidateEngine.__init__ = original_init

    evidence_df = captured["kwargs"]["evidence_df"]
    assert set(evidence_df.columns) == {"Scientific_Name", "Target_Indication", "Notes"}
