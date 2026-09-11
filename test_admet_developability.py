import json

import pandas as pd
import pytest

import admet_developability as ad
from admet_developability import (
    assess_compound_admet,
    aggregate_plant_admet,
    attach_admet_developability,
    collect_linked_compound_names,
    parse_admet_summary,
    parse_admet_key_flags,
    OVERALL_FAVORABLE,
    OVERALL_REVIEW,
    OVERALL_HIGH_CONCERN,
    OVERALL_INSUFFICIENT_DATA,
    OVERALL_UNAVAILABLE,
    ABSORPTION_FAVORABLE,
    ABSORPTION_REVIEW,
    ABSORPTION_POOR,
    ABSORPTION_INSUFFICIENT,
    TOXICITY_SERIOUS,
    TOXICITY_MODERATE,
    TOXICITY_INSUFFICIENT,
)
from candidate_shortlisting import merge_authoritative_scores


# ---------------------------------------------------------------------------
# Compound-level assessment
# ---------------------------------------------------------------------------

def test_compound_absorption_favorable_no_lipinski_violations():
    r = assess_compound_admet(
        "Clean Compound",
        pubchem_properties={
            "MolecularWeight": 250, "XLogP": 1.5, "TPSA": 50,
            "HBondDonorCount": 1, "HBondAcceptorCount": 3, "RotatableBondCount": 2,
        },
    )
    assert r["absorption"]["status"] == ABSORPTION_FAVORABLE
    assert r["absorption"]["evidence_level"] == ad.PROVENANCE_PROPERTY_COMPUTATIONAL


def test_compound_absorption_poor_multiple_violations():
    r = assess_compound_admet(
        "Heavy Compound",
        pubchem_properties={
            "MolecularWeight": 900, "XLogP": 8, "TPSA": 200,
            "HBondDonorCount": 8, "HBondAcceptorCount": 15, "RotatableBondCount": 20,
        },
    )
    assert r["absorption"]["status"] == ABSORPTION_POOR
    assert len(r["absorption"]["details"]) >= 1


def test_compound_absorption_insufficient_when_too_few_descriptors():
    r = assess_compound_admet("Sparse Compound", pubchem_properties={"MolecularWeight": 300})
    assert r["absorption"]["status"] == ABSORPTION_INSUFFICIENT


def test_compound_absorption_insufficient_with_no_inputs_at_all():
    r = assess_compound_admet("No Data Compound")
    assert r["absorption"]["status"] == ABSORPTION_INSUFFICIENT
    assert r["metabolism"]["status"] == ABSORPTION_INSUFFICIENT
    assert r["distribution"]["status"] == ABSORPTION_INSUFFICIENT
    assert r["excretion"]["status"] == ABSORPTION_INSUFFICIENT


def test_compound_curated_bioavailability_preferred_over_property_heuristic():
    # A curated "High" bioavailability rating should win over a mediocre
    # (1-violation) property-derived profile, and be labeled DATABASE_DERIVED.
    r = assess_compound_admet(
        "Curated Compound",
        pubchem_properties={
            "MolecularWeight": 550, "XLogP": 2, "TPSA": 60,
            "HBondDonorCount": 1, "HBondAcceptorCount": 3, "RotatableBondCount": 2,
        },
        compound_profile={"bioavailability": "High", "toxicity": ""},
    )
    assert r["absorption"]["status"] == "FAVORABLE_CURATED_BIOAVAILABILITY"
    assert r["absorption"]["evidence_level"] == ad.PROVENANCE_DATABASE_CURATED


def test_compound_curated_toxicity_flag_surfaced_but_not_experimental():
    r = assess_compound_admet(
        "Risky Compound", compound_profile={"bioavailability": "", "toxicity": "High"},
    )
    assert r["compound_toxicity_signal"]["status"] == "CURATED_CONCERN_UNVERIFIED"
    assert "not independently verified" in r["compound_toxicity_signal"]["details"][0]


def test_assess_compound_admet_never_raises_on_malformed_inputs():
    r = assess_compound_admet(
        None,
        pubchem_properties={"MolecularWeight": "not-a-number", "XLogP": None},
        compound_profile={"bioavailability": 12345, "toxicity": object()},
    )
    assert r["absorption"]["status"] in (ABSORPTION_INSUFFICIENT, ABSORPTION_REVIEW, ABSORPTION_POOR, ABSORPTION_FAVORABLE)


# ---------------------------------------------------------------------------
# Plant-level aggregation
# ---------------------------------------------------------------------------

def test_plant_no_compounds_no_safety_is_insufficient_data():
    agg = aggregate_plant_admet("Empty Plant", [], safety_fields=None)
    assert agg["overall_developability_status"] == OVERALL_INSUFFICIENT_DATA
    assert agg["compounds_assessed_count"] == 0


def test_plant_missing_safety_data_never_implies_favorable():
    # No compounds, no safety evidence at all -- must not be FAVORABLE.
    agg = aggregate_plant_admet("Unknown Safety Plant", [], safety_fields={})
    assert agg["overall_developability_status"] != OVERALL_FAVORABLE


def test_plant_serious_safety_concern_yields_high_concern_regardless_of_absorption():
    good_compound = assess_compound_admet(
        "Good Compound",
        pubchem_properties={"MolecularWeight": 200, "XLogP": 1, "TPSA": 40, "HBondDonorCount": 1, "HBondAcceptorCount": 2, "RotatableBondCount": 1},
    )
    agg = aggregate_plant_admet(
        "Concern Plant", [good_compound],
        safety_fields={
            "Safety_Assertion_Status": "SAFETY_CONCERN_RETRIEVED",
            "Safety_Concern_Level": "SERIOUS",
            "Safety_Status_Rationale": "Hepatotoxicity reported in a case series.",
            "Safety_Evidence_IDs": ["E1", "E2"],
        },
    )
    assert agg["overall_developability_status"] == OVERALL_HIGH_CONCERN
    assert agg["toxicity"]["status"] == TOXICITY_SERIOUS


def test_plant_moderate_interaction_signal_is_review_not_high_concern():
    agg = aggregate_plant_admet(
        "Moderate Plant", [],
        safety_fields={
            "Safety_Assertion_Status": "INTERACTION_SIGNAL_RETRIEVED",
            "Safety_Concern_Level": "MODERATE",
            "Safety_Status_Rationale": "CYP3A4 interaction reported.",
            "Safety_Evidence_IDs": ["E3"],
        },
    )
    assert agg["overall_developability_status"] == OVERALL_REVIEW
    assert agg["toxicity"]["status"] == TOXICITY_MODERATE


def test_plant_reassurance_only_never_becomes_favorable_without_good_absorption():
    agg = aggregate_plant_admet(
        "Reassured Plant", [],
        safety_fields={
            "Safety_Assertion_Status": "STUDY_SPECIFIC_REASSURANCE_ONLY",
            "Safety_Concern_Level": "NONE",
            "Safety_Status_Rationale": "No adverse events reported in one small trial.",
            "Safety_Evidence_IDs": ["E4"],
        },
    )
    # No compound data at all -> absorption stays INSUFFICIENT_DATA, so even
    # with reassurance the overall label must NOT be FAVORABLE.
    assert agg["overall_developability_status"] != OVERALL_FAVORABLE


def test_plant_favorable_absorption_plus_reassurance_is_review_not_favorable_in_v1():
    # CORRECTION 1 (2026-09-11): V1 must not emit overall FAVORABLE while
    # Distribution/Metabolism/Excretion remain INSUFFICIENT_DATA, even when
    # absorption is favorable and safety evidence is reassuring.
    favorable_compound = assess_compound_admet(
        "Favorable Compound",
        pubchem_properties={"MolecularWeight": 220, "XLogP": 1, "TPSA": 40, "HBondDonorCount": 1, "HBondAcceptorCount": 2, "RotatableBondCount": 1},
    )
    assert favorable_compound["absorption"]["status"] == ABSORPTION_FAVORABLE
    agg = aggregate_plant_admet(
        "Genuinely Favorable Plant", [favorable_compound],
        safety_fields={
            "Safety_Assertion_Status": "STUDY_SPECIFIC_REASSURANCE_ONLY",
            "Safety_Concern_Level": "NONE",
            "Safety_Status_Rationale": "No adverse events reported.",
            "Safety_Evidence_IDs": ["E5"],
        },
    )
    # Test 1: overall must be REVIEW, not FAVORABLE.
    assert agg["overall_developability_status"] == OVERALL_REVIEW
    assert agg["overall_developability_status"] != OVERALL_FAVORABLE
    # The underlying dimension statuses must be unchanged by this correction.
    assert agg["absorption"]["status"] == ABSORPTION_FAVORABLE
    assert agg["toxicity"]["status"] == ad.TOXICITY_LIMITED_REASSURANCE
    # Test 2: rationale must explicitly say major ADME dimensions are unassessed.
    reasons_text = " ".join(agg["overall_status_reasons"])
    assert "major ADME dimensions remain unassessed" in reasons_text


def test_plant_single_compound_concern_does_not_blanket_condemn_whole_plant_summary_text():
    # Rule: a single compound concern must not silently become "this plant
    # is unsafe" -- the disclaimer must always be present and explicit.
    agg = aggregate_plant_admet("Multi Compound Plant", [], safety_fields=None)
    assert "not a measured pharmacokinetic profile" in agg["disclaimer"]
    assert "single compound" in agg["disclaimer"].lower() or "single compound" in agg["disclaimer"]


def test_plant_aggregation_is_deterministic():
    compound = assess_compound_admet(
        "Determinism Compound",
        pubchem_properties={"MolecularWeight": 300, "XLogP": 2, "TPSA": 60, "HBondDonorCount": 2, "HBondAcceptorCount": 4, "RotatableBondCount": 3},
    )
    safety = {
        "Safety_Assertion_Status": "SAFETY_CONCERN_RETRIEVED", "Safety_Concern_Level": "MODERATE",
        "Safety_Status_Rationale": "x", "Safety_Evidence_IDs": ["E6"],
    }
    results = [aggregate_plant_admet("Det Plant", [compound], safety_fields=safety) for _ in range(5)]
    statuses = {r["overall_developability_status"] for r in results}
    assert len(statuses) == 1


# ---------------------------------------------------------------------------
# Correction 2 (2026-09-11): conservative data-completeness label thresholds.
# The current V1 architecture (Distribution/Metabolism/Excretion always
# INSUFFICIENT_DATA) can never itself resolve more than 2/5 dimensions, so
# tests 6/7 exercise the completeness-label helper directly rather than
# fabricating ADMET evidence, per the correction's own instruction.
# ---------------------------------------------------------------------------

def test_completeness_label_zero_resolved_is_low():
    assert ad._completeness_label(0) == "LOW"


def test_completeness_label_one_resolved_is_low():
    assert ad._completeness_label(1) == "LOW"


def test_completeness_label_two_resolved_is_low():
    assert ad._completeness_label(2) == "LOW"


def test_completeness_label_three_or_four_resolved_is_moderate():
    assert ad._completeness_label(3) == "MODERATE"
    assert ad._completeness_label(4) == "MODERATE"


def test_completeness_label_five_resolved_is_high():
    assert ad._completeness_label(5) == "HIGH"


def test_completeness_numeric_score_calculation_is_unchanged():
    # The dimensions_resolved/5 calculation itself must be untouched by
    # Correction 2 -- only the categorical label thresholds changed.
    compound = assess_compound_admet(
        "Coverage Compound",
        pubchem_properties={"MolecularWeight": 250, "XLogP": 2, "TPSA": 50, "HBondDonorCount": 1, "HBondAcceptorCount": 3, "RotatableBondCount": 2},
    )
    agg = aggregate_plant_admet("Coverage Plant", [compound], safety_fields={
        "Safety_Assertion_Status": "STUDY_SPECIFIC_REASSURANCE_ONLY", "Safety_Concern_Level": "NONE",
    })
    # Absorption + toxicity (reassurance) resolved -> 2/5 = 0.4
    assert agg["data_completeness_score"] == 0.4
    assert agg["data_completeness_label"] == "LOW"


def test_v1_typical_case_absorption_and_toxicity_only_is_low_completeness():
    compound = assess_compound_admet(
        "Typical Compound",
        pubchem_properties={"MolecularWeight": 300, "XLogP": 2, "TPSA": 60, "HBondDonorCount": 2, "HBondAcceptorCount": 4, "RotatableBondCount": 3},
    )
    agg = aggregate_plant_admet("Typical Plant", [compound], safety_fields={
        "Safety_Assertion_Status": "SAFETY_CONCERN_RETRIEVED", "Safety_Concern_Level": "MODERATE",
    })
    assert agg["data_completeness_label"] == "LOW"


# ---------------------------------------------------------------------------
# attach_admet_developability() -- report_df integration
# ---------------------------------------------------------------------------

def _base_report_df():
    return pd.DataFrame([
        {
            "Alternative_Plant": "Melissa officinalis", "Overall_Score": 91.2,
            "R&D_Opportunity_Score": 91.2, "Decision_Class_AH": "A", "Go_Investigate_Hold_NoGo": "Go",
            "Scientific_Triage_Status": "Included",
            "Safety_Assertion_Status": "SAFETY_CONCERN_RETRIEVED", "Safety_Concern_Level": "MODERATE",
            "Safety_Status_Rationale": "CYP interaction reported.", "Safety_Evidence_IDs": ["E1"],
            "Discovery_Linked_Compounds": "Rosmarinic acid; Citral",
        },
        {
            "Alternative_Plant": "Passiflora incarnata", "Overall_Score": 74.5,
            "R&D_Opportunity_Score": 74.5, "Decision_Class_AH": "B", "Go_Investigate_Hold_NoGo": "Investigate",
            "Scientific_Triage_Status": "Included",
            "Safety_Assertion_Status": "NO_SAFETY_EVIDENCE_RETRIEVED", "Safety_Concern_Level": "UNKNOWN",
            "Safety_Status_Rationale": "", "Safety_Evidence_IDs": [],
            "Discovery_Linked_Compounds": "",
        },
    ])


def _plant_compounds_df():
    return pd.DataFrame([
        {"scientific_name": "Melissa officinalis", "compound_name": "Rosmarinic acid"},
        {"scientific_name": "Melissa officinalis", "compound_name": "Citral"},
    ])


def _compound_profiles_df():
    return pd.DataFrame([
        {"compound_name": "Rosmarinic acid", "bioavailability": "Medium", "toxicity": "Low"},
        {"compound_name": "Citral", "bioavailability": "Low", "toxicity": "Medium"},
    ])


def test_attach_admet_developability_is_purely_additive():
    df = _base_report_df()
    original = df.copy(deep=True)
    out = attach_admet_developability(
        df, plant_compounds_df=_plant_compounds_df(), compound_profiles_df=_compound_profiles_df(), compound_property_map={},
    )
    assert len(out) == len(original)
    assert list(out["Alternative_Plant"]) == list(original["Alternative_Plant"])
    for col in original.columns:
        for i in range(len(original)):
            a, b = out.loc[i, col], original.loc[i, col]
            if isinstance(a, list) or isinstance(b, list):
                assert a == b
            else:
                assert a == b or (pd.isna(a) and pd.isna(b))
    new_cols = set(out.columns) - set(original.columns)
    assert "ADMET_Overall_Status" in new_cols
    assert "ADMET_Detail" in new_cols


def test_attach_admet_developability_empty_df_passthrough():
    empty = pd.DataFrame()
    assert attach_admet_developability(empty) is empty


def test_attach_admet_developability_missing_plant_column_passthrough():
    df = pd.DataFrame([{"Some_Other_Col": 1}])
    out = attach_admet_developability(df)
    assert "ADMET_Overall_Status" not in out.columns


def test_attach_admet_developability_missing_compound_data_never_crashes():
    df = pd.DataFrame([{"Alternative_Plant": "No Data Plant", "Overall_Score": 10}])
    out = attach_admet_developability(df, plant_compounds_df=None, compound_profiles_df=None, compound_property_map=None)
    assert out.loc[0, "ADMET_Overall_Status"] == OVERALL_INSUFFICIENT_DATA


def test_attach_admet_developability_one_candidate_failure_does_not_remove_others(monkeypatch):
    df = _base_report_df()

    real_aggregate = ad.aggregate_plant_admet

    def flaky_aggregate(plant_name, *a, **k):
        if str(plant_name) == "Melissa officinalis":
            raise RuntimeError("simulated per-candidate failure")
        return real_aggregate(plant_name, *a, **k)

    monkeypatch.setattr(ad, "aggregate_plant_admet", flaky_aggregate)
    out = attach_admet_developability(df, plant_compounds_df=_plant_compounds_df(), compound_profiles_df=_compound_profiles_df())

    assert len(out) == 2
    assert set(out["Alternative_Plant"]) == {"Melissa officinalis", "Passiflora incarnata"}
    row = out[out["Alternative_Plant"] == "Melissa officinalis"].iloc[0]
    assert row["ADMET_Overall_Status"] == OVERALL_UNAVAILABLE
    other = out[out["Alternative_Plant"] == "Passiflora incarnata"].iloc[0]
    assert other["ADMET_Overall_Status"] != OVERALL_UNAVAILABLE


def test_no_data_case_produces_insufficient_not_favorable():
    df = pd.DataFrame([{"Alternative_Plant": "Totally Unknown Plant", "Overall_Score": 5}])
    out = attach_admet_developability(df)
    assert out.loc[0, "ADMET_Overall_Status"] == OVERALL_INSUFFICIENT_DATA
    assert out.loc[0, "ADMET_Overall_Status"] != OVERALL_FAVORABLE


def test_known_concern_compound_produces_expected_flag():
    df = _base_report_df()
    out = attach_admet_developability(df, plant_compounds_df=_plant_compounds_df(), compound_profiles_df=_compound_profiles_df())
    row = out[out["Alternative_Plant"] == "Melissa officinalis"].iloc[0]
    flags = parse_admet_key_flags(row["ADMET_Key_Flags"])
    assert any("Citral" in f for f in flags)  # curated Medium toxicity rating


def test_collect_linked_compound_names_dedupes_across_plants():
    df = pd.DataFrame([
        {"Alternative_Plant": "Plant A", "Discovery_Linked_Compounds": "Apigenin; Luteolin"},
        {"Alternative_Plant": "Plant B", "Discovery_Linked_Compounds": "Apigenin; Vitexin"},
    ])
    names = collect_linked_compound_names(df)
    assert names.count("Apigenin") == 1
    assert set(names) == {"Apigenin", "Luteolin", "Vitexin"}


def test_json_columns_round_trip_via_parse_helpers():
    df = _base_report_df()
    out = attach_admet_developability(df, plant_compounds_df=_plant_compounds_df(), compound_profiles_df=_compound_profiles_df())
    row = out.iloc[0]
    summary = parse_admet_summary(row["ADMET_Summary"])
    assert "absorption" in summary and "toxicity" in summary
    detail = parse_admet_summary(row["ADMET_Detail"])
    assert "compound_level_detail" in detail


# ---------------------------------------------------------------------------
# Regression: ADMET must never change existing ranking/scoring/safety output
# ---------------------------------------------------------------------------

def _raw_and_plant_summary_fixture():
    raw_df = pd.DataFrame([
        {
            "Alternative_Plant": "Melissa officinalis", "R&D_Opportunity_Score": 91.2,
            "Source_Record_IDs": "R1", "Rationale": "Strong evidence base.",
        },
        {
            "Alternative_Plant": "Passiflora incarnata", "R&D_Opportunity_Score": 74.5,
            "Source_Record_IDs": "R2", "Rationale": "Moderate evidence base.",
        },
        {
            "Alternative_Plant": "Valeriana officinalis", "R&D_Opportunity_Score": 40.0,
            "Source_Record_IDs": "R3", "Rationale": "Weak evidence base.",
        },
    ])
    plant_summary = pd.DataFrame([
        {
            "Alternative_Plant": "Melissa officinalis", "Overall_Score": 91.2,
            "Decision_Class_AH": "A", "Go_Investigate_Hold_NoGo": "Go",
            "Scientific_Triage_Status": "Included",
            "Safety_Assertion_Status": "SAFETY_CONCERN_RETRIEVED", "Safety_Concern_Level": "MODERATE",
            "Safety_Evidence_IDs": ["E1"],
        },
        {
            "Alternative_Plant": "Passiflora incarnata", "Overall_Score": 74.5,
            "Decision_Class_AH": "B", "Go_Investigate_Hold_NoGo": "Investigate",
            "Scientific_Triage_Status": "Included",
            "Safety_Assertion_Status": "NO_SAFETY_EVIDENCE_RETRIEVED", "Safety_Concern_Level": "UNKNOWN",
            "Safety_Evidence_IDs": [],
        },
        {
            "Alternative_Plant": "Valeriana officinalis", "Overall_Score": 40.0,
            "Decision_Class_AH": "D", "Go_Investigate_Hold_NoGo": "No-Go",
            "Scientific_Triage_Status": "Excluded",
            "Safety_Assertion_Status": "INSUFFICIENT_OR_UNKNOWN", "Safety_Concern_Level": "UNKNOWN",
            "Safety_Evidence_IDs": [],
        },
    ])
    return raw_df, plant_summary


def test_ranking_and_scoring_identical_before_and_after_admet_attach():
    raw_df, plant_summary = _raw_and_plant_summary_fixture()
    report_ready = merge_authoritative_scores(raw_df, plant_summary)

    before_order = list(report_ready["Alternative_Plant"])
    before_scores = list(report_ready["Overall_Score"])
    before_rd_scores = list(report_ready["R&D_Opportunity_Score"])
    before_decision = list(report_ready["Decision_Class_AH"])
    before_gate = list(report_ready["Go_Investigate_Hold_NoGo"])
    before_triage = list(report_ready["Scientific_Triage_Status"])
    before_safety_status = list(report_ready["Safety_Assertion_Status"])
    before_safety_level = list(report_ready["Safety_Concern_Level"])
    before_count = len(report_ready)

    admet_attached = attach_admet_developability(
        report_ready, plant_compounds_df=_plant_compounds_df(), compound_profiles_df=_compound_profiles_df(),
    )

    assert len(admet_attached) == before_count
    assert list(admet_attached["Alternative_Plant"]) == before_order
    assert list(admet_attached["Overall_Score"]) == before_scores
    assert list(admet_attached["R&D_Opportunity_Score"]) == before_rd_scores
    assert list(admet_attached["Decision_Class_AH"]) == before_decision
    assert list(admet_attached["Go_Investigate_Hold_NoGo"]) == before_gate
    assert list(admet_attached["Scientific_Triage_Status"]) == before_triage
    assert list(admet_attached["Safety_Assertion_Status"]) == before_safety_status
    assert list(admet_attached["Safety_Concern_Level"]) == before_safety_level

    # ADMET only ADDS columns -- every pre-existing column must still exist.
    assert set(report_ready.columns).issubset(set(admet_attached.columns))


def test_admet_columns_are_not_in_authoritative_fields():
    # Architecture clarification: ADMET must stay OUTSIDE the authoritative
    # scoring merge -- merge_authoritative_scores() must not reference any
    # ADMET_* field, and calling it again after ADMET has been attached
    # must not error or need any ADMET-aware handling.
    import inspect
    source = inspect.getsource(merge_authoritative_scores)
    assert "ADMET" not in source


def test_reapplying_merge_authoritative_scores_after_admet_is_harmless():
    raw_df, plant_summary = _raw_and_plant_summary_fixture()
    report_ready = merge_authoritative_scores(raw_df, plant_summary)
    admet_attached = attach_admet_developability(
        report_ready, plant_compounds_df=_plant_compounds_df(), compound_profiles_df=_compound_profiles_df(),
    )
    # Simulate a downstream refresh that rebuilds report_ready_df from the
    # same raw/plant_summary frames (e.g. a commercial-only refresh) --
    # ranking/scoring output must be identical whether or not ADMET was
    # ever attached in between.
    rebuilt = merge_authoritative_scores(raw_df, plant_summary)
    assert list(rebuilt["Overall_Score"]) == list(report_ready["Overall_Score"])
    assert list(rebuilt["Alternative_Plant"]) == list(report_ready["Alternative_Plant"])
