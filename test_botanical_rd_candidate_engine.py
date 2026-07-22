"""
Regression test suite for botanical_rd_candidate_engine.py.

WHY THIS EXISTS
Over one long debugging session, ~20 real bugs were found and fixed in
this engine — several of them silent (no crash, no error message, just
subtly wrong scientific output) and each one took real back-and-forth
to notice, diagnose, and confirm fixed. This file turns every one of
those bugs into a permanent, fast (a few seconds, no network/Supabase
needed), repeatable check — so the NEXT time this file changes, it's
possible to know in seconds whether any of those bugs came back, instead
of re-discovering them one CSV export at a time.

WHAT THIS DOES NOT COVER
These are all synthetic-data unit tests of the ENGINE'S LOGIC — they
confirm the code behaves correctly given controlled inputs. They do NOT
confirm the real Dr. Duke's/Supabase data is clean, or that a specific
real plant (e.g. "does Matricaria chamomilla score well for real")
behaves as expected — that still requires periodically testing against
the live app with real data, the way the "known-answer validation"
round (chamomile/mint/milk thistle/aristolochia/comfrey/ginkgo) was done
earlier. Think of this file as the seatbelt for the ENGINE, not a
replacement for real-world spot checks.

HOW TO RUN
    pytest -q test_botanical_rd_candidate_engine.py
    (or just `pytest -q` from the repo root — this file is auto-discovered)

This file used to run its own hand-rolled pass/fail collector (a
module-level `test(name)` decorator wrapping anonymous `def _():`
bodies). That pattern never produced anything pytest could discover —
no function in the file matched pytest's default `test_*` collection
pattern, so `pytest -q` silently collected zero tests from it. Every
check below is now a real `def test_...():` function using plain
`assert`, which is exactly what pytest is built to collect and report
on — no custom runner, no fixtures beyond pytest's own, nothing else
needed.
"""

import pandas as pd

try:
    import pytest
except ImportError:
    pytest = None

import botanical_rd_candidate_engine as eng


def make_engine(rows, similar_groups=None, compound_targets=None):
    """Builds an engine from a list of plant_compounds-shaped dicts,
    with enough unrelated background rows added that frequency-based
    statistics (compound commonality, target genericity) behave the way
    they would on a real, larger database rather than degenerating to
    the tiny-sample edge case."""
    if similar_groups is not None:
        eng.SIMILAR_COMPOUND_GROUPS = similar_groups
    if compound_targets is not None:
        eng.COMPOUND_TARGETS = compound_targets

    background = [
        dict(scientific_name=f"Bg{i}", compound_name=f"BgCompound{i}",
             indication="background", target="Antioxidant",
             common_name="", plant_part="", extraction_method="")
        for i in range(25)
    ]

    df = pd.DataFrame(list(rows) + background)
    return eng.BotanicalRDCandidateEngine(
        plant_compounds_df=df,
        compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(),
        use_live_search=False,
    )


# ---------------------------------------------------------------------
# 1) Ubiquitous compounds (the original "Quercetin problem") must not
#    dominate results just because they're common everywhere.
# ---------------------------------------------------------------------
def test_compound_commonality_demotes_an_ubiquitous_compound_match():
    rows = [
        dict(scientific_name="PlantRef", compound_name="CommonCompound",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="PlantRef", compound_name="RareCompound",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="PlantAltRare", compound_name="RareCompound",
             indication="Other", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
    ]
    for i in range(30):
        rows.append(dict(scientific_name=f"CommonHost{i}", compound_name="CommonCompound",
                          indication="unrelated", target="",
                          common_name="", plant_part="", extraction_method=""))

    engine = make_engine(rows, similar_groups={})
    result = engine.run(indication="TestIndication", dosage_form="Infusion", market="EU")

    common_row = result[result["Alternative_Plant"].astype(str).str.startswith("CommonHost")]
    rare_row = result[result["Alternative_Plant"] == "PlantAltRare"]

    assert not rare_row.empty, "expected the rare-compound alt candidate to appear"
    if not common_row.empty:
        assert (
            common_row.iloc[0]["R&D_Opportunity_Score"]
            < rare_row.iloc[0]["R&D_Opportunity_Score"]
        ), "a compound common to 30+ plants scored >= a genuinely rare match"


# ---------------------------------------------------------------------
# 2) A shared target confirmation is only as strong as how specific
#    that target actually is (not a hard cutoff — a smooth decay).
# ---------------------------------------------------------------------
def test_target_specificity_scales_the_target_verified_bonus_continuously():
    eng.SIMILAR_COMPOUND_GROUPS = {"TestClass": ["RefCompound", "SpecificAlt", "GenericAlt"]}
    eng.COMPOUND_TARGETS = {
        "RefCompound": ["GenericPathway", "RareSpecificTarget"],
        "SpecificAlt": ["GenericPathway", "RareSpecificTarget"],
        "GenericAlt": ["GenericPathway"],
        "Filler1": ["GenericPathway"], "Filler2": ["GenericPathway"],
        "Filler3": ["GenericPathway"], "Filler4": ["GenericPathway"],
        "Filler5": ["GenericPathway"], "Filler6": ["GenericPathway"],
    }
    rows = [
        dict(scientific_name="PlantRef", compound_name="RefCompound",
             indication="TestIndication", target="", common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="PlantSpecific", compound_name="SpecificAlt",
             indication="Other", target="", common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="PlantGeneric", compound_name="GenericAlt",
             indication="Other", target="", common_name="", plant_part="", extraction_method=""),
    ]
    engine = make_engine(rows)
    result = engine.run(indication="TestIndication", dosage_form="Infusion", market="EU")

    specific_row = result[result["Alternative_Plant"] == "PlantSpecific"]
    generic_row = result[result["Alternative_Plant"] == "PlantGeneric"]
    assert not specific_row.empty and not generic_row.empty
    assert (
        specific_row.iloc[0]["R&D_Opportunity_Score"]
        > generic_row.iloc[0]["R&D_Opportunity_Score"]
    ), "a match via a rare shared target should outscore a match via a generic pathway"


# ---------------------------------------------------------------------
# 3) Safety flags must be scoped to the MATCHED compound only, never
#    contaminated by an unrelated compound elsewhere in the same plant.
# ---------------------------------------------------------------------
def test_safety_flags_dont_leak_from_an_unrelated_compound_in_the_same_plant():
    eng.SIMILAR_COMPOUND_GROUPS = {"TestClass": ["RefClassCompound", "InnocentClassCompound"]}
    eng.COMPOUND_TARGETS = {}
    rows = [
        dict(scientific_name="PlantRef", compound_name="RefClassCompound",
             indication="TestIndication", target="Laxative", common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="AltPlantInnocent", compound_name="InnocentClassCompound",
             indication="Other", target="Antioxidant", common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="AltPlantInnocent", compound_name="SomeUnrelatedCompound",
             indication="Other", target="Carcinogenic", common_name="", plant_part="", extraction_method=""),
    ]
    engine = make_engine(rows)
    result = engine.run(indication="TestIndication", dosage_form="Infusion", market="EU")
    row = result[result["Alternative_Plant"] == "AltPlantInnocent"]
    assert not row.empty
    assert "carcinogenic" not in str(row.iloc[0]["Safety_Flags"]).lower(), (
        "an unrelated compound's hazard tag leaked into a different compound's match"
    )


# ---------------------------------------------------------------------
# 4) Hard vs. controversial safety tiers.
# ---------------------------------------------------------------------
def test_hard_safety_terms_exclude_controversial_only_terms_just_cap():
    d1 = eng.BotanicalRDCandidateEngine._decision_class(
        None, score=80, safety_flags="lithogenic", interaction_flags="",
        has_evidence=True, match_quality="exact", evidence_level="Clinical / human evidence",
    )
    assert d1 == "Safety concern — not suitable without expert review"

    d2 = eng.BotanicalRDCandidateEngine._decision_class(
        None, score=80, safety_flags="carcinogenic; mutagenic", interaction_flags="",
        has_evidence=True, match_quality="exact", evidence_level="Clinical / human evidence",
    )
    assert d2 != "Safety concern — not suitable without expert review", (
        "carcinogenic/mutagenic alone should not hard-exclude"
    )


# ---------------------------------------------------------------------
# 5) The "anti-X" collision.
# ---------------------------------------------------------------------
def test_db_activity_flags_dont_trigger_on_their_own_anti_x_opposite():
    engine = make_engine([], similar_groups={})
    protective_only = {"Anticonvulsant", "Antihepatotoxic", "Sedative"}
    result = engine._extract_hazard_flags_exact(protective_only, eng.DB_ACTIVITY_SAFETY_TERMS)
    assert result == "", f"expected no hazard flags, got: {result!r}"

    genuine = {"Convulsant", "Emetic"}
    result2 = engine._extract_hazard_flags_exact(genuine, eng.DB_ACTIVITY_SAFETY_TERMS)
    assert "convulsant" in result2 and "emetic" in result2


# ---------------------------------------------------------------------
# 6) Same collision, but in free-text evidence — plus negation phrases.
# ---------------------------------------------------------------------
def test_free_text_safety_extraction_handles_anti_prefix_and_negation():
    engine = make_engine([], similar_groups={})
    cases = [
        ("No adverse events were reported.", False),
        ("Significant adverse effects on the liver were noted.", True),
        ("The extract showed antitoxic properties in the assay.", False),
        ("High doses caused toxic reactions.", True),
        ("No contraindications have been identified.", False),
    ]
    for text, should_flag in cases:
        result = engine._extract_flags_negation_aware(text, eng.SAFETY_TERMS)
        got_flag = bool(result)
        assert got_flag == should_flag, (
            f"text={text!r} expected flag={should_flag} got={got_flag} ({result!r})"
        )


# ---------------------------------------------------------------------
# 7) Compound names containing a comma must survive intact.
# ---------------------------------------------------------------------
def test_compound_names_with_internal_commas_arent_fragmented():
    engine = make_engine([], similar_groups={})
    result = engine._split_compound_terms("1,8-Cineole; Limonene; Rosmarinic acid")
    assert result == ["1,8-Cineole", "Limonene", "Rosmarinic acid"], result
    assert "1" not in result, "a comma inside a compound name was treated as a delimiter"


# ---------------------------------------------------------------------
# 8) Hybrid/infraspecific taxonomic name matching.
# ---------------------------------------------------------------------
def test_reference_plant_matching_handles_hybrid_infraspecific_taxonomy():
    eng.SIMILAR_COMPOUND_GROUPS = {"TestClass": ["RefCompoundX", "AltCompoundY"]}
    eng.COMPOUND_TARGETS = {}
    rows = [
        dict(scientific_name="Mentha x piperita subsp. nothosubsp. piperita",
             compound_name="RefCompoundX", indication="TestIndication", target="",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="AltPlant", compound_name="AltCompoundY",
             indication="Other", target="", common_name="", plant_part="", extraction_method=""),
    ]
    engine = make_engine(rows)
    result = engine.run(
        indication="TestIndication", dosage_form="Infusion", market="EU",
        reference_plant="Mentha piperita",
    )
    assert not result.empty, "a hybrid taxon wasn't found by its common working name"
    assert (result["Reference_Plant"] == "Mentha x piperita subsp. nothosubsp. piperita").any()


# ---------------------------------------------------------------------
# 9) reference_plant restriction must search the FULL plant universe.
# ---------------------------------------------------------------------
def test_reference_plant_restriction_isnt_limited_to_the_indication_shortlist():
    eng.SIMILAR_COMPOUND_GROUPS = {"TestClass": ["RefCompoundA", "AltCompoundB"]}
    eng.COMPOUND_TARGETS = {}
    rows = [
        dict(scientific_name="ObscurePlant", compound_name="RefCompoundA",
             indication="Some other indication entirely", target="",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="AltPlant", compound_name="AltCompoundB",
             indication="Other", target="", common_name="", plant_part="", extraction_method=""),
    ]
    for i in range(15):
        rows.append(dict(scientific_name=f"Decoy{i}", compound_name=f"DecoyCompound{i}",
                          indication="TestIndication", target="",
                          common_name="", plant_part="", extraction_method=""))

    engine = make_engine(rows)
    result = engine.run(
        indication="TestIndication", dosage_form="Infusion", market="EU",
        reference_plant="ObscurePlant",
    )
    assert not result.empty, "reference_plant restriction failed to find a plant outside the shortlist"


# ---------------------------------------------------------------------
# 10) Self-row must not be hard-excluded by one trace compound's flag.
# ---------------------------------------------------------------------
def test_self_row_isnt_hard_excluded_by_one_trace_compounds_hazard_flag():
    eng.SIMILAR_COMPOUND_GROUPS = {}
    eng.COMPOUND_TARGETS = {}
    rows = [
        dict(scientific_name="TestPlant", compound_name="MainActiveCompound",
             indication="TestIndication", target="Hepatoprotective",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="TestPlant", compound_name="TraceCompound",
             indication="TestIndication", target="Abortifacient; Convulsant",
             common_name="", plant_part="", extraction_method=""),
    ]
    engine = make_engine(rows)
    result = engine.run(indication="TestIndication", dosage_form="Infusion", market="EU")
    self_row = result[
        (result["Reference_Plant"] == "TestPlant") & (result["Alternative_Plant"] == "TestPlant")
    ]
    assert not self_row.empty
    assert self_row.iloc[0]["Decision_Class"] != "Safety concern — not suitable without expert review"
    assert "convulsant" in str(self_row.iloc[0]["Safety_Flags"]).lower()


# ---------------------------------------------------------------------
# 11) Merged rows keep Safety_Flags, Decision_Class, and Rationale in sync.
# ---------------------------------------------------------------------
def test_merged_rows_keep_safety_flags_decision_class_and_rationale_in_sync():
    eng.SIMILAR_COMPOUND_GROUPS = {"TestClass": ["RefCompoundA", "RefCompoundB", "AltCompound"]}
    eng.COMPOUND_TARGETS = {}
    rows = [
        dict(scientific_name="PlantRef", compound_name="RefCompoundA",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="PlantRef", compound_name="RefCompoundB",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="AltPlant", compound_name="AltCompound",
             indication="Other", target="Lithogenic",
             common_name="", plant_part="", extraction_method=""),
    ]
    engine = make_engine(rows)
    result = engine.run(indication="TestIndication", dosage_form="Infusion", market="EU")
    row = result[result["Alternative_Plant"] == "AltPlant"]
    assert not row.empty
    r = row.iloc[0]
    assert r["Decision_Class"] == "Safety concern — not suitable without expert review"
    assert "lithogenic" in str(r["Safety_Flags"]).lower(), (
        "Decision_Class says Safety concern but Safety_Flags doesn't show why"
    )
    assert f"Decision: {r['Decision_Class']}." in str(r["Rationale"]), (
        "Rationale's trailing 'Decision: ...' sentence doesn't match the final Decision_Class"
    )


# ---------------------------------------------------------------------
# 12) No crash when merging rows with a Safety-concern sub-row.
# ---------------------------------------------------------------------
def test_merging_rows_with_a_safety_concern_sub_row_doesnt_crash():
    eng.SIMILAR_COMPOUND_GROUPS = {"TestClass": ["RefCompoundA", "RefCompoundC", "AltCompound"]}
    eng.COMPOUND_TARGETS = {}
    rows = [
        dict(scientific_name="RefPlantA", compound_name="RefCompoundA",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="RefPlantA", compound_name="RefCompoundC",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="AltPlant", compound_name="AltCompound",
             indication="Other", target="Lithogenic",
             common_name="", plant_part="", extraction_method=""),
    ]
    engine = make_engine(rows)
    engine.run(indication="TestIndication", dosage_form="Infusion", market="EU")


# ---------------------------------------------------------------------
# 13) A common-compound sub-row can't single-handedly cap a strong
#     multi-compound match.
# ---------------------------------------------------------------------
def test_a_common_compound_sub_row_cant_single_handedly_cap_a_strong_multi_match():
    engine = make_engine([], similar_groups={})

    strong_row = dict(
        Reference_Plant="RefPlant", Alternative_Plant="AltPlant",
        Reference_Compound="RareCompoundA", Shared_or_Similar_Compound="RareCompoundA",
        Safety_Flags="No explicit flag found", Interaction_Flags="No explicit flag found",
        Decision_Class="Strong R&D candidate",
        Novelty_Status="Novel cross-region candidate", Rationale="... Decision: Strong R&D candidate.",
    )
    strong_row["R&D_Opportunity_Score"] = 90

    weak_common_row = dict(
        Reference_Plant="RefPlant", Alternative_Plant="AltPlant",
        Reference_Compound="CommonCompoundB", Shared_or_Similar_Compound="CommonCompoundB",
        Safety_Flags="No explicit flag found", Interaction_Flags="No explicit flag found",
        Decision_Class="Low priority / insufficient data",
        Novelty_Status="Common/non-specific compound — found in 50+ plants database-wide, low differentiation value",
        Rationale="... Decision: Low priority / insufficient data.",
    )
    weak_common_row["R&D_Opportunity_Score"] = 20

    output = pd.DataFrame([strong_row, weak_common_row])
    merged = engine._merge_multi_compound_matches(output)

    assert len(merged) == 1
    result_decision = merged.iloc[0]["Decision_Class"]
    assert result_decision != "Low priority / insufficient data", (
        f"a common/non-specific sub-row alone dragged a strong multi-compound match down "
        f"to '{result_decision}'"
    )

    both_common = output.copy()
    both_common.loc[0, "Novelty_Status"] = "Common/non-specific compound — found in 40+ plants database-wide"
    merged_both_common = engine._merge_multi_compound_matches(both_common)
    assert merged_both_common.iloc[0]["Decision_Class"] == "Low priority / insufficient data", (
        "when EVERY sub-row is common/non-specific, the conservative cap should still apply"
    )


# ---------------------------------------------------------------------
# 15) _extract_concentration (Phase 4, audit 4.10) must return "" — not
#     a placeholder string — when nothing is found, since the score
#     bonus and two display fallbacks elsewhere in the engine rely on
#     that falsiness. And when text mixes two different concentration
#     bases, the result must say so explicitly rather than silently
#     joining them as if they were on equal footing.
# ---------------------------------------------------------------------
def test_extract_concentration_stays_falsy_when_empty_and_flags_mixed_bases():
    engine = make_engine([], similar_groups={})

    assert engine._extract_concentration("no numbers in this text at all") == ""
    assert engine._extract_concentration("") == ""

    mixed = engine._extract_concentration(
        "One study reported 2 mg/g dry weight while another reported 5% total extract."
    )
    assert mixed.startswith("Not directly comparable"), mixed

    single_basis = engine._extract_concentration(
        "Two batches: 2 mg/g dry weight and 6 mg/g dry weight."
    )
    assert "Not directly comparable" not in single_basis, single_basis


# ---------------------------------------------------------------------
# 16) Evidence_Hierarchy_Detail (Phase 4, audit 4.14) must actually show
#     up end-to-end through engine.run() and distinguish a real RCT from
#     a run-of-the-mill literature mention — not just work in isolation
#     on the classifier module.
# ---------------------------------------------------------------------
def test_evidence_hierarchy_detail_is_populated_end_to_end_through_run():
    eng.SIMILAR_COMPOUND_GROUPS = {}
    eng.COMPOUND_TARGETS = {}
    rows = [
        dict(scientific_name="TestPlant", compound_name="ActiveCompound",
             indication="TestIndication", target="Hepatoprotective",
             common_name="", plant_part="", extraction_method=""),
    ]
    engine = make_engine(rows)
    # Feed a live-search-shaped evidence_df so raw_evidence text actually
    # reaches _evidence_level / classify_evidence_hierarchy — a bare
    # plant_compounds row alone has no free-text evidence to classify.
    evidence_df = pd.DataFrame([{
        "Scientific_Name": "TestPlant",
        "Target_Indication": "TestIndication",
        "Notes": (
            "A randomized controlled trial, double-blind and "
            "placebo-controlled, found significant hepatoprotective effects."
        ),
    }])
    engine_with_evidence = make_engine(rows)
    engine_with_evidence.evidence_df = evidence_df
    result = engine_with_evidence.run(indication="TestIndication", dosage_form="Infusion", market="EU")

    assert "Evidence_Hierarchy_Detail" in result.columns
    self_row = result[
        (result["Reference_Plant"] == "TestPlant") & (result["Alternative_Plant"] == "TestPlant")
    ]
    assert not self_row.empty
    # Whatever the exact value, it must be a real classification, not a
    # silently-empty/missing column.
    assert self_row.iloc[0]["Evidence_Hierarchy_Detail"] != ""


# ---------------------------------------------------------------------
# 17) Negative evidence (Phase 4, audit 4.15) hiding in a non-best
#     sub-row must survive the multi-compound merge — the same
#     reasoning already applied to Safety_Flags/Interaction_Flags.
#     Also confirms Evidence_Hierarchy_Detail/negative-evidence columns
#     are populated end-to-end through engine.run().
# ---------------------------------------------------------------------
def test_negative_evidence_in_a_non_best_sub_row_survives_the_merge():
    engine = make_engine([], similar_groups={})

    strong_row_no_negative = dict(
        Reference_Plant="RefPlant", Alternative_Plant="AltPlant",
        Reference_Compound="RareCompoundA", Shared_or_Similar_Compound="RareCompoundA",
        Safety_Flags="No explicit flag found", Interaction_Flags="No explicit flag found",
        Decision_Class="Strong R&D candidate",
        Novelty_Status="Novel cross-region candidate", Rationale="... Decision: Strong R&D candidate.",
        Has_Negative_Evidence=False, Negative_Evidence_Types="",
    )
    strong_row_no_negative["R&D_Opportunity_Score"] = 90

    weaker_row_with_negative = dict(
        Reference_Plant="RefPlant", Alternative_Plant="AltPlant",
        Reference_Compound="RareCompoundB", Shared_or_Similar_Compound="RareCompoundB",
        Safety_Flags="No explicit flag found", Interaction_Flags="No explicit flag found",
        Decision_Class="Early-stage candidate; more evidence needed",
        Novelty_Status="Novel cross-region candidate", Rationale="... Decision: Early-stage candidate; more evidence needed.",
        Has_Negative_Evidence=True, Negative_Evidence_Types="Null result",
    )
    weaker_row_with_negative["R&D_Opportunity_Score"] = 50

    output = pd.DataFrame([strong_row_no_negative, weaker_row_with_negative])
    merged = engine._merge_multi_compound_matches(output)

    assert len(merged) == 1
    assert bool(merged.iloc[0]["Has_Negative_Evidence"]) is True, (
        "negative evidence on a lower-scoring sub-row silently disappeared after merging"
    )
    assert "Null result" in str(merged.iloc[0]["Negative_Evidence_Types"])


# ---------------------------------------------------------------------
# 18) ChEMBL connector rejects molecule records with no structure data.
# ---------------------------------------------------------------------
def test_chembl_connector_rejects_molecule_records_with_no_structure_data():
    import chembl_connector

    class _FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "molecules": [
                    {"pref_name": "CHAMOMILE", "molecule_chembl_id": "CHEMBL0",
                     "molecule_structures": None},
                    {"pref_name": "Apigenin", "molecule_chembl_id": "CHEMBL1",
                     "molecule_structures": {"canonical_smiles": "c1ccccc1"}},
                ]
            }

    orig_get = chembl_connector.requests.get
    chembl_connector.requests.get = lambda *a, **k: _FakeResponse()
    try:
        records = chembl_connector.search_chembl("Matricaria chamomilla", "Test")
    finally:
        chembl_connector.requests.get = orig_get

    chembl_ids_kept = [r for r in records]
    assert len(chembl_ids_kept) == 1, (
        f"expected only the structurally-real molecule to survive, got {len(chembl_ids_kept)}"
    )
    assert not any("CHAMOMILE" in r["Notes"] for r in records), (
        "a whole-plant record with no real chemical structure survived as a phytochemical"
    )


# ---------------------------------------------------------------------
# Direct-execution fallback: `python3 test_botanical_rd_candidate_engine.py`
# still works with no pytest installed (useful with no local Python
# environment to pip install into) by delegating to pytest.main() when
# pytest is importable, and otherwise falling back to a plain
# introspection-based runner over every real test_* function here.
# ---------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    if pytest is not None:
        sys.exit(pytest.main([__file__, "-v"]))
    else:
        this_module = sys.modules[__name__]
        test_fns = [
            getattr(this_module, name)
            for name in dir(this_module)
            if name.startswith("test_") and callable(getattr(this_module, name))
        ]
        passed, failed = [], []
        for fn in test_fns:
            try:
                fn()
            except AssertionError as exc:
                failed.append((fn.__name__, str(exc) or "assertion failed"))
            except Exception as exc:  # noqa: BLE001
                failed.append((fn.__name__, f"{type(exc).__name__}: {exc}"))
            else:
                passed.append(fn.__name__)

        print(f"\n{len(passed) + len(failed)} test(s) run.\n")
        for name in passed:
            print(f"  \u2705 {name}")
        if failed:
            print()
            for name, reason in failed:
                print(f"  \u274c {name}\n     -> {reason}")
            print(f"\n{len(failed)} FAILED, {len(passed)} passed.\n")
            sys.exit(1)
        print(f"\nALL TESTS PASSED ({len(passed)}/{len(passed)}).\n")
        sys.exit(0)
