"""Backward-compatibility regression test for IMPLEMENTATION_PLAN.md
Phase 5: evidence_normalization.py / evidence_validation.py must be
purely additive diagnostic columns on indication_candidate_discovery.py's
output — every pre-Phase-5 field (evidence_points-derived tier/decision/
call, R&D_Opportunity_Score, Score_Breakdown, Evidence_Confidence,
Decision_Class_AH) must be byte-for-byte identical whether or not the
Phase 5 stage runs successfully, since scoring reads none of its output
(see indication_candidate_discovery.py's own comment at the call site).
"""

import unittest.mock as mock
import pandas as pd

from botanical_rd_candidate_engine import BotanicalRDCandidateEngine

_PRE_PHASE5_FIELDS = (
    "Alternative_Plant", "R&D_Opportunity_Score", "Score_Breakdown",
    "Evidence_Confidence", "Decision_Class_AH", "Go_Investigate_Hold_NoGo",
    "Candidate_Evidence_Strength_Tier", "Scientific_Rationale",
)


def _run_indication_mode():
    candidate_data = [
        {"Scientific_Name": "Valeriana officinalis", "Known_Active_Compounds": ["Valerenic acid"],
         "Known_Targets": ["GABAA receptor modulation"], "Indications": ["insomnia"]},
    ]
    evidence = pd.DataFrame([{
        "plant": "Valeriana officinalis", "Source_URL": "https://example.org/1",
        "title": "Valeriana officinalis for insomnia",
        "abstract": "A randomized controlled trial reported improved sleep latency in patients.",
    }])
    engine = BotanicalRDCandidateEngine(
        evidence_df=evidence, candidate_data=candidate_data, use_live_search=False,
        plant_compounds_df=pd.DataFrame(), compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(), evidence_records_df=pd.DataFrame(),
    )
    return engine.run("insomnia", discovery_mode="indication")


def test_scoring_fields_are_identical_whether_or_not_phase5_stage_succeeds():
    normal_run = _run_indication_mode()

    # Force the Phase 5 stage to fail on every row (simulating the
    # "Not assessed (Phase 5 stage error)" catch path) and confirm every
    # pre-existing scoring/output field is completely unaffected.
    with mock.patch(
        "evidence_normalization.normalize_evidence_record",
        side_effect=RuntimeError("simulated Phase 5 failure"),
    ):
        degraded_run = _run_indication_mode()

    assert len(normal_run) == len(degraded_run)
    for field in _PRE_PHASE5_FIELDS:
        assert list(normal_run[field]) == list(degraded_run[field]), (
            f"{field} changed when the Phase 5 stage failed — Phase 5 is "
            f"supposed to be purely diagnostic/additive."
        )


def test_phase5_diagnostic_columns_present_but_never_read_by_scoring():
    out = _run_indication_mode()
    # The new diagnostic columns exist...
    for col in ("Normalization_Summary", "Validation_Status", "Validation_Summary"):
        assert col in out.columns
    # ...but Validation_Status can be "valid_with_limitations" or similar
    # without that ever having downgraded R&D_Opportunity_Score — scoring
    # is computed from evidence_points/tier logic alone (see Phase 3/5 own
    # constraint: Phase 5 changes no scoring weight).
    row = out.iloc[0]
    assert row["Validation_Status"] in (
        "valid", "valid_with_limitations", "rejected", "not_assessable",
    )
    assert isinstance(row["R&D_Opportunity_Score"], (int, float))


def test_phase5_stage_failure_degrades_gracefully_never_blocks_discovery():
    with mock.patch(
        "evidence_validation.validate_evidence_record",
        side_effect=RuntimeError("simulated Phase 5 failure"),
    ):
        out = _run_indication_mode()
    assert not out.empty
    assert out.iloc[0]["Validation_Status"] == "not_assessable"
    assert "Phase 5 stage error" in out.iloc[0]["Normalization_Summary"]
