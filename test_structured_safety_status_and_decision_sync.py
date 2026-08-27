"""Regression coverage for this session's Part 4 and Part 9 additions:

Part 9 -- a structured, candidate-level safety STATUS
(Safety_Assertion_Status / Safety_Concern_Level / Safety_Evidence_IDs /
Safety_Rationale), reusing the existing structured safety-assertion
architecture (safety_assertion_engine.py) rather than a new keyword scan
or an AI guess. "No adverse events reported in one study" must never
become "safe".

Part 4 -- Final_Decision_Status must never contradict a downgraded
Decision_Class_AH/Go_Investigate_Hold_NoGo after the adjudication cap
runs.
"""
import pandas as pd

import botanical_rd_candidate_engine as eng
import evidence_adjudication_engine as ea
from safety_assertion_engine import (
    AssertionPolarity,
    SafetyAssertion,
    SafetyAssertionType,
    SafetyConfidence,
    derive_structured_safety_status,
)
from assertion_vocabulary import SeverityLevel
from test_botanical_rd_candidate_engine import make_engine


def _assertion(assertion_type, severity, polarity, evidence_record_id="ev1"):
    return SafetyAssertion(
        assertion_type=assertion_type,
        severity=severity,
        polarity=polarity,
        evidence_strength=SafetyConfidence.MODERATE,
        evidence_record_id=evidence_record_id,
    )


# ---------------------------------------------------------------------
# Part 9 -- unit coverage of derive_structured_safety_status() itself
# ---------------------------------------------------------------------
def test_no_assertions_is_no_safety_evidence_retrieved_not_safe():
    result = derive_structured_safety_status([])
    assert result["Safety_Assertion_Status"] == "NO_SAFETY_EVIDENCE_RETRIEVED"
    assert result["Safety_Concern_Level"] == "UNKNOWN"
    assert result["Safety_Assertion_Status"] != "SAFE"
    assert "no safety-relevant evidence" in result["Safety_Rationale"].lower()


def test_reassurance_only_never_becomes_general_safety_claim():
    assertions = [_assertion(
        SafetyAssertionType.REASSURANCE, SeverityLevel.NONE, AssertionPolarity.RISK_ABSENT,
    )]
    result = derive_structured_safety_status(assertions)
    assert result["Safety_Assertion_Status"] == "STUDY_SPECIFIC_REASSURANCE_ONLY"
    assert "does not establish" in result["Safety_Rationale"].lower()


def test_risk_present_contraindication_is_safety_concern():
    assertions = [_assertion(
        SafetyAssertionType.CONTRAINDICATION, SeverityLevel.SERIOUS, AssertionPolarity.RISK_PRESENT,
    )]
    result = derive_structured_safety_status(assertions)
    assert result["Safety_Assertion_Status"] == "SAFETY_CONCERN_RETRIEVED"
    assert result["Safety_Concern_Level"] == "SERIOUS"
    assert result["Safety_Evidence_IDs"] == ("ev1",)


def test_interaction_type_is_its_own_bucket_not_generic_concern():
    assertions = [_assertion(
        SafetyAssertionType.SERIOUS_DRUG_INTERACTION, SeverityLevel.SERIOUS, AssertionPolarity.RISK_PRESENT,
    )]
    result = derive_structured_safety_status(assertions)
    assert result["Safety_Assertion_Status"] == "INTERACTION_SIGNAL_RETRIEVED"


def test_risk_and_reassurance_together_is_conflicting_not_averaged():
    assertions = [
        _assertion(SafetyAssertionType.ORGAN_TOXICITY, SeverityLevel.MODERATE, AssertionPolarity.RISK_PRESENT, "ev1"),
        _assertion(SafetyAssertionType.REASSURANCE, SeverityLevel.NONE, AssertionPolarity.RISK_ABSENT, "ev2"),
    ]
    result = derive_structured_safety_status(assertions)
    assert result["Safety_Assertion_Status"] == "CONFLICTING_SAFETY_EVIDENCE"
    assert set(result["Safety_Evidence_IDs"]) == {"ev1", "ev2"}


# ---------------------------------------------------------------------
# Part 9 -- end-to-end: fields reach the live engine's row output
# ---------------------------------------------------------------------
def _engine_row(evidence_rows, *, alt="AltPlantSafetyStatus"):
    eng.SIMILAR_COMPOUND_GROUPS = {}
    eng.COMPOUND_TARGETS = {}
    rows = [
        dict(scientific_name="RefPlantSafetyStatus", compound_name="SharedCompoundSS", indication="TestIndicationSS",
             target="Laxative", common_name="", plant_part="", extraction_method=""),
        dict(scientific_name=alt, compound_name="SharedCompoundSS", indication="TestIndicationSS",
             target="Laxative", common_name="", plant_part="", extraction_method=""),
    ]
    engine = make_engine(rows)
    engine.evidence_df = pd.DataFrame(evidence_rows)
    result = engine.run(indication="TestIndicationSS", dosage_form="Infusion", market="EU")
    return result[
        (result["Reference_Plant"] == "RefPlantSafetyStatus") & (result["Alternative_Plant"] == alt)
    ].iloc[0]


def test_engine_row_exposes_structured_safety_status_fields():
    row = _engine_row([{
        "Scientific_Name": "AltPlantSafetyStatus",
        "Target_Indication": "TestIndicationSS",
        "Notes": "Use is contraindicated during pregnancy.",
        "Evidence_Record_ID": "ev-status-1",
        "Source_Organization": "European Medicines Agency",
        "Source_Type": "HMPC monograph",
        "Source_URL": "https://example.invalid/regulator-record",
    }])
    assert row["Safety_Assertion_Status"] == "SAFETY_CONCERN_RETRIEVED"
    assert row["Safety_Concern_Level"] == "SERIOUS"
    assert "ev-status-1" in str(row["Safety_Evidence_IDs"])
    assert row["Safety_Status_Rationale"]


def test_engine_row_with_no_safety_evidence_is_explicit_not_zero_or_blank():
    row = _engine_row([{
        "Scientific_Name": "AltPlantSafetyStatus",
        "Target_Indication": "TestIndicationSS",
        "Notes": "A pharmacokinetic profiling study was conducted.",
        "Evidence_Record_ID": "ev-status-2",
        "Source_Organization": "Independent Lab",
        "Source_Type": "Journal article",
        "Source_URL": "https://example.invalid/pk-study",
    }])
    assert row["Safety_Assertion_Status"] == "NO_SAFETY_EVIDENCE_RETRIEVED"
    assert row["Safety_Concern_Level"] == "UNKNOWN"


# ---------------------------------------------------------------------
# Part 4 -- Final_Decision_Status synchronization
# ---------------------------------------------------------------------
def test_sync_downgrades_final_status_when_cap_applies_hold():
    new_status = ea.sync_final_decision_status("GO", "G — Hold / insufficient evidence")
    assert new_status == "INSUFFICIENT EVIDENCE"


def test_sync_never_weakens_an_existing_stronger_no_go():
    # An existing NO_GO_REGULATORY (a real regulatory hard-stop) must never
    # be weakened to INSUFFICIENT_EVIDENCE just because the efficacy cap
    # (Decision_Class_AH="G") also fired for this row.
    new_status = ea.sync_final_decision_status("NO GO REGULATORY", "G — Hold / insufficient evidence")
    assert new_status == "NO GO REGULATORY"


def test_sync_is_a_no_op_when_decision_class_was_not_capped():
    # Decision_Class_AH values this module's cap never produces (e.g. the
    # normal "B — Established..." class) must not perturb an existing
    # Final_Decision_Status.
    new_status = ea.sync_final_decision_status("GO", "B — Established scientific candidate")
    assert new_status == "GO"


def test_merge_and_sync_helper_fixes_a_contradictory_input_state():
    import step_rd_candidates as src

    raw_df = pd.DataFrame([{
        "Alternative_Plant": "Plant A", "R&D_Opportunity_Score": 10,
        "Final_Decision_Status": "GO",
    }])
    plant_summary = pd.DataFrame([{
        "Alternative_Plant": "Plant A", "Overall_Score": 40.0,
        # Simulates the exact contradiction Part 4 describes: the
        # adjudication cap already downgraded these two...
        "Decision_Class_AH": "G — Hold / insufficient evidence",
        "Go_Investigate_Hold_NoGo": "Hold",
    }])
    merged = src._merge_and_sync_final_decision_status(raw_df, plant_summary)
    # ...and Final_Decision_Status ("GO", inherited unchanged from the raw
    # row) must now be synchronized to match, not left contradicting them.
    assert merged.loc[0, "Decision_Class_AH"] == "G — Hold / insufficient evidence"
    assert merged.loc[0, "Go_Investigate_Hold_NoGo"] == "Hold"
    assert merged.loc[0, "Final_Decision_Status"] == "INSUFFICIENT EVIDENCE"


# ---------------------------------------------------------------------
# Part 10 -- deterministic final rationale
# ---------------------------------------------------------------------
def test_final_rationale_reflects_structured_facts_not_generic_text():
    row = {
        "Evidence_Adjudication_Rationale": "Moderate human evidence mostly supports the requested indication.",
        "Preparation_Compatibility": "MISMATCH",
        "Route_Compatibility": "DIRECT",
        "Plant_Part_Compatibility": "DIRECT",
        "Safety_Status_Rationale": "A safety concern (e.g. contraindication, adverse event, organ toxicity) was retrieved from the evidence.",
        "Commercial_Status_For_Indication": "NOVEL",
        "Final_Decision_Status": "GO WITH CAUTION",
        "Decision_Class_AH": "C — Alternative-source R&D candidate",
    }
    rationale = ea.build_final_rationale(row)
    assert "moderate human evidence" in rationale.lower()
    assert "preparation" in rationale.lower() and "does not match" in rationale.lower()
    assert "safety concern" in rationale.lower()
    assert "novel" in rationale.lower()
    assert "go with caution" in rationale.lower()


def test_final_rationale_never_fabricates_missing_fields():
    rationale = ea.build_final_rationale({})
    assert rationale == "Insufficient structured evidence was available to generate a detailed rationale."


def test_merge_and_sync_helper_adds_final_rationale_column():
    import step_rd_candidates as src

    raw_df = pd.DataFrame([{"Alternative_Plant": "Plant A", "R&D_Opportunity_Score": 10}])
    plant_summary = pd.DataFrame([{
        "Alternative_Plant": "Plant A", "Overall_Score": 40.0,
        "Decision_Class_AH": "G — Hold / insufficient evidence",
        "Go_Investigate_Hold_NoGo": "Hold",
        "Preparation_Compatibility": "MISMATCH",
    }])
    merged = src._merge_and_sync_final_decision_status(raw_df, plant_summary)
    assert "Final_Rationale" in merged.columns
    assert "does not match" in merged.loc[0, "Final_Rationale"].lower()
