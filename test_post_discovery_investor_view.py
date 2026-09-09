import math

import pandas as pd

import post_discovery_investor_view as piv
from rd_discovery_classification import (
    DISCOVERY_LANE_EVIDENCE_BACKED,
    DISCOVERY_LANE_HYPOTHESIS,
    DISCOVERY_LANE_CATALOGUE_HYPOTHESIS,
    DISCOVERY_LANE_EVIDENCE_GAP,
    DISCOVERY_LANE_CATALOGUE_EVIDENCE_GAP,
    DISCOVERY_LANE_REGULATORY_STOP,
    DISCOVERY_LANE_SAFETY_STOP,
    DISCOVERY_LANE_INSUFFICIENT,
)
from commercial_opportunity_classification import (
    OPP_WHITE_SPACE_OPPORTUNITY,
    OPP_CROWDED_MARKET,
    OPP_REPURPOSING_OPPORTUNITY,
)


def _row(**overrides):
    base = {
        "Alternative_Plant": "Withania somnifera",
        "RD_Discovery_Lane": DISCOVERY_LANE_HYPOTHESIS,
        "Already_In_Internal_Catalogue": False,
        "Discovery_Linked_Target_Count": 0,
        "Discovery_Linked_Mechanism_Count": 0,
        "Discovery_Linked_Compound_Count": 0,
        "Direct_Indication_Evidence_Count": 0,
        "Discovery_Potential_Score": 60.0,
        "Evidence_Maturity_Score": 10.0,
        "Overall_Score": 45.0,
        "R&D_Opportunity_Score": 45.0,
        "Commercial_Status_Overall": "UNKNOWN",
        "Commercial_Status_For_Indication": "UNKNOWN",
        "Commercial_Opportunity_Class": None,
        "Safety_Concern_Level": "NONE",
        "Safety_Assertion_Status": "NO_SAFETY_EVIDENCE_RETRIEVED",
        "Regulatory_Prohibition_Present": False,
        "Dosage_Form_Compatibility": "Compatible / unspecified",
        "Outcome_Consistency": "Results not reported",
        "Commercial_Assessment_Status": "NOT_ASSESSED",
    }
    base.update(overrides)
    return base


# --- Discovery_Admission_Path / Rationale / has_defensible_admission -----

def test_mechanistic_linkage_gives_profile_derived_admission_path():
    row = _row(Discovery_Linked_Target_Count=2, Discovery_Linked_Mechanism_Count=1)
    assert piv.discovery_admission_path(row) == "Profile-derived mechanistic linkage"
    assert piv.has_defensible_admission(row) is True
    assert "2 linked target" in piv.discovery_admission_rationale(row)


def test_direct_evidence_gives_direct_evidence_admission_path():
    row = _row(Direct_Indication_Evidence_Count=3)
    assert piv.discovery_admission_path(row) == "Direct indication evidence record"
    assert piv.has_defensible_admission(row) is True


def test_catalogue_membership_alone_is_a_named_admission_path():
    row = _row(
        RD_Discovery_Lane=DISCOVERY_LANE_EVIDENCE_GAP,
        Already_In_Internal_Catalogue=True,
    )
    assert piv.discovery_admission_path(row) == "Catalogue membership (no matched provenance)"
    assert piv.has_defensible_admission(row) is True


def test_no_provenance_at_all_is_not_defensible():
    """The Acacia senegal scenario from the cahier des charges: no linked
    target/mechanism/compound, no direct evidence, not a catalogue-gap
    lane -- must not be presented as a positive hypothesis.
    """
    row = _row(RD_Discovery_Lane=DISCOVERY_LANE_INSUFFICIENT, Already_In_Internal_Catalogue=False)
    assert piv.discovery_admission_path(row) == "No defensible admission provenance"
    assert piv.has_defensible_admission(row) is False


# --- Opportunity_Type ------------------------------------------------------

def test_safety_stop_lane_is_safety_de_risking_opportunity_type():
    row = _row(RD_Discovery_Lane=DISCOVERY_LANE_SAFETY_STOP)
    assert piv.opportunity_type(row) == "Safety-De-Risking Research Lead"


def test_regulatory_stop_lane_is_regulatory_constrained_opportunity_type():
    row = _row(RD_Discovery_Lane=DISCOVERY_LANE_REGULATORY_STOP)
    assert piv.opportunity_type(row) == "Regulatory-Constrained Candidate"


def test_crowded_market_overrides_to_commercially_crowded():
    row = _row(
        RD_Discovery_Lane=DISCOVERY_LANE_EVIDENCE_BACKED,
        Commercial_Opportunity_Class=OPP_CROWDED_MARKET,
    )
    assert piv.opportunity_type(row) == "Commercially Crowded Candidate"


def test_evidence_backed_not_catalogued_is_novel_botanical_discovery():
    row = _row(RD_Discovery_Lane=DISCOVERY_LANE_EVIDENCE_BACKED, Already_In_Internal_Catalogue=False)
    assert piv.opportunity_type(row) == "Novel Botanical Discovery"


def test_evidence_backed_catalogued_is_evidence_backed_validation_candidate():
    row = _row(RD_Discovery_Lane=DISCOVERY_LANE_EVIDENCE_BACKED, Already_In_Internal_Catalogue=True)
    assert piv.opportunity_type(row) == "Evidence-Backed Validation Candidate"


# --- What_Is_New -----------------------------------------------------------

def test_not_in_catalogue_is_always_novel_to_catalogue():
    row = _row(Already_In_Internal_Catalogue=False, RD_Discovery_Lane=DISCOVERY_LANE_EVIDENCE_BACKED)
    assert piv.what_is_new(row) == "Novel-to-catalogue botanical"


def test_catalogue_plant_never_called_novel_discovery():
    """Explicit anti-regression for the doc's repeated warning: a catalogue
    plant must never be described as a novel botanical discovery."""
    row = _row(
        Already_In_Internal_Catalogue=True,
        RD_Discovery_Lane=DISCOVERY_LANE_CATALOGUE_HYPOTHESIS,
    )
    result = piv.what_is_new(row)
    assert "novel" not in result.lower() or "hypothesis" in result.lower()
    assert result == "Mechanistic repurposing hypothesis"


# --- Key_Evidence_Gap precedence -------------------------------------------

def test_serious_safety_concern_is_top_priority_gap():
    row = _row(Safety_Concern_Level="SERIOUS", Direct_Indication_Evidence_Count=5)
    assert piv.key_evidence_gap(row) == "Safety characterization insufficient"


def test_no_direct_evidence_with_mechanistic_linkage_is_mechanistic_evidence_only():
    row = _row(Direct_Indication_Evidence_Count=0, Discovery_Linked_Target_Count=2)
    assert piv.key_evidence_gap(row) == "Mechanistic evidence only"


def test_no_direct_evidence_and_no_linkage_is_no_direct_human_evidence():
    row = _row(Direct_Indication_Evidence_Count=0)
    assert piv.key_evidence_gap(row) == "No direct human evidence for queried indication"


def test_commercial_not_assessed_is_lowest_priority_gap():
    row = _row(
        Direct_Indication_Evidence_Count=2,
        Commercial_Assessment_Status="NOT_ASSESSED",
    )
    assert piv.key_evidence_gap(row) == "Commercial market not assessed"


# --- Next_R&D_Step precedence -----------------------------------------------

def test_safety_concern_next_step_is_resolve_toxicology():
    row = _row(Safety_Concern_Level="SERIOUS")
    assert piv.next_rd_step(row) == "Resolve toxicology/interaction risk before efficacy development."


def test_mechanistic_only_next_step_is_confirm_preclinical():
    row = _row(Direct_Indication_Evidence_Count=0, Discovery_Linked_Target_Count=1)
    assert piv.next_rd_step(row) == "Confirm indication-specific activity in a controlled preclinical model."


def test_direct_evidence_with_dosage_mismatch_next_step_is_validate_transferability():
    row = _row(Direct_Indication_Evidence_Count=2, Dosage_Form_Compatibility="Incompatible")
    assert piv.next_rd_step(row) == "Validate preparation/exposure transferability."


# --- commercial_assessment_fields / commercial_opportunity_score -----------

def test_no_commercial_search_at_all_is_not_assessed_with_nan_score():
    row = _row(Commercial_Status_Overall="UNKNOWN", Commercial_Status_For_Indication="UNKNOWN")
    assessment = piv.commercial_assessment_fields(row)
    assert assessment["Commercial_Assessment_Status"] == "NOT_ASSESSED"
    assert assessment["Commercial_Data_Completeness"] == 0.0
    score = piv.commercial_opportunity_score(row, commercial_assessment=assessment)
    assert score is None


def test_both_dimensions_assessed_meets_threshold_and_can_score():
    row = _row(
        Commercial_Status_Overall="NO_VERIFIED_PRODUCT_FOUND_IN_COVERED_SOURCES",
        Commercial_Status_For_Indication="NO_VERIFIED_PRODUCT_FOR_INDICATION_IN_COVERED_SOURCES",
        Commercial_Opportunity_Class=OPP_WHITE_SPACE_OPPORTUNITY,
    )
    assessment = piv.commercial_assessment_fields(row)
    assert assessment["Commercial_Assessment_Status"] == "ASSESSED"
    assert assessment["Commercial_Data_Completeness"] == 1.0
    score = piv.commercial_opportunity_score(row, commercial_assessment=assessment)
    assert score == 85.0


def test_partial_assessment_is_distinct_from_full_or_none():
    row = _row(
        Commercial_Status_Overall="VERIFIED_MARKETED",
        Commercial_Status_For_Indication="UNKNOWN",
    )
    assessment = piv.commercial_assessment_fields(row)
    assert assessment["Commercial_Assessment_Status"] == "PARTIALLY_ASSESSED"
    assert 0.0 < assessment["Commercial_Data_Completeness"] < 1.0
    assert piv.commercial_opportunity_score(row, commercial_assessment=assessment) is None


def test_patent_and_regulatory_are_explicitly_not_integrated_not_fabricated():
    row = _row()
    assessment = piv.commercial_assessment_fields(row)
    assert assessment["Patent_Assessment_Status"] == "NOT_INTEGRATED"
    assert assessment["Regulatory_Assessment_Status"] == "NOT_INTEGRATED"


def test_search_not_performed_never_treated_as_assessed():
    """Section 5's central rule: SEARCH_NOT_PERFORMED-shaped statuses must
    never be read as a completed search."""
    row = _row(
        Commercial_Status_Overall="SEARCH_NOT_PERFORMED",
        Commercial_Status_For_Indication="NOT_REQUESTED",
    )
    assessment = piv.commercial_assessment_fields(row)
    assert assessment["Retail_Assessment_Status"] == "NOT_ASSESSED"
    assert assessment["Indication_Market_Assessment_Status"] == "NOT_ASSESSED"


# --- build_investor_opportunity_view ----------------------------------------

def test_build_investor_opportunity_view_returns_full_and_compact_frames():
    df = pd.DataFrame([
        _row(Alternative_Plant="Strong plant", Direct_Indication_Evidence_Count=3, Discovery_Potential_Score=90.0),
        _row(Alternative_Plant="Weak plant", RD_Discovery_Lane=DISCOVERY_LANE_INSUFFICIENT, Discovery_Potential_Score=10.0),
    ])
    full_df, compact_df = piv.build_investor_opportunity_view(df)
    assert "Why_Interesting" in full_df.columns
    assert "Discovery_Admission_Path" in full_df.columns
    assert list(compact_df.columns) == [
        c for c in piv.INVESTOR_VIEW_COMPACT_COLUMNS if c in compact_df.columns
    ]


def test_non_defensible_candidate_excluded_from_compact_view_but_kept_in_full():
    df = pd.DataFrame([
        _row(Alternative_Plant="No provenance plant", RD_Discovery_Lane=DISCOVERY_LANE_INSUFFICIENT),
    ])
    full_df, compact_df = piv.build_investor_opportunity_view(df)
    assert len(full_df) == 1
    assert full_df.loc[0, "Has_Defensible_Admission"] == False  # noqa: E712
    assert compact_df.empty


def test_compact_view_ranked_by_discovery_potential_not_overall_score():
    df = pd.DataFrame([
        _row(Alternative_Plant="High discovery low overall", Direct_Indication_Evidence_Count=1,
             Discovery_Potential_Score=95.0, Overall_Score=20.0),
        _row(Alternative_Plant="Low discovery high overall", Direct_Indication_Evidence_Count=1,
             Discovery_Potential_Score=15.0, Overall_Score=95.0),
    ])
    _, compact_df = piv.build_investor_opportunity_view(df)
    assert compact_df.iloc[0]["Candidate"] == "High discovery low overall"


def test_empty_and_non_dataframe_inputs_handled():
    full_df, compact_df = piv.build_investor_opportunity_view(pd.DataFrame())
    assert compact_df.empty
    full_df, compact_df = piv.build_investor_opportunity_view(None)
    assert compact_df.empty


def test_compact_view_contains_commercial_opportunity_class():
    """Mandatory required test (2026-09-09 follow-up, Feature 3): the
    compact Stage-6 investor view must contain Commercial_Opportunity_Class,
    not just derived fields like Commercial_Whitespace.
    """
    df = pd.DataFrame([
        _row(Direct_Indication_Evidence_Count=1, Commercial_Opportunity_Class=OPP_REPURPOSING_OPPORTUNITY),
    ])
    _, compact_df = piv.build_investor_opportunity_view(df)
    assert "Commercial_Opportunity_Class" in compact_df.columns
    assert compact_df.iloc[0]["Commercial_Opportunity_Class"] == OPP_REPURPOSING_OPPORTUNITY
