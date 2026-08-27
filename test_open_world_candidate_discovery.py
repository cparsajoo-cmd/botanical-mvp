"""Required scenario tests for open-world botanical candidate discovery.

Covers the six acceptance scenarios from the architecture request:
  1. Existing catalogue plant found in literature -> one candidate, no dup.
  2. Valid novel candidate (absent from plant_compounds) -> survives Stage 2,
     enters Stage 5, is scorable despite missing compound data.
  3. False botanical entity -> rejected, never enters Stage 5.
  4. Synonym (literature synonym, Supabase accepted name) -> one canonical
     candidate, no duplicate.
  5. Supabase unavailable -> existing fallback still works; validated
     external discoveries may supplement it; no crash.
  6. External taxonomy validation unavailable -> known internal candidates
     unaffected; pipeline doesn't crash; unverified novel candidates are
     NOT silently promoted.

No live network calls are made anywhere in this file.
"""
import pandas as pd

import botanical_entity_validation as bev
import research_engine as re_mod
from botanical_rd_candidate_engine import BotanicalRDCandidateEngine


def _alias_catalog_for(scientific_name, common_name=""):
    aliases = {(scientific_name.lower(), "scientific")}
    if common_name:
        aliases.add((common_name.lower(), "common"))
    return {scientific_name: aliases}


# ---------------------------------------------------------------------
# 1. Existing catalogue plant
# ---------------------------------------------------------------------

def test_catalogue_plant_found_in_literature_is_not_duplicated_by_open_world_path():
    alias_catalog = _alias_catalog_for("Valeriana officinalis", "valerian")
    records = [{
        "Title": "Valeriana officinalis for sleep: a randomized controlled trial",
        "Abstract": "Patients with insomnia received valerian extract nightly.",
        "Source_Type": "PubMed",
        "Record_ID": "1",
    }]

    catalogue_ranked, _ = re_mod._extract_catalogued_plants(
        records, alias_catalog, ["sleep", "insomnia"]
    )
    assert catalogue_ranked == ["Valeriana officinalis"]

    # The open-world path must skip this mention entirely -- it is already
    # covered by the internal catalogue -- so no duplicate candidate for
    # the same plant is ever produced by the two paths together.
    novel_ranked, _, novel_diag = re_mod._extract_open_world_botanical_candidates(
        records, alias_catalog, ["sleep", "insomnia"]
    )
    assert novel_ranked == []
    assert novel_diag["potential_external_botanical_mentions"] == 0

    # Stage 5: internal catalogue candidate, no discovered_candidates ->
    # exactly one row for this plant, origin internal_catalogue.
    internal_df = pd.DataFrame([{
        "scientific_name": "Valeriana officinalis", "common_name": "valerian",
        "compound_name": "Valerenic acid", "target": "GABA-A receptor",
        "indication": "sleep", "plant_part": "root", "extraction_method": "ethanol",
    }])
    engine = BotanicalRDCandidateEngine(
        plant_compounds_df=internal_df, compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(), evidence_records_df=pd.DataFrame(),
        use_live_search=False,
    )
    frame = engine._candidate_frame()
    matches = frame[frame["Scientific_Name"] == "Valeriana officinalis"]
    assert len(matches) == 1
    assert matches.iloc[0]["candidate_origin"] == "internal_catalogue"
    assert bool(matches.iloc[0]["already_in_supabase"]) is True


# ---------------------------------------------------------------------
# 2. Valid novel candidate
# ---------------------------------------------------------------------

def test_valid_novel_candidate_survives_stage2_and_enters_stage5(monkeypatch):
    # Empty internal catalogue -- this plant is genuinely absent from
    # plant_compounds/plants.
    alias_catalog = {}
    records = [{
        "Title": "Ocimum tenuiflorum extract reduces stress biomarkers",
        "Abstract": "A randomized controlled trial of Ocimum tenuiflorum in "
                     "stress patients showed significant cortisol reduction.",
        "Source_Type": "PubMed",
        "Record_ID": "2",
    }]

    monkeypatch.setattr(
        bev, "search_kew_plants",
        lambda name, limit=20: [{"Scientific_Name": "Ocimum tenuiflorum", "Source": "Kew POWO"}],
    )
    monkeypatch.setattr(bev, "search_gbif_plants", lambda name, limit=30: [])

    novel_ranked, novel_meta, novel_diag = re_mod._extract_open_world_botanical_candidates(
        records, alias_catalog, ["stress"]
    )
    assert novel_ranked == ["Ocimum tenuiflorum"]
    assert novel_diag["validated_external_candidates"] == 1
    assert novel_meta["Ocimum tenuiflorum"]["candidate_origin"] == "literature_discovered"

    # Stage 5: engine built from an EMPTY internal catalogue (Supabase has
    # nothing for this plant) plus this one discovered candidate.
    discovered_candidates = [{
        "Scientific_Name": "Ocimum tenuiflorum",
        "Common_Name": "", "Region": "",
        "Indications": ["stress"],
        "Known_Active_Compounds": [],  # explicitly missing, never fabricated
        "Known_Targets": [],
        "Plant_Part": "", "Extraction_Method": "", "EMA_Status": "",
        "candidate_origin": "literature_discovered",
        "already_in_supabase": False,
        "botanical_validation_status": novel_meta["Ocimum tenuiflorum"]["botanical_validation_status"],
        "botanical_validation_score": novel_meta["Ocimum tenuiflorum"]["botanical_validation_score"],
        "taxonomic_source": novel_meta["Ocimum tenuiflorum"]["taxonomic_source"],
        "matched_scientific_name": "Ocimum tenuiflorum",
        "original_mention": "Ocimum tenuiflorum",
    }]
    engine = BotanicalRDCandidateEngine(
        plant_compounds_df=pd.DataFrame(), compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(), evidence_records_df=pd.DataFrame(),
        use_live_search=False, discovered_candidates=discovered_candidates,
    )
    assert engine.discovered_candidates_merged_count == 1
    frame = engine._candidate_frame()
    row = frame[frame["Scientific_Name"] == "Ocimum tenuiflorum"]
    assert len(row) == 1
    # Lack of internal compound data must not have been fabricated.
    assert row.iloc[0]["Known_Active_Compounds"] == ""
    assert row.iloc[0]["candidate_origin"] == "literature_discovered"
    assert bool(row.iloc[0]["already_in_supabase"]) is False


# ---------------------------------------------------------------------
# 3. False botanical entity
# ---------------------------------------------------------------------

def test_false_botanical_entity_is_rejected_and_never_enters_stage5(monkeypatch):
    alias_catalog = {}
    records = [{
        "Title": "Randomized Placebo trial of Interleukin signaling in sleep disorders",
        "Abstract": "This is a purely biomedical mechanistic discussion.",
        "Source_Type": "PubMed",
        "Record_ID": "3",
    }]

    # No external source confirms anything -- simulates a genuine
    # non-botanical phrase that happens to be capitalized.
    monkeypatch.setattr(bev, "search_kew_plants", lambda name, limit=20: [])
    monkeypatch.setattr(bev, "search_gbif_plants", lambda name, limit=30: [])

    novel_ranked, novel_meta, novel_diag = re_mod._extract_open_world_botanical_candidates(
        records, alias_catalog, ["sleep"]
    )
    assert novel_ranked == []
    assert novel_diag["validated_external_candidates"] == 0

    # Nothing to merge into Stage 5 -- candidate_data is unaffected.
    engine = BotanicalRDCandidateEngine(
        plant_compounds_df=pd.DataFrame(), compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(), evidence_records_df=pd.DataFrame(),
        use_live_search=False, discovered_candidates=[],
    )
    names = [c["Scientific_Name"] for c in engine.candidate_data]
    assert "Interleukin signaling" not in names
    assert "Randomized Placebo" not in names


# ---------------------------------------------------------------------
# 4. Synonym
# ---------------------------------------------------------------------

def test_literature_synonym_resolves_to_the_same_canonical_candidate_as_supabase():
    # Supabase holds the accepted name; literature uses the older synonym.
    internal_df = pd.DataFrame([{
        "scientific_name": "Actaea racemosa", "common_name": "black cohosh",
        "compound_name": "Triterpene glycoside", "target": "estrogen receptor",
        "indication": "menopause", "plant_part": "root", "extraction_method": "ethanol",
    }])

    discovered_candidates = [{
        "Scientific_Name": "Cimicifuga racemosa",  # known synonym
        "Common_Name": "", "Region": "",
        "Indications": ["menopause"],
        "Known_Active_Compounds": [], "Known_Targets": [],
        "Plant_Part": "", "Extraction_Method": "", "EMA_Status": "",
        "candidate_origin": "literature_discovered",
        "already_in_supabase": False,
        "botanical_validation_status": bev.STATUS_VALIDATED_CURATED_SYNONYM,
        "botanical_validation_score": 1.0,
        "taxonomic_source": "internal_curated_mapping",
        "matched_scientific_name": "Actaea racemosa",
        "original_mention": "Cimicifuga racemosa",
    }]

    engine = BotanicalRDCandidateEngine(
        plant_compounds_df=internal_df, compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(), evidence_records_df=pd.DataFrame(),
        use_live_search=False, discovered_candidates=discovered_candidates,
    )
    # The synonym must NOT have been appended as a second row.
    assert engine.discovered_candidates_merged_count == 0
    frame = engine._candidate_frame()
    matches = frame[frame["Scientific_Name"].isin(["Actaea racemosa", "Cimicifuga racemosa"])]
    assert len(matches) == 1
    assert matches.iloc[0]["Scientific_Name"] == "Actaea racemosa"


# ---------------------------------------------------------------------
# 5. Supabase unavailable
# ---------------------------------------------------------------------

def test_supabase_unavailable_fallback_still_works_and_can_be_supplemented():
    # Empty Supabase tables everywhere -> engine must fall back to the
    # local seed dataset, exactly as before this change, and must not crash.
    discovered_candidates = [{
        "Scientific_Name": "Ocimum tenuiflorum",
        "Common_Name": "", "Region": "",
        "Indications": ["stress"],
        "Known_Active_Compounds": [], "Known_Targets": [],
        "Plant_Part": "", "Extraction_Method": "", "EMA_Status": "",
        "candidate_origin": "literature_discovered",
        "already_in_supabase": False,
        "botanical_validation_status": bev.STATUS_VALIDATED_EXTERNAL_TAXONOMY,
        "botanical_validation_score": 0.75,
        "taxonomic_source": "GBIF",
        "matched_scientific_name": "Ocimum tenuiflorum",
        "original_mention": "Ocimum tenuiflorum",
    }]

    engine = BotanicalRDCandidateEngine(
        plant_compounds_df=pd.DataFrame(), compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(), evidence_records_df=pd.DataFrame(),
        use_live_search=False, discovered_candidates=discovered_candidates,
    )
    assert engine.candidate_source == "local_fallback"
    assert len(engine.candidate_data) > 0  # existing fallback still populated
    names = [c["Scientific_Name"] for c in engine.candidate_data]
    assert "Ocimum tenuiflorum" in names  # supplemented, not replaced
    assert engine.discovered_candidates_merged_count == 1


# ---------------------------------------------------------------------
# 6. External taxonomy validation unavailable
# ---------------------------------------------------------------------

def test_external_taxonomy_unavailable_known_candidates_unaffected_novel_not_promoted(monkeypatch):
    # Both external connectors degrade to [] (their own real failure mode).
    monkeypatch.setattr(bev, "search_kew_plants", lambda name, limit=20: [])
    monkeypatch.setattr(bev, "search_gbif_plants", lambda name, limit=30: [])

    alias_catalog = _alias_catalog_for("Valeriana officinalis", "valerian")
    records = [{
        "Title": "Valeriana officinalis and a novel plant Zzyzxia fictumus for sleep",
        "Abstract": "Valerian extract was compared to Zzyzxia fictumus in a sleep trial.",
        "Source_Type": "PubMed",
        "Record_ID": "6",
    }]

    # Known catalogue plant: entirely unaffected by external taxonomy
    # availability -- it never needs external validation.
    catalogue_ranked, _ = re_mod._extract_catalogued_plants(
        records, alias_catalog, ["sleep"]
    )
    assert catalogue_ranked == ["Valeriana officinalis"]

    # Novel candidate: no exception is raised, and it is NOT silently
    # promoted -- it must come back unresolved/rejected.
    novel_ranked, novel_meta, novel_diag = re_mod._extract_open_world_botanical_candidates(
        records, alias_catalog, ["sleep"]
    )
    assert novel_ranked == []
    assert novel_diag["rejected_or_unresolved_external_candidates"] >= 1

    # Full engine construction with an empty discovered_candidates list
    # (nothing survived validation) must not crash and must still surface
    # the internal candidate.
    internal_df = pd.DataFrame([{
        "scientific_name": "Valeriana officinalis", "common_name": "valerian",
        "compound_name": "Valerenic acid", "target": "GABA-A receptor",
        "indication": "sleep", "plant_part": "root", "extraction_method": "ethanol",
    }])
    engine = BotanicalRDCandidateEngine(
        plant_compounds_df=internal_df, compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(), evidence_records_df=pd.DataFrame(),
        use_live_search=False, discovered_candidates=[],
    )
    names = [c["Scientific_Name"] for c in engine.candidate_data]
    assert "Valeriana officinalis" in names
    assert "Zzyzxia fictumus" not in names
