import pandas as pd
from botanical_rd_candidate_engine import BotanicalRDCandidateEngine


def _engine(df):
    return BotanicalRDCandidateEngine(
        use_live_search=False,
        plant_compounds_df=df,
        compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(),
    )


def test_multi_concept_query_does_not_match_one_generic_token_only():
    engine = _engine(pd.DataFrame())
    assert engine._indication_match_score("Metabolic & blood sugar support", "blood pressure support") == 0
    assert engine._indication_match_score("Metabolic & blood sugar support", "metabolic blood sugar") > 0


def test_inventory_is_relevance_ranked_not_alphabetical():
    df = pd.DataFrame([
        {"scientific_name": "Abies alba", "compound_name": "x", "indication": "unrelated fatigue marker", "target": "x"},
        {"scientific_name": "Panax ginseng", "compound_name": "ginsenoside", "indication": "Energy / fatigue", "target": "anti-fatigue"},
        {"scientific_name": "Rhodiola rosea", "compound_name": "salidroside", "indication": "Energy fatigue", "target": "HPA axis"},
    ])
    result = _engine(df).known_inventory_df("Energy / fatigue")
    assert list(result["Known_Plant"].unique())[:2] == ["Panax ginseng", "Rhodiola rosea"]
    assert "Abies alba" not in set(result["Known_Plant"])


def test_reference_plants_prioritize_match_strength_and_support():
    df = pd.DataFrame([
        {"scientific_name": "Alpha plant", "compound_name": "a", "indication": "Energy fatigue", "target": "HPA axis"},
        {"scientific_name": "Zeta plant", "compound_name": "z1", "indication": "Energy / fatigue", "target": "HPA axis"},
        {"scientific_name": "Zeta plant", "compound_name": "z2", "indication": "Energy / fatigue", "target": "AMPK"},
    ])
    refs = _engine(df)._reference_plants_from_supabase("Energy / fatigue", 10)
    assert refs.iloc[0]["Scientific_Name"] == "Zeta plant"
