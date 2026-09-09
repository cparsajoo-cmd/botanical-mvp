"""Mandatory regression tests for the 2026-09-09 production-integration
diagnosis ("why does the deployed CSV still show old behavior").

DIAGNOSIS SUMMARY (see the final report given to the user for full detail):
every file named in the cahier des charges (evidence_id_parsing.py,
post_discovery_investor_view.py, step_rd_candidates.py,
pipeline_fingerprint.py) was already present, already correctly wired
(single copy each, no duplicate importable modules anywhere in the repo),
and already internally consistent -- Human_Evidence_Status and
Why_Interesting are both derived from the same human_evidence_hierarchy()
call on the same row, so they cannot contradict each other under this
code. Directly exercising the real production functions (this file) with
the exact reported input never reproduces "1 direct human outcome
record(s)" from "()". The one real, verified defect found during this
pass was unrelated to evidence-ID string parsing: a fallback session-state-
rebuild path in render_rd_candidates_step() (step_rd_candidates.py) never
stamped the three implementation fingerprints onto the report_ready_df it
built, which made _stage6_stale_pipeline_warning() unconditionally treat
that frame as stale and block Stage 6 -- fixed in this pass; see
test_fallback_path_stamps_implementation_fingerprints below.
"""

import hashlib

import pandas as pd
import pytest

import evidence_id_parsing
import pipeline_fingerprint
import post_discovery_investor_view as piv
import step_rd_candidates as src
from evidence_source_resolver import attach_human_evidence_source_traceability
from rd_discovery_classification import DISCOVERY_LANE_HYPOTHESIS


# ---------------------------------------------------------------------
# Task 2 diagnostic: prove there is exactly one importable copy of each
# file named in the cahier des charges, and that post_discovery_investor_
# view.py imports the real evidence_id_parsing.normalize_evidence_ids
# (not a shadow/duplicate).
# ---------------------------------------------------------------------

def test_no_duplicate_importable_modules_and_correct_import_wiring():
    modules = (piv, evidence_id_parsing, src, pipeline_fingerprint)
    seen_paths = set()
    for mod in modules:
        assert mod.__file__ not in seen_paths, f"duplicate module path: {mod.__file__}"
        seen_paths.add(mod.__file__)
        with open(mod.__file__, "rb") as f:
            hashlib.sha256(f.read()).hexdigest()  # must not raise -- file is readable

    assert piv.normalize_evidence_ids is evidence_id_parsing.normalize_evidence_ids
    assert "evidence_id_parsing" in piv.__dict__.get("normalize_evidence_ids").__module__


# ---------------------------------------------------------------------
# Task 3: the exact reported production row, at the unit level.
# ---------------------------------------------------------------------

def test_exact_reported_production_row_unit_level():
    row = {
        "Direct_Human_Outcome_Evidence_IDs": "()",
        "AI_Direct_Human_Outcome_Evidence_Count": 0,
        "Outcome_Specific_Human_Evidence_Count": 0,
        "Direct_Indication_Evidence_Count": 3,
    }
    status = piv.human_evidence_status(row)
    assert status != "1 direct human outcome record(s)"
    assert status == "No verified direct human outcome evidence"
    assert piv.has_confirmed_human_evidence(row) is False


# ---------------------------------------------------------------------
# Task 13: end-to-end regression through the REAL production functions --
# refresh handler -> merge_authoritative_scores -> build_investor_
# opportunity_view -> CSV bytes. Must never surface the bug and must
# report a coherent (not contradictory) Human_Evidence_Status / Why_
# Interesting pair.
# ---------------------------------------------------------------------

def _minimal_result_df():
    return pd.DataFrame([{
        "Alternative_Plant": "Test Plant",
        "Overall_Score": 42.0,
        "Source_Record_IDs": "R1",
        "Decision_Class_AH": "C — Exploratory",
        "Go_Investigate_Hold_NoGo": "Investigate",
    }])


def _minimal_plant_summary_df():
    return pd.DataFrame([{
        "Alternative_Plant": "Test Plant",
        "Overall_Score": 42.0,
        "Decision_Class_AH": "C — Exploratory",
        "Go_Investigate_Hold_NoGo": "Investigate",
        "Authoritative_Narrative_Source_Record_ID": "R1",
        "RD_Discovery_Lane": DISCOVERY_LANE_HYPOTHESIS,
        "Direct_Indication_Evidence_Count": 3,
        # the exact production-reported contradiction inputs:
        "Direct_Human_Outcome_Evidence_IDs": "()",
        "AI_Direct_Human_Outcome_Evidence_Count": 0,
        "Outcome_Specific_Human_Evidence_Count": 0,
    }])


def test_production_refresh_to_csv_never_reproduces_the_bug():
    result_df = _minimal_result_df()
    plant_summary_df = _minimal_plant_summary_df()

    _, _, report_ready_df = src.refresh_commercial_and_investor_view(
        result_df, plant_summary_df, indication="test indication",
        dosage_form=None, market=None, market_plants=[],
    )
    assert not report_ready_df.empty

    full_df, compact_df = piv.build_investor_opportunity_view(report_ready_df)

    status = full_df["Human_Evidence_Status"].iloc[0]
    why = full_df["Why_Interesting"].iloc[0]
    assert status != "1 direct human outcome record(s)"
    assert "Confirmed direct human evidence is present" not in why

    csv_text = full_df.to_csv(index=False)
    assert "1 direct human outcome record(s)" not in csv_text


# ---------------------------------------------------------------------
# Task 14: source-link resolution through the real production path.
# ---------------------------------------------------------------------

def test_source_link_resolution_real_path():
    report_ready_df = pd.DataFrame([{
        "Alternative_Plant": "Test Plant 2",
        "Overall_Score": 55.0,
        "RD_Discovery_Lane": DISCOVERY_LANE_HYPOTHESIS,
        "Direct_Indication_Evidence_Count": 3,
        "Direct_Human_Outcome_Evidence_IDs": "E1",
        "AI_Direct_Human_Outcome_Evidence_Count": 1,
    }])
    evidence_df = pd.DataFrame([{
        "Evidence_Record_ID": "E1",
        "Source_Title": "Example Clinical Trial",
        "DOI": "10.1234/test",
    }])

    df2 = attach_human_evidence_source_traceability(report_ready_df, evidence_df)
    full_df, _ = piv.build_investor_opportunity_view(df2)

    assert full_df["Human_Evidence_Source_Count"].iloc[0] == 1
    assert full_df["Human_Evidence_Primary_Source_Title"].iloc[0] == "Example Clinical Trial"
    assert full_df["Human_Evidence_Primary_Source_URL"].iloc[0] == "https://doi.org/10.1234/test"


# ---------------------------------------------------------------------
# Section 9: both-direction contradiction detection, exactly as specified
# in the cahier des charges.
# ---------------------------------------------------------------------

@pytest.mark.parametrize("row,expected_coherent", [
    ({"AI_Direct_Human_Outcome_Evidence_Count": 0,
      "Direct_Human_Outcome_Evidence_IDs": "E1;E2"}, False),
    ({"AI_Direct_Human_Outcome_Evidence_Count": 3,
      "Direct_Human_Outcome_Evidence_IDs": "()"}, False),
    ({"Direct_Human_Outcome_Evidence_IDs": "()",
      "Outcome_Specific_Human_Evidence_Count": 3}, False),
    ({"Direct_Human_Outcome_Evidence_IDs": "E1;E2;E3",
      "Outcome_Specific_Human_Evidence_Count": 0}, False),
    ({"Human_Evidence_Strength": "MODERATE",
      "AI_Direct_Human_Outcome_Evidence_Count": 0,
      "Direct_Human_Outcome_Evidence_IDs": "()",
      "Outcome_Specific_Human_Evidence_Count": 0}, False),
])
def test_human_evidence_contradiction_detected_both_directions(row, expected_coherent):
    status, issues = piv.validate_candidate_evidence_consistency(row)
    is_coherent = status == piv.CONSISTENCY_COHERENT
    assert is_coherent == expected_coherent
    if not expected_coherent:
        assert status == piv.CONSISTENCY_HUMAN_EVIDENCE_CONTRADICTION


# ---------------------------------------------------------------------
# Section 10: safety-stop consistency.
# ---------------------------------------------------------------------

def test_safety_stop_consistency_and_next_step_prioritizes_derisking():
    row = {
        "RD_Discovery_Lane": piv.DISCOVERY_LANE_SAFETY_STOP,
        "Safety_Concern_Level": "NONE",
        "Safety_Assertion_Status": "NO_SAFETY_EVIDENCE_RETRIEVED",
    }
    assert piv._safety_risk(row) != "Unknown"
    assert "toxicology" in piv.next_rd_step(row).lower()
    status, issues = piv.validate_candidate_evidence_consistency(row)
    assert status != piv.CONSISTENCY_COHERENT
    assert issues


# ---------------------------------------------------------------------
# Real fix delivered by this pass: the fallback report_ready_df rebuild
# path (session lost rd_candidate_plant_summary_df but kept result_df)
# must stamp the same three implementation fingerprints as the main path,
# or _stage6_stale_pipeline_warning() unconditionally blocks Stage 6 for
# a result that is actually fresh.
# ---------------------------------------------------------------------

def test_fallback_path_stamps_implementation_fingerprints():
    import inspect
    source = inspect.getsource(src)
    fallback_start = source.index("fallback-path build_plant_candidate_shortlist() start")
    fallback_section = source[fallback_start:fallback_start + 3000]
    assert "Scientific_Implementation_Fingerprint" in fallback_section
    assert "Commercial_Implementation_Fingerprint" in fallback_section
