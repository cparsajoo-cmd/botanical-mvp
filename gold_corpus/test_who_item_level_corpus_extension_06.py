from gold_corpus.who_item_level_corpus_extension_06 import load_records, coverage

def test_extension_06_contains_only_verified_who_hosted_records():
    records = load_records()
    assert len(records) == 2
    assert all(r["source_family"] == "WHO_MONOGRAPH" for r in records)
    assert all(r["source_url"].startswith("https://iris.who.int/") for r in records)
    assert all(r["verification_level"] == "WHO_hosted_item_level_text_verified" for r in records)

def test_extension_06_has_unique_item_level_monographs():
    records = load_records()
    assert len({(r["volume"], r["monograph"]) for r in records}) == len(records)

def test_extension_06_has_explicit_locators():
    assert all(r["locator"] and ("p." in r["locator"] or "pp." in r["locator"]) for r in load_records())

def test_extension_06_does_not_present_curator_summary_as_verbatim():
    assert all(r["curator_summary_is_verbatim"] is False for r in load_records())

def test_extension_06_has_therapeutic_scope_and_part():
    assert all(r["plant_part"] for r in load_records())
    assert all(r["therapeutic_scope"] for r in load_records())

def test_extension_06_coverage_counts():
    assert coverage() == {
        "total": 2,
        "unique_monographs": 2,
        "who_hosted": 2,
        "item_level_verified": 2,
    }
