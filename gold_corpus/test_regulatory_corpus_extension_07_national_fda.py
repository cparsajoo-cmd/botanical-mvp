from gold_corpus.regulatory_corpus_extension_07_national_fda import load_records,coverage
def test_extension_07_has_11_real_regulatory_records():
    assert len(load_records())==11
def test_extension_07_authority_balance():
    c=coverage()
    assert c["mhra"]==8
    assert c["fda"]==3
def test_extension_07_uses_official_domains_only():
    for r in load_records():
        if r["authority"]=="MHRA":
            assert r["source_url"].startswith("https://www.gov.uk/")
        elif r["authority"]=="FDA":
            assert r["source_url"].startswith("https://www.fda.gov/") or r["source_url"].startswith("https://www.accessdata.fda.gov/")
def test_extension_07_keeps_fda_corpus_only():
    fda=[r for r in load_records() if r["authority"]=="FDA"]
    assert fda
    assert all(r["source_family"]=="FDA_REGULATORY" for r in fda)
def test_extension_07_has_explicit_product_scope_and_legal_locator():
    assert all(r["product_scope"] and r["legal_locator"] and r["regulatory_effect"] for r in load_records())
def test_extension_07_contains_multiple_regulatory_effect_types():
    cats={r["regulatory_category"] for r in load_records()}
    assert {"PROHIBITION","DOSE_RESTRICTION","PHARMACY_ONLY"}.issubset(cats)
