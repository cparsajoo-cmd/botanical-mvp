"""Phase 2B regression suite — ema_regulatory_connector.py's taxonomic
name-matching and PDF-parsing fixes.

WHAT THIS COVERS
- _latin_root() (Latin genitive-suffix-aware stemming, replacing a
  fixed-length prefix truncation that caused real cross-genus
  collisions).
- _parse_substance_names() (structural rejection of non-botanical PDF
  text via the trailing plant-part-noun requirement).
- _classify_inventory_match() (the full taxonomic match-category
  vocabulary: exact_species_match, verified_synonym_match,
  verified_pharmacopoeial_name_match, genus_only_match,
  related_species_only, ambiguous_match, searched_not_found).
- search_regulatory_sources_real()'s summary/detail consistency (never
  "Listed" in EMA_Status unless the match category actually earns it),
  and its source_unavailable/parsing_failed distinction.

ALL FIXTURES ARE SYNTHETIC. The real regression shapes from the Phase
2B audit report (Glycyrrhiza glabra vs Glycine max, Asparagus
officinalis vs address text, Mentha longifolia vs other Mentha
species) are included as TEST ASSERTIONS ONLY — production code in
ema_regulatory_connector.py contains no plant names, and this file
does not add any either. Every other test uses invented genus/species/
plant-part combinations that do not correspond to any real regulatory
question, so nothing here is indication- or plant-specific to the
menopause/infusion regression run that originally prompted this audit.
"""

import unittest.mock as mock

import pytest

import ema_regulatory_connector as erc


# ---------------------------------------------------------------------
# _latin_root() — Latin genitive-suffix stemming.
# ---------------------------------------------------------------------

@pytest.mark.parametrize(
    "word_a,word_b,should_match",
    [
        # Genitive-form variance of the SAME genus must still match.
        ("Valeriana", "Valerianae", True),
        ("Zizyphus", "Zizyphi", True),
        # The real regression: two genuinely different genera whose
        # first 4 letters happen to coincide must NOT match once a
        # real Latin root (not a 4-char prefix) is compared.
        ("Glycyrrhiza", "Glycine", False),
        # Two unrelated, invented genera sharing a short prefix by
        # coincidence — generic proof the fix isn't special-cased to
        # the one real example above.
        ("Zingiberis", "Zingoxylum", False),
    ],
)
def test_latin_root_genus_matching(word_a, word_b, should_match):
    result = erc._latin_root(word_a) == erc._latin_root(word_b)
    assert result == should_match, (
        f"_latin_root({word_a!r})={erc._latin_root(word_a)!r}, "
        f"_latin_root({word_b!r})={erc._latin_root(word_b)!r}"
    )


def test_latin_root_never_collapses_to_a_prefix_shorter_than_min_root_len():
    # Guards against silently reintroducing the old 4-char truncation.
    for word in ("Glycyrrhiza", "Glycine", "Valerianae", "Menthae"):
        assert len(erc._latin_root(word)) >= erc._MIN_ROOT_LEN


# ---------------------------------------------------------------------
# _parse_substance_names() — structural rejection of non-botanical text.
# ---------------------------------------------------------------------

def test_parser_accepts_genuine_two_word_pharmacopoeial_entry():
    text = "Some preamble line\nZingoxylum radix\nAnother line"
    entries = erc._parse_substance_names(text)
    assert "Zingoxylum radix" in entries


def test_parser_accepts_genuine_three_word_species_specific_entry():
    text = "Menthae longifoliae folium"
    entries = erc._parse_substance_names(text)
    assert "Menthae longifoliae folium" in entries


def test_parser_rejects_administrative_address_text():
    # The real regression: "Official address Domenico Scarlattilaan"
    # (EMA's own letterhead) must never be treated as a botanical entry.
    text = "Official address Domenico Scarlattilaan"
    entries = erc._parse_substance_names(text)
    assert entries == [], f"administrative text was accepted as entries: {entries!r}"


def test_parser_rejects_document_titles_and_headers():
    for noise_line in (
        "European Union herbal monograph programme",
        "Committee on Herbal Medicinal Products",
        "Annex Table of contents",
    ):
        entries = erc._parse_substance_names(noise_line)
        assert entries == [], f"{noise_line!r} was incorrectly accepted: {entries!r}"


def test_parser_rejects_capitalized_words_not_ending_in_a_part_noun():
    text = "Randomia Placeholderia Nonexistentia"
    entries = erc._parse_substance_names(text)
    assert entries == []


def test_parser_handles_wrapped_line_entry():
    text = "Ginkgoa bilobae\nfolium"
    entries = erc._parse_substance_names(text)
    assert "Ginkgoa bilobae folium" in entries


# ---------------------------------------------------------------------
# _classify_inventory_match() — full match-category vocabulary.
# Synthetic inventory built directly via _build_stem_index(), never a
# live fetch.
# ---------------------------------------------------------------------

def _index(entries):
    return erc._build_stem_index(entries)


def test_exact_species_match():
    stem_index = _index(["Zingoxylum arenosae radix"])
    category, matched = erc._classify_inventory_match("Zingoxylum arenosum", stem_index)
    assert category == "exact_species_match"
    assert matched == {"Zingoxylum arenosae radix"}


def test_genus_only_match_when_entry_names_no_species():
    stem_index = _index(["Zingoxylum radix"])
    category, matched = erc._classify_inventory_match("Zingoxylum arenosum", stem_index)
    assert category == "genus_only_match"
    assert matched == {"Zingoxylum radix"}


def test_related_species_only_when_entry_names_a_different_species():
    stem_index = _index(["Zingoxylum montanae radix"])
    category, matched = erc._classify_inventory_match("Zingoxylum arenosum", stem_index)
    assert category == "related_species_only"
    assert matched == {"Zingoxylum montanae radix"}


def test_ambiguous_match_when_genus_only_and_other_species_both_present():
    stem_index = _index(["Zingoxylum radix", "Zingoxylum montanae folium"])
    category, matched = erc._classify_inventory_match("Zingoxylum arenosum", stem_index)
    assert category == "ambiguous_match"
    assert matched == {"Zingoxylum radix", "Zingoxylum montanae folium"}


def test_searched_not_found_when_genus_absent_entirely():
    stem_index = _index(["Unrelatia radix"])
    category, matched = erc._classify_inventory_match("Zingoxylum arenosum", stem_index)
    assert category == "searched_not_found"
    assert matched == set()


def test_unverified_pharmacopoeial_trade_name_fallback_is_rejected():
    # PHASE 2B CORRECTION: a searched species epithet matching an
    # unrelated inventory entry's head word must NEVER be accepted as
    # an exact match — that was an unverified inference, not a
    # taxonomic match.
    stem_index = _index(["Fabricatoginseng radix"])
    category, matched = erc._classify_inventory_match("Panax fabricatoginseng", stem_index)
    assert category == "searched_not_found"
    assert matched == set()


def test_pharmacopoeial_trade_name_accepted_only_via_verified_mapping(monkeypatch):
    # Paired test: the SAME scenario as above must succeed once — and
    # only once — an explicit, verified mapping exists. Direction:
    # KEY = searched scientific name, VALUE = the verified
    # pharmacopoeial inventory entry text itself.
    stem_index = _index(["Fabricatoginseng radix"])
    monkeypatch.setitem(
        erc._VERIFIED_SPECIES_TO_PHARMACOPOEIAL_NAME,
        "panax fabricatoginseng", "Fabricatoginseng radix",
    )
    category, matched = erc._classify_inventory_match("Panax fabricatoginseng", stem_index)
    assert category == "verified_pharmacopoeial_name_match"
    assert matched == {"Fabricatoginseng radix"}


@pytest.mark.parametrize(
    "searched_species,unrelated_entry",
    [
        ("Randomia alba", "Placeholderia alba folium"),
        ("Randomia officinalis", "Placeholderia officinalis radix"),
        ("Randomia vulgaris", "Placeholderia vulgaris herba"),
        ("Randomia major", "Placeholderia major folium"),
        ("Randomia minor", "Placeholderia minor folium"),
    ],
)
def test_common_epithets_never_create_a_cross_genus_match(searched_species, unrelated_entry):
    # Generic regression: widely-shared, generic Latin species epithets
    # ("alba", "officinalis", "vulgaris", "major", "minor") must never
    # create a match across genera just because they coincide.
    stem_index = _index([unrelated_entry])
    category, matched = erc._classify_inventory_match(searched_species, stem_index)
    assert category == "searched_not_found"
    assert matched == set()


def test_species_epithet_equal_to_unrelated_inventory_head_word_is_rejected():
    # The epithet itself, standing alone, must never be treated as if
    # it were a genus-level head word from an unrelated entry.
    stem_index = _index(["Epithetword radix"])
    category, matched = erc._classify_inventory_match("Genusia epithetword", stem_index)
    assert category == "searched_not_found"
    assert matched == set()


def test_no_genus_match_and_no_verified_mapping_always_returns_searched_not_found():
    stem_index = _index(["Completelyunrelateda radix", "Anotherunrelatedb folium"])
    for name in ("Zingoxylum arenosum", "Randomia alba", "Genusia epithetword"):
        category, matched = erc._classify_inventory_match(name, stem_index)
        assert category == "searched_not_found"
        assert matched == set()


def test_verified_synonym_table_resolves_when_populated(monkeypatch):
    stem_index = _index(["Zingoxylum arenosae radix"])
    monkeypatch.setitem(
        erc._VERIFIED_SYNONYMS, "synonymia arenosa", "zingoxylum arenosum"
    )
    category, matched = erc._classify_inventory_match("Synonymia arenosa", stem_index)
    assert category == "verified_synonym_match"
    assert matched == {"Zingoxylum arenosae radix"}


def test_verified_pharmacopoeial_name_table_resolves_when_populated(monkeypatch):
    # Direction (Phase 2B consistency correction): KEY is the searched
    # scientific name; VALUE is the verified pharmacopoeial inventory
    # entry text it resolves to — e.g. "panax ginseng" -> "Ginseng radix".
    stem_index = _index(["Tradenamia radix"])
    monkeypatch.setitem(
        erc._VERIFIED_SPECIES_TO_PHARMACOPOEIAL_NAME,
        "zingoxylum arenosum", "Tradenamia radix",
    )
    category, matched = erc._classify_inventory_match("Zingoxylum arenosum", stem_index)
    assert category == "verified_pharmacopoeial_name_match"
    assert matched == {"Tradenamia radix"}


def test_scientific_name_resolves_via_verified_mapping_and_fails_without_it(monkeypatch):
    # THE required consistency test: the same scientific-name search
    # resolves to its verified pharmacopoeial inventory entry once the
    # mapping exists, and fails (searched_not_found) when it doesn't —
    # proving the mapping, not some other path, is what makes it work.
    stem_index = _index(["Ginsengia radix"])

    category, matched = erc._classify_inventory_match("Panax fabricatoginseng", stem_index)
    assert category == "searched_not_found"
    assert matched == set()

    monkeypatch.setitem(
        erc._VERIFIED_SPECIES_TO_PHARMACOPOEIAL_NAME,
        "panax fabricatoginseng", "Ginsengia radix",
    )
    category, matched = erc._classify_inventory_match("Panax fabricatoginseng", stem_index)
    assert category == "verified_pharmacopoeial_name_match"
    assert matched == {"Ginsengia radix"}


def test_synonym_and_pharmacopoeial_tables_are_empty_by_default():
    # Guards against ever silently pre-populating these with an
    # unverified guess.
    assert erc._VERIFIED_SYNONYMS == {}
    assert erc._VERIFIED_SPECIES_TO_PHARMACOPOEIAL_NAME == {}


# ---------------------------------------------------------------------
# Real regression shapes from the Phase 2B audit report. Fixtures only
# — the matching/parsing logic above them contains no plant names.
# ---------------------------------------------------------------------

def test_regression_glycyrrhiza_glabra_does_not_match_glycine_max():
    stem_index = _index(["Glycine max radix"])
    category, matched = erc._classify_inventory_match("Glycyrrhiza glabra", stem_index)
    assert category == "searched_not_found"
    assert matched == set()


def test_regression_asparagus_officinalis_does_not_match_address_text():
    # The address text itself must never even become an "entry" (see
    # the parser tests above) — confirmed again here end-to-end: an
    # inventory built from real-looking PDF noise produces zero
    # entries, so genus/species matching has nothing false to match.
    noise_text = "Official address Domenico Scarlattilaan 1083 HS Amsterdam"
    entries = erc._parse_substance_names(noise_text)
    stem_index = erc._build_stem_index(entries)
    category, matched = erc._classify_inventory_match("Asparagus officinalis", stem_index)
    assert category == "searched_not_found"
    assert matched == set()


def test_regression_mentha_longifolia_not_marked_listed_via_other_mentha_species():
    stem_index = _index(["Menthae arvensis herba", "Menthae piperitae folium"])
    category, matched = erc._classify_inventory_match("Mentha longifolia", stem_index)
    assert category == "related_species_only"
    assert category != "exact_species_match"
    assert "Menthae longifoliae" not in " ".join(matched)


# ---------------------------------------------------------------------
# search_regulatory_sources_real() — summary/detail consistency and
# source_unavailable vs parsing_failed distinction. _get_inventory() is
# mocked (no live network) but the record-building logic downstream of
# it is exercised for real.
# ---------------------------------------------------------------------

def _mock_inventory(entries):
    return mock.patch.object(erc, "_get_inventory", return_value=(_index(entries), entries, None))


def test_exact_match_record_says_listed_and_tags_the_match_category():
    with _mock_inventory(["Zingoxylum arenosae radix"]):
        result = erc.search_regulatory_sources_real("Zingoxylum arenosum")
    record = result[0]
    assert "Listed" in record["EMA_Status"]
    assert record["Taxonomic_Match_Status"] == "exact_species_match"


@pytest.mark.parametrize(
    "entries,expected_category",
    [
        (["Zingoxylum radix"], "genus_only_match"),
        (["Zingoxylum montanae folium"], "related_species_only"),
        (["Zingoxylum radix", "Zingoxylum montanae folium"], "ambiguous_match"),
        ([], "searched_not_found"),
    ],
)
def test_non_exact_categories_never_say_listed_in_ema_status(entries, expected_category):
    with _mock_inventory(entries):
        result = erc.search_regulatory_sources_real("Zingoxylum arenosum")
    record = result[0]
    assert record["Taxonomic_Match_Status"] == expected_category
    assert "Listed" not in record["EMA_Status"], (
        f"category {expected_category!r} incorrectly produced a 'Listed' EMA_Status: "
        f"{record['EMA_Status']!r}"
    )
    # Downstream consistency check: the shared normalization helper
    # must resolve this to something other than inventory_listed.
    from standard_evidence_builder import classify_ema_hmpc_signal
    assert classify_ema_hmpc_signal(record["EMA_Status"]) != "inventory_listed"


def test_summary_and_detail_are_never_contradictory_across_all_categories():
    # THE regression this phase exists to fix: EMA_HMPC_Status (the
    # compact summary, derived downstream from EMA_Status) must never
    # say "Listed" while EMA_Status/Notes (the detail) says not found.
    from standard_evidence_builder import classify_ema_hmpc_signal
    scenarios = {
        "exact_species_match": ["Zingoxylum arenosae radix"],
        "genus_only_match": ["Zingoxylum radix"],
        "related_species_only": ["Zingoxylum montanae folium"],
        "ambiguous_match": ["Zingoxylum radix", "Zingoxylum montanae folium"],
        "searched_not_found": [],
    }
    for expected_category, entries in scenarios.items():
        with _mock_inventory(entries):
            result = erc.search_regulatory_sources_real("Zingoxylum arenosum")
        record = result[0]
        assert record["Taxonomic_Match_Status"] == expected_category
        signal = classify_ema_hmpc_signal(record["EMA_Status"])
        if expected_category == "exact_species_match":
            assert signal == "inventory_listed"
        else:
            assert signal in ("searched_not_found", "unknown"), (
                f"{expected_category}: EMA_Status {record['EMA_Status']!r} resolved to "
                f"{signal!r}, which could still read as 'Listed' downstream"
            )


def test_source_unavailable_is_distinguished_from_parsing_failed():
    with mock.patch.object(erc, "_get_inventory", return_value=({}, [], "Could not fetch EMA inventory PDF: timeout")):
        result = erc.search_regulatory_sources_real("Zingoxylum arenosum")
    assert result[0]["Taxonomic_Match_Status"] == "source_unavailable"

    with mock.patch.object(erc, "_get_inventory", return_value=({}, [], "Fetched the PDF but could not parse any entries from it.")):
        result = erc.search_regulatory_sources_real("Zingoxylum arenosum")
    assert result[0]["Taxonomic_Match_Status"] == "parsing_failed"


def test_error_path_never_says_listed_either():
    with mock.patch.object(erc, "_get_inventory", return_value=({}, [], "Could not fetch EMA inventory PDF: timeout")):
        result = erc.search_regulatory_sources_real("Zingoxylum arenosum")
    assert "Listed" not in result[0]["EMA_Status"]


def test_every_returned_record_carries_taxonomic_match_status():
    # Additive-field guard: every branch of search_regulatory_sources_real
    # must populate the new field, never omit it.
    with _mock_inventory(["Zingoxylum arenosae radix"]):
        result = erc.search_regulatory_sources_real("Zingoxylum arenosum")
    assert "Taxonomic_Match_Status" in result[0]
    with _mock_inventory([]):
        result = erc.search_regulatory_sources_real("Zingoxylum arenosum")
    assert "Taxonomic_Match_Status" in result[0]
    with mock.patch.object(erc, "_get_inventory", return_value=({}, [], "Could not fetch EMA inventory PDF: timeout")):
        result = erc.search_regulatory_sources_real("Zingoxylum arenosum")
    assert "Taxonomic_Match_Status" in result[0]
