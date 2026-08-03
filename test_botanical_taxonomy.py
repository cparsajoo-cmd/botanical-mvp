"""Tests for the taxonomic synonym canonicalization layer.

Covers:
1. synonym collapse across different origins (candidate_selection.py
   integration),
2. provenance preservation (contributing_original_names / contributing_origins),
3. accepted name used in the final selected list,
4. aliases retained for literature query generation,
5. unrelated plants are not merged,
6. deterministic behavior.
"""
import botanical_taxonomy as tax
import candidate_selection as cs


# ---------------------------------------------------------------------
# Module-level behavior
# ---------------------------------------------------------------------

def test_accepted_name_resolves_known_synonym():
    assert tax.accepted_name("Cimicifuga racemosa") == "Actaea racemosa"
    assert tax.accepted_name("actaea racemosa") == "Actaea racemosa"


def test_accepted_name_unmapped_plant_returned_unchanged():
    assert tax.accepted_name("Some Unmapped Plant") == "Some Unmapped Plant"


def test_is_synonym_true_only_for_non_accepted_alias():
    assert tax.is_synonym("Cimicifuga racemosa") is True
    assert tax.is_synonym("Actaea racemosa") is False
    assert tax.is_synonym("Unmapped Plant") is False


def test_all_aliases_includes_accepted_name_and_synonyms():
    aliases = tax.all_aliases("Cimicifuga racemosa")
    normalized = {a.lower() for a in aliases}
    assert "actaea racemosa" in normalized
    assert "cimicifuga racemosa" in normalized


def test_all_aliases_unmapped_plant_returns_just_itself():
    assert tax.all_aliases("Totally Unmapped Plant") == ["Totally Unmapped Plant"]


def test_taxon_provenance_structure():
    provenance = tax.taxon_provenance("Cimicifuga racemosa")
    assert provenance["submitted_name"] == "Cimicifuga racemosa"
    assert provenance["accepted_name"] == "Actaea racemosa"
    assert provenance["is_synonym"] is True
    assert provenance["source"] == "internal_curated_mapping"


def test_registered_source_takes_priority_over_curated_mapping():
    from general_indication_relevance import normalize_text
    custom_record = tax.TaxonRecord(
        accepted_name="Custom Accepted Name",
        synonyms=("Custom Synonym Plant",),
        source="test_registered_source",
    )
    tax.register_taxon_source({normalize_text("Custom Synonym Plant"): custom_record})
    try:
        assert tax.accepted_name("Custom Synonym Plant") == "Custom Accepted Name"
    finally:
        tax._EXTRA_SOURCES.clear()  # test cleanup, not production code


# ---------------------------------------------------------------------
# 1 & 3. synonym collapse across origins; accepted name in final list
# ---------------------------------------------------------------------

def test_synonym_collapse_across_different_origins():
    seed = cs.make_candidate("Actaea racemosa", cs.ORIGIN_REFERENCE_SEED, score=2)
    literature = cs.make_candidate(
        "Cimicifuga racemosa", cs.ORIGIN_VALIDATED_LITERATURE, score=20,
        evidence_status=cs.STATUS_VALIDATED_DIRECT,
    )
    fallback = cs.make_candidate("actaea racemosa", cs.ORIGIN_RANKED_FALLBACK, score=1)

    merged = cs.merge_candidates([seed, literature, fallback])
    assert len(merged) == 1
    assert merged[0].name == "Actaea racemosa"
    assert merged[0].evidence_status == cs.STATUS_VALIDATED_DIRECT


def test_final_selected_list_contains_one_accepted_taxon_only():
    records = [
        cs.make_candidate("Actaea racemosa", cs.ORIGIN_REFERENCE_SEED, score=2),
        cs.make_candidate(
            "Cimicifuga racemosa", cs.ORIGIN_VALIDATED_LITERATURE, score=20,
            evidence_status=cs.STATUS_VALIDATED_DIRECT,
        ),
    ]
    selected, diagnostics = cs.select_candidates(records, requested_count=5)
    names = [r.name for r in selected]
    assert names.count("Actaea racemosa") == 1
    assert "Cimicifuga racemosa" not in names
    assert diagnostics["deduplicated_candidate_count"] == 1


# ---------------------------------------------------------------------
# 2. provenance preservation
# ---------------------------------------------------------------------

def test_provenance_preserves_all_contributing_original_names_and_origins():
    records = [
        cs.make_candidate("Actaea racemosa", cs.ORIGIN_REFERENCE_SEED, score=2),
        cs.make_candidate(
            "Cimicifuga racemosa", cs.ORIGIN_VALIDATED_LITERATURE, score=20,
            evidence_status=cs.STATUS_VALIDATED_DIRECT,
        ),
    ]
    selected, diagnostics = cs.select_candidates(records, requested_count=5)
    provenance = diagnostics["candidate_provenance"]["Actaea racemosa"]
    assert set(provenance["contributing_original_names"]) == {
        "Actaea racemosa", "Cimicifuga racemosa",
    }
    assert set(provenance["contributing_origins"]) == {
        cs.ORIGIN_REFERENCE_SEED, cs.ORIGIN_VALIDATED_LITERATURE,
    }


# ---------------------------------------------------------------------
# 4. aliases retained for literature query generation
# ---------------------------------------------------------------------

def test_aliases_available_for_literature_query_generation():
    # A caller building literature-search queries can still search under
    # BOTH the accepted name and its synonym(s) -- canonicalization for
    # dedup/selection purposes does not erase the alias list.
    aliases = tax.all_aliases("Actaea racemosa")
    normalized = {a.lower() for a in aliases}
    assert "actaea racemosa" in normalized
    assert "cimicifuga racemosa" in normalized
    # Works starting from the synonym too.
    aliases_from_synonym = tax.all_aliases("Cimicifuga racemosa")
    assert set(a.lower() for a in aliases_from_synonym) == normalized


# ---------------------------------------------------------------------
# 5. unrelated plants not merged
# ---------------------------------------------------------------------

def test_unrelated_plants_are_not_merged():
    records = [
        cs.make_candidate("Actaea racemosa", cs.ORIGIN_REFERENCE_SEED, score=2),
        cs.make_candidate("Valeriana officinalis", cs.ORIGIN_REFERENCE_SEED, score=2),
        cs.make_candidate("Melissa officinalis", cs.ORIGIN_RANKED_FALLBACK, score=1),
    ]
    merged = cs.merge_candidates(records)
    assert len(merged) == 3
    assert {r.name for r in merged} == {
        "Actaea racemosa", "Valeriana officinalis", "Melissa officinalis",
    }


# ---------------------------------------------------------------------
# 6. deterministic behavior
# ---------------------------------------------------------------------

def test_synonym_collapse_is_deterministic_regardless_of_input_order():
    seed = cs.make_candidate("Actaea racemosa", cs.ORIGIN_REFERENCE_SEED, score=2)
    literature = cs.make_candidate(
        "Cimicifuga racemosa", cs.ORIGIN_VALIDATED_LITERATURE, score=20,
        evidence_status=cs.STATUS_VALIDATED_DIRECT,
    )

    first = cs.merge_candidates([seed, literature])
    second = cs.merge_candidates([literature, seed])

    assert first[0].name == second[0].name == "Actaea racemosa"
    assert first[0].evidence_status == second[0].evidence_status == cs.STATUS_VALIDATED_DIRECT
    assert (
        sorted(first[0].score_components["contributing_original_names"])
        == sorted(second[0].score_components["contributing_original_names"])
    )
