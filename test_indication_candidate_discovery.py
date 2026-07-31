import pandas as pd
from botanical_rd_candidate_engine import BotanicalRDCandidateEngine


def test_indication_mode_does_not_require_shared_compound():
    candidate_data = [
        {"Scientific_Name": "Plantus directus", "Known_Active_Compounds": ["Unique X"],
         "Known_Targets": ["GLUT4 glucose uptake"], "Indications": ["type 2 diabetes"]},
        {"Scientific_Name": "Plantus unrelated", "Known_Active_Compounds": ["Unique Y"],
         "Known_Targets": ["sedative"], "Indications": ["sleep"]},
    ]
    evidence = pd.DataFrame([{
        "plant": "Plantus directus", "Source_URL": "https://example.org/1",
        "title": "Plantus directus in type 2 diabetes", "abstract": "Reduced fasting blood glucose in a clinical trial",
    }])
    engine = BotanicalRDCandidateEngine(
        evidence_df=evidence, candidate_data=candidate_data, use_live_search=False,
        plant_compounds_df=pd.DataFrame(), compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(), evidence_records_df=pd.DataFrame(),
    )
    out = engine.run("type 2 diabetes", discovery_mode="indication")
    assert "Plantus directus" in set(out["Alternative_Plant"])
    assert "Plantus unrelated" not in set(out["Alternative_Plant"])
    assert set(out["Reference_Compound"]) == {"Not used as candidate gate"}
