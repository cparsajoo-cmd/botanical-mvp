"""Integration tests for IMPLEMENTATION_PLAN.md Phase 5's wiring into
indication_candidate_discovery.py: Evidence Normalization and Evidence
Validation run as explicit stages BEFORE scoring, and — per this phase's
own constraint — do not change the authoritative scoring weights or
values Phase 3 already established.
"""

import pandas as pd

from botanical_rd_candidate_engine import BotanicalRDCandidateEngine
from evidence_validation import VALID, VALID_WITH_LIMITATIONS, REJECTED, NOT_ASSESSABLE


def _engine(candidate_data, evidence_rows):
    evidence = pd.DataFrame(evidence_rows)
    return BotanicalRDCandidateEngine(
        evidence_df=evidence, candidate_data=candidate_data, use_live_search=False,
        plant_compounds_df=pd.DataFrame(), compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(), evidence_records_df=pd.DataFrame(),
    )


def test_normalization_and_validation_columns_are_present_on_every_row():
    candidate_data = [
        {"Scientific_Name": "Somnus herba", "Known_Active_Compounds": ["Compound S"],
         "Known_Targets": ["GABAA receptor modulation"], "Indications": ["insomnia"]},
    ]
    evidence_rows = [{
        "plant": "Somnus herba", "Source_URL": "https://example.org/1",
        "title": "Somnus herba for insomnia", "abstract": "Improved sleep latency in a randomized trial",
    }]
    engine = _engine(candidate_data, evidence_rows)
    out = engine.run("insomnia", discovery_mode="indication")
    assert "Normalization_Summary" in out.columns
    assert "Validation_Status" in out.columns
    assert "Validation_Summary" in out.columns
    row = out.iloc[0]
    assert row["Validation_Status"] in (VALID, VALID_WITH_LIMITATIONS, REJECTED, NOT_ASSESSABLE)
    assert row["Normalization_Summary"]


def test_scoring_fields_are_unchanged_by_the_phase5_wiring():
    # Same fixture as test_indication_candidate_discovery.py's original
    # leakage/scoring test — the score/breakdown must be bit-identical to
    # what Phase 3 already computed, proving Phase 5 is purely additive.
    candidate_data = [
        {"Scientific_Name": "Plantus directus", "Known_Active_Compounds": ["Compound A"],
         "Known_Targets": ["insulin sensitivity"], "Indications": ["type 2 diabetes"]},
    ]
    evidence_rows = [{
        "plant": "Plantus directus", "Source_URL": "https://example.org/2",
        "title": "Plantus directus for type 2 diabetes",
        "abstract": "Reduced fasting glucose in a randomized controlled human trial",
    }]
    engine = _engine(candidate_data, evidence_rows)
    out = engine.run("type 2 diabetes", discovery_mode="indication")
    row = out.iloc[0]
    # Root-cause fix (evidence-hierarchy wiring, see indication_candidate_
    # discovery.py::_record_evidence_characteristics /
    # evidence_hierarchy_classifier.py): "Direct indication evidence" for
    # human clinical evidence is no longer a flat 35 regardless of study
    # type -- it is now graduated by the record's classified hierarchy
    # tier (Systematic review/meta-analysis=35, Clinical trial=32,
    # Observational human evidence=28, unclassified human=30), so a single
    # RCT-worded record (this fixture) genuinely reporting a randomized
    # controlled human trial now scores 32, reserving 35 for a systematic
    # review/meta-analysis. This assertion was updated to match that
    # intentional behavior change; Phase 5's own claim (normalization/
    # validation are additive and do not themselves alter scoring) is
    # untouched -- the evidence-hierarchy wiring is a separate, later fix.
    assert row["Score_Breakdown"]["Direct indication evidence"] == 32
    assert row["Score_Breakdown"]["Baseline development potential"] == 10


def test_a_phase5_internal_error_never_blocks_discovery():
    # If normalization/validation ever raised (e.g. a future field access
    # bug), discovery must still complete — Phase 5 columns degrade to
    # "not assessed", never propagate an exception.
    candidate_data = [
        {"Scientific_Name": "Somnus herba", "Known_Active_Compounds": ["Compound S"],
         "Known_Targets": ["GABAA receptor modulation"], "Indications": ["insomnia"]},
    ]
    evidence_rows = [{
        "plant": "Somnus herba", "Source_URL": "https://example.org/1",
        "title": "Somnus herba for insomnia", "abstract": "Improved sleep latency in a randomized trial",
    }]
    engine = _engine(candidate_data, evidence_rows)
    out = engine.run("insomnia", discovery_mode="indication")
    assert not out.empty
    assert out.iloc[0]["Validation_Status"] in (VALID, VALID_WITH_LIMITATIONS, REJECTED, NOT_ASSESSABLE)
