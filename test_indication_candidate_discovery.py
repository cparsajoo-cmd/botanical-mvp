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


def test_indication_mode_covers_a_second_curated_family_sleep():
    candidate_data = [
        {"Scientific_Name": "Somnus herba", "Known_Active_Compounds": ["Compound S"],
         "Known_Targets": ["GABAA receptor modulation"], "Indications": ["insomnia"]},
        {"Scientific_Name": "Plantus unrelated", "Known_Active_Compounds": ["Compound U"],
         "Known_Targets": ["digestive"], "Indications": ["digestion"]},
    ]
    evidence = pd.DataFrame([{
        "plant": "Somnus herba", "Source_URL": "https://example.org/2",
        "title": "Somnus herba for insomnia", "abstract": "Improved sleep latency in a randomized trial",
    }])
    engine = BotanicalRDCandidateEngine(
        evidence_df=evidence, candidate_data=candidate_data, use_live_search=False,
        plant_compounds_df=pd.DataFrame(), compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(), evidence_records_df=pd.DataFrame(),
    )
    out = engine.run("insomnia", discovery_mode="indication")
    assert "Somnus herba" in set(out["Alternative_Plant"])
    assert "Plantus unrelated" not in set(out["Alternative_Plant"])


def test_indication_mode_falls_back_gracefully_for_an_uncurated_indication():
    # "joint comfort" matches no DISEASE_FAMILIES trigger, so this exercises
    # the generic token-matching fallback rather than a curated term set.
    candidate_data = [
        {"Scientific_Name": "Articulus planta", "Known_Active_Compounds": ["Compound J"],
         "Known_Targets": ["cox-2 inhibition"], "Indications": ["joint comfort"]},
        {"Scientific_Name": "Plantus unrelated", "Known_Active_Compounds": ["Compound U"],
         "Known_Targets": ["digestive"], "Indications": ["digestion"]},
    ]
    evidence = pd.DataFrame([{
        "plant": "Articulus planta", "Source_URL": "https://example.org/3",
        "title": "Articulus planta and joint comfort", "abstract": "Supports joint comfort in an animal model",
    }])
    engine = BotanicalRDCandidateEngine(
        evidence_df=evidence, candidate_data=candidate_data, use_live_search=False,
        plant_compounds_df=pd.DataFrame(), compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(), evidence_records_df=pd.DataFrame(),
    )
    out = engine.run("joint comfort", discovery_mode="indication")
    assert "Articulus planta" in set(out["Alternative_Plant"])
    assert "Plantus unrelated" not in set(out["Alternative_Plant"])
