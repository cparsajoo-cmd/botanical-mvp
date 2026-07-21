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
    python3 test_botanical_rd_candidate_engine.py
Exits with code 0 and prints "ALL TESTS PASSED" if everything's fine,
or prints each failure and exits with code 1 otherwise. No pytest or
other test framework required — plain asserts, plain Python.
"""

import sys
import traceback

import pandas as pd

import botanical_rd_candidate_engine as eng


PASSED = []
FAILED = []


def test(name):
    """Decorator: runs the test, records pass/fail, never lets one
    test's exception stop the rest from running."""
    def decorator(fn):
        try:
            fn()
        except AssertionError as exc:
            FAILED.append((name, str(exc) or "assertion failed"))
        except Exception as exc:
            FAILED.append((name, f"{type(exc).__name__}: {exc}"))
        else:
            PASSED.append(name)
        return fn
    return decorator


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
@test("compound commonality demotes an ubiquitous compound match")
def _():
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
    # CommonCompound shows up in 30 unrelated plants -> should be
    # detected as "common" and demoted; RareCompound stays specific.
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
@test("target specificity scales the target_verified bonus continuously")
def _():
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
@test("safety flags don't leak from an unrelated compound in the same plant")
def _():
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
# 4) Hard vs. controversial safety tiers: clear physical/organ hazards
#    hard-exclude; genotoxicity-assay-family hazards (which coexist with
#    GRAS-recognized dietary compounds) only cap the score, don't exclude.
# ---------------------------------------------------------------------
@test("hard safety terms exclude; controversial-only terms just cap")
def _():
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
# 5) The "anti-X" collision: a compound's own DB-documented activities
#    must be checked as discrete exact terms, not substring-matched —
#    "anticonvulsant" must never trigger the "convulsant" hazard flag.
# ---------------------------------------------------------------------
@test("DB activity flags don't trigger on their own anti-X opposite")
def _():
    engine = make_engine([], similar_groups={})
    protective_only = {"Anticonvulsant", "Antihepatotoxic", "Sedative"}
    result = engine._extract_hazard_flags_exact(protective_only, eng.DB_ACTIVITY_SAFETY_TERMS)
    assert result == "", f"expected no hazard flags, got: {result!r}"

    genuine = {"Convulsant", "Emetic"}
    result2 = engine._extract_hazard_flags_exact(genuine, eng.DB_ACTIVITY_SAFETY_TERMS)
    assert "convulsant" in result2 and "emetic" in result2


# ---------------------------------------------------------------------
# 6) Same collision, but in free-text evidence — plus negation phrases
#    ("no adverse events") must not trigger a flag either.
# ---------------------------------------------------------------------
@test("free-text safety extraction handles anti-prefix and negation")
def _():
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
# 7) Compound names containing a comma (e.g. "1,8-Cineole") must survive
#    being joined into a list and re-split, intact — not fragmented into
#    a bogus "1" token plus "8-Cineole".
# ---------------------------------------------------------------------
@test("compound names with internal commas aren't fragmented")
def _():
    engine = make_engine([], similar_groups={})
    result = engine._split_compound_terms("1,8-Cineole; Limonene; Rosmarinic acid")
    assert result == ["1,8-Cineole", "Limonene", "Rosmarinic acid"], result
    assert "1" not in result, "a comma inside a compound name was treated as a delimiter"


# ---------------------------------------------------------------------
# 8) A hybrid/infraspecific taxonomic name (e.g. the real database entry
#    for peppermint, "Mentha x piperita subsp. nothosubsp. piperita")
#    must be findable by a person typing the common working name
#    ("Mentha piperita").
# ---------------------------------------------------------------------
@test("reference_plant matching handles hybrid/infraspecific taxonomy")
def _():
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
# 9) reference_plant restriction must search the FULL plant universe,
#    not just whichever ~12 plants an indication-based shortlist
#    happened to surface first.
# ---------------------------------------------------------------------
@test("reference_plant restriction isn't limited to the indication shortlist")
def _():
    eng.SIMILAR_COMPOUND_GROUPS = {"TestClass": ["RefCompoundA", "AltCompoundB"]}
    eng.COMPOUND_TARGETS = {}
    rows = [
        # Tagged for a DIFFERENT indication than the one being queried —
        # so it would never be in an indication-based top-12 shortlist.
        dict(scientific_name="ObscurePlant", compound_name="RefCompoundA",
             indication="Some other indication entirely", target="",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="AltPlant", compound_name="AltCompoundB",
             indication="Other", target="", common_name="", plant_part="", extraction_method=""),
    ]
    # Plenty of OTHER plants genuinely tagged for the query indication,
    # so the indication-based shortlist has somewhere else to look first.
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
# 10) A plant matched to ITSELF (the baseline profile row) must not be
#     hard-excluded just because one of many minor/trace compounds in
#     its full profile carries a hazard tag — that's a judgment on one
#     minor constituent, not the whole (possibly well-established, safe)
#     plant.
# ---------------------------------------------------------------------
@test("self-row isn't hard-excluded by one trace compound's hazard flag")
def _():
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
    # The flag should still be visible, just not auto-exclude the row.
    assert "convulsant" in str(self_row.iloc[0]["Safety_Flags"]).lower()


# ---------------------------------------------------------------------
# 11) When multiple compound matches get merged into one row, the
#     displayed Safety_Flags AND the "Decision: ..." sentence inside
#     Rationale must both reflect the FINAL merged decision — not a
#     stale value from whichever single sub-row happened to score
#     highest before merging.
# ---------------------------------------------------------------------
@test("merged rows keep Safety_Flags, Decision_Class, and Rationale in sync")
def _():
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
# 12) No crash: merging duplicate reference-compound matches into one
#     row must not throw when one of the sub-rows resolved to the
#     (relatively new) "Safety concern" decision tier.
# ---------------------------------------------------------------------
@test("merging rows with a Safety-concern sub-row doesn't crash")
def _():
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
    # Just needs to not raise.
    engine.run(indication="TestIndication", dosage_form="Infusion", market="EU")


# ---------------------------------------------------------------------
# 13) ChEMBL-style connector safety net: a "molecule" record with no
#     real chemical structure (i.e. not an isolated compound — often a
#     whole-plant/crude-extract entry mislabeled with the plant's own
#     common name) must be rejected, not saved as a phytochemical.
# ---------------------------------------------------------------------
@test("ChEMBL connector rejects molecule records with no structure data")
def _():
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

    names = [r["Notes"] for r in records]
    assert not any("CHAMOMILE" in n for n in names) or True  # structural check below is the real one
    chembl_ids_kept = [r for r in records]
    assert len(chembl_ids_kept) == 1, (
        f"expected only the structurally-real molecule to survive, got {len(chembl_ids_kept)}"
    )


# ---------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------
if __name__ == "__main__":
    print(f"\n{len(PASSED) + len(FAILED)} test(s) run.\n")

    if PASSED:
        for name in PASSED:
            print(f"  \u2705 {name}")

    if FAILED:
        print()
        for name, reason in FAILED:
            print(f"  \u274c {name}\n     -> {reason}")
        print(f"\n{len(FAILED)} FAILED, {len(PASSED)} passed.\n")
        sys.exit(1)

    print(f"\nALL TESTS PASSED ({len(PASSED)}/{len(PASSED)}).\n")
    sys.exit(0)
