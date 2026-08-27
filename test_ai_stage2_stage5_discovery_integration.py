"""Stage 2 -> Stage 5 acceptance tests for the AI botanical-entity
discovery path (Tests C, D, F, L from the hybrid AI-R&D architecture).

No live network calls anywhere in this file: llm_extractor's
get_openai_client is never invoked because ai_botanical_entity_extractor
is monkeypatched directly at the llm_client boundary; Kew/GBIF are
monkeypatched exactly like the existing
test_open_world_candidate_discovery.py suite this file complements.
"""
import pandas as pd

import botanical_entity_validation as bev
import research_engine as re_mod
import ai_botanical_entity_extractor as ai_bev
from botanical_rd_candidate_engine import BotanicalRDCandidateEngine


# ---------------------------------------------------------------------
# Test C: common-name novel candidate. LLM proposes common name ->
# scientific name; taxonomy validates; candidate enters Stage 2's novel
# pool and, unchanged from the existing bridge, Stage 5.
# ---------------------------------------------------------------------

def test_c_llm_common_name_proposal_validated_and_reaches_stage5(monkeypatch):
    alias_catalog = {}  # genuinely absent from the internal catalogue
    records = [{
        "Title": "Tulsi reduces anxiety in a randomized trial",
        "Abstract": "Tulsi extract significantly reduced anxiety scores "
                    "compared to placebo in a randomized controlled trial.",
        "Source_Type": "PubMed",
        "Record_ID": "10",
    }]

    # The regex path finds nothing here -- "Tulsi" alone is not a binomial.
    # Only the AI path proposes a candidate.
    monkeypatch.setattr(
        ai_bev.llm_client, "call_structured_json",
        lambda **kw: {
            "entities": [{
                "original_mention": "Tulsi",
                "proposed_scientific_name": "Ocimum tenuiflorum",
                "common_name": "tulsi",
                "genus": "Ocimum",
                "species": "tenuiflorum",
                "is_botanical": True,
                "confidence": 0.92,
                "context_support": "Tulsi extract significantly reduced anxiety scores",
            }]
        },
    )
    monkeypatch.setattr(
        bev, "search_kew_plants",
        lambda name, limit=20: [{"Scientific_Name": "Ocimum tenuiflorum", "Source": "Kew POWO"}],
    )
    monkeypatch.setattr(bev, "search_gbif_plants", lambda name, limit=30: [])

    novel_ranked, novel_meta, novel_diag = re_mod._extract_open_world_botanical_candidates(
        records, alias_catalog, ["anxiety"]
    )

    assert novel_ranked == ["Ocimum tenuiflorum"]
    assert novel_diag["validated_external_candidates"] == 1
    assert novel_meta["Ocimum tenuiflorum"]["candidate_origin"] == "literature_discovered"
    assert novel_meta["Ocimum tenuiflorum"]["candidate_sources"] == ["llm_open_world"]

    # Same Stage 2 -> Stage 5 bridge as the existing regex path, unchanged.
    # Ocimum tenuiflorum is genuinely absent from GLOBAL_PLANT_CANDIDATES
    # (the engine's hardcoded fallback pool), so a merged_count of 1 here
    # is a real, meaningful signal that this novel candidate actually
    # entered Stage 5 -- not an artifact of a name that was already
    # present regardless of this discovery path.
    discovered_candidates = [{
        "Scientific_Name": "Ocimum tenuiflorum",
        "Common_Name": "", "Region": "",
        "Indications": ["anxiety"],
        "Known_Active_Compounds": [],  # never fabricated
        "Known_Targets": [],
        "Plant_Part": "", "Extraction_Method": "", "EMA_Status": "",
        "candidate_origin": "literature_discovered",
        "already_in_supabase": False,
        "botanical_validation_status": novel_meta["Ocimum tenuiflorum"]["botanical_validation_status"],
        "botanical_validation_score": novel_meta["Ocimum tenuiflorum"]["botanical_validation_score"],
        "taxonomic_source": novel_meta["Ocimum tenuiflorum"]["taxonomic_source"],
        "matched_scientific_name": "Ocimum tenuiflorum",
        "original_mention": "Tulsi",
        "candidate_sources": novel_meta["Ocimum tenuiflorum"]["candidate_sources"],
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
    assert row.iloc[0]["candidate_origin"] == "literature_discovered"
    assert bool(row.iloc[0]["already_in_supabase"]) is False


# ---------------------------------------------------------------------
# Test D: LLM hallucinates a non-plant. Taxonomic validation fails ->
# rejected, never enters Stage 2's novel pool or Stage 5.
# ---------------------------------------------------------------------

def test_d_llm_hallucinated_non_plant_is_rejected_by_taxonomy(monkeypatch):
    alias_catalog = {}
    records = [{
        "Title": "Ibuprofen reduces inflammation markers in a clinical trial",
        "Abstract": "Patients receiving ibuprofen showed reduced CRP levels.",
        "Source_Type": "PubMed",
        "Record_ID": "11",
    }]

    # The LLM incorrectly (is_botanical=True) proposes a drug as a plant --
    # simulating a hallucination the prompt-level safeguard failed to
    # catch. The enforced safeguard is taxonomic validation, not the
    # prompt.
    monkeypatch.setattr(
        ai_bev.llm_client, "call_structured_json",
        lambda **kw: {
            "entities": [{
                "original_mention": "Ibuprofen",
                "proposed_scientific_name": "Ibuprofen vulgaris",
                "common_name": "ibuprofen",
                "genus": "Ibuprofen",
                "species": "vulgaris",
                "is_botanical": True,
                "confidence": 0.99,
                "context_support": "Ibuprofen reduces inflammation markers",
            }]
        },
    )
    # No external taxonomic source confirms this fabricated binomial.
    monkeypatch.setattr(bev, "search_kew_plants", lambda name, limit=20: [])
    monkeypatch.setattr(bev, "search_gbif_plants", lambda name, limit=30: [])

    novel_ranked, novel_meta, novel_diag = re_mod._extract_open_world_botanical_candidates(
        records, alias_catalog, ["inflammation"]
    )

    # Nothing is ever accepted -- taxonomic validation is the enforced
    # safeguard. (The regex path may ALSO incidentally produce its own
    # format-plausible-but-unconfirmed candidate from ordinary
    # capitalized prose -- that is pre-existing regex behavior, not
    # something this AI path changes -- so this asserts on rejection,
    # not on an exact single-candidate count.)
    assert novel_ranked == []
    assert novel_diag["validated_external_candidates"] == 0
    assert novel_diag["rejected_or_unresolved_external_candidates"] >= 1

    engine = BotanicalRDCandidateEngine(
        plant_compounds_df=pd.DataFrame(), compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(), evidence_records_df=pd.DataFrame(),
        use_live_search=False, discovered_candidates=[],
    )
    names = [c["Scientific_Name"] for c in engine.candidate_data]
    assert "Ibuprofen vulgaris" not in names


# ---------------------------------------------------------------------
# Test F: same plant found by BOTH regex (binomial in the abstract) and
# LLM (a separate common-name mention) -> one canonical Stage 2
# candidate, with provenance showing both discovery sources.
# ---------------------------------------------------------------------

def test_f_duplicate_discovery_across_regex_and_llm_collapses_to_one_candidate(monkeypatch):
    alias_catalog = {}
    records = [{
        "Title": "Withania somnifera and ashwagandha in stress management",
        "Abstract": "Withania somnifera (ashwagandha) root extract lowered "
                    "cortisol in a randomized trial of stressed adults.",
        "Source_Type": "PubMed",
        "Record_ID": "12",
    }]

    # LLM proposes the common-name mention "ashwagandha" -> the same
    # accepted scientific name the regex path already finds directly in
    # the same text.
    monkeypatch.setattr(
        ai_bev.llm_client, "call_structured_json",
        lambda **kw: {
            "entities": [{
                "original_mention": "ashwagandha",
                "proposed_scientific_name": "Withania somnifera",
                "common_name": "ashwagandha",
                "genus": "Withania",
                "species": "somnifera",
                "is_botanical": True,
                "confidence": 0.9,
                "context_support": "ashwagandha root extract lowered cortisol",
            }]
        },
    )
    monkeypatch.setattr(
        bev, "search_kew_plants",
        lambda name, limit=20: [{"Scientific_Name": "Withania somnifera", "Source": "Kew POWO"}],
    )
    monkeypatch.setattr(bev, "search_gbif_plants", lambda name, limit=30: [])

    novel_ranked, novel_meta, novel_diag = re_mod._extract_open_world_botanical_candidates(
        records, alias_catalog, ["stress"]
    )

    # Exactly one canonical candidate -- not two.
    assert novel_ranked == ["Withania somnifera"]
    sources = novel_meta["Withania somnifera"]["candidate_sources"]
    assert "regex_open_world" in sources
    assert "llm_open_world" in sources
    assert len(sources) == 2

    # And the Stage 2 -> Stage 5 bridge still only produces one row.
    discovered_candidates = [{
        "Scientific_Name": "Withania somnifera",
        "Common_Name": "", "Region": "", "Indications": ["stress"],
        "Known_Active_Compounds": [], "Known_Targets": [],
        "Plant_Part": "", "Extraction_Method": "", "EMA_Status": "",
        "candidate_origin": "literature_discovered",
        "already_in_supabase": False,
        "botanical_validation_status": novel_meta["Withania somnifera"]["botanical_validation_status"],
        "botanical_validation_score": novel_meta["Withania somnifera"]["botanical_validation_score"],
        "taxonomic_source": novel_meta["Withania somnifera"]["taxonomic_source"],
        "matched_scientific_name": "Withania somnifera",
        "original_mention": "Withania somnifera",
        "candidate_sources": sources,
    }]
    engine = BotanicalRDCandidateEngine(
        plant_compounds_df=pd.DataFrame(), compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(), evidence_records_df=pd.DataFrame(),
        use_live_search=False, discovered_candidates=discovered_candidates,
    )
    frame = engine._candidate_frame()
    rows = frame[frame["Scientific_Name"] == "Withania somnifera"]
    assert len(rows) == 1


# ---------------------------------------------------------------------
# Test L: existing (pre-AI) regex-only open-world discovery must keep
# working exactly as before when the AI path is unavailable/off (a
# direct regression check on the architecture implemented previously).
# ---------------------------------------------------------------------

def test_l_existing_regex_only_open_world_discovery_still_works_when_ai_unavailable(monkeypatch):
    alias_catalog = {}
    records = [{
        "Title": "Ocimum tenuiflorum extract reduces stress biomarkers",
        "Abstract": "A randomized controlled trial of Ocimum tenuiflorum in "
                    "stress patients showed significant cortisol reduction.",
        "Source_Type": "PubMed",
        "Record_ID": "13",
    }]

    def _raise(**kwargs):
        raise RuntimeError("OPENAI_API_KEY is missing.")

    monkeypatch.setattr(ai_bev.llm_client, "call_structured_json", _raise)
    monkeypatch.setattr(
        bev, "search_kew_plants",
        lambda name, limit=20: [{"Scientific_Name": "Ocimum tenuiflorum", "Source": "Kew POWO"}],
    )
    monkeypatch.setattr(bev, "search_gbif_plants", lambda name, limit=30: [])

    novel_ranked, novel_meta, novel_diag = re_mod._extract_open_world_botanical_candidates(
        records, alias_catalog, ["stress"]
    )
    assert novel_ranked == ["Ocimum tenuiflorum"]
    assert novel_meta["Ocimum tenuiflorum"]["candidate_sources"] == ["regex_open_world"]
