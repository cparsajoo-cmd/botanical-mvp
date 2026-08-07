from gold_corpus.botanical_identity_corpus_extension_13 import load_records,coverage

def test_extension_13_has_8_unique_kew_records():
    r=load_records()
    assert len(r)==8
    assert len({x["source_url"] for x in r})==8
    assert all(x["source_url"].startswith("https://powo.science.kew.org/") for x in r)

def test_extension_13_has_expected_status_mix():
    c=coverage()
    assert c["accepted"]==6
    assert c["synonym"]==2

def test_extension_13_synonyms_resolve_to_accepted_names():
    s=[x for x in load_records() if x["taxonomic_status"]=="synonym"]
    assert all(x["submitted_name"] != x["accepted_name"] for x in s)

def test_extension_13_accepted_names_are_identity_preserving():
    a=[x for x in load_records() if x["taxonomic_status"]=="accepted"]
    assert all(x["submitted_name"] == x["accepted_name"] for x in a)

def test_extension_13_uses_official_kew_only():
    assert all(x["verification_level"]=="official_kew_taxonomic_page" for x in load_records())

def test_extension_13_completes_identity_target_range():
    # Extension 08 had 12 records; +8 here = 20 total planned identity records.
    assert 12 + coverage()["total"] == 20
