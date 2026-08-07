from gold_corpus.authoritative_monograph_corpus_extension_05 import load_records,coverage

def test_extension_05_has_12_unique_official_source_urls():
    records=load_records()
    assert len(records)==12
    assert len({r["source_url"] for r in records})==12

def test_extension_05_uses_only_official_ema_or_escop_domains():
    for r in load_records():
        if r["source_family"]=="EMA_HMPC":
            assert r["source_url"].startswith("https://www.ema.europa.eu/")
        elif r["source_family"]=="ESCOP_MONOGRAPH":
            assert r["source_url"].startswith("https://www.escop.com/")
        else:
            raise AssertionError(r["source_family"])

def test_extension_05_balances_ema_and_escop():
    c=coverage()
    assert c["by_source_family"]=={"EMA_HMPC":6,"ESCOP_MONOGRAPH":6}

def test_extension_05_never_mislabels_curator_summary_as_quote():
    assert all(r["verification_level"]=="official_public_summary" for r in load_records())
    assert all(r["curator_summary"] for r in load_records())

def test_extension_05_has_botanical_part_and_scope_fields():
    assert all(r["botanical_name"] and r["herbal_drug"] and r["plant_part"] for r in load_records())
    assert all(isinstance(r["therapeutic_scope"],list) and r["therapeutic_scope"] for r in load_records())

def test_extension_05_does_not_claim_who_item_level_records():
    assert all(r["source_family"]!="WHO_MONOGRAPH" for r in load_records())
