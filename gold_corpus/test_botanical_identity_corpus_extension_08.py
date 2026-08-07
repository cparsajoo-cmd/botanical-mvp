from gold_corpus.botanical_identity_corpus_extension_08 import load_records,coverage
def test_extension_08_has_12_unique_kew_records():
    r=load_records()
    assert len(r)==12
    assert len({x["source_url"] for x in r})==12
    assert all(x["source_url"].startswith("https://powo.science.kew.org/") for x in r)
def test_extension_08_contains_accepted_and_synonym_cases():
    c=coverage()
    assert c["accepted"]==10
    assert c["synonym"]==2
def test_extension_08_synonyms_resolve_to_different_accepted_names():
    s=[x for x in load_records() if x["taxonomic_status"]=="synonym"]
    assert all(x["submitted_name"] != x["accepted_name"] for x in s)
def test_extension_08_accepted_names_are_identity_preserving():
    a=[x for x in load_records() if x["taxonomic_status"]=="accepted"]
    assert all(x["submitted_name"] == x["accepted_name"] for x in a)
def test_extension_08_is_taxonomy_only():
    assert all(x["verification_level"]=="official_kew_taxonomic_page" for x in load_records())
def test_extension_08_has_family_metadata():
    assert all(x["family"] for x in load_records())
