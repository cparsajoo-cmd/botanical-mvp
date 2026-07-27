"""
Task 11.1 — Activate ScientificEvidence as the in-memory representation
of each active evidence_records row. Regression tests.

WHAT THIS COVERS
1. standard_evidence_builder.build_scientific_evidence() — the adapter
   from an active evidence_records row (build_standard_evidence()'s own
   shape / database.load_evidence_records()'s reload shape) into
   data_contracts.ScientificEvidence.
2. standard_evidence_builder.normalize_evidence_level() — conservative
   Evidence_Level -> EvidenceHierarchyLevel normalization.
3. botanical_rd_candidate_engine.BotanicalRDCandidateEngine.
   _build_scientific_evidence_index() — the structured, separate
   evidence_record_id -> ScientificEvidence index.
4. Non-regression: scores/ranking/gates/Decision_Class_AH unchanged;
   no new Supabase column introduced; no legacy module reachable.

HOW TO RUN
    pytest -q test_task11_1_scientific_evidence_activation.py
    (or `pytest -q` from the repo root — auto-discovered)
"""

import pandas as pd

import botanical_rd_candidate_engine as eng
import database
import repo_dependency_audit
from data_contracts import EvidenceApplicability, EvidenceHierarchyLevel, ScientificEvidence
from standard_evidence_builder import (
    build_scientific_evidence,
    build_standard_evidence,
    normalize_evidence_level,
)


# ======================================================================
# 1) build_scientific_evidence() — supported fields map, unsupported
#    fields stay None, applicability survives, id is preserved.
# ======================================================================

def _full_row(**overrides):
    base = {
        "Source_Type": "PubMed",
        "Source_URL": "https://pubmed.ncbi.nlm.nih.gov/12345/",
        "Evidence_Type": "Randomized Controlled Trial",
        "Study_Type": "Randomized Controlled Trial",
        "Population": "human",
        "Comparator": "placebo",
        "Primary_Outcome": "improved sleep latency",
        "Evidence_Level": "High",
        "Evidence_Record_ID": 42,
        "Applicability_Classification": EvidenceApplicability.PARTIALLY_APPLICABLE.value,
        "Applicability_Rationale": "PARTIALLY_APPLICABLE: indication and dosage form match.",
        "Applicability_Evaluated_Dimensions": "indication; dosage_form",
        "Applicability_Missing_Dimensions": "plant_part; extraction_or_solvent",
        "Applicability_Detected_Mismatches": "",
    }
    base.update(overrides)
    return base


def test_supported_fields_map_correctly():
    evidence = build_scientific_evidence(_full_row())
    assert isinstance(evidence, ScientificEvidence)
    assert evidence.source_type == "PubMed"
    assert evidence.doi_pmid_url == "https://pubmed.ncbi.nlm.nih.gov/12345/"
    assert evidence.study_type == "Randomized Controlled Trial"
    assert evidence.population == "human"
    assert evidence.comparator == "placebo"
    assert evidence.outcome == "improved sleep latency"


def test_unsupported_fields_remain_none():
    evidence = build_scientific_evidence(_full_row())
    # No current source anywhere in the active schema (Task 11 audit).
    assert evidence.sample_size is None
    assert evidence.intervention is None
    assert evidence.dose is None
    assert evidence.duration is None
    assert evidence.statistical_result is None
    assert evidence.plant_identity_verified is None
    assert evidence.extract_characterized is None
    assert evidence.risk_of_bias is None
    assert evidence.confidence_score is None
    assert evidence.is_negative_or_contradictory is False
    assert evidence.negative_finding_type is None


def test_relevance_fields_not_reused_for_applicability():
    """Explicit correction: relevance_to_dosage_form/relevance_to_indication
    must NOT be repurposed to carry applicability data — they stay at
    their own default (None, no current safe source), while
    applicability lives on its own dedicated fields."""
    evidence = build_scientific_evidence(_full_row())
    assert evidence.relevance_to_dosage_form is None
    assert evidence.relevance_to_indication is None
    assert evidence.applicability_classification == EvidenceApplicability.PARTIALLY_APPLICABLE


def test_applicability_survives_in_the_object():
    evidence = build_scientific_evidence(_full_row())
    assert evidence.applicability_classification == EvidenceApplicability.PARTIALLY_APPLICABLE
    assert "PARTIALLY_APPLICABLE" in evidence.applicability_rationale
    assert evidence.applicability_evaluated_dimensions == ["indication", "dosage_form"]
    assert evidence.applicability_missing_dimensions == ["plant_part", "extraction_or_solvent"]
    assert evidence.applicability_detected_mismatches == []


def test_applicability_classification_unparseable_value_stays_none():
    row = _full_row(Applicability_Classification="Some Foreign Value")
    evidence = build_scientific_evidence(row)
    assert evidence.applicability_classification is None


def test_each_object_retains_the_existing_evidence_record_id():
    evidence = build_scientific_evidence(_full_row(Evidence_Record_ID=777))
    assert evidence.source_record_id == "777"


def test_missing_evidence_record_id_yields_none_source_record_id():
    row = _full_row()
    row["Evidence_Record_ID"] = ""
    evidence = build_scientific_evidence(row)
    assert evidence.source_record_id is None


# ======================================================================
# 2) Old rows remain readable — a row shaped like it was built before
#    Task 10.2/11.1 existed (no Applicability_*, no Evidence_Record_ID)
#    must not raise, and must degrade to the dataclass defaults.
# ======================================================================

def test_old_rows_without_task_10_2_or_11_1_fields_remain_readable():
    old_style_row = {
        "Source_Type": "PubMed",
        "Source_URL": "https://pubmed.ncbi.nlm.nih.gov/999/",
        "Evidence_Type": "Observational Study",
        "Population": "human",
        "Evidence_Level": "Moderate",
        # No Evidence_Record_ID, no Applicability_* keys at all.
    }
    evidence = build_scientific_evidence(old_style_row)
    assert evidence.source_type == "PubMed"
    assert evidence.source_record_id is None
    assert evidence.applicability_classification is None
    assert evidence.applicability_rationale is None
    assert evidence.applicability_evaluated_dimensions == []


def test_build_scientific_evidence_accepts_build_standard_evidence_output_directly():
    """The two functions must be directly composable: whatever
    build_standard_evidence() produces, build_scientific_evidence()
    must accept without any reshaping in between."""
    raw = {
        "Scientific_Name": "PlantAlt",
        "Dosage_Form": "Infusion",
        "Target_Indication": "Sleep support",
        "Detected_Dosage_Forms": "Infusion tea",
        "Detected_Indications": "Sleep support",
        "Source_Type": "PubMed",
        "Source_URL": "https://pubmed.ncbi.nlm.nih.gov/1/",
        "Evidence_Level": "Traditional",
    }
    standardized = build_standard_evidence(raw)
    evidence = build_scientific_evidence(standardized)
    assert evidence.source_type == "PubMed"
    assert evidence.applicability_classification == EvidenceApplicability.PARTIALLY_APPLICABLE
    assert evidence.evidence_hierarchy_level == EvidenceHierarchyLevel.TRADITIONAL_USE_MONOGRAPH


# ======================================================================
# 3) normalize_evidence_level() — conservative, fails safely.
# ======================================================================

def test_enum_normalization_maps_traditional_safely():
    assert normalize_evidence_level("Traditional") == EvidenceHierarchyLevel.TRADITIONAL_USE_MONOGRAPH
    assert normalize_evidence_level("traditional") == EvidenceHierarchyLevel.TRADITIONAL_USE_MONOGRAPH
    assert (
        normalize_evidence_level("Listed in official EMA HMPC inventory")
        == EvidenceHierarchyLevel.TRADITIONAL_USE_MONOGRAPH
    )


def test_enum_normalization_fails_safely_for_unmapped_values():
    # These are real, currently-observed Evidence_Level values across
    # this repo's connectors/LLM output (verified by grep) — none of
    # them safely determine a STUDY-TYPE hierarchy tier from a
    # QUALITY-ordinal label, so all must normalize to None.
    for value in (
        "High", "Very High", "Moderate", "Low", "Very Low",
        "Supporting", "Not available", "Checked, not found",
        "Unknown", "", None, "Something entirely unrecognized",
    ):
        assert normalize_evidence_level(value) is None, f"{value!r} should normalize to None"


# ======================================================================
# 4) BotanicalRDCandidateEngine._build_scientific_evidence_index()
# ======================================================================

def _base_plant_compound_rows():
    return [
        dict(scientific_name="PlantRef", compound_name="RefCompoundA",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="PlantAlt", compound_name="RefCompoundA",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
    ]


def _make_engine(evidence_df):
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
        evidence_df=evidence_df,
        use_live_search=False,
    )


def test_scientific_evidence_index_is_empty_before_run():
    engine = _make_engine(pd.DataFrame())
    assert engine.scientific_evidence_index == {}


def test_scientific_evidence_index_built_and_keyed_by_evidence_record_id():
    evidence_df = pd.DataFrame([{
        "Scientific_Name": "PlantAlt",
        "Plant": "PlantAlt",
        "Notes": "RefCompoundA study text",
        "Source_Type": "PubMed",
        "Source_URL": "https://pubmed.ncbi.nlm.nih.gov/1/",
        "Evidence_Type": "Clinical Study",
        "Population": "human",
        "Evidence_Level": "Moderate",
        "Evidence_Record_ID": "ev-1",
        "Applicability_Classification": EvidenceApplicability.NOT_ASSESSABLE.value,
    }])
    engine = _make_engine(evidence_df)
    index = engine._build_scientific_evidence_index()

    assert set(index.keys()) == {"ev-1"}
    evidence = index["ev-1"]
    assert isinstance(evidence, ScientificEvidence)
    assert evidence.source_record_id == "ev-1"
    assert evidence.study_type == "Clinical Study"
    assert evidence.applicability_classification == EvidenceApplicability.NOT_ASSESSABLE


def test_scientific_evidence_index_skips_rows_without_an_id():
    evidence_df = pd.DataFrame([{
        "Scientific_Name": "PlantAlt",
        "Plant": "PlantAlt",
        "Notes": "RefCompoundA study text, no id",
        "Source_Type": "PubMed",
    }])
    engine = _make_engine(evidence_df)
    index = engine._build_scientific_evidence_index()
    assert index == {}


def test_scientific_evidence_index_built_automatically_by_run():
    evidence_df = pd.DataFrame([{
        "Scientific_Name": "PlantAlt",
        "Plant": "PlantAlt",
        "Notes": "RefCompoundA study text",
        "Source_Type": "PubMed",
        "Evidence_Record_ID": "ev-run-1",
    }])
    engine = _make_engine(evidence_df)
    engine.run(indication="TestIndication", dosage_form="Infusion", market="EU")
    assert "ev-run-1" in engine.scientific_evidence_index


# ======================================================================
# 5) Non-regression: scores/ranking/gates/Decision_Class_AH unchanged;
#    all existing public DataFrame columns preserved.
# ======================================================================

def test_public_output_columns_unchanged_by_task_11_1():
    """Task 11.1 must add NO new OUTPUT_COLUMNS entry — the structured
    evidence index is an instance attribute, never a DataFrame column."""
    evidence_df = pd.DataFrame([{
        "Scientific_Name": "PlantAlt", "Plant": "PlantAlt",
        "Notes": "RefCompoundA study text",
        "Evidence_Record_ID": "ev-1",
        "Applicability_Classification": EvidenceApplicability.PARTIALLY_APPLICABLE.value,
    }])
    engine = _make_engine(evidence_df)
    result = engine.run(indication="TestIndication", dosage_form="Infusion", market="EU")
    assert list(result.columns) == eng.OUTPUT_COLUMNS
    assert "ScientificEvidence" not in result.columns
    assert "Scientific_Evidence_Index" not in result.columns


def test_scores_ranking_gates_and_decision_class_unchanged():
    evidence_df = pd.DataFrame([{
        "Scientific_Name": "PlantAlt", "Plant": "PlantAlt",
        "Notes": "randomized controlled trial RefCompoundA outcome improved",
        "Primary_Outcome": "randomized controlled trial RefCompoundA outcome improved",
        "Source_Type": "PubMed",
        "Evidence_Record_ID": "ev-1",
        "Evidence_Level": "High",
        "Applicability_Classification": EvidenceApplicability.PARTIALLY_APPLICABLE.value,
        "Applicability_Rationale": "systematic review meta-analysis clinical trial stress test text",
    }])
    engine_a = _make_engine(pd.DataFrame([{
        "Scientific_Name": "PlantAlt", "Plant": "PlantAlt",
        "Notes": "randomized controlled trial RefCompoundA outcome improved",
        "Primary_Outcome": "randomized controlled trial RefCompoundA outcome improved",
    }]))
    engine_b = _make_engine(evidence_df)

    result_a = engine_a.run(indication="TestIndication", dosage_form="Infusion", market="EU")
    result_b = engine_b.run(indication="TestIndication", dosage_form="Infusion", market="EU")

    row_a = result_a[result_a["Alternative_Plant"] == "PlantAlt"].iloc[0]
    row_b = result_b[result_b["Alternative_Plant"] == "PlantAlt"].iloc[0]

    assert row_a["R&D_Opportunity_Score"] == row_b["R&D_Opportunity_Score"]
    assert row_a["Decision_Class"] == row_b["Decision_Class"]
    assert row_a["Decision_Class_AH"] == row_b["Decision_Class_AH"]
    assert row_a["Gate_Results"] == row_b["Gate_Results"]
    assert row_a["Evidence_Hierarchy_Detail"] == row_b["Evidence_Hierarchy_Detail"]
    assert row_a["Has_Negative_Evidence"] == row_b["Has_Negative_Evidence"]


# ======================================================================
# 6) No duplicate Supabase columns; no legacy module reachable.
# ======================================================================

def test_no_new_supabase_columns_introduced_by_task_11_1():
    """Task 11.1 is explicitly in-memory-only: save_evidence_record()'s
    insert dict must contain exactly the same keys Task 10.2 left it
    with — no new applicability/scientific-evidence-shaped column."""
    import inspect
    source = inspect.getsource(database.save_evidence_record)
    # Every Task 10.2 column must still be there (unchanged)...
    for existing_column in (
        "applicability_classification", "applicability_rationale",
        "applicability_evaluated_dimensions", "applicability_missing_dimensions",
        "applicability_detected_mismatches",
    ):
        assert f'"{existing_column}"' in source
    # ...and no new "scientific_evidence"-shaped column was added.
    for forbidden_column in (
        "source_record_id", "scientific_evidence", "doi_pmid_url",
        "evidence_hierarchy_level", "study_type_normalized",
    ):
        assert f'"{forbidden_column}"' not in source, (
            f"Task 11.1 must not add a new Supabase column ({forbidden_column!r}) "
            "— ScientificEvidence is built in-memory from already-persisted fields."
        )


def test_no_legacy_module_becomes_production_reachable():
    sets = repo_dependency_audit.compute_dependency_sets(".")
    assert "scientific_evidence_collector" not in sets.production_active
    assert "scientific_evidence_collector" in sets.legacy_candidates
    assert "dosage_classifier" not in sets.production_active
    assert "dosage_classifier" in sets.legacy_candidates
    assert "standard_evidence_builder" in sets.production_active
    assert "botanical_rd_candidate_engine" in sets.production_active
    assert "data_contracts" in sets.production_active
