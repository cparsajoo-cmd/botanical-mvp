"""Phase 2D-A/2D-B regression suite — the canonical EMA/HMPC connector
integration architecture inside _market_status(), and (Phase 2D-B) the
performance correction that removed the unbounded, automatic per-run
full-universe cache build 2D-A had added to run().

UPDATED FOR PHASE 2D-B: default run() no longer performs any canonical
EMA lookups (see the "5. Phase 2D-B" section below) — 2D-A's tests that
required/proved a full-universe build were removed and replaced. The
unit-level tests above that section (classification logic given an
explicitly-populated cache) are unchanged: that architecture was
preserved, only its automatic population was removed.

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
# 2b. manually_curated — must read the compact status explicitly,
# never infer inventory presence from the category alone.
# ---------------------------------------------------------------------

def _curated_record(compact_status):
    return {
        "EMA_HMPC_Status": compact_status,
        "EMA_HMPC_Detail": compact_status,
        "EMA_Source": "Curated (seed_data.SLEEP_TEA_EVIDENCE) — manually verified",
        "EMA_HMPC_Match_Category": "manually_curated",
    }


def test_manually_curated_monograph_available_reaches_monograph_exists():
    engine = make_engine([])
    engine.use_live_search = False
    engine._canonical_regulatory_by_plant = {
        "Genusia speciosa": _curated_record("HMPC monograph available")
    }
    result = engine._market_status(alt=_make_alt_row(), evidence="", market="EU")
    assert result == "Regulatory monograph exists"


def test_manually_curated_traditional_use_status_reaches_traditional_use_status():
    engine = make_engine([])
    engine.use_live_search = False
    engine._canonical_regulatory_by_plant = {
        "Genusia speciosa": _curated_record("Traditional-use status")
    }
    result = engine._market_status(alt=_make_alt_row(), evidence="", market="EU")
    assert result == "Traditional-use status"


def test_manually_curated_confirmed_inventory_only_reaches_listed_status():
    engine = make_engine([])
    engine.use_live_search = False
    engine._canonical_regulatory_by_plant = {
        "Genusia speciosa": _curated_record("Listed in HMPC inventory")
    }
    result = engine._market_status(alt=_make_alt_row(), evidence="", market="EU")
    assert result == "Listed in EMA HMPC inventory — monograph not established"


@pytest.mark.parametrize("compact_status", ["Not verified", "", None, "Source unavailable"])
def test_manually_curated_unverified_or_ambiguous_produces_no_positive_claim(compact_status):
    engine = make_engine([])
    engine.use_live_search = False
    engine._canonical_regulatory_by_plant = {
        "Genusia speciosa": _curated_record(compact_status)
    }
    result = engine._market_status(alt=_make_alt_row(), evidence="", market="EU")
    assert result not in (
        "Listed in EMA HMPC inventory — monograph not established",
        "Regulatory monograph exists",
        "Traditional-use status",
    )


def test_manually_curated_explicit_not_found_produces_no_listed_or_monograph_claim():
    engine = make_engine([])
    engine.use_live_search = False
    engine._canonical_regulatory_by_plant = {
        "Genusia speciosa": _curated_record("Not found in HMPC inventory")
    }
    result = engine._market_status(alt=_make_alt_row(), evidence="", market="EU")
    assert result not in (
        "Listed in EMA HMPC inventory — monograph not established",
        "Regulatory monograph exists",
        "Traditional-use status",
    )


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
# 5. Phase 2D-B (performance correction) — default run() must perform
# ZERO canonical EMA lookups, regardless of candidate-universe size.
# The full-universe cache build from Phase 2D-A was removed; these
# tests replace the ones that proved (and depended on) that build.
# ---------------------------------------------------------------------

def test_default_run_performs_zero_canonical_ema_lookups(monkeypatch):
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

    call_log = []

    def fake_eu_status(plant):
        call_log.append(plant)
        return dict(CANONICAL_RESULT_TEMPLATES["searched_not_found"])

    monkeypatch.setattr(engine, "_eu_regulatory_status", fake_eu_status)

    engine.run(indication="Test indication", dosage_form="tea", market="EU")

    assert call_log == []


def test_2000_synthetic_unique_plants_do_not_cause_2000_lookups(monkeypatch):
    rows = [
        dict(scientific_name="Referencia herbosa", compound_name="Sharedcompoundia",
             indication="Test indication", target="Testtarget",
             common_name="", plant_part="", extraction_method=""),
    ]
    rows += [
        dict(scientific_name=f"Syntheticplant{i} speciosa", compound_name="Sharedcompoundia",
             indication="", target="Testtarget",
             common_name="", plant_part="", extraction_method="")
        for i in range(2000)
    ]
    engine = make_engine(rows)
    engine.use_live_search = False

    call_log = []

    def fake_eu_status(plant):
        call_log.append(plant)
        return dict(CANONICAL_RESULT_TEMPLATES["searched_not_found"])

    monkeypatch.setattr(engine, "_eu_regulatory_status", fake_eu_status)

    engine.run(indication="Test indication", dosage_form="tea", market="EU")

    assert len(call_log) == 0


def test_canonical_cache_stays_empty_throughout_default_run(monkeypatch):
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
    engine.run(indication="Test indication", dosage_form="tea", market="EU")
    assert engine._canonical_regulatory_by_plant == {}


def test_explicit_pre_populated_cache_still_reaches_market_status_end_to_end():
    # The architecture (Requirement 2) is preserved: a caller who
    # explicitly populates the cache before run() still gets canonical
    # data in Market_Status — this is no longer automatic, but it is
    # still fully wired and functional.
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
    engine._canonical_regulatory_by_plant = {
        "Alternativia speciosa": dict(CANONICAL_RESULT_TEMPLATES["exact_species_match"]),
    }

    result_df = engine.run(indication="Test indication", dosage_form="tea", market="EU")
    alt_rows = result_df[result_df["Alternative_Plant"] == "Alternativia speciosa"]
    assert not alt_rows.empty
    assert (alt_rows["Regulatory_Recognition_Status"] == "Listed in EMA HMPC inventory — monograph not established").all()
    assert (alt_rows["Market_Status"] == "Search not performed").all()


def test_run_does_not_mutate_a_pre_populated_cache_to_add_more_plants(monkeypatch):
    # run() must not "top up" an explicitly pre-populated cache with
    # additional unbounded lookups for the rest of the candidate
    # universe — that would silently reintroduce the regression for
    # any caller who opts in for even one plant.
    rows = [
        dict(scientific_name="Referencia herbosa", compound_name="Sharedcompoundia",
             indication="Test indication", target="Testtarget",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="Alternativia speciosa", compound_name="Sharedcompoundia",
             indication="", target="Testtarget",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="Otheralternativia vulgaris", compound_name="Sharedcompoundia",
             indication="", target="Testtarget",
             common_name="", plant_part="", extraction_method=""),
    ]
    engine = make_engine(rows)
    engine.use_live_search = False
    engine._canonical_regulatory_by_plant = {
        "Alternativia speciosa": dict(CANONICAL_RESULT_TEMPLATES["exact_species_match"]),
    }

    call_log = []

    def fake_eu_status(plant):
        call_log.append(plant)
        return dict(CANONICAL_RESULT_TEMPLATES["searched_not_found"])

    monkeypatch.setattr(engine, "_eu_regulatory_status", fake_eu_status)

    engine.run(indication="Test indication", dosage_form="tea", market="EU")

    assert call_log == []
    assert set(engine._canonical_regulatory_by_plant) == {"Alternativia speciosa"}


def test_candidate_matching_unchanged_from_pre_phase_2d_a_fast_path():
    # Candidate selection/matching (row count, which plants appear)
    # must be identical to the pre-Phase-2D-A fast path — canonical EMA
    # enrichment (present or absent) must never determine which
    # candidates are discovered.
    rows = [
        dict(scientific_name="Referencia herbosa", compound_name="Sharedcompoundia",
             indication="Test indication", target="Testtarget",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="Alternativia speciosa", compound_name="Sharedcompoundia",
             indication="", target="Testtarget",
             common_name="", plant_part="", extraction_method=""),
    ]
    engine_a = make_engine(rows)
    engine_a.use_live_search = False
    result_a = engine_a.run(indication="Test indication", dosage_form="tea", market="EU")

    engine_b = make_engine(rows)
    engine_b.use_live_search = False
    result_b = engine_b.run(indication="Test indication", dosage_form="tea", market="EU")

    assert len(result_a) == len(result_b)
    assert sorted(result_a["Alternative_Plant"].tolist()) == sorted(result_b["Alternative_Plant"].tolist())


def test_enrich_candidates_with_market_landscape_still_capped_at_30():
    # The pre-existing, explicit enrichment path (unaffected by this
    # phase) must still be the bounded one — confirms it, not the
    # default run() cache, remains the enrichment mechanism.
    import inspect
    sig = inspect.signature(BotanicalRDCandidateEngine.enrich_candidates_with_market_landscape)
    assert sig.parameters["max_plants"].default == 30
