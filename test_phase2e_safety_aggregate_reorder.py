"""Phase 2E regression suite — moving _aggregate_plant_safety() from
before the relevance gate to immediately after it, inside
discover_indication_candidates()'s main per-plant loop.

Scope: this reorder ONLY. No relevance rule, threshold, match type,
candidate inclusion/exclusion, safety extraction logic, normalization,
validation, row construction, output schema, shortlisting, scoring, or
Streamlit flow changed. All fixtures are synthetic.
"""

import unittest.mock as mock

import pandas as pd
import pytest

from botanical_rd_candidate_engine import BotanicalRDCandidateEngine
import indication_candidate_discovery as icd


def make_engine(plant_rows, evidence_rows):
    plants_df = pd.DataFrame(plant_rows)
    evidence_df = pd.DataFrame(evidence_rows) if evidence_rows else pd.DataFrame()
    return BotanicalRDCandidateEngine(
        plant_compounds_df=plants_df,
        compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(),
        evidence_df=evidence_df,
        use_live_search=False,
    )


def _plant_row(name, indication="", target=""):
    return dict(
        scientific_name=name, compound_name="Compoundia",
        indication=indication, target=target,
        common_name="", plant_part="", extraction_method="",
    )


def _evidence_row(plant, text, record_id):
    return dict(
        scientific_name=plant,
        text=text,
        source="TestSource",
        record_id=record_id,
        target_indication="Test indication",
    )


# ---------------------------------------------------------------------
# 1-3. Call-count behavior of _aggregate_plant_safety().
# ---------------------------------------------------------------------

def test_irrelevant_plant_never_calls_aggregate_plant_safety():
    plant_rows = [_plant_row("Irrelevantia nullius")]
    evidence_rows = [
        _evidence_row("Irrelevantia nullius", "Text about something completely unrelated to any indication.", "r1"),
    ]
    engine = make_engine(plant_rows, evidence_rows)

    with mock.patch.object(icd, "_aggregate_plant_safety", wraps=icd._aggregate_plant_safety) as spy:
        icd.discover_indication_candidates(engine, indication="Cough", dosage_form="Infusion", market="EU")
        assert spy.call_count == 0


def test_relevant_plant_calls_aggregate_plant_safety_exactly_once():
    plant_rows = [_plant_row("Relevantia herbosa", indication="Cough")]
    evidence_rows = [
        _evidence_row("Relevantia herbosa", "A clinical study on Cough treatment with this herb.", "r1"),
    ]
    engine = make_engine(plant_rows, evidence_rows)

    with mock.patch.object(icd, "_aggregate_plant_safety", wraps=icd._aggregate_plant_safety) as spy:
        icd.discover_indication_candidates(engine, indication="Cough", dosage_form="Infusion", market="EU")
        assert spy.call_count == 1
        assert spy.call_args[0][1] == "Relevantia herbosa"


def test_relevant_plant_with_multiple_evidence_records_still_calls_once():
    plant_rows = [_plant_row("Multirecordia speciosa", indication="Cough")]
    evidence_rows = [
        _evidence_row("Multirecordia speciosa", "First study on Cough with this herb.", "r1"),
        _evidence_row("Multirecordia speciosa", "Second study on Cough with this herb, different result.", "r2"),
        _evidence_row("Multirecordia speciosa", "Third mention of Cough for this herb.", "r3"),
    ]
    engine = make_engine(plant_rows, evidence_rows)

    with mock.patch.object(icd, "_aggregate_plant_safety", wraps=icd._aggregate_plant_safety) as spy:
        icd.discover_indication_candidates(engine, indication="Cough", dosage_form="Infusion", market="EU")
        assert spy.call_count == 1
        # Confirms it received ALL of the plant's records together, not
        # once per record.
        (records_arg, plant_arg), _ = spy.call_args
        assert len(records_arg) == 3
        assert plant_arg == "Multirecordia speciosa"


def test_mixed_relevant_and_irrelevant_plants_only_call_for_relevant_ones():
    plant_rows = [
        _plant_row("Relevantia herbosa", indication="Cough"),
        _plant_row("Irrelevantia nullius"),
        _plant_row("Anotherrelevantia vulgaris", indication="Cough"),
    ]
    evidence_rows = [
        _evidence_row("Relevantia herbosa", "A clinical study on Cough treatment with this herb.", "r1"),
        _evidence_row("Irrelevantia nullius", "Text about something completely unrelated.", "r2"),
        _evidence_row("Anotherrelevantia vulgaris", "Cough relief demonstrated in this trial.", "r3"),
    ]
    engine = make_engine(plant_rows, evidence_rows)

    real_aggregate = icd._aggregate_plant_safety
    with mock.patch.object(icd, "_aggregate_plant_safety", side_effect=real_aggregate) as spy:
        icd.discover_indication_candidates(engine, indication="Cough", dosage_form="Infusion", market="EU")
        called_plants = [c[0][1] for c in spy.call_args_list]
        assert "Irrelevantia nullius" not in called_plants
        assert called_plants.count("Relevantia herbosa") == 1
        assert called_plants.count("Anotherrelevantia vulgaris") == 1


# ---------------------------------------------------------------------
# 4. Output rows and safety fields unchanged.
# ---------------------------------------------------------------------

def test_output_rows_and_safety_fields_for_retained_plants():
    plant_rows = [
        _plant_row("Relevantia herbosa", indication="Cough"),
        _plant_row("Irrelevantia nullius"),
    ]
    evidence_rows = [
        _evidence_row(
            "Relevantia herbosa",
            "A clinical study on Cough treatment with this herb. Adverse events: mild nausea reported.",
            "r1",
        ),
        _evidence_row("Irrelevantia nullius", "Text about something completely unrelated.", "r2"),
    ]
    engine = make_engine(plant_rows, evidence_rows)

    out = icd.discover_indication_candidates(engine, indication="Cough", dosage_form="Infusion", market="EU")

    assert "Irrelevantia nullius" not in out["Alternative_Plant"].tolist()
    relevant_rows = out[out["Alternative_Plant"] == "Relevantia herbosa"]
    assert not relevant_rows.empty
    # Safety_Flags/Interaction_Flags/Safety_Reassurance/Safety_Data_Status
    # must still be populated from _aggregate_plant_safety()'s result —
    # the reorder must not have broken this data flow.
    assert "Safety_Data_Status" in relevant_rows.columns
    assert (relevant_rows["Safety_Data_Status"] != "").all() or (
        relevant_rows["Safety_Data_Status"].notna().all()
    )


def test_output_deterministic_across_repeated_runs():
    # Same input, run twice independently (fresh engine each time) —
    # output must be identical, proving the reorder introduced no
    # nondeterminism (e.g. from dict ordering or shared mutable state).
    plant_rows = [
        _plant_row("Relevantia herbosa", indication="Cough"),
        _plant_row("Anotherrelevantia vulgaris", indication="Cough"),
        _plant_row("Irrelevantia nullius"),
    ]
    evidence_rows = [
        _evidence_row("Relevantia herbosa", "A clinical study on Cough treatment with this herb.", "r1"),
        _evidence_row("Anotherrelevantia vulgaris", "Cough relief demonstrated in this trial.", "r2"),
        _evidence_row("Irrelevantia nullius", "Text about something completely unrelated.", "r3"),
    ]

    engine_a = make_engine(plant_rows, evidence_rows)
    out_a = icd.discover_indication_candidates(engine_a, indication="Cough", dosage_form="Infusion", market="EU")

    engine_b = make_engine(plant_rows, evidence_rows)
    out_b = icd.discover_indication_candidates(engine_b, indication="Cough", dosage_form="Infusion", market="EU")

    assert len(out_a) == len(out_b)
    assert sorted(out_a["Alternative_Plant"].tolist()) == sorted(out_b["Alternative_Plant"].tolist())
    for col in ("Safety_Flags", "Interaction_Flags", "Safety_Data_Status", "R&D_Opportunity_Score"):
        assert out_a.sort_values("Alternative_Plant")[col].tolist() == out_b.sort_values("Alternative_Plant")[col].tolist()


# ---------------------------------------------------------------------
# Structural proof that the reorder actually took effect: safety
# aggregation happens strictly after relevance has been determined
# (i.e. after the gate), never before.
# ---------------------------------------------------------------------

def test_aggregate_plant_safety_runs_after_relevance_gate_structurally():
    plant_rows = [_plant_row("Relevantia herbosa", indication="Cough")]
    evidence_rows = [
        _evidence_row("Relevantia herbosa", "A clinical study on Cough treatment with this herb.", "r1"),
    ]
    engine = make_engine(plant_rows, evidence_rows)

    call_order = []
    real_score = icd.score_record_relevance_hybrid
    real_safety = icd._aggregate_plant_safety

    def score_spy(*args, **kwargs):
        call_order.append("relevance")
        return real_score(*args, **kwargs)

    def safety_spy(*args, **kwargs):
        call_order.append("safety_aggregate")
        return real_safety(*args, **kwargs)

    with mock.patch.object(icd, "score_record_relevance_hybrid", side_effect=score_spy), \
         mock.patch.object(icd, "_aggregate_plant_safety", side_effect=safety_spy):
        icd.discover_indication_candidates(engine, indication="Cough", dosage_form="Infusion", market="EU")

    assert "safety_aggregate" in call_order
    assert "relevance" in call_order
    first_safety_index = call_order.index("safety_aggregate")
    # Every relevance call up to and including the ones that determine
    # this plant's inclusion must have happened before safety_aggregate.
    assert "relevance" in call_order[:first_safety_index]
