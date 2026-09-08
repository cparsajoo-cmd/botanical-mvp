import pandas as pd

from botanical_rd_candidate_engine import BotanicalRDCandidateEngine


def test_supabase_candidate_preserves_row_level_compound_target_links():
    plant_compounds_df = pd.DataFrame([
        {
            "scientific_name": "Linkia testii",
            "compound_name": "Relevantol",
            "target": "GABA-A receptor",
            "mechanism": "GABAergic modulation",
            "plant_part": "leaf",
            "source": "Dr. Duke",
            "reference_url": "https://example.org/relevant",
        },
        {
            "scientific_name": "Linkia testii",
            "compound_name": "RareButUnrelated",
            "target": "NF-kB",
            "mechanism": "anti-inflammatory",
            "plant_part": "root",
            "source": "Dr. Duke",
            "reference_url": "https://example.org/unrelated",
        },
    ])
    engine = BotanicalRDCandidateEngine(
        evidence_df=pd.DataFrame(),
        plant_compounds_df=plant_compounds_df,
        compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(),
        evidence_records_df=pd.DataFrame(),
        use_live_search=False,
    )

    candidate = next(
        row for row in engine.candidate_data
        if row["Scientific_Name"] == "Linkia testii"
    )
    links = candidate["Mechanistic_Links"]
    assert len(links) == 2
    assert {
        (link["compound_name"], link["target"], link["mechanism"])
        for link in links
    } == {
        ("Relevantol", "GABA-A receptor", "GABAergic modulation"),
        ("RareButUnrelated", "NF-kB", "anti-inflammatory"),
    }
    assert {
        link["compound_name"]: link["reference_url"] for link in links
    }["Relevantol"] == "https://example.org/relevant"
