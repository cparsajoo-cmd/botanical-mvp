"""Regression tests for candidate_output_adapter.py (Data Contracts adapter)."""

import pandas as pd

from candidate_output_adapter import validate_row, validate_result_df, _split_list
from data_contracts import CandidateAssessment


def _make_real_shaped_row(**overrides):
    base = {
        "Reference_Plant": "Silybum marianum",
        "Reference_Plant_Part": "Seed",
        "Reference_Compound": "Silymarin",
        "Alternative_Plant": "Allium cepa",
        "Alternative_Plant_Part": "Bulb",
        "Shared_or_Similar_Compound": "Quercetin",
        "Target_or_Mechanism": "Hepatoprotective",
        "Target_Provenance": "Not applicable (no shared-target claim for this match type)",
        "Concentration_Info": "2 mg/g dry weight",
        "Extraction_Method": "Aqueous infusion",
        "Industrial_Feasibility": "Moderate feasibility",
        "Co_Compounds": "CompoundA; CompoundB",
        "Safety_Flags": "No explicit flag found",
        "Interaction_Flags": "No explicit flag found",
        "Evidence_Source": "Live-collected evidence (PubMed/Europe PMC/Supabase)",
        "Source_Record_IDs": "https://pubmed.ncbi.nlm.nih.gov/1/; https://pubmed.ncbi.nlm.nih.gov/2/",
        "Occurrence_Corroboration": "Corroborated by 2 independent sources",
        "Candidate_Evidence_Strength_Tier": "Broad Evidence",
        "Evidence_Level": "Clinical / human evidence",
        "Evidence_Hierarchy_Detail": "Clinical trial",
        "Has_Negative_Evidence": False,
        "Negative_Evidence_Types": "",
        "Market_Status": "Regulatory monograph exists",
        "Regulatory_Barriers": "None identified",
        "Novelty_Status": "Alternative cross-region candidate",
        "R&D_Opportunity_Score": 72.0,
        "Score_Breakdown": "Evidence quality: +24.0; Chemical/mechanistic link: +15.0",
        "Evidence_Confidence": 85.0,
        "Decision_Class": "Promising candidate; verify safety and standardization",
        "Decision_Class_AH": "C — Alternative-source R&D candidate",
        "White_Space_Type": "",
        "Confidence_Note": "",
        "Go_Investigate_Hold_NoGo": "Investigate",
        "Scientific_Rationale": "Shares a validated biological target.",
        "Commercial_Regulatory_Rationale": "Market status: Regulatory monograph exists.",
        "Evidence_Strengths": "High evidence confidence (85.0)",
        "Evidence_Weaknesses": "None identified",
        "Next_Experiment_Suggestion": "Quantify compound concentration in Allium cepa.",
        "Comparative_Rationale": "Top-ranked candidate for this reference (R&D_Opportunity_Score 72.0).",
        "Rationale": "Full narrative rationale text.",
    }
    base.update(overrides)
    return base


def test_split_list_handles_real_placeholder_strings_as_empty():
    assert _split_list("No explicit flag found") == []
    assert _split_list("None identified") == []
    assert _split_list("") == []
    assert _split_list(None) == []


def test_split_list_splits_real_semicolon_joined_values():
    assert _split_list("CompoundA; CompoundB; CompoundC") == ["CompoundA", "CompoundB", "CompoundC"]


def test_validate_row_produces_a_valid_candidate_assessment():
    record, errors = validate_row(_make_real_shaped_row(), indication="Liver support", project_id="p1")
    assert errors == []
    assert isinstance(record, CandidateAssessment)
    assert record.reference_plant == "Silybum marianum"
    assert record.alternative_plant == "Allium cepa"
    assert record.rd_opportunity_score == 72.0
    assert record.evidence_confidence == 85.0


def test_validate_row_converts_semicolon_strings_to_real_lists():
    record, _ = validate_row(_make_real_shaped_row(), indication="Liver support")
    assert record.co_compounds == ["CompoundA", "CompoundB"]
    assert record.source_record_ids == [
        "https://pubmed.ncbi.nlm.nih.gov/1/", "https://pubmed.ncbi.nlm.nih.gov/2/",
    ]
    assert record.safety_flags == []  # "No explicit flag found" -> empty, not a fake flag


def test_validate_row_flags_missing_required_fields():
    row = _make_real_shaped_row(Reference_Plant="", Alternative_Plant="")
    record, errors = validate_row(row, indication="Liver support")
    assert record is None
    assert any("Reference_Plant" in e for e in errors)
    assert any("Alternative_Plant" in e for e in errors)


def test_validate_row_flags_unparseable_numeric_field_without_crashing():
    row = _make_real_shaped_row(**{"R&D_Opportunity_Score": "not a number"})
    record, errors = validate_row(row, indication="Liver support")
    assert record is not None  # non-fatal — the rest of the row still validates
    assert record.rd_opportunity_score is None
    assert any("R&D_Opportunity_Score" in e for e in errors)


def test_validate_row_converts_has_negative_evidence_to_real_bool():
    record_true, _ = validate_row(_make_real_shaped_row(Has_Negative_Evidence=True), indication="X")
    record_false, _ = validate_row(_make_real_shaped_row(Has_Negative_Evidence=False), indication="X")
    assert record_true.has_negative_evidence is True
    assert record_false.has_negative_evidence is False


def test_validate_result_df_end_to_end_with_no_errors():
    df = pd.DataFrame([_make_real_shaped_row(), _make_real_shaped_row(Alternative_Plant="Camellia sinensis")])
    records, errors_df = validate_result_df(df, indication="Liver support", project_id="p1")
    assert len(records) == 2
    assert errors_df.empty


def test_validate_result_df_reports_which_row_and_field_broke():
    good_row = _make_real_shaped_row()
    bad_row = _make_real_shaped_row(Alternative_Plant="")  # missing required field
    df = pd.DataFrame([good_row, bad_row])
    records, errors_df = validate_result_df(df, indication="Liver support")
    assert len(records) == 1  # only the good row validated
    assert len(errors_df) == 1
    assert errors_df.iloc[0]["row_index"] == 1
    assert "Alternative_Plant" in errors_df.iloc[0]["error"]


def test_validate_result_df_handles_empty_dataframe():
    records, errors_df = validate_result_df(pd.DataFrame(), indication="X")
    assert records == []
    assert errors_df.empty


def test_validate_result_df_against_a_real_engine_run():
    # The actual point of this adapter: run it against genuine
    # engine.run() output, not just hand-built rows, to catch real
    # column-name drift if it ever happens.
    import sys
    sys.path.insert(0, ".")
    import botanical_rd_candidate_engine as eng

    eng.SIMILAR_COMPOUND_GROUPS = {}
    eng.COMPOUND_TARGETS = {}
    rows = [
        dict(scientific_name="TestPlant", compound_name="ActiveCompound",
             indication="TestIndication", target="Hepatoprotective",
             common_name="", plant_part="Root", extraction_method=""),
    ]
    background = [
        dict(scientific_name=f"Bg{i}", compound_name=f"BgCompound{i}",
             indication="background", target="Antioxidant",
             common_name="", plant_part="", extraction_method="")
        for i in range(25)
    ]
    df = pd.DataFrame(rows + background)
    engine = eng.BotanicalRDCandidateEngine(
        plant_compounds_df=df, compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(), use_live_search=False,
    )
    result = engine.run(indication="TestIndication", dosage_form="Infusion", market="EU")

    records, errors_df = validate_result_df(result, indication="TestIndication", project_id="smoke-test")
    assert len(records) == len(result), (
        f"expected every real run() row to validate cleanly, but got errors: "
        f"{errors_df.to_dict('records') if not errors_df.empty else 'none'}"
    )
    assert errors_df.empty, f"real engine output failed contract validation: {errors_df.to_dict('records')}"


if __name__ == "__main__":
    import sys

    try:
        import pytest
        sys.exit(pytest.main([__file__, "-v"]))
    except ImportError:
        this_module = sys.modules[__name__]
        test_fns = [
            getattr(this_module, name)
            for name in dir(this_module)
            if name.startswith("test_") and callable(getattr(this_module, name))
        ]
        passed, failed = [], []
        for fn in test_fns:
            try:
                fn()
            except AssertionError as exc:
                failed.append((fn.__name__, str(exc) or "assertion failed"))
            except Exception as exc:  # noqa: BLE001
                failed.append((fn.__name__, f"{type(exc).__name__}: {exc}"))
            else:
                passed.append(fn.__name__)
        print(f"\n{len(passed) + len(failed)} test(s) run.\n")
        for name in passed:
            print(f"  \u2705 {name}")
        if failed:
            print()
            for name, reason in failed:
                print(f"  \u274c {name}\n     -> {reason}")
            print(f"\n{len(failed)} FAILED, {len(passed)} passed.\n")
            sys.exit(1)
        print(f"\nALL TESTS PASSED ({len(passed)}/{len(passed)}).\n")
        sys.exit(0)
