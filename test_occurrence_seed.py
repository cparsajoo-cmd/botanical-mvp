"""
Task 7 — Populating data_contracts.PlantCompoundOccurrence.

WHAT THIS COVERS
occurrence_seed.py's derivation from seed_data.py, and
BotanicalRDCandidateEngine._best_extraction()'s use of it. The two
non-negotiable guarantees: (1) every occurrence record is traceable to
seed_data.py's own existing data — no new botanical claim is invented
anywhere in this task, and (2) _best_extraction() is byte-identical to
its pre-Task-7 behavior whenever no structured occurrence is populated
for the (plant, compound) pair in question.

HOW TO RUN
    pytest -q test_occurrence_seed.py
"""

import botanical_rd_candidate_engine as eng
from data_contracts import VerificationStatus
from occurrence_seed import (
    SOURCE_LABEL,
    _norm,
    build_occurrence_lookup,
    load_occurrence_records,
)
from seed_data import PLANT_COMPOUNDS, PLANTS
from test_botanical_rd_candidate_engine import make_engine


# ---------------------------------------------------------------------
# load_occurrence_records / build_occurrence_lookup — traceability to
# seed_data.py's own existing data, no new claims invented.
# ---------------------------------------------------------------------

def test_every_occurrence_record_traces_to_a_real_plant_compounds_entry():
    records = load_occurrence_records()
    assert len(records) > 0
    for occurrence in records:
        compounds = PLANT_COMPOUNDS.get(occurrence.plant_scientific_name)
        assert compounds is not None, f"{occurrence.plant_scientific_name} not in seed_data.PLANT_COMPOUNDS"
        matching = [c for c in compounds if c[0] == occurrence.compound_id]
        assert matching, f"{occurrence.compound_id} not listed for {occurrence.plant_scientific_name}"
        # The extraction hint itself must be exactly the seed tuple's
        # own third element — never reworded, never invented.
        assert occurrence.extraction_solvent == matching[0][2]


def test_occurrence_records_only_include_entries_with_a_non_empty_extraction_hint():
    records = load_occurrence_records()
    for occurrence in records:
        assert occurrence.extraction_solvent


def test_plant_part_comes_from_seed_data_plants_not_invented():
    plant_parts = {p[0]: p[4] for p in PLANTS}
    records = load_occurrence_records()
    checked = 0
    for occurrence in records:
        if occurrence.plant_part is not None:
            assert occurrence.plant_part == plant_parts.get(occurrence.plant_scientific_name)
            checked += 1
    assert checked > 0


def test_no_record_claims_verified_or_scored_confidence():
    # This is a structural re-derivation of an internal seed dataset,
    # not an independently verified/confidence-scored claim — every
    # record must say so honestly.
    records = load_occurrence_records()
    for occurrence in records:
        assert occurrence.verification_status == VerificationStatus.UNKNOWN
        assert occurrence.confidence is None
        assert occurrence.study_or_source == SOURCE_LABEL


def test_record_count_matches_seed_data_entries_with_extraction_hints():
    expected = sum(
        1 for compounds in PLANT_COMPOUNDS.values() for _n, _c, ext in compounds if ext
    )
    assert len(load_occurrence_records()) == expected


def test_build_occurrence_lookup_keys_are_normalized():
    lookup = build_occurrence_lookup()
    for plant, compounds in PLANT_COMPOUNDS.items():
        for compound_name, _cls, extraction in compounds:
            if extraction:
                assert (_norm(plant), _norm(compound_name)) in lookup


def test_norm_matches_engine_norm_algorithm():
    # occurrence_seed._norm() is a deliberate duplicate of
    # BotanicalRDCandidateEngine._norm() (see occurrence_seed.py's own
    # docstring on why) — this test is the guardrail that the two
    # never silently diverge.
    for raw in ["  Matricaria   chamomilla ", "NaN", None, "Bisabolol", "none", ""]:
        assert _norm(raw) == eng.BotanicalRDCandidateEngine._norm(raw)


# ---------------------------------------------------------------------
# _structured_occurrence / _best_extraction wiring
# ---------------------------------------------------------------------

def test_structured_occurrence_returns_none_for_unknown_pair():
    result = eng.BotanicalRDCandidateEngine._structured_occurrence("Unknown Plant", "Unknown Compound")
    assert result is None


def test_structured_occurrence_returns_none_when_either_argument_is_missing():
    assert eng.BotanicalRDCandidateEngine._structured_occurrence(None, "Bisabolol") is None
    assert eng.BotanicalRDCandidateEngine._structured_occurrence("Matricaria chamomilla", None) is None


def test_structured_occurrence_finds_a_real_seeded_pair():
    result = eng.BotanicalRDCandidateEngine._structured_occurrence("Matricaria chamomilla", "Bisabolol")
    assert result is not None
    assert result.extraction_solvent == "Steam distillation"
    assert result.plant_part == "Flower heads"


def test_best_extraction_backward_compatible_when_no_structured_occurrence_exists():
    # Byte-identical to pre-Task-7 behavior: no alt_plant/matched_compound
    # given, or given but unknown to occurrence_seed — falls straight
    # through to the pre-existing free-text/row logic.
    engine = make_engine([dict(
        scientific_name="RefPlant", compound_name="CompoundX", indication="I",
        target="T", common_name="", plant_part="", extraction_method="Cold-pressed",
    )])
    alt_row = {"Extraction_Method": "Cold-pressed"}
    result_no_args = engine._best_extraction(alt_row, "some evidence text with ethanol mentioned")
    result_unknown_pair = engine._best_extraction(
        alt_row, "some evidence text with ethanol mentioned",
        alt_plant="Totally Unknown Plant", matched_compound="Totally Unknown Compound",
    )
    assert result_no_args == result_unknown_pair


def test_best_extraction_prefers_structured_occurrence_when_present():
    engine = make_engine([dict(
        scientific_name="RefPlant", compound_name="Bisabolol", indication="I",
        target="T", common_name="", plant_part="", extraction_method="",
    )])
    alt_row = {"Extraction_Method": ""}  # deliberately empty — structured value must still surface
    result = engine._best_extraction(
        alt_row, "", alt_plant="Matricaria chamomilla", matched_compound="Bisabolol",
    )
    assert result == "Steam distillation (from Flower heads)"


def test_best_extraction_structured_value_is_compound_specific_not_plant_level():
    # The gap this task closes: within the SAME plant, two different
    # compounds must be able to report two DIFFERENT extraction
    # methods, not the plant-level "first compound wins" flattening.
    engine = make_engine([dict(
        scientific_name="RefPlant", compound_name="Apigenin", indication="I",
        target="T", common_name="", plant_part="", extraction_method="",
    )])
    alt_row = {"Extraction_Method": ""}
    bisabolol_result = engine._best_extraction(
        alt_row, "", alt_plant="Matricaria chamomilla", matched_compound="Bisabolol",
    )
    apigenin_result = engine._best_extraction(
        alt_row, "", alt_plant="Matricaria chamomilla", matched_compound="Apigenin",
    )
    assert bisabolol_result != apigenin_result
    assert "Steam distillation" in bisabolol_result
    assert "Infusion" in apigenin_result


# ---------------------------------------------------------------------
# End-to-end through run(): identical scores/ranking for the
# non-structured path, and a genuinely more specific Extraction_Method
# for the structured path — never a Decision_Class/score change either
# way, since Extraction_Method only feeds industrial_feasibility/
# _extraction_fit_score exactly as it did before Task 7.
# ---------------------------------------------------------------------

def test_run_end_to_end_structured_extraction_method_surfaces_in_output():
    eng.SIMILAR_COMPOUND_GROUPS = {}
    eng.COMPOUND_TARGETS = {}
    rows = [
        dict(scientific_name="RefPlant", compound_name="Bisabolol",
             indication="TestIndication", target="Test",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="Matricaria chamomilla", compound_name="Bisabolol",
             indication="Other", target="Test",
             common_name="", plant_part="", extraction_method=""),
    ]
    engine = make_engine(rows)
    result = engine.run(indication="TestIndication", dosage_form="Essential oil", market="EU")
    row = result[result["Alternative_Plant"] == "Matricaria chamomilla"].iloc[0]
    assert row["Extraction_Method"] == "Steam distillation (from Flower heads)"


def test_run_end_to_end_unaffected_for_plants_outside_the_seed_dataset():
    eng.SIMILAR_COMPOUND_GROUPS = {}
    eng.COMPOUND_TARGETS = {}
    rows = [
        dict(scientific_name="RefPlant", compound_name="SharedCompound",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="AltPlant", compound_name="SharedCompound",
             indication="Other", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
    ]
    engine = make_engine(rows)
    result = engine.run(indication="TestIndication", dosage_form="Infusion", market="EU")
    alt_row = result[
        (result["Reference_Plant"] == "RefPlant") & (result["Alternative_Plant"] == "AltPlant")
    ].iloc[0]
    # Exact recorded SCORE from the Task 1/3 regression locks — this
    # fixture's plants/compounds aren't in seed_data.py, so nothing
    # about Task 7 changes this outcome. Decision_Class changed under
    # Phase 4 (this fixture has zero evidence text, now correctly
    # INCOMPLETE rather than the old fail-open "Low priority" label —
    # see test_scoring_config.py for the same fixture/reasoning).
    # PHASE 5 (§10 fix): market_neutral_default +3 -> 0.0 (confirmed
    # defect fixed, main audit §3.1) — see the identical comment in
    # test_gate_layer.py's sibling assertion on the same fixture.
    assert alt_row["R&D_Opportunity_Score"] == 35.0
    assert alt_row["Decision_Class"] == (
        "Incomplete — insufficient safety/regulatory evidence for a validated recommendation"
    )
