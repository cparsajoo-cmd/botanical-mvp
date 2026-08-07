from gold_corpus.safety_corpus_extension_11 import load_records,coverage

def test_extension_11_has_12_traceable_ema_safety_records():
    r=load_records()
    assert len(r)==12
    assert len({x["record_id"] for x in r})==12
    assert all(x["source_url"].startswith("https://www.ema.europa.eu/") for x in r)
    assert all(x["locator"] and x["safety_effect"] for x in r)

def test_extension_11_has_multiple_botanicals():
    assert coverage()["unique_botanicals"] >= 6

def test_extension_11_has_age_and_pregnancy_coverage():
    c=coverage()
    assert c["age_related"] >= 3
    assert c["pregnancy_lactation"] >= 2

def test_extension_11_has_multiple_contraindication_types():
    assert coverage()["contraindication_like"] >= 7

def test_extension_11_is_ema_only():
    assert coverage()["ema_only"] is True

def test_extension_11_is_claim_level_not_case_level():
    assert all(x["verification_level"].startswith("official_ema") for x in load_records())
