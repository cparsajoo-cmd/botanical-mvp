"""Architecture-level invariants for Preparation Intelligence / Transferability.

Generic rules only: no Gold Case, PMID, botanical-specific exception, or
benchmark wording.  The contract is source-vs-target separation plus current-
product applicability recomputation before efficacy can influence a decision.
"""
from __future__ import annotations

import pandas as pd

import botanical_rd_candidate_engine as eng
import evidence_standardizer
from evidence_extractor import extract_evidence_from_text
from standard_evidence_builder import (
    build_transferability_target_context,
    evaluate_applicability,
    evidence_transferability_fields,
)


VALID_EMPTY_GATE = {"safety_assertions": [], "regulatory_assertions": []}


def _context(*, prep="", route="oral", part="leaf", dose="240 mg/day", indication="pain"):
    project = {
        "target_indication": indication,
        "dosage_form": prep,
        "route": route,
        "target_plant_part": part,
        "target_dose": dose,
    }
    return build_transferability_target_context(indication, prep, project)


def _evidence(*, prep="standardized dry extract", route="oral", part="leaf", dose="240 mg/day"):
    return evidence_transferability_fields(
        species="Example species",
        plant_part=part,
        preparation=prep,
        route=route,
        dose=dose,
        indication_match_type="exact_indication",
    )


def _make_engine(plant: str):
    eng.SIMILAR_COMPOUND_GROUPS = {}
    eng.COMPOUND_TARGETS = {}
    rows = [
        dict(
            scientific_name=plant,
            compound_name="TransferCompound",
            indication="pain",
            target="Analgesic",
            common_name="",
            plant_part="",
            extraction_method="",
        )
    ]
    rows += [
        dict(
            scientific_name=f"TransferBg{i}",
            compound_name=f"TransferBgCompound{i}",
            indication="background",
            target="Antioxidant",
            common_name="",
            plant_part="",
            extraction_method="",
        )
        for i in range(25)
    ]
    return eng.BotanicalRDCandidateEngine(
        plant_compounds_df=pd.DataFrame(rows),
        compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(),
        use_live_search=False,
    )


def _self_row(result, plant):
    rows = result[
        (result["Reference_Plant"] == plant)
        & (result["Alternative_Plant"] == plant)
    ]
    assert not rows.empty
    return rows.iloc[0]


def test_literal_extractor_reports_study_preparation_not_requested_product():
    text = (
        "A randomized trial studied Example species leaf standardized dry extract. "
        "Participants were administered 240 mg/day orally for 24 weeks."
    )
    out = extract_evidence_from_text(text)
    assert out["Dosage_Form"] == "Extract"
    assert out["Preparation"] == "standardized dry extract"
    assert out["Plant_Part"] == "leaf"
    assert out["Administration_Route"] == "oral"
    assert out["Dose"] == "240 mg/day"
    assert out["Duration"] == "24 weeks"


def test_standardizer_keeps_requested_context_separate_and_fills_study_fields_from_llm(monkeypatch):
    captured = {}

    def fake_llm(record, selected_dosage_form="", selected_indication=""):
        captured["selected_dosage_form"] = selected_dosage_form
        captured["selected_indication"] = selected_indication
        return {
            "plant_scientific_name": "Example species",
            "evidence_type": "Randomized Controlled Trial",
            "study_model": "Human",
            "dosage_form": "Extract",
            "plant_part": "leaf",
            "preparation": "standardized dry extract EGX",
            "preparation_category": "dry_extract",
            "administration_route": "oral",
            "dose": "240 mg/day",
            "dose_unit": "mg/day",
            "extraction_method": "",
            "duration": "24 weeks",
            "target_indication": "pain",
            "dosage_form_relevance": "Indirect",
            "population": "adults",
            "sample_size": "100",
            "comparator": "placebo",
            "main_outcome": "pain improved",
            "result_direction": "Positive",
            "safety_signal": "None",
            "evidence_level": "High",
            "ema_relevance": "No",
            "who_relevance": "No",
            "escop_relevance": "No",
            "reason": "source text",
        }

    monkeypatch.setattr(evidence_standardizer, "extract_evidence_with_llm", fake_llm)
    monkeypatch.setattr(evidence_standardizer, "extract_gate_assertions_with_llm", None)

    out = evidence_standardizer.standardize_extracted_record(
        {
            "Scientific_Name": "Example species",
            "Requested_Target_Indication": "sleep",
            "Requested_Dosage_Form": "Infusion",
            "Source_Title": "trial",
            "Notes": "Study text",
        },
        {"source_type": "PubMed", "source_title": "trial", "source_url": "", "source_organization": "PubMed"},
    )

    assert captured == {"selected_dosage_form": "Infusion", "selected_indication": "sleep"}
    # Canonical evidence facts come from source-text extraction, not the request.
    assert out["Dosage_Form"] == "Extract"
    assert out["Target_Indication"] == "pain"
    assert out["Preparation"] == "standardized dry extract EGX"
    assert out["Plant_Part"] == "leaf"
    assert out["Administration_Route"] == "oral"
    assert out["Dose"] == "240 mg/day"
    assert out["Requested_Dosage_Form"] == "Infusion"
    assert out["Requested_Target_Indication"] == "sleep"


def test_source_provided_preparation_context_is_never_overwritten_by_llm(monkeypatch):
    def fake_llm(*args, **kwargs):
        return {
            "plant_scientific_name": "Example species", "evidence_type": "Clinical Study",
            "study_model": "Human", "dosage_form": "Capsule", "plant_part": "root",
            "preparation": "ethanolic extract", "preparation_category": "ethanolic",
            "administration_route": "topical", "dose": "999 mg/day", "dose_unit": "mg/day",
            "extraction_method": "ethanolic", "duration": "99 weeks",
            "target_indication": "other", "dosage_form_relevance": "Indirect",
            "population": "", "sample_size": "", "comparator": "", "main_outcome": "",
            "result_direction": "Unknown", "safety_signal": "Unknown", "evidence_level": "Moderate",
            "ema_relevance": "No", "who_relevance": "No", "escop_relevance": "No", "reason": "",
        }

    monkeypatch.setattr(evidence_standardizer, "extract_evidence_with_llm", fake_llm)
    monkeypatch.setattr(evidence_standardizer, "extract_gate_assertions_with_llm", None)
    out = evidence_standardizer.standardize_extracted_record(
        {
            "Scientific_Name": "Example species",
            "Preparation": "aqueous infusion",
            "Plant_Part": "leaf",
            "Administration_Route": "oral",
            "Dose": "2 g/day",
            "Target_Indication": "pain",
            "Result_Direction": "Positive",
            "Evidence_Level": "High",
            "Notes": "source",
        },
        {"source_type": "PubMed", "source_title": "source", "source_url": "", "source_organization": "PubMed"},
    )
    assert out["Preparation"] == "aqueous infusion"
    assert out["Plant_Part"] == "leaf"
    assert out["Administration_Route"] == "oral"
    assert out["Dose"] == "2 g/day"
    assert out["Target_Indication"] == "pain"


def test_capsule_is_dosage_form_not_automatically_a_preparation_and_missing_context_is_not_full_match():
    ctx = build_transferability_target_context(
        "pain", "Capsule", {"target_indication": "pain", "dosage_form": "Capsule"}
    )
    assert "Target_Preparation" not in ctx
    result = evaluate_applicability(_evidence(), ctx)
    assert result["Applicability_Classification"] == "UNKNOWN"
    assert result["Applicability_Data_Completeness"] == "incomplete"
    assert result["Record_Applicability_Factor"] < 1.0



def test_unambiguous_part_and_route_spelling_variants_do_not_create_false_mismatch():
    result = evaluate_applicability(
        _evidence(part="leaves", route="orally", prep="standardized dry extract"),
        _context(part="leaf", route="oral", prep="standardized dry extract"),
    )
    assert result["Dimension_Status"]["plant_part"] == "MATCH"
    assert result["Dimension_Status"]["route"] == "MATCH"

def test_dry_extract_evidence_is_not_transferable_to_infusion():
    result = evaluate_applicability(_evidence(), _context(prep="Infusion"))
    assert result["Dimension_Status"]["preparation"] == "MISMATCH"
    assert result["Applicability_Classification"] == "MISMATCH"


def test_same_aqueous_parent_category_is_partial_not_direct_match():
    result = evaluate_applicability(
        _evidence(prep="decoction"), _context(prep="Infusion")
    )
    assert result["Dimension_Status"]["preparation"] == "PARTIAL"
    assert result["Applicability_Classification"] == "PARTIAL"


def test_leaf_evidence_does_not_transfer_to_root_target():
    result = evaluate_applicability(_evidence(part="leaf"), _context(part="root", prep="standardized dry extract"))
    assert result["Dimension_Status"]["plant_part"] == "MISMATCH"
    assert result["Applicability_Classification"] == "MISMATCH"


def test_oral_evidence_does_not_transfer_to_topical_target():
    result = evaluate_applicability(_evidence(route="oral"), _context(route="topical", prep="standardized dry extract"))
    assert result["Dimension_Status"]["route"] == "MISMATCH"
    assert result["Applicability_Classification"] == "MISMATCH"


def test_out_of_range_dose_is_mismatch_when_units_are_comparable():
    result = evaluate_applicability(
        _evidence(dose="500 mg/day"), _context(prep="standardized dry extract", dose="240 mg/day")
    )
    assert result["Dimension_Status"]["dose"] == "MISMATCH"
    assert result["Applicability_Classification"] == "MISMATCH"


def test_compound_mode_preparation_mismatch_cannot_create_efficacy_go():
    plant = "TransferMismatchPlant"
    engine = _make_engine(plant)
    engine.evidence_df = pd.DataFrame([{
        "Scientific_Name": plant,
        "Target_Indication": "pain",
        "Preparation": "standardized dry extract",
        "Plant_Part": "leaf",
        "Administration_Route": "oral",
        "Dose": "240 mg/day",
        "Notes": "A randomized controlled trial found significantly improved pain versus placebo.",
        "Result_Direction": "Positive",
        "Study_Type": "Randomized Controlled Trial",
        "Evidence_Record_ID": "transfer-mismatch-1",
        "LLM_Gate_Assertions": VALID_EMPTY_GATE,
    }])
    ctx = _context(prep="Infusion")
    row = _self_row(
        engine.run(indication="pain", dosage_form="Infusion", market="EU", target_context=ctx),
        plant,
    )
    assert row["Evidence_Direction"] == "unclear"
    assert row["Final_Decision_Status"] == "INSUFFICIENT EVIDENCE"


def test_compound_mode_same_efficacy_record_becomes_usable_when_target_preparation_matches():
    plant = "TransferSwitchPlant"
    engine = _make_engine(plant)
    engine.evidence_df = pd.DataFrame([{
        "Scientific_Name": plant,
        "Target_Indication": "pain",
        "Preparation": "standardized dry extract",
        "Plant_Part": "leaf",
        "Administration_Route": "oral",
        "Dose": "240 mg/day",
        "Notes": "A randomized controlled trial found significantly improved pain versus placebo.",
        "Result_Direction": "Positive",
        "Study_Type": "Randomized Controlled Trial",
        "Evidence_Record_ID": "transfer-switch-1",
        "LLM_Gate_Assertions": VALID_EMPTY_GATE,
    }])
    mismatch = _self_row(
        engine.run(indication="pain", dosage_form="Infusion", market="EU", target_context=_context(prep="Infusion")),
        plant,
    )
    match = _self_row(
        engine.run(
            indication="pain", dosage_form="standardized dry extract", market="EU",
            target_context=_context(prep="standardized dry extract"),
        ),
        plant,
    )
    assert mismatch["Final_Decision_Status"] == "INSUFFICIENT EVIDENCE"
    assert match["Evidence_Direction"] == "positive"
    assert match["Final_Decision_Status"] in {"GO", "GO WITH CAUTION"}


def test_serious_safety_is_not_discarded_by_preparation_mismatch():
    plant = "TransferSafetyPlant"
    engine = _make_engine(plant)
    engine.evidence_df = pd.DataFrame([{
        "Scientific_Name": plant,
        "Target_Indication": "pain",
        "Preparation": "standardized dry extract",
        "Notes": "Use caused a life-threatening event requiring hospitalization.",
        "Result_Direction": "Unknown",
        "Evidence_Record_ID": "transfer-safety-1",
        "LLM_Gate_Assertions": {
            "safety_assertions": [{
                "hazard_present": True,
                "hazard_type": "serious_adverse_event",
                "reported_outcome": "life-threatening event requiring hospitalization",
                "seriousness": "serious",
                "seriousness_criterion": "life_threatening",
                "polarity": "risk_present",
                "causal_relationship": "causal",
                "preparation": "standardized dry extract",
                "route": "oral",
                "dose_dependency": "unknown",
                "affected_population": ["general"],
                "context_applicability": "relevant",
                "supporting_text": "life-threatening event requiring hospitalization",
                "extraction_confidence": 0.99,
            }],
            "regulatory_assertions": [],
        },
    }])
    row = _self_row(
        engine.run(indication="pain", dosage_form="Infusion", market="EU", target_context=_context(prep="Infusion")),
        plant,
    )
    assert row["Final_Decision_Status"] == "NO GO SAFETY"
    assert bool(row["Eligible_For_Normal_Ranking"]) is False


def test_structured_preparation_category_is_not_lost_when_preparation_text_is_blank():
    fields = evidence_transferability_fields(
        species="Example species",
        plant_part="leaf",
        preparation="",
        preparation_category="essential_oil",
        route="oral",
        dose="0.3 ml/day",
        indication_match_type="exact_indication",
    )
    result = evaluate_applicability(
        fields,
        _context(prep="Infusion", part="leaf", route="oral", dose="0.3 ml/day"),
    )
    assert fields["Evidence_Preparation_Category"] == "essential_oil"
    assert result["Dimension_Status"]["preparation"] == "MISMATCH"
    assert result["Applicability_Classification"] == "MISMATCH"


def test_dry_extract_category_survives_word_order_with_explicit_plant_part():
    fields = evidence_transferability_fields(
        species="Example species",
        plant_part="leaf",
        preparation="standardized dry leaf extract",
        preparation_category="dry_extract",
        route="oral",
        dose="240 mg/day",
        indication_match_type="exact_indication",
    )
    result = evaluate_applicability(
        fields,
        _context(prep="Infusion", part="leaf", route="oral", dose="240 mg/day"),
    )
    assert fields["Evidence_Preparation_Category"] == "dry_extract"
    assert result["Applicability_Classification"] == "MISMATCH"


def test_literal_extractor_recovers_plant_part_from_powdered_seeds():
    out = extract_evidence_from_text(
        "Participants swallowed powdered seeds orally at 5 g/day for the target condition."
    )
    assert out["Preparation"] == "powder"
    assert out["Plant_Part"] == "seed"


def test_llm_transferability_postprocess_recovers_only_explicit_missing_fields():
    from llm_extractor import _normalize_transferability_extraction

    out = _normalize_transferability_extraction(
        {
            "plant_part": "",
            "preparation": "",
            "preparation_category": "powder",
        },
        "Subjects consumed powdered seeds orally at 5 g/day.",
    )
    assert out["plant_part"] == "seed"
    assert "powdered seeds" in out["preparation"].lower()
    assert out["preparation_category"] == "powder"

    # No source wording -> no fabricated preparation/part.
    untouched = _normalize_transferability_extraction(
        {"plant_part": "", "preparation": "", "preparation_category": "dry_extract"},
        "The intervention was administered for 8 weeks.",
    )
    assert untouched["plant_part"] == ""
    assert untouched["preparation"] == ""
