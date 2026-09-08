import pandas as pd

from compound_plant_resolver import (
    normalize_compound_name,
    build_compound_plant_index,
    find_plants_for_compound,
    compound_plant_count,
    compound_specificity_score,
    compound_specificity_tier,
    SOURCE_PLANT_COMPOUNDS_DATABASE,
    SOURCE_LEGACY_FALLBACK_MAP,
)


def _plant_compounds_df():
    return pd.DataFrame([
        {
            "scientific_name": "Obscura testii", "common_name": "Test plant",
            "compound_name": "Novelol", "compound_class": "Flavonoid",
            "plant_part": "leaf", "target": "GABA-A receptor",
            "mechanism": "GABAergic modulation", "evidence_level": "In vitro",
            "confidence_score": 0.6, "source": "Dr. Duke", "source_year": "1992",
            "reference_title": "Test ref", "reference_url": "http://example.org",
        },
        {
            "scientific_name": "Quercus ubiquitum", "common_name": "",
            "compound_name": "Quercetin", "compound_class": "Flavonoid",
            "plant_part": "bark", "target": "", "mechanism": "",
            "evidence_level": "Occurrence only", "confidence_score": None,
            "source": "Dr. Duke", "source_year": "", "reference_title": "", "reference_url": "",
        },
        {
            "scientific_name": "Alia planta", "common_name": "",
            "compound_name": "quercetin", "compound_class": "Flavonoid",
            "plant_part": "root", "target": "", "mechanism": "",
            "evidence_level": "Occurrence only", "confidence_score": None,
            "source": "Dr. Duke", "source_year": "", "reference_title": "", "reference_url": "",
        },
    ])


def test_normalize_compound_name_is_case_and_whitespace_insensitive():
    assert normalize_compound_name("  Quercetin  ") == "quercetin"
    assert normalize_compound_name("QUERCETIN") == normalize_compound_name("quercetin")
    assert normalize_compound_name(None) == ""
    assert normalize_compound_name("NaN") == ""


def test_build_index_empty_on_missing_or_empty_input():
    assert build_compound_plant_index(None) == {}
    assert build_compound_plant_index(pd.DataFrame()) == {}
    assert build_compound_plant_index(pd.DataFrame([{"foo": "bar"}])) == {}


def test_build_index_groups_by_normalized_compound():
    index = build_compound_plant_index(_plant_compounds_df())
    assert "quercetin" in index
    assert len(index["quercetin"]) == 2  # Quercus ubiquitum + Alia planta
    assert "novelol" in index
    assert len(index["novelol"]) == 1


def test_find_plants_for_compound_returns_structured_records_with_provenance():
    index = build_compound_plant_index(_plant_compounds_df())
    records = find_plants_for_compound("Novelol", index)
    assert len(records) == 1
    record = records[0]
    assert record["scientific_name"] == "Obscura testii"
    assert record["target"] == "GABA-A receptor"
    assert record["origin"] == SOURCE_PLANT_COMPOUNDS_DATABASE
    assert record["source"] == "Dr. Duke"


def test_find_plants_for_compound_case_insensitive():
    index = build_compound_plant_index(_plant_compounds_df())
    assert len(find_plants_for_compound("NOVELOL", index)) == 1
    assert len(find_plants_for_compound("novelol", index)) == 1


def test_find_plants_for_compound_substring_fallback_within_real_index():
    index = build_compound_plant_index(_plant_compounds_df())
    # "quercetin 3-o-glucoside" isn't in the index verbatim, but contains
    # "quercetin" -- must still surface the real database records, not
    # nothing and not the legacy map.
    records = find_plants_for_compound("Quercetin 3-O-glucoside", index)
    names = {r["scientific_name"] for r in records}
    assert names == {"Quercus ubiquitum", "Alia planta"}
    assert all(r["origin"] == SOURCE_PLANT_COMPOUNDS_DATABASE for r in records)


def test_find_plants_for_compound_unknown_with_no_fallback_is_empty():
    index = build_compound_plant_index(_plant_compounds_df())
    assert find_plants_for_compound("Totally unknown compound", index) == []


def test_find_plants_for_compound_uses_legacy_fallback_only_when_real_index_empty():
    index = build_compound_plant_index(_plant_compounds_df())
    legacy_map = {"curcumin": ["Curcuma longa"]}
    records = find_plants_for_compound("curcumin", index, legacy_fallback_map=legacy_map)
    assert len(records) == 1
    assert records[0]["scientific_name"] == "Curcuma longa"
    assert records[0]["origin"] == SOURCE_LEGACY_FALLBACK_MAP
    assert "not database-verified" in records[0]["source"]


def test_find_plants_for_compound_real_index_always_wins_over_legacy():
    index = build_compound_plant_index(_plant_compounds_df())
    legacy_map = {"quercetin": ["Some Other Plant"]}
    records = find_plants_for_compound("quercetin", index, legacy_fallback_map=legacy_map)
    names = {r["scientific_name"] for r in records}
    assert "Some Other Plant" not in names
    assert all(r["origin"] == SOURCE_PLANT_COMPOUNDS_DATABASE for r in records)


def test_compound_plant_count_counts_distinct_plants_real_index_only():
    index = build_compound_plant_index(_plant_compounds_df())
    assert compound_plant_count("quercetin", index) == 2
    assert compound_plant_count("novelol", index) == 1
    assert compound_plant_count("unknown compound", index) == 0


def test_compound_specificity_score_decreases_with_plant_count():
    s1 = compound_specificity_score(1)
    s2 = compound_specificity_score(5)
    s3 = compound_specificity_score(300)
    assert s1 == 1.0
    assert s1 > s2 > s3
    assert 0.0 <= s3 < 0.2


def test_compound_specificity_tier_labels():
    assert compound_specificity_tier(0) == "Unknown occurrence"
    assert compound_specificity_tier(2) == "Rare / mechanism-specific"
    assert compound_specificity_tier(10) == "Moderate occurrence"
    assert compound_specificity_tier(400) == "Common / non-specific"
