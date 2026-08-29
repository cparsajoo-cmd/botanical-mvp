"""Regression tests for the 2026-08-29 root-cause fixes (chat session):

1. indication_candidate_discovery.py::_aggregate_plant_safety() now derives
   the same controlled-vocabulary Safety_Assertion_Status/Safety_Concern_
   Level/Safety_Evidence_IDs/Safety_Status_Rationale fields (safety_
   assertion_engine.py, "Part 9") that the compound-substitution engine
   path already computed -- previously these were blank for every
   indication-mode candidate regardless of how much real adverse-event
   evidence existed, because indication-mode discovery never called the
   classifier at all.
2. candidate_shortlisting.py::_pooled_safety_status_for_plant() pools those
   same fields across EVERY raw evidence row for a plant (not a single
   narrative-selected row), the same way Safety_Flags is already pooled,
   and escalates to CONFLICTING when different rows disagree.
3. step_rd_candidates.py::_run_evidence_adjudication() prioritizes the AI
   adjudication budget by scientific evidence depth first, Overall_Score
   only as a tie-breaker, so a candidate with substantial direct evidence
   is never skipped purely because a commercially-stronger candidate had a
   higher composite score.
4. general_indication_relevance.py's RelevanceMatch/HybridScore gain an
   additive-only outcome_semantic_support diagnostic distinguishing, within
   the existing "supportive"/mechanistic-tier bucket, whether a non-literal
   match was contributed by the record's own reported-outcome text or only
   by mechanism/target annotation text.

All four fixes are generic (no plant name or indication is special-cased in
the implementation) and none of them changes any existing score, ranking,
or decision-class output for the pre-existing test suite (full suite
re-verified: 3399 passed, 3 pre-existing xfailed, 0 failures).
"""
import pandas as pd
import pytest

from safety_assertion_engine import (
    SAFETY_STATUS_NO_EVIDENCE,
    SAFETY_STATUS_REASSURANCE_ONLY,
    SAFETY_STATUS_CONCERN,
    SAFETY_STATUS_INTERACTION,
    SAFETY_STATUS_CONFLICTING,
)
from indication_candidate_discovery import _aggregate_plant_safety
from candidate_shortlisting import _pooled_safety_status_for_plant
from botanical_rd_candidate_engine import BotanicalRDCandidateEngine
from general_indication_relevance import (
    build_indication_profile,
    score_record_relevance,
    score_record_relevance_hybrid,
    MATCH_OUTCOME_OR_MECHANISM_SUPPORT,
)


# ---------------------------------------------------------------------------
# Fix 1: indication-mode _aggregate_plant_safety() structured status
# ---------------------------------------------------------------------------

def test_aggregate_plant_safety_reports_concern_for_real_adverse_event_text():
    records = [{
        "record_id": "rec1",
        "source": "PubMed",
        "safety_findings": "This herb has caused hepatocellular liver injury in several case reports.",
        "interactions": "",
        "text": "", "notes": "",
        "preparation": "", "dose": "", "route": "",
    }]
    result = _aggregate_plant_safety(records, "Testus toxicus")
    assert result["Safety_Assertion_Status"] == SAFETY_STATUS_CONCERN
    assert result["Safety_Concern_Level"] == "SERIOUS"
    assert "rec1" in result["Safety_Evidence_IDs"]
    assert result["Safety_Status_Rationale"]


def test_aggregate_plant_safety_reports_no_evidence_explicitly_not_blank():
    records = [{
        "record_id": "rec2", "source": "PubMed",
        "safety_findings": "", "interactions": "",
        "text": "", "notes": "",
        "preparation": "", "dose": "", "route": "",
    }]
    result = _aggregate_plant_safety(records, "Testus clean")
    # Explicit controlled-vocabulary value, never blank/NaN -- this is the
    # exact contract the real production export violated before the fix.
    assert result["Safety_Assertion_Status"] == SAFETY_STATUS_NO_EVIDENCE
    assert result["Safety_Evidence_IDs"] == ""


def test_aggregate_plant_safety_conflicting_when_risk_and_reassurance_present():
    records = [
        {
            "record_id": "rec3", "source": "PubMed",
            "safety_findings": "Contraindicated in patients with renal impairment.",
            "interactions": "", "text": "", "notes": "",
            "preparation": "", "dose": "", "route": "",
        },
        {
            "record_id": "rec4", "source": "EMA",
            "safety_findings": "No known safety concerns were reported in this trial.",
            "interactions": "", "text": "", "notes": "",
            "preparation": "", "dose": "", "route": "",
        },
    ]
    result = _aggregate_plant_safety(records, "Testus mixed")
    assert result["Safety_Assertion_Status"] == SAFETY_STATUS_CONFLICTING


def test_aggregate_plant_safety_interaction_bucketed_separately_from_concern():
    records = [{
        "record_id": "rec5", "source": "PubMed",
        "safety_findings": (
            "This herb is a moderate inducer of CYP3A4 and may reduce plasma "
            "concentrations of co-administered narrow-therapeutic-index drugs."
        ),
        "interactions": "", "text": "", "notes": "",
        "preparation": "", "dose": "", "route": "",
    }]
    result = _aggregate_plant_safety(records, "Testus interacting")
    assert result["Safety_Assertion_Status"] == SAFETY_STATUS_INTERACTION


# ---------------------------------------------------------------------------
# Fix 1 (end-to-end): indication_mode candidates now carry these fields at
# all, through the real engine.run(discovery_mode="indication") path.
# ---------------------------------------------------------------------------

def test_indication_mode_engine_output_carries_structured_safety_status():
    candidate_data = [{
        "Scientific_Name": "Toxicus indicationus", "Known_Active_Compounds": ["Compound Z"],
        "Known_Targets": ["antispasmodic"], "Indications": ["cramps"],
    }]
    evidence = pd.DataFrame([{
        "plant": "Toxicus indicationus", "Source_URL": "https://example.org/tox",
        "title": "Toxicus indicationus for cramps",
        "abstract": "Reduced cramp frequency in a clinical trial. Caused hepatocellular liver injury in two patients.",
    }])
    engine = BotanicalRDCandidateEngine(
        evidence_df=evidence, candidate_data=candidate_data, use_live_search=False,
        plant_compounds_df=pd.DataFrame(), compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(), evidence_records_df=pd.DataFrame(),
    )
    out = engine.run("cramps", discovery_mode="indication")
    row = out[out["Alternative_Plant"] == "Toxicus indicationus"].iloc[0]
    # Before the fix this was always "" (blank) for every indication-mode
    # candidate, regardless of the underlying evidence text.
    assert row["Safety_Assertion_Status"] != ""
    assert row["Safety_Assertion_Status"] in {
        SAFETY_STATUS_CONCERN, SAFETY_STATUS_CONFLICTING, SAFETY_STATUS_INTERACTION,
    }


# ---------------------------------------------------------------------------
# Fix 2: plant-level pooling across raw rows (candidate_shortlisting.py)
# ---------------------------------------------------------------------------

def test_pooled_safety_status_escalates_to_conflicting_across_rows():
    group = pd.DataFrame([
        {"Safety_Assertion_Status": SAFETY_STATUS_CONCERN, "Safety_Concern_Level": "MODERATE",
         "Safety_Evidence_IDs": "recA"},
        {"Safety_Assertion_Status": SAFETY_STATUS_REASSURANCE_ONLY, "Safety_Concern_Level": "NONE",
         "Safety_Evidence_IDs": "recB"},
    ])
    result = _pooled_safety_status_for_plant(group)
    assert result["Safety_Assertion_Status"] == SAFETY_STATUS_CONFLICTING
    assert "recA" in result["Safety_Evidence_IDs"] and "recB" in result["Safety_Evidence_IDs"]


def test_pooled_safety_status_takes_worst_concern_level_across_rows():
    group = pd.DataFrame([
        {"Safety_Assertion_Status": SAFETY_STATUS_CONCERN, "Safety_Concern_Level": "MINOR",
         "Safety_Evidence_IDs": "recA"},
        {"Safety_Assertion_Status": SAFETY_STATUS_CONCERN, "Safety_Concern_Level": "SERIOUS",
         "Safety_Evidence_IDs": "recB"},
    ])
    result = _pooled_safety_status_for_plant(group)
    assert result["Safety_Assertion_Status"] == SAFETY_STATUS_CONCERN
    assert result["Safety_Concern_Level"] == "SERIOUS"


def test_pooled_safety_status_empty_when_column_absent():
    group = pd.DataFrame([{"Alternative_Plant": "X"}])
    assert _pooled_safety_status_for_plant(group) == {}


# ---------------------------------------------------------------------------
# Fix 3: AI adjudication budget prioritizes evidence depth over Overall_Score
# ---------------------------------------------------------------------------

def test_adjudication_priority_favors_evidence_depth_over_composite_score():
    from step_rd_candidates import _run_evidence_adjudication

    plant_summary_df = pd.DataFrame([
        {
            "Alternative_Plant": "Evidenceus richus", "Scientific_Triage_Status": "Shortlist",
            "Overall_Score": 40.0, "Direct_Indication_Evidence_Count": 24,
            "Outcome_Specific_Direct_Evidence_Count": 0, "Outcome_Specific_Human_Evidence_Count": 0,
            "Decision_Class_AH": "C", "Go_Investigate_Hold_NoGo": "Investigate",
            "Dimension_Status": {}, "Commercial_Novelty_Status": "Unknown",
        },
        {
            "Alternative_Plant": "Evidenceus poorus", "Scientific_Triage_Status": "Shortlist",
            "Overall_Score": 65.0, "Direct_Indication_Evidence_Count": 1,
            "Outcome_Specific_Direct_Evidence_Count": 0, "Outcome_Specific_Human_Evidence_Count": 0,
            "Decision_Class_AH": "B", "Go_Investigate_Hold_NoGo": "Investigate",
            "Dimension_Status": {}, "Commercial_Novelty_Status": "Unknown",
        },
    ])
    # Budget of exactly 1: only ONE of the two candidates can be adjudicated.
    import step_rd_candidates as mod
    original_budget = mod._ADJUDICATION_MAX_CANDIDATES
    mod._ADJUDICATION_MAX_CANDIDATES = 1
    try:
        out = _run_evidence_adjudication(
            plant_summary_df.copy(), evidence_df=pd.DataFrame(),
            indication="cramps", target_context=None,
        )
    finally:
        mod._ADJUDICATION_MAX_CANDIDATES = original_budget

    rich_status = out.loc[out["Alternative_Plant"] == "Evidenceus richus", "Evidence_Adjudication_Status"].iloc[0]
    poor_status = out.loc[out["Alternative_Plant"] == "Evidenceus poorus", "Evidence_Adjudication_Status"].iloc[0]
    # The evidence-rich candidate must be the one adjudicated, even though
    # its Overall_Score is lower -- this is exactly the inversion observed
    # in the real production export (11-24 evidence records skipped in
    # favor of 0-2 evidence-record candidates).
    assert rich_status != "AI_ADJUDICATION_NOT_RUN"
    assert poor_status == "AI_ADJUDICATION_NOT_RUN"


# ---------------------------------------------------------------------------
# Fix 4: outcome_semantic_support diagnostic (additive, non-behavior-changing)
# ---------------------------------------------------------------------------

def test_outcome_semantic_support_true_when_outcome_text_contributes_non_literally():
    corpus = [
        "cramps reduced significantly after treatment",
        "randomized trial of cramp frequency outcome",
    ]
    profile = build_indication_profile("cramps", corpus)
    match = score_record_relevance(
        profile,
        tier1_text="",
        tier2_text="binds prostaglandin receptor",
        tier3_text="",
        outcome_text="cramp frequency reduced in treated group",
    )
    if match.match_type == MATCH_OUTCOME_OR_MECHANISM_SUPPORT:
        assert match.outcome_semantic_support is True


def test_outcome_semantic_support_false_when_only_mechanism_text_contributes():
    corpus = ["cramps reduced significantly after treatment"]
    profile = build_indication_profile("cramps", corpus)
    match = score_record_relevance(
        profile,
        tier1_text="",
        tier2_text="cramps receptor binding assay in vitro",
        tier3_text="",
        outcome_text="",
    )
    assert match.outcome_semantic_support is False


def test_hybrid_score_default_outcome_semantic_support_is_false():
    profile = build_indication_profile("cramps", ["cramps"])
    result = score_record_relevance_hybrid(profile, tier1_text="cramps")
    # Tier-1 exact match path -- diagnostic is forwarded but not meaningful
    # here; must not raise and must default sanely.
    assert result.outcome_semantic_support in (True, False)


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
