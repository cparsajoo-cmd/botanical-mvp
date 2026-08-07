from gold_corpus.safety_interaction_corpus_extension_09 import load_records, coverage

def test_extension_09_has_12_traceable_safety_records():
    r=load_records()
    assert len(r)==12
    assert len({x["record_id"] for x in r})==12
    assert all(x["source_url"] and x["locator"] and x["safety_effect"] for x in r)

def test_extension_09_uses_official_ema_or_who_sources_only():
    for x in load_records():
        assert x["source_url"].startswith("https://www.ema.europa.eu/") or x["source_url"].startswith("https://iris.who.int/")

def test_extension_09_avoids_existing_hypericum_and_ginkgo_safety_gold_cases():
    names={x["botanical_name"] for x in load_records()}
    assert not any("Hypericum" in n for n in names)
    assert not any("Ginkgo" in n for n in names)

def test_extension_09_contains_interactions_and_contraindications():
    c=coverage()
    assert c["interaction_like"] >= 4
    assert c["contraindication_like"] >= 4

def test_extension_09_has_multi_botanical_coverage():
    assert coverage()["unique_botanicals"] >= 7

def test_extension_09_is_corpus_only():
    assert all(x["verification_level"] for x in load_records())
