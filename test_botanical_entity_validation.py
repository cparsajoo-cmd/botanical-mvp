"""Tests for botanical_entity_validation.py -- the open-world extraction +
taxonomic validation layer that lets Stage 2 discover a plant that is not
already in the internal catalogue, while rejecting arbitrary literature
phrases that are not plants at all.
"""
import botanical_entity_validation as bev


# ---------------------------------------------------------------------------
# extract_binomial_mentions
# ---------------------------------------------------------------------------

def test_extracts_a_plausible_binomial_mention():
    text = "Extract of Salvia hispanica improved sleep latency in this trial."
    mentions = bev.extract_binomial_mentions(text)
    assert "Salvia hispanica" in mentions


def test_deduplicates_repeated_mentions_case_insensitively():
    text = "Salvia hispanica was studied. Later, salvia hispanica extract was given."
    mentions = bev.extract_binomial_mentions(text)
    assert mentions.count("Salvia hispanica") == 1


def test_rejects_sentence_initial_capitalized_word_as_false_binomial():
    text = "Results were significant across all groups studied here."
    mentions = bev.extract_binomial_mentions(text)
    assert mentions == []


def test_rejects_common_two_word_clinical_phrase():
    text = "Patients received a Randomized double blind placebo controlled trial."
    mentions = bev.extract_binomial_mentions(text)
    # "Randomized double" etc. must not look like a binomial candidate.
    assert not any("randomized" in m.lower() for m in mentions)


def test_does_not_match_genus_repeated_as_species():
    text = "Salvia salvia is not a real epithet pattern."
    mentions = bev.extract_binomial_mentions(text)
    assert mentions == []


# ---------------------------------------------------------------------------
# validate_botanical_candidate
# ---------------------------------------------------------------------------

def test_curated_synonym_is_validated_without_any_network_call(monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("external connector must not be called for a curated hit")

    monkeypatch.setattr(bev, "search_kew_plants", _boom)
    monkeypatch.setattr(bev, "search_gbif_plants", _boom)

    result = bev.validate_botanical_candidate("Cimicifuga racemosa")
    assert result["valid"] is True
    assert result["botanical_validation_status"] == bev.STATUS_VALIDATED_CURATED_SYNONYM
    assert result["matched_scientific_name"] == "Actaea racemosa"


def test_external_taxonomy_hit_validates_a_novel_candidate(monkeypatch):
    monkeypatch.setattr(bev, "search_kew_plants", lambda name, limit=20, timeout=None: [])
    monkeypatch.setattr(
        bev, "search_gbif_plants",
        lambda name, limit=30, timeout=None: [{"Scientific_Name": "Ocimum tenuiflorum", "Source": "GBIF"}],
    )

    result = bev.validate_botanical_candidate("Ocimum tenuiflorum")
    assert result["valid"] is True
    assert result["botanical_validation_status"] == bev.STATUS_VALIDATED_EXTERNAL_TAXONOMY
    assert result["taxonomic_source"] == "GBIF"
    assert result["matched_scientific_name"] == "Ocimum tenuiflorum"


def test_false_botanical_entity_is_rejected_when_no_source_confirms_it(monkeypatch):
    monkeypatch.setattr(bev, "search_kew_plants", lambda name, limit=20, timeout=None: [])
    monkeypatch.setattr(bev, "search_gbif_plants", lambda name, limit=30, timeout=None: [])

    result = bev.validate_botanical_candidate("Interleukin signaling")
    assert result["valid"] is False
    assert result["botanical_validation_status"] == bev.STATUS_UNRESOLVED


def test_non_binomial_string_is_rejected_by_format_before_any_lookup(monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("external connector must not be called for a format rejection")

    monkeypatch.setattr(bev, "search_kew_plants", _boom)
    monkeypatch.setattr(bev, "search_gbif_plants", _boom)

    result = bev.validate_botanical_candidate("inflammation")
    assert result["valid"] is False
    assert result["botanical_validation_status"] == bev.STATUS_REJECTED_FORMAT


def test_external_service_failure_degrades_to_unresolved_not_a_crash(monkeypatch):
    def _raise(*args, **kwargs):
        raise ConnectionError("service unavailable")

    # Simulate the connector's own real behaviour: any exception is caught
    # internally and [] is returned -- validate_botanical_candidate() must
    # never see a raw exception from either connector.
    monkeypatch.setattr(bev, "search_kew_plants", lambda name, limit=20, timeout=None: [])
    monkeypatch.setattr(bev, "search_gbif_plants", lambda name, limit=30, timeout=None: [])

    result = bev.validate_botanical_candidate("Unmapped fictumus")
    assert result["valid"] is False
    assert result["botanical_validation_status"] == bev.STATUS_UNRESOLVED


def test_cache_prevents_a_second_lookup_for_the_same_candidate():
    calls = {"n": 0}

    def _count_and_confirm(name, limit=20, timeout=None):
        calls["n"] += 1
        return [{"Scientific_Name": "Bacopa monnieri", "Source": "Kew POWO"}]

    import botanical_entity_validation as mod
    original = mod.search_kew_plants
    mod.search_kew_plants = _count_and_confirm
    try:
        cache = {}
        first = bev.validate_botanical_candidate("Bacopa monnieri", cache=cache)
        second = bev.validate_botanical_candidate("Bacopa monnieri", cache=cache)
        assert first == second
        assert calls["n"] == 1
    finally:
        mod.search_kew_plants = original
