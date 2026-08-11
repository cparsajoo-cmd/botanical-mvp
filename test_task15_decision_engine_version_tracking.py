"""
Task 15 — Decision Engine Version Tracking.

WHAT THIS COVERS
- botanical_rd_candidate_engine.DECISION_ENGINE_VERSION and
  "Decision_Engine_Version" on OUTPUT_COLUMNS/every candidate row.
- candidate_output_adapter's mapping onto
  CandidateAssessment.decision_engine_version.
- decision_record_persistence's "decision_engine_version" entry in
  _PERSISTED_RECORD_FIELDS.
- Non-regression: scoring, ranking, gates, confidence, Decision_Class
  unchanged apart from the one additive metadata column.

WHAT THIS DELIBERATELY DOES NOT COVER
Scoring formulas, gate logic, applicability, ScientificEvidence,
RegulatoryRecord, evidence extraction, decision vocabulary, ranking
algorithms, persistence schema beyond the one new allowlist entry,
report content, Streamlit workflow, benchmark cases, or regulatory/
market enrichment — none of these were touched by this task.

HOW TO RUN
    pytest -q test_task15_decision_engine_version_tracking.py
    (or `pytest -q` from the repo root — auto-discovered)
"""

import pandas as pd

import botanical_rd_candidate_engine as eng
import data_contracts as dc
from candidate_output_adapter import validate_result_df
from decision_record_persistence import _PERSISTED_RECORD_FIELDS, _serialize_record
from test_decision_record_persistence import _FakeSupabaseClient, _sample_candidate_assessment


def _base_plant_compound_rows():
    return [
        dict(scientific_name="PlantRef", compound_name="RefCompoundA",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="PlantAlt", compound_name="RefCompoundA",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="PlantAlt2", compound_name="RefCompoundA",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
    ]


def _make_engine(evidence_df=None):
    rows = _base_plant_compound_rows() + [
        dict(scientific_name=f"Bg{i}", compound_name=f"BgCompound{i}",
             indication="background", target="Antioxidant",
             common_name="", plant_part="", extraction_method="")
        for i in range(25)
    ]
    return eng.BotanicalRDCandidateEngine(
        plant_compounds_df=pd.DataFrame(rows),
        compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(),
        evidence_df=evidence_df if evidence_df is not None else pd.DataFrame(),
        use_live_search=False,
    )


def _run(evidence_df=None):
    engine = _make_engine(evidence_df)
    return engine.run(indication="TestIndication", dosage_form="Infusion", market="EU")


# ---------------------------------------------------------------------
# 1) DECISION_ENGINE_VERSION exists and equals "1.8.0" (bumped by
#    Phase 4's Eligibility Gate redesign, which changes Decision_Class
#    for exactly the rows the Phase 4 audit proved were mis-classified
#    by the pre-Phase-4 same_plant bypass — see
#    botanical_rd_candidate_engine.py's DECISION_ENGINE_VERSION comment
#    and eligibility_gate.py for the exact change).
# ---------------------------------------------------------------------

def test_decision_engine_version_constant_exists_and_equals_1_0_1():
    assert eng.DECISION_ENGINE_VERSION == "1.8.0"


# ---------------------------------------------------------------------
# 2) Every generated candidate row contains Decision_Engine_Version.
# ---------------------------------------------------------------------

def test_every_candidate_row_contains_decision_engine_version():
    result = _run()
    assert "Decision_Engine_Version" in result.columns
    assert not result.empty
    assert result["Decision_Engine_Version"].notna().all()


# ---------------------------------------------------------------------
# 3) The value comes from the canonical constant.
# ---------------------------------------------------------------------

def test_value_comes_from_the_canonical_constant():
    result = _run()
    assert (result["Decision_Engine_Version"] == eng.DECISION_ENGINE_VERSION).all()


# ---------------------------------------------------------------------
# 4) All rows produced in one run carry the same version.
# ---------------------------------------------------------------------

def test_all_rows_in_one_run_carry_the_same_version():
    result = _run()
    assert result["Decision_Engine_Version"].nunique() == 1
    assert result["Decision_Engine_Version"].iloc[0] == eng.DECISION_ENGINE_VERSION


# ---------------------------------------------------------------------
# 5) The metadata field is appended without removing existing output
#    fields.
# ---------------------------------------------------------------------

def test_metadata_field_appended_last_existing_fields_preserved():
    assert eng.OUTPUT_COLUMNS[-1] == "Decision_Engine_Version"
    for pre_existing in (
        "Reference_Plant", "Alternative_Plant", "R&D_Opportunity_Score",
        "Decision_Class", "Decision_Class_AH", "Gate_Results",
        "Scoring_Config_Version", "Applicability_Summary",
    ):
        assert pre_existing in eng.OUTPUT_COLUMNS

    result = _run()
    assert list(result.columns) == eng.OUTPUT_COLUMNS


# ---------------------------------------------------------------------
# 6) Changing or reading the version metadata has no role in scoring
#    or ranking.
# ---------------------------------------------------------------------

def test_version_metadata_never_read_by_scoring_gates_or_decision_logic():
    """Static proof: neither _score_candidate(), _decision_class(),
    _evaluate_gates(), nor go_investigate_hold_no_go() reference
    DECISION_ENGINE_VERSION or Decision_Engine_Version anywhere in
    their source."""
    import inspect
    for fn in (
        eng.BotanicalRDCandidateEngine._score_candidate,
        eng.BotanicalRDCandidateEngine._decision_class,
        eng.BotanicalRDCandidateEngine._evaluate_gates,
    ):
        source = inspect.getsource(fn)
        assert "DECISION_ENGINE_VERSION" not in source
        assert "Decision_Engine_Version" not in source


# ---------------------------------------------------------------------
# 7) Candidate order remains unchanged when version metadata is
#    ignored.
# ---------------------------------------------------------------------

def test_candidate_order_unchanged_with_or_without_considering_version_column():
    evidence_df = pd.DataFrame([
        {
            "Scientific_Name": "PlantAlt", "Plant": "PlantAlt",
            "Notes": "randomized controlled trial RefCompoundA outcome improved",
            "Primary_Outcome": "randomized controlled trial RefCompoundA outcome improved",
            "Source_Type": "PubMed", "Target_Indication": "TestIndication", "Evidence_Record_ID": "ev-1", "Evidence_Level": "High",
        },
        {
            "Scientific_Name": "PlantAlt2", "Plant": "PlantAlt2",
            "Notes": "weak observational report RefCompoundA no clear effect",
            "Source_Type": "PubMed", "Target_Indication": "TestIndication", "Evidence_Record_ID": "ev-2", "Evidence_Level": "Low",
        },
    ])
    result = _run(evidence_df)
    ordering_with_version_column = list(result["Alternative_Plant"])
    ordering_without_version_column = list(
        result.drop(columns=["Decision_Engine_Version"])["Alternative_Plant"]
    )
    assert ordering_with_version_column == ordering_without_version_column
    assert ordering_with_version_column[0] == "PlantAlt"  # stronger evidence ranks first


# ---------------------------------------------------------------------
# 8) Persisted decision records contain decision_engine_version.
# ---------------------------------------------------------------------

def test_persisted_decision_record_contains_decision_engine_version():
    assert "decision_engine_version" in _PERSISTED_RECORD_FIELDS
    record = _sample_candidate_assessment(decision_engine_version="1.0.0")
    serialized = _serialize_record(record)
    assert serialized["decision_engine_version"] == "1.0.0"


# ---------------------------------------------------------------------
# 9) The persisted value matches the originating candidate row.
# ---------------------------------------------------------------------

def test_persisted_value_matches_originating_candidate_row_end_to_end():
    result = _run()
    records, errors = validate_result_df(result, indication="TestIndication")
    assert errors.empty
    assert records

    for row_value, record in zip(result["Decision_Engine_Version"], records):
        assert record.decision_engine_version == row_value == eng.DECISION_ENGINE_VERSION

    serialized = _serialize_record(records[0])
    assert serialized["decision_engine_version"] == records[0].decision_engine_version


# ---------------------------------------------------------------------
# 10) scoring_config_version remains present and separate.
# ---------------------------------------------------------------------

def test_scoring_config_version_remains_present_and_distinct():
    result = _run()
    assert "Scoring_Config_Version" in result.columns
    assert "Decision_Engine_Version" in result.columns

    record = _sample_candidate_assessment(
        scoring_config_version="2.0-custom", decision_engine_version="1.0.0",
    )
    serialized = _serialize_record(record)
    assert serialized["scoring_config_version"] == "2.0-custom"
    assert serialized["decision_engine_version"] == "1.0.0"
    assert serialized["scoring_config_version"] != serialized["decision_engine_version"]


# ---------------------------------------------------------------------
# 11) Old records without decision_engine_version remain readable.
# ---------------------------------------------------------------------

def test_old_records_without_decision_engine_version_remain_readable():
    old_style_record = {
        "reference_plant": "Silybum marianum",
        "alternative_plant": "Allium cepa",
        "rd_opportunity_score": 50.0,
        "decision_class": "Early-stage candidate",
        # No decision_engine_version key at all.
    }
    serialized = _serialize_record(old_style_record)
    assert serialized["decision_engine_version"] is None
    assert serialized["reference_plant"] == "Silybum marianum"


def test_old_persisted_row_round_trips_through_fake_supabase_without_error():
    import json
    from decision_record_persistence import DECISION_RECORD_TABLE_NAME, persist_decision_record

    old_style_record = _sample_candidate_assessment()  # decision_engine_version left at dataclass default
    assert old_style_record.decision_engine_version is None

    client = _FakeSupabaseClient()
    persist_decision_record([old_style_record], indication="Liver support", supabase_client=client)
    persisted_row = client.store[DECISION_RECORD_TABLE_NAME][0]
    persisted_records = json.loads(persisted_row["records"])
    assert persisted_records[0]["decision_engine_version"] is None


# ---------------------------------------------------------------------
# 12) Missing historical version is not silently rewritten as "1.0.0".
# ---------------------------------------------------------------------

def test_missing_historical_version_is_not_fabricated_as_1_0_0():
    old_style_record = {"reference_plant": "X", "alternative_plant": "Y"}
    serialized = _serialize_record(old_style_record)
    assert serialized["decision_engine_version"] is None
    assert serialized["decision_engine_version"] != "1.0.0"

    # A record explicitly missing the field on CandidateAssessment
    # (dataclass default) must also serialize as None, not "1.0.0".
    record = dc.CandidateAssessment(
        project_id="p1", indication="X", product_type="Y",
        dosage_form="Y", target_market="EU",
        reference_plant="A", reference_plant_part=None,
        reference_compound="B", reference_compound_id=None,
        alternative_plant="C", alternative_plant_part=None,
        alternative_compound="D", alternative_compound_id=None,
    )
    assert record.decision_engine_version is None
    serialized2 = _serialize_record(record)
    assert serialized2["decision_engine_version"] is None


# ---------------------------------------------------------------------
# 13) Unrelated candidate fields are still excluded from the
#     persistence allowlist.
# ---------------------------------------------------------------------

def test_unrelated_candidate_fields_still_excluded():
    record = _sample_candidate_assessment(
        decision_engine_version="1.0.0",
        source_record_ids=["https://pubmed.ncbi.nlm.nih.gov/1/"],
        evidence_gaps=["no dose data"],
        rationale="Free-text rationale that must not leak into persistence.",
        white_space_type="E. White-space opportunity",
    )
    serialized = _serialize_record(record)
    assert set(serialized.keys()) == set(_PERSISTED_RECORD_FIELDS)
    for unexpected_field in ("source_record_ids", "evidence_gaps", "rationale", "white_space_type"):
        assert unexpected_field not in serialized


# ---------------------------------------------------------------------
# 14) Existing persistence behavior for applicability_summary and
#     evidence IDs remains unchanged.
# ---------------------------------------------------------------------

def test_applicability_summary_and_evidence_ids_persistence_unchanged():
    summary = {
        "strongest_category": "Partially applicable",
        "total_evidence_items": 2,
        "not_assessable_items": 1,
        "evidence_record_ids": ["ev-101", "ev-102"],
        "critical_mismatches": [],
        "missing_dimensions": ["plant_part"],
        "summary_rationale": "2 evidence item(s) assessed.",
    }
    record = _sample_candidate_assessment(
        applicability_summary=summary, decision_engine_version="1.0.0",
    )
    serialized = _serialize_record(record)
    assert serialized["applicability_summary"] == summary
    assert serialized["applicability_summary"]["evidence_record_ids"] == ["ev-101", "ev-102"]
    assert serialized["decision_engine_version"] == "1.0.0"


# ---------------------------------------------------------------------
# 15) Scoring, Gate_Results, ranking, confidence, and Decision_Class
#     remain exactly unchanged apart from the additive metadata
#     column.
# ---------------------------------------------------------------------

def test_scoring_gates_ranking_confidence_decision_class_unchanged():
    evidence_df = pd.DataFrame([
        {
            "Scientific_Name": "PlantAlt", "Plant": "PlantAlt",
            "Notes": "randomized controlled trial RefCompoundA outcome improved",
            "Primary_Outcome": "randomized controlled trial RefCompoundA outcome improved",
            "Source_Type": "PubMed", "Target_Indication": "TestIndication", "Evidence_Record_ID": "ev-1", "Evidence_Level": "High",
        },
        {
            "Scientific_Name": "PlantAlt2", "Plant": "PlantAlt2",
            "Notes": "weak observational report RefCompoundA no clear effect",
            "Source_Type": "PubMed", "Target_Indication": "TestIndication", "Evidence_Record_ID": "ev-2", "Evidence_Level": "Low",
        },
    ])

    result_a = _run(evidence_df)
    result_b = _run(evidence_df)  # fresh engine instance, same inputs

    compare_columns = [
        "Alternative_Plant", "R&D_Opportunity_Score", "Decision_Class",
        "Decision_Class_AH", "Gate_Results", "Evidence_Confidence",
    ]
    captured_a = result_a[compare_columns].reset_index(drop=True)
    captured_b = result_b[compare_columns].reset_index(drop=True)

    for col in compare_columns:
        assert captured_a[col].tolist() == captured_b[col].tolist(), f"mismatch in {col}"

    # And the ONLY new column present is the additive metadata one.
    assert set(result_a.columns) - set(result_b.columns) == set()
    new_columns_vs_pre_task_15 = set(result_a.columns) - {
        c for c in eng.OUTPUT_COLUMNS if c != "Decision_Engine_Version"
    }
    assert new_columns_vs_pre_task_15 == {"Decision_Engine_Version"}
