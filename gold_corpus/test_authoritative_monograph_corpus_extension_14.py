from gold_corpus.authoritative_monograph_corpus_extension_14 import load_records,coverage

def test_extension_14_has_6_unique_official_ema_records():
    r=load_records()
    assert len(r)==6
    assert len({x["source_url"] for x in r})==6
    assert all(x["source_url"].startswith("https://www.ema.europa.eu/") for x in r)

def test_extension_14_all_have_final_eu_monograph_outcome():
    assert all(x["assessment_status"]=="F: Assessment finalised" for x in load_records())
    assert all(x["assessment_outcome"]=="European Union herbal monograph" for x in load_records())

def test_extension_14_has_traceable_reference_numbers():
    assert all(x["adopted_reference_number"] for x in load_records())

def test_extension_14_has_identity_part_and_therapeutic_area():
    assert all(x["botanical_name"] and x["plant_part"] for x in load_records())
    assert all(x["therapeutic_area"] for x in load_records())

def test_extension_14_has_six_distinct_herbal_drugs():
    assert coverage()["unique_herbal_drugs"]==6

def test_extension_14_is_authoritative_corpus_not_new_gold_cases():
    assert coverage()["ema_hmpc"]==6
