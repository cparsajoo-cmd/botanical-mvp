import pandas as pd

from botanical_taxonomy import taxon_match_key
from botanical_rd_candidate_engine import BotanicalRDCandidateEngine


def test_taxon_match_key_strips_nomenclatural_authors_but_preserves_infraspecific_rank():
    assert taxon_match_key("Ginkgo biloba L.") == "ginkgo biloba"
    assert taxon_match_key("Matricaria chamomilla L.") == "matricaria chamomilla"
    assert taxon_match_key("Echinacea purpurea (L.) Moench") == "echinacea purpurea"
    assert taxon_match_key("Plantus example var. minor Author") == "plantus example var minor"


def test_taxon_match_key_resolves_known_synonym_before_matching():
    assert taxon_match_key("Cimicifuga racemosa") == "actaea racemosa"
    assert taxon_match_key("Actaea racemosa L.") == "actaea racemosa"


def test_evidence_index_attaches_author_suffix_record_to_plain_binomial_candidate():
    evidence = pd.DataFrame([{
        "Evidence_Record_ID": "r1",
        "Scientific_Name": "Ginkgo biloba L.",
        "Notes": "Concomitant dabigatran use requires caution.",
        "Source_URL": "https://example.test/r1",
        "Source_Type": "EMA",
    }])
    engine = BotanicalRDCandidateEngine(
        evidence_df=evidence,
        candidate_data=pd.DataFrame(),
        use_live_search=False,
        plant_compounds_df=pd.DataFrame(),
        compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(),
        evidence_records_df=pd.DataFrame(),
    )

    indexes = engine._build_evidence_text_index()
    text, urls, _authority, records = engine._collect_raw_evidence(
        indexes[0], "Ginkgo biloba", "unknown-compound", "unrelated-problem",
        source_index=indexes[1], authority_index=indexes[3], records_index=indexes[4],
    )

    assert "dabigatran" in text.lower()
    assert urls == ["https://example.test/r1"]
    assert [r["evidence_record_id"] for r in records] == ["r1"]
