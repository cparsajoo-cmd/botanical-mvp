import pandas as pd

from commercial_opportunity_classification import (
    classify_commercial_opportunity,
    add_commercial_opportunity_class,
    OPP_SAFETY_DE_RISKING_REQUIRED,
    OPP_REGULATORY_CONSTRAINED,
    OPP_INSUFFICIENT_MARKET_DATA,
    OPP_CROWDED_MARKET,
    OPP_COMMERCIALLY_ESTABLISHED,
    OPP_ESTABLISHED_BOTANICAL_NEW_INDICATION,
    OPP_EMERGING_BOTANICAL_NEW_INDICATION,
    OPP_REPURPOSING_OPPORTUNITY,
    OPP_WHITE_SPACE_OPPORTUNITY,
    ESTABLISHED_OVERALL_PRODUCT_THRESHOLD,
)
from rd_discovery_classification import (
    DISCOVERY_LANE_REGULATORY_STOP,
    DISCOVERY_LANE_SAFETY_STOP,
)


def _row(**overrides):
    base = {
        "RD_Discovery_Lane": None,
        "Safety_Concern_Level": "NONE",
        "Safety_Assertion_Status": "NO_SAFETY_EVIDENCE_RETRIEVED",
        "Regulatory_Prohibition_Present": False,
        "Commercial_Status_Overall": "UNKNOWN",
        "Commercial_Status_For_Indication": "UNKNOWN",
        "Indication_Market_Saturation": "UNKNOWN",
        "Overall_Product_Hits": None,
        "Discovery_Potential_Score": 0.0,
        "Evidence_Maturity_Score": 0.0,
        "Scientific_Triage_Status": "Excluded",
    }
    base.update(overrides)
    return base


# --- Priority 1: safety -----------------------------------------------

def test_serious_safety_concern_overrides_everything_else():
    row = _row(
        Safety_Concern_Level="SERIOUS",
        Commercial_Status_For_Indication="VERIFIED_MARKETED_FOR_INDICATION",
        Indication_Market_Saturation="HIGH",
    )
    assert classify_commercial_opportunity(row) == OPP_SAFETY_DE_RISKING_REQUIRED


def test_conflicting_safety_status_triggers_de_risking():
    row = _row(Safety_Assertion_Status="CONFLICTING_SAFETY_EVIDENCE")
    assert classify_commercial_opportunity(row) == OPP_SAFETY_DE_RISKING_REQUIRED


def test_discovery_lane_safety_stop_triggers_de_risking():
    row = _row(RD_Discovery_Lane=DISCOVERY_LANE_SAFETY_STOP)
    assert classify_commercial_opportunity(row) == OPP_SAFETY_DE_RISKING_REQUIRED


# --- Priority 2: regulatory ---------------------------------------------

def test_regulatory_prohibition_flag_triggers_constrained():
    row = _row(Regulatory_Prohibition_Present=True)
    assert classify_commercial_opportunity(row) == OPP_REGULATORY_CONSTRAINED


def test_discovery_lane_regulatory_stop_triggers_constrained():
    row = _row(RD_Discovery_Lane=DISCOVERY_LANE_REGULATORY_STOP)
    assert classify_commercial_opportunity(row) == OPP_REGULATORY_CONSTRAINED


def test_safety_takes_priority_over_regulatory_when_both_present():
    row = _row(Safety_Concern_Level="SERIOUS", Regulatory_Prohibition_Present=True)
    assert classify_commercial_opportunity(row) == OPP_SAFETY_DE_RISKING_REQUIRED


# --- Priority 3: insufficient data --------------------------------------

def test_no_search_on_either_axis_is_insufficient_data():
    row = _row(
        Commercial_Status_Overall="UNKNOWN",
        Commercial_Status_For_Indication="NOT_REQUESTED",
    )
    assert classify_commercial_opportunity(row) == OPP_INSUFFICIENT_MARKET_DATA


def test_unclear_indication_presence_with_no_overall_read_is_insufficient_data():
    row = _row(
        Commercial_Status_Overall="UNKNOWN",
        Commercial_Status_For_Indication="COMMERCIAL_PRESENCE_INDICATION_UNCLEAR",
    )
    assert classify_commercial_opportunity(row) == OPP_INSUFFICIENT_MARKET_DATA


def test_zero_products_after_completed_search_is_not_insufficient_data():
    """The core distinction the spec insists on (Section 7): a completed
    search with zero results is NOT the same as no search -- it must reach
    a real classification (white space here), not INSUFFICIENT_MARKET_DATA.
    """
    row = _row(
        Commercial_Status_Overall="NO_VERIFIED_PRODUCT_FOUND_IN_COVERED_SOURCES",
        Commercial_Status_For_Indication="NO_VERIFIED_PRODUCT_FOR_INDICATION_IN_COVERED_SOURCES",
        Discovery_Potential_Score=40.0,
    )
    assert classify_commercial_opportunity(row) == OPP_WHITE_SPACE_OPPORTUNITY


# --- Priority 4/5: verified for this exact indication --------------------

def test_verified_for_indication_high_saturation_is_crowded_market():
    row = _row(
        Commercial_Status_For_Indication="VERIFIED_MARKETED_FOR_INDICATION",
        Indication_Market_Saturation="HIGH",
    )
    assert classify_commercial_opportunity(row) == OPP_CROWDED_MARKET


def test_verified_for_indication_low_saturation_is_commercially_established():
    row = _row(
        Commercial_Status_For_Indication="VERIFIED_MARKETED_FOR_INDICATION",
        Indication_Market_Saturation="LOW",
    )
    assert classify_commercial_opportunity(row) == OPP_COMMERCIALLY_ESTABLISHED


# --- Priority 6: repurposing family --------------------------------------

def test_marketed_overall_but_not_for_indication_with_high_hits_is_established_new_indication():
    row = _row(
        Commercial_Status_Overall="VERIFIED_MARKETED",
        Commercial_Status_For_Indication="NO_VERIFIED_PRODUCT_FOR_INDICATION_IN_COVERED_SOURCES",
        Overall_Product_Hits=ESTABLISHED_OVERALL_PRODUCT_THRESHOLD,
    )
    assert classify_commercial_opportunity(row) == OPP_ESTABLISHED_BOTANICAL_NEW_INDICATION


def test_marketed_overall_but_not_for_indication_with_low_hits_is_emerging_new_indication():
    row = _row(
        Commercial_Status_Overall="VERIFIED_MARKETED",
        Commercial_Status_For_Indication="NO_VERIFIED_PRODUCT_FOR_INDICATION_IN_COVERED_SOURCES",
        Overall_Product_Hits=2,
    )
    assert classify_commercial_opportunity(row) == OPP_EMERGING_BOTANICAL_NEW_INDICATION


def test_marketed_overall_but_not_for_indication_with_unusable_count_is_generic_repurposing():
    row = _row(
        Commercial_Status_Overall="VERIFIED_MARKETED",
        Commercial_Status_For_Indication="NO_VERIFIED_PRODUCT_FOR_INDICATION_IN_COVERED_SOURCES",
        Overall_Product_Hits=None,
    )
    assert classify_commercial_opportunity(row) == OPP_REPURPOSING_OPPORTUNITY


# --- Priority 7: white space ----------------------------------------------

def test_nothing_verified_anywhere_with_real_science_is_white_space_opportunity():
    row = _row(
        Commercial_Status_Overall="NO_VERIFIED_PRODUCT_FOUND_IN_COVERED_SOURCES",
        Commercial_Status_For_Indication="NO_VERIFIED_PRODUCT_FOR_INDICATION_IN_COVERED_SOURCES",
        Evidence_Maturity_Score=15.0,
    )
    assert classify_commercial_opportunity(row) == OPP_WHITE_SPACE_OPPORTUNITY


def test_nothing_verified_anywhere_with_no_scientific_signal_is_not_classified():
    """Weak/absent science + no market presence is a scientific problem, not
    a commercial one -- this module must not paper over that by handing out
    WHITE_SPACE_OPPORTUNITY regardless of scientific merit.
    """
    row = _row(
        Commercial_Status_Overall="NO_VERIFIED_PRODUCT_FOUND_IN_COVERED_SOURCES",
        Commercial_Status_For_Indication="NO_VERIFIED_PRODUCT_FOR_INDICATION_IN_COVERED_SOURCES",
        Discovery_Potential_Score=0.0,
        Evidence_Maturity_Score=0.0,
        Scientific_Triage_Status="Excluded",
    )
    assert classify_commercial_opportunity(row) is None


def test_scientific_triage_status_shortlist_counts_as_real_signal_fallback():
    """Backward compatibility: rows built without Discovery_Potential_Score/
    Evidence_Maturity_Score (older callers) still get a real-signal read
    from Scientific_Triage_Status.
    """
    row = _row(
        Commercial_Status_Overall="NO_VERIFIED_PRODUCT_FOUND_IN_COVERED_SOURCES",
        Commercial_Status_For_Indication="NO_VERIFIED_PRODUCT_FOR_INDICATION_IN_COVERED_SOURCES",
        Discovery_Potential_Score=None,
        Evidence_Maturity_Score=None,
        Scientific_Triage_Status="Shortlist",
    )
    assert classify_commercial_opportunity(row) == OPP_WHITE_SPACE_OPPORTUNITY


# --- add_commercial_opportunity_class() vectorized wrapper ---------------

def test_add_commercial_opportunity_class_is_additive_and_never_mutates_input():
    df = pd.DataFrame([_row(Commercial_Status_For_Indication="VERIFIED_MARKETED_FOR_INDICATION",
                              Indication_Market_Saturation="HIGH")])
    original_columns = list(df.columns)
    out = add_commercial_opportunity_class(df)
    assert list(df.columns) == original_columns  # input untouched
    assert "Commercial_Opportunity_Class" in out.columns
    assert out.loc[0, "Commercial_Opportunity_Class"] == OPP_CROWDED_MARKET


def test_add_commercial_opportunity_class_handles_empty_and_non_dataframe_inputs():
    assert add_commercial_opportunity_class(pd.DataFrame()).empty
    assert add_commercial_opportunity_class(None) is None
