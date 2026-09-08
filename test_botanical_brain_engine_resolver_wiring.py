import pandas as pd

from botanical_brain_engine import UniversalBotanicalBrainEngine, COMPOUND_PLANT_MAP


def test_find_plants_for_compound_uses_real_plant_compounds_first():
    plant_compounds_df = pd.DataFrame([
        {"scientific_name": "Novel discoverica", "compound_name": "Curcumin",
         "target": "NF-kB", "source": "Dr. Duke"},
    ])
    engine = UniversalBotanicalBrainEngine(plant_compounds_df=plant_compounds_df)
    results = engine._find_plants_for_compound("Curcumin")
    names = {p for p, _source in results}
    # The real database record must be present...
    assert "Novel discoverica" in names
    # ...and take priority: the legacy map's "Curcuma longa" must NOT
    # also appear once the real index has a match (tier boundary, see
    # find_plants_for_compound()'s docstring).
    assert "Curcuma longa" not in names


def test_find_plants_for_compound_falls_back_to_legacy_map_when_no_real_data():
    engine = UniversalBotanicalBrainEngine(plant_compounds_df=None)
    results = engine._find_plants_for_compound("Curcumin")
    names = {p for p, _source in results}
    assert "Curcuma longa" in names
    sources = {s for _p, s in results}
    assert any("MVP compound-plant occurrence map" in s for s in sources)


def test_find_plants_for_compound_empty_plant_compounds_df_falls_back_too():
    engine = UniversalBotanicalBrainEngine(plant_compounds_df=pd.DataFrame())
    results = engine._find_plants_for_compound("Curcumin")
    names = {p for p, _source in results}
    assert "Curcuma longa" in names


def test_backward_compatible_constructor_without_plant_compounds_df():
    # Existing callers (e.g. step_botanical_brain.py) that never pass
    # plant_compounds_df must keep working exactly as before.
    engine = UniversalBotanicalBrainEngine(evidence_df=pd.DataFrame())
    results = engine._find_plants_for_compound("Curcumin")
    assert any(p == "Curcuma longa" for p, _s in results)


def test_legacy_map_is_untouched():
    # This module must not delete or shrink the legacy map -- it is still
    # the documented, explicitly-labelled fallback tier.
    assert "curcumin" in COMPOUND_PLANT_MAP
    assert "Curcuma longa" in COMPOUND_PLANT_MAP["curcumin"]
