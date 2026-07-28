"""
GRADE certainty persistence — closing the result_df ->
CandidateAssessment -> decision_records gap.

WHAT THIS COVERS
Before this change, GRADE_Certainty/GRADE_Certainty_Rationale were
computed by botanical_rd_candidate_engine.run() and present in
result_df, but candidate_output_adapter.validate_row() had no
allowlist entry for them — CandidateAssessment silently never carried
them, and decision_record_persistence.py never persisted them. The
only place a GRADE_Certainty value could actually be seen was a raw
CSV export. This file proves that gap is closed:
  1. CandidateAssessment has grade_certainty/grade_certainty_rationale
     fields, defaulting to None.
  2. validate_row() correctly maps GRADE_Certainty/GRADE_Certainty_Rationale
     from a result_df-shaped row onto those fields.
  3. A row that lacks these columns entirely (e.g. one produced before
     this field existed) degrades to None, never crashes.
  4. decision_record_persistence._PERSISTED_RECORD_FIELDS includes
     both fields.
  5. End-to-end: a real botanical_rd_candidate_engine.run() result,
     run through validate_row() and persist_decision_record(), ends
     up with grade_certainty/grade_certainty_rationale in the
     persisted JSON blob.

WHAT THIS DELIBERATELY DOES NOT COVER
The internal correctness of classify_grade_certainty() itself (see
test_grade_certainty_classifier.py) or of the engine's own wiring of
GRADE_Certainty into result_df (see test_botanical_rd_candidate_engine.py) —
this file only covers that those two already-computed columns now
survive the adapter and persistence layers, unchanged in every other
respect (scoring, ranking, gates, UI, sensitivity are untouched by
this change).

HOW TO RUN
    pytest -q test_grade_certainty_persistence.py
    (or `pytest -q` from the repo root — auto-discovered)
"""

import json

import pandas as pd

import data_contracts as dc
from candidate_output_adapter import validate_row, validate_result_df
from decision_record_persistence import (
    _PERSISTED_RECORD_FIELDS,
    _serialize_record,
    persist_decision_record,
)


# ---------------------------------------------------------------------
# Fake Supabase client — same shape as test_decision_record_persistence.py's.
# ---------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, data):
        self.data = data


class _FakeTable:
    def __init__(self, store, table_name):
        self._store = store
        self._table_name = table_name
        self._pending_row = None

    def insert(self, row):
        self._pending_row = row
        return self

    def execute(self):
        self._store.setdefault(self._table_name, []).append(self._pending_row)
        self._pending_row = None
        return _FakeResponse(None)


class _FakeSupabaseClient:
    def __init__(self):
        self.store = {}

    def table(self, name):
        return _FakeTable(self.store, name)


# ---------------------------------------------------------------------
# 1) CandidateAssessment has the two fields, defaulting to None.
# ---------------------------------------------------------------------

def test_candidate_assessment_has_grade_certainty_fields_defaulting_to_none():
    record = dc.CandidateAssessment(
        project_id="p1", indication="Sleep", reference_plant="RefPlant",
        alternative_plant="AltPlant", product_type=None, dosage_form=None,
        target_market=None, reference_plant_part=None, reference_compound=None,
        reference_compound_id=None, alternative_plant_part=None,
        alternative_compound=None, alternative_compound_id=None,
    )
    assert record.grade_certainty is None
    assert record.grade_certainty_rationale is None


def test_candidate_assessment_accepts_grade_certainty_values():
    record = dc.CandidateAssessment(
        project_id="p1", indication="Sleep", reference_plant="RefPlant",
        alternative_plant="AltPlant", product_type=None, dosage_form=None,
        target_market=None, reference_plant_part=None, reference_compound=None,
        reference_compound_id=None, alternative_plant_part=None,
        alternative_compound=None, alternative_compound_id=None,
        grade_certainty="Moderate",
        grade_certainty_rationale="Starting certainty: High. Downgraded for: publication bias (serious).",
    )
    assert record.grade_certainty == "Moderate"
    assert "publication bias" in record.grade_certainty_rationale


# ---------------------------------------------------------------------
# 2) validate_row() maps GRADE_Certainty/GRADE_Certainty_Rationale.
# ---------------------------------------------------------------------

def _sample_row(**overrides):
    row = {
        "Reference_Plant": "RefPlant",
        "Alternative_Plant": "AltPlant",
        "GRADE_Certainty": "Moderate",
        "GRADE_Certainty_Rationale": "Starting certainty: High. Downgraded for: publication bias (serious).",
    }
    row.update(overrides)
    return pd.Series(row)


def test_validate_row_maps_grade_certainty_fields():
    record, errors = validate_row(_sample_row(), indication="Sleep")
    assert errors == []
    assert record is not None
    assert record.grade_certainty == "Moderate"
    assert record.grade_certainty_rationale == "Starting certainty: High. Downgraded for: publication bias (serious)."


def test_validate_row_maps_not_grade_applicable_value():
    record, _ = validate_row(
        _sample_row(GRADE_Certainty="Not GRADE-applicable", GRADE_Certainty_Rationale="x"),
        indication="Sleep",
    )
    assert record.grade_certainty == "Not GRADE-applicable"


def test_validate_result_df_maps_grade_certainty_across_multiple_rows():
    df = pd.DataFrame([
        _sample_row(Alternative_Plant="AltPlant1", GRADE_Certainty="High"),
        _sample_row(Alternative_Plant="AltPlant2", GRADE_Certainty="Very Low"),
    ])
    records, errors = validate_result_df(df, indication="Sleep")
    assert len(errors) == 0
    assert len(records) == 2
    certainties = {r.alternative_plant: r.grade_certainty for r in records}
    assert certainties == {"AltPlant1": "High", "AltPlant2": "Very Low"}


# ---------------------------------------------------------------------
# 3) Backward compatibility: a row without these columns at all must
#    degrade to None, never crash — same convention as every other
#    additive field in this adapter (Gate_Results, Applicability_Summary,
#    Decision_Engine_Version).
# ---------------------------------------------------------------------

def test_validate_row_row_missing_grade_columns_entirely_degrades_to_none():
    row = pd.Series({
        "Reference_Plant": "RefPlant",
        "Alternative_Plant": "AltPlant",
        # No GRADE_Certainty / GRADE_Certainty_Rationale keys at all.
    })
    record, errors = validate_row(row, indication="Sleep")
    assert errors == []
    assert record is not None
    assert record.grade_certainty is None
    assert record.grade_certainty_rationale is None


def test_validate_row_empty_string_grade_certainty_becomes_none():
    record, _ = validate_row(
        _sample_row(GRADE_Certainty="", GRADE_Certainty_Rationale=""),
        indication="Sleep",
    )
    assert record.grade_certainty is None
    assert record.grade_certainty_rationale is None


# ---------------------------------------------------------------------
# 4) _PERSISTED_RECORD_FIELDS includes both fields.
# ---------------------------------------------------------------------

def test_persisted_record_fields_includes_grade_certainty():
    assert "grade_certainty" in _PERSISTED_RECORD_FIELDS
    assert "grade_certainty_rationale" in _PERSISTED_RECORD_FIELDS


def test_serialize_record_includes_grade_certainty_when_present():
    record, _ = validate_row(_sample_row(), indication="Sleep")
    serialized = _serialize_record(record)
    assert serialized["grade_certainty"] == "Moderate"
    assert "publication bias" in serialized["grade_certainty_rationale"]


def test_serialize_record_includes_none_grade_certainty_when_absent():
    row = pd.Series({"Reference_Plant": "RefPlant", "Alternative_Plant": "AltPlant"})
    record, _ = validate_row(row, indication="Sleep")
    serialized = _serialize_record(record)
    assert serialized["grade_certainty"] is None
    assert serialized["grade_certainty_rationale"] is None


# ---------------------------------------------------------------------
# 5) End-to-end: real engine output -> validate_row() ->
#    persist_decision_record() -> grade_certainty actually present in
#    the persisted JSON blob.
# ---------------------------------------------------------------------

def test_end_to_end_real_engine_output_persists_grade_certainty():
    import botanical_rd_candidate_engine as eng

    eng.SIMILAR_COMPOUND_GROUPS = {}
    eng.COMPOUND_TARGETS = {}

    rows = [dict(
        scientific_name="TestPlant", compound_name="ActiveCompound",
        indication="TestIndication", target="Hepatoprotective",
        common_name="", plant_part="", extraction_method="",
    )]
    evidence_df = pd.DataFrame([{
        "Scientific_Name": "TestPlant",
        "Target_Indication": "TestIndication",
        "Notes": (
            "A double-blind, placebo-controlled trial with n = 250 "
            "patients found significant hepatoprotective effects."
        ),
    }])
    engine = eng.BotanicalRDCandidateEngine(
        plant_compounds_df=pd.DataFrame(rows),
        compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(),
        evidence_df=evidence_df,
        use_live_search=False,
    )
    result_df = engine.run(indication="TestIndication", dosage_form="Infusion", market="EU")

    # Sanity: the engine itself did compute a real (non-null,
    # non-"Not GRADE-applicable") certainty for this Clinical-trial-tier
    # evidence, confirming this test actually exercises the case it
    # claims to.
    row = result_df[
        (result_df["Reference_Plant"] == "TestPlant")
        & (result_df["Alternative_Plant"] == "TestPlant")
    ].iloc[0]
    assert row["GRADE_Certainty"] not in (None, "", "Not GRADE-applicable")

    records, errors = validate_result_df(result_df, indication="TestIndication")
    assert errors.empty
    assert len(records) > 0
    assert any(r.grade_certainty == row["GRADE_Certainty"] for r in records)

    client = _FakeSupabaseClient()
    summary = persist_decision_record(records, indication="TestIndication", supabase_client=client)
    assert summary["status"] == "persisted"

    persisted_row = client.store["decision_records"][0]
    persisted_records = json.loads(persisted_row["records"])
    assert any(
        r["grade_certainty"] == row["GRADE_Certainty"] for r in persisted_records
    )
    assert any(
        r["grade_certainty_rationale"] not in (None, "") for r in persisted_records
    )
