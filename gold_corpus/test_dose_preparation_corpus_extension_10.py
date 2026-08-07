from gold_corpus.dose_preparation_corpus_extension_10 import load_records,coverage

def test_extension_10_has_12_traceable_records():
    r=load_records()
    assert len(r)==12
    assert len({x["record_id"] for x in r})==12
    assert all(x["source_url"] and x["source_reference"] and x["locator"] for x in r)

def test_extension_10_avoids_existing_preparation_gold_case_botanicals():
    names={x["botanical_name"] for x in load_records()}
    assert "Valeriana officinalis L." not in names
    assert "Ginkgo biloba L." not in names
    assert "Hypericum perforatum L." not in names

def test_extension_10_preserves_route_specificity():
    routes=set(coverage()["routes"])
    assert {"oral","oromucosal","cutaneous"}.issubset(routes)

def test_extension_10_has_preparation_diversity():
    assert coverage()["unique_preparations"] >= 10

def test_extension_10_has_explicit_dose_context():
    assert coverage()["with_explicit_numeric_dose"] >= 11

def test_extension_10_never_infers_equivalent_doses():
    assert all("equivalent" not in x["applicability_note"].lower() or "not" in x["applicability_note"].lower() for x in load_records())
