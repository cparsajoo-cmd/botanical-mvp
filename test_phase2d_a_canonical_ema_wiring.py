"""Phase 2D-A regression suite — wiring the canonical EMA/HMPC connector
result into BotanicalRDCandidateEngine's main Candidate Discovery path
via a per-run cached plant-level lookup.

All fixtures are synthetic; no live EMA network access. Monkeypatches
_eu_regulatory_status() directly (the existing canonical Path B
interface) rather than the underlying connector, since this phase's
scope is strictly the wiring between the engine and that existing
interface — not the connector itself.
"""

import pandas as pd
import pytest

import botanical_rd_candidate_engine as eng
from botanical_rd_candidate_engine import BotanicalRDCandidateEngine


def make_engine(rows, similar_groups=None, compound_targets=None):
    if similar_groups is not None:
        eng.SIMILAR_COMPOUND_GROUPS = similar_groups
    if compound_targets is not None:
        eng.COMPOUND_TARGETS = compound_targets

    background = [
        dict(scientific_name=f"Bg{i}", compound_name=f"BgCompound{i}",
             indication="background", target="Antioxidant",
             common_name="", plant_part="", extraction_method="")
        for i in range(25)
    ]
    df = pd.DataFrame(list(rows) + background)
    return BotanicalRDCandidateEngine(
        plant_compounds_df=df,
        compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(),
        evidence_df=pd.DataFrame(),
        use_live_search=False,
    )


CANONICAL_RESULT_TEMPLATES = {
    "exact_species_match": {
        "EMA_HMPC_Status": "Listed in HMPC inventory",
        "EMA_HMPC_Detail": "Listed in HMPC inventory as 'Genusia radix' — see source PDF for monograph status",
        "EMA_Source": "EMA HMPC — Inventory of herbal substances for assessment",
        "EMA_HMPC_Match_Category": "exact_species_match",
    },
    "verified_synonym_match": {
        "EMA_HMPC_Status": "Listed in HMPC inventory",
        "EMA_HMPC_Detail": "Listed in HMPC inventory as 'Genusia radix' — see source PDF for monograph status",
        "EMA_Source": "EMA HMPC — Inventory of herbal substances for assessment",
        "EMA_HMPC_Match_Category": "verified_synonym_match",
    },
    "verified_pharmacopoeial_name_match": {
        "EMA_HMPC_Status": "Listed in HMPC inventory",
        "EMA_HMPC_Detail": "Listed in HMPC inventory as 'Tradenamia radix' — see source PDF for monograph status",
        "EMA_Source": "EMA HMPC — Inventory of herbal substances for assessment",
        "EMA_HMPC_Match_Category": "verified_pharmacopoeial_name_match",
    },
    "genus_only_match": {
        "EMA_HMPC_Status": "Not found in HMPC inventory",
        "EMA_HMPC_Detail": "Genus listed in HMPC inventory, but species-level match not found — see source PDF",
        "EMA_Source": "EMA HMPC — Inventory of herbal substances for assessment",
        "EMA_HMPC_Match_Category": "genus_only_match",
    },
    "related_species_only": {
        "EMA_HMPC_Status": "Not found in HMPC inventory",
        "EMA_HMPC_Detail": "Different species of the same genus found in HMPC inventory; not found",
        "EMA_Source": "EMA HMPC — Inventory of herbal substances for assessment",
        "EMA_HMPC_Match_Category": "related_species_only",
    },
    "ambiguous_match": {
        "EMA_HMPC_Status": "Not found in HMPC inventory",
        "EMA_HMPC_Detail": "Ambiguous match in HMPC inventory text — not found with confidence",
        "EMA_Source": "EMA HMPC — Inventory of herbal substances for assessment",
        "EMA_HMPC_Match_Category": "ambiguous_match",
    },
    "searched_not_found": {
        "EMA_HMPC_Status": "Not found in HMPC inventory",
        "EMA_HMPC_Detail": "Not in HMPC inventory (as of 2021 snapshot)",
        "EMA_Source": "EMA HMPC — Inventory of herbal substances for assessment",
        "EMA_HMPC_Match_Category": "searched_not_found",
    },
    "parsing_failed": {
        "EMA_HMPC_Status": "Not verified",
        "EMA_HMPC_Detail": "Not yet verified",
        "EMA_Source": "EMA HMPC (PDF parsing failed)",
        "EMA_HMPC_Match_Category": "parsing_failed",
    },
    "source_unavailable": {
        "EMA_HMPC_Status": "Not verified",
        "EMA_HMPC_Detail": "Not yet verified",
        "EMA_Source": "EMA HMPC (live fetch failed)",
        "EMA_HMPC_Match_Category": "source_unavailable",
    },
}


def _make_alt_row(scientific_name="Genusia speciosa"):
    return pd.Series({"Scientific_Name": scientific_name, "EMA_Status": ""})


# ---------------------------------------------------------------------
# 1. Safe attribute / __new__() compatibility.
# ---------------------------------------------------------------------

def test_canonical_cache_initialized_empty_in_init():
    engine = make_engine([])
    assert engine._canonical_regulatory_by_plant == {}


def test_new_constructed_engine_does_not_crash_in_market_status():
    engine = BotanicalRDCandidateEngine.__new__(BotanicalRDCandidateEngine)
    engine.use_live_search = False
    result = engine._market_status(alt=_make_alt_row(), evidence="", market="EU")
    assert result in ("Search not performed", "Search incomplete")


# ---------------------------------------------------------------------
# 2. Match-category -> Market_Status mapping.
# ---------------------------------------------------------------------

@pytest.mark.parametrize(
    "category",
    ["exact_species_match", "verified_synonym_match", "verified_pharmacopoeial_name_match"],
)
def test_confident_match_categories_reach_inventory_listed_status(category):
    engine = make_engine([])
    engine.use_live_search = False
    engine._canonical_regulatory_by_plant = {
        "Genusia speciosa": CANONICAL_RESULT_TEMPLATES[category]
    }
    result = engine._market_status(alt=_make_alt_row(), evidence="", market="EU")
    assert result == "Listed in EMA HMPC inventory — monograph not established"


@pytest.mark.parametrize(
    "category",
    [
        "genus_only_match", "related_species_only", "ambiguous_match", "searched_not_found",
    ],
)
def test_non_confident_categories_never_reach_listed_status(category):
    engine = make_engine([])
    engine.use_live_search = False
    engine._canonical_regulatory_by_plant = {
        "Genusia speciosa": CANONICAL_RESULT_TEMPLATES[category]
    }
    result = engine._market_status(alt=_make_alt_row(), evidence="", market="EU")
    assert result not in (
        "Listed in EMA HMPC inventory — monograph not established",
        "Regulatory monograph exists",
        "Traditional-use status",
    )
    assert result in ("Search not performed", "Search incomplete")


@pytest.mark.parametrize("category", ["parsing_failed", "source_unavailable"])
def test_connector_failure_categories_are_distinct_from_searched_not_found(category):
    engine = make_engine([])
    engine.use_live_search = False
    engine._canonical_regulatory_by_plant = {
        "Genusia speciosa": CANONICAL_RESULT_TEMPLATES[category]
    }
    result = engine._market_status(alt=_make_alt_row(), evidence="", market="EU")
    assert result == "Source unavailable"
    assert result not in ("Search not performed", "Search incomplete")


def test_monograph_status_requires_independent_compact_status_confirmation():
    engine = make_engine([])
    engine.use_live_search = False
    template = dict(CANONICAL_RESULT_TEMPLATES["exact_species_match"])
    template["EMA_HMPC_Status"] = "HMPC monograph available"
    engine._canonical_regulatory_by_plant = {"Genusia speciosa": template}
    result = engine._market_status(alt=_make_alt_row(), evidence="", market="EU")
    assert result == "Regulatory monograph exists"


def test_traditional_use_status_requires_independent_compact_status_confirmation():
    engine = make_engine([])
    engine.use_live_search = False
    template = dict(CANONICAL_RESULT_TEMPLATES["exact_species_match"])
    template["EMA_HMPC_Status"] = "Traditional-use status"
    engine._canonical_regulatory_by_plant = {"Genusia speciosa": template}
    result = engine._market_status(alt=_make_alt_row(), evidence="", market="EU")
    assert result == "Traditional-use status"


def test_no_canonical_entry_for_plant_falls_back_to_pre_existing_behavior():
    engine = make_engine([])
    engine.use_live_search = False
    engine._canonical_regulatory_by_plant = {}  # nothing cached for this plant
    result = engine._market_status(alt=_make_alt_row(), evidence="", market="EU")
    assert result == "Search not performed"


# ---------------------------------------------------------------------
# 3. Public signature unchanged.
# ---------------------------------------------------------------------

def test_market_status_signature_unchanged():
    import inspect
    sig = inspect.signature(BotanicalRDCandidateEngine._market_status)
    assert list(sig.parameters) == ["self", "alt", "evidence", "market"]


# ---------------------------------------------------------------------
# 4. traditional_use_patterns branch byte-for-byte unchanged.
# ---------------------------------------------------------------------

def test_traditional_use_text_branch_unchanged_with_no_canonical_data():
    engine = make_engine([])
    engine.use_live_search = False
    engine._canonical_regulatory_by_plant = {}
    result = engine._market_status(
        alt=_make_alt_row(), evidence="This has a long history of traditional use.", market="EU"
    )
    assert result == "Traditional-use status"


def test_traditional_use_text_branch_unchanged_when_canonical_says_not_found():
    # Even with a real canonical "searched_not_found" entry present,
    # the untouched text-scan branch below must still fire exactly as
    # before this phase (Phase 2D-A explicitly does not touch it).
    engine = make_engine([])
    engine.use_live_search = False
    engine._canonical_regulatory_by_plant = {
        "Genusia speciosa": CANONICAL_RESULT_TEMPLATES["searched_not_found"]
    }
    result = engine._market_status(
        alt=_make_alt_row(), evidence="Well-established use in traditional medicine.", market="EU"
    )
    assert result == "Traditional-use status"


# ---------------------------------------------------------------------
# 5. run()-level: one lookup per unique plant, cache rebuilt every run().
# ---------------------------------------------------------------------

def test_run_builds_one_canonical_lookup_per_unique_plant(monkeypatch):
    rows = [
        dict(scientific_name="Referencia herbosa", compound_name="Sharedcompoundia",
             indication="Test indication", target="Testtarget",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="Alternativia speciosa", compound_name="Sharedcompoundia",
             indication="", target="Testtarget",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="Alternativia speciosa", compound_name="Sharedcompoundia2",
             indication="", target="Testtarget",
             common_name="", plant_part="", extraction_method=""),
    ]
    engine = make_engine(rows)
    engine.use_live_search = False

    call_log = []

    def fake_eu_status(plant):
        call_log.append(plant)
        return dict(CANONICAL_RESULT_TEMPLATES["searched_not_found"])

    monkeypatch.setattr(engine, "_eu_regulatory_status", fake_eu_status)

    engine.run(indication="Test indication", dosage_form="tea", market="EU")

    # "Alternativia speciosa" appears twice in the candidate data
    # (two compounds) but must only be looked up once.
    assert call_log.count("Alternativia speciosa") <= 1
    assert len(call_log) == len(set(call_log))


def test_run_rebuilds_cache_on_every_call_not_carried_over(monkeypatch):
    rows = [
        dict(scientific_name="Referencia herbosa", compound_name="Sharedcompoundia",
             indication="Test indication", target="Testtarget",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="Alternativia speciosa", compound_name="Sharedcompoundia",
             indication="", target="Testtarget",
             common_name="", plant_part="", extraction_method=""),
    ]
    engine = make_engine(rows)
    engine.use_live_search = False

    call_count = {"n": 0}

    def fake_eu_status(plant):
        call_count["n"] += 1
        return dict(CANONICAL_RESULT_TEMPLATES["searched_not_found"])

    monkeypatch.setattr(engine, "_eu_regulatory_status", fake_eu_status)

    engine.run(indication="Test indication", dosage_form="tea", market="EU")
    first_call_count = call_count["n"]
    assert first_call_count > 0

    # A second run() call on the SAME engine instance (simulating
    # step_rd_candidates.py's @st.cache_resource-cached engine reused
    # across an indication/market change) must rebuild the cache from
    # scratch — i.e. call _eu_regulatory_status() again for the same
    # plants, not silently reuse stale state from the first call.
    engine.run(indication="Test indication", dosage_form="capsule", market="US")
    assert call_count["n"] > first_call_count


def test_run_activates_canonical_listed_status_end_to_end(monkeypatch):
    rows = [
        dict(scientific_name="Referencia herbosa", compound_name="Sharedcompoundia",
             indication="Test indication", target="Testtarget",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="Alternativia speciosa", compound_name="Sharedcompoundia",
             indication="", target="Testtarget",
             common_name="", plant_part="", extraction_method=""),
    ]
    engine = make_engine(rows)
    engine.use_live_search = False

    def fake_eu_status(plant):
        if plant == "Alternativia speciosa":
            return dict(CANONICAL_RESULT_TEMPLATES["exact_species_match"])
        return dict(CANONICAL_RESULT_TEMPLATES["searched_not_found"])

    monkeypatch.setattr(engine, "_eu_regulatory_status", fake_eu_status)

    result_df = engine.run(indication="Test indication", dosage_form="tea", market="EU")
    alt_rows = result_df[result_df["Alternative_Plant"] == "Alternativia speciosa"]
    assert not alt_rows.empty
    assert (alt_rows["Market_Status"] == "Listed in EMA HMPC inventory — monograph not established").all()
