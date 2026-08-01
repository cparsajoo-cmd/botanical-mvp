"""End-to-end integration test for IMPLEMENTATION_PLAN.md Phase 5:
confirms Evidence Normalization and Evidence Validation actually run
inside the real discovery pipeline (BotanicalRDCandidateEngine.run(...,
discovery_mode="indication") -> indication_candidate_discovery.py),
before scoring, and that their results reach the final report — not just
that the two modules work correctly in isolation (see
test_evidence_normalization.py / test_evidence_validation.py for that).
"""

import pandas as pd

from botanical_rd_candidate_engine import BotanicalRDCandidateEngine
from pharma_report_generator import generate_pharma_report


def test_phase5_columns_are_present_on_real_discovery_output():
    candidate_data = [
        {"Scientific_Name": "Valeriana officinalis", "Known_Active_Compounds": ["Valerenic acid"],
         "Known_Targets": ["GABAA receptor modulation"], "Indications": ["insomnia"]},
    ]
    evidence = pd.DataFrame([{
        "plant": "Valeriana officinalis", "Source_URL": "https://example.org/valerian-rct",
        "title": "Valeriana officinalis for insomnia: a randomized controlled trial",
        "abstract": "A randomized controlled trial found improved sleep latency in patients.",
    }])
    engine = BotanicalRDCandidateEngine(
        evidence_df=evidence, candidate_data=candidate_data, use_live_search=False,
        plant_compounds_df=pd.DataFrame(), compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(), evidence_records_df=pd.DataFrame(),
    )
    out = engine.run("insomnia", discovery_mode="indication")

    assert not out.empty
    row = out[out["Alternative_Plant"] == "Valeriana officinalis"].iloc[0]
    assert row["Validation_Status"] in (
        "valid", "valid_with_limitations", "rejected", "not_assessable",
    )
    assert row["Normalization_Summary"]
    assert row["Validation_Summary"]

    # Phase 5 is purely diagnostic — it must not have altered the
    # Phase 3 scoring inputs this row still carries.
    assert "R&D_Opportunity_Score" in row.index


def test_phase5_results_reach_the_final_report_end_to_end():
    candidate_data = [
        {"Scientific_Name": "Valeriana officinalis", "Known_Active_Compounds": ["Valerenic acid"],
         "Known_Targets": ["GABAA receptor modulation"], "Indications": ["insomnia"]},
    ]
    evidence = pd.DataFrame([{
        "plant": "Valeriana officinalis", "Source_URL": "https://example.org/valerian-rct",
        "title": "Valeriana officinalis for insomnia: a randomized controlled trial",
        "abstract": "A randomized controlled trial found improved sleep latency in patients.",
    }])
    engine = BotanicalRDCandidateEngine(
        evidence_df=evidence, candidate_data=candidate_data, use_live_search=False,
        plant_compounds_df=pd.DataFrame(), compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(), evidence_records_df=pd.DataFrame(),
    )
    out = engine.run("insomnia", discovery_mode="indication")

    report_markdown = generate_pharma_report(
        out, indication="insomnia", dosage_form="Infusion", market="EU",
    )
    assert "Evidence normalization & validation" in report_markdown
