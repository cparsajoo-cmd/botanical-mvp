"""Tests for decision_metadata.py (IMPLEMENTATION_PLAN.md Phase 4)."""

import pandas as pd

from decision_metadata import (
    compute_evidence_snapshot,
    compute_candidate_set_fingerprint,
    build_decision_metadata,
    SCORING_MODEL_VERSION,
    NORMALIZATION_VERSION,
    VALIDATION_VERSION,
)


def _df(rows):
    return pd.DataFrame(rows)


# --- 1. Identical evidence and configuration produce the same fingerprint ---

def test_identical_evidence_produces_the_same_snapshot_id():
    df1 = _df([
        {"Alternative_Plant": "A", "Source_Record_IDs": "PMID:1; PMID:2"},
        {"Alternative_Plant": "B", "Source_Record_IDs": "PMID:3"},
    ])
    df2 = _df([
        {"Alternative_Plant": "A", "Source_Record_IDs": "PMID:1; PMID:2"},
        {"Alternative_Plant": "B", "Source_Record_IDs": "PMID:3"},
    ])
    snap1 = compute_evidence_snapshot(df1)
    snap2 = compute_evidence_snapshot(df2)
    assert snap1["status"] == "computed"
    assert snap1["evidence_snapshot_id"] == snap2["evidence_snapshot_id"]


def test_identical_configuration_produces_the_same_full_metadata_shape():
    df = _df([{"Alternative_Plant": "A", "Scientific_Triage_Status": "Shortlist",
                "Overall_Score": 80.0, "Source_Record_IDs": "PMID:1"}])
    meta1 = build_decision_metadata(df, indication="sleep", dosage_form="Infusion",
                                     market="EU", discovery_mode="indication")
    meta2 = build_decision_metadata(df, indication="sleep", dosage_form="Infusion",
                                     market="EU", discovery_mode="indication")
    assert meta1["evidence_snapshot_id"] == meta2["evidence_snapshot_id"]
    assert meta1["candidate_set_fingerprint"] == meta2["candidate_set_fingerprint"]
    assert meta1["scoring_model_version"] == meta2["scoring_model_version"] == SCORING_MODEL_VERSION


# --- 2. Changed evidence produces a different fingerprint ------------------

def test_changed_evidence_produces_a_different_snapshot_id():
    df1 = _df([{"Alternative_Plant": "A", "Source_Record_IDs": "PMID:1; PMID:2"}])
    df2 = _df([{"Alternative_Plant": "A", "Source_Record_IDs": "PMID:1; PMID:2; PMID:3"}])
    snap1 = compute_evidence_snapshot(df1)
    snap2 = compute_evidence_snapshot(df2)
    assert snap1["evidence_snapshot_id"] != snap2["evidence_snapshot_id"]


def test_changed_candidate_score_produces_a_different_fingerprint():
    df1 = _df([{"Alternative_Plant": "A", "Scientific_Triage_Status": "Shortlist", "Overall_Score": 80.0}])
    df2 = _df([{"Alternative_Plant": "A", "Scientific_Triage_Status": "Shortlist", "Overall_Score": 81.0}])
    assert compute_candidate_set_fingerprint(df1) != compute_candidate_set_fingerprint(df2)


def test_added_candidate_produces_a_different_fingerprint():
    df1 = _df([{"Alternative_Plant": "A", "Scientific_Triage_Status": "Shortlist", "Overall_Score": 80.0}])
    df2 = _df([
        {"Alternative_Plant": "A", "Scientific_Triage_Status": "Shortlist", "Overall_Score": 80.0},
        {"Alternative_Plant": "B", "Scientific_Triage_Status": "Exploratory", "Overall_Score": 50.0},
    ])
    assert compute_candidate_set_fingerprint(df1) != compute_candidate_set_fingerprint(df2)


# --- 3. Row-order changes do not affect the fingerprint --------------------

def test_row_order_does_not_affect_the_evidence_snapshot_id():
    df_forward = _df([
        {"Alternative_Plant": "A", "Source_Record_IDs": "PMID:1"},
        {"Alternative_Plant": "B", "Source_Record_IDs": "PMID:2"},
        {"Alternative_Plant": "C", "Source_Record_IDs": "PMID:3"},
    ])
    df_reversed = df_forward.iloc[::-1].reset_index(drop=True)
    snap_forward = compute_evidence_snapshot(df_forward)
    snap_reversed = compute_evidence_snapshot(df_reversed)
    assert snap_forward["evidence_snapshot_id"] == snap_reversed["evidence_snapshot_id"]


def test_row_order_does_not_affect_the_candidate_set_fingerprint():
    df_forward = _df([
        {"Alternative_Plant": "A", "Scientific_Triage_Status": "Shortlist", "Overall_Score": 90.0},
        {"Alternative_Plant": "B", "Scientific_Triage_Status": "Exploratory", "Overall_Score": 40.0},
    ])
    df_shuffled = df_forward.iloc[::-1].reset_index(drop=True)
    assert compute_candidate_set_fingerprint(df_forward) == compute_candidate_set_fingerprint(df_shuffled)


# --- 5. Missing evidence IDs are represented honestly -----------------------

def test_no_source_record_ids_column_is_marked_unavailable_not_fabricated():
    df = _df([{"Alternative_Plant": "A", "Overall_Score": 80.0}])
    snap = compute_evidence_snapshot(df)
    assert snap["status"] == "unavailable"
    assert snap["evidence_snapshot_id"] is None


def test_empty_source_record_ids_values_are_marked_unavailable():
    df = _df([
        {"Alternative_Plant": "A", "Source_Record_IDs": ""},
        {"Alternative_Plant": "B", "Source_Record_IDs": None},
    ])
    snap = compute_evidence_snapshot(df)
    assert snap["status"] == "unavailable"
    assert snap["evidence_snapshot_id"] is None


def test_empty_dataframe_is_marked_unavailable_not_a_crash():
    snap = compute_evidence_snapshot(pd.DataFrame())
    assert snap["status"] == "unavailable"
    assert snap["evidence_snapshot_id"] is None
    assert compute_candidate_set_fingerprint(pd.DataFrame()) is None


def test_partial_availability_still_computes_from_what_exists():
    # One row has an identifier, one doesn't — the snapshot is computed
    # from what's genuinely there, not marked unavailable just because
    # coverage is incomplete (that's a data-quality question for the
    # report to surface separately, not this function's job to hide).
    df = _df([
        {"Alternative_Plant": "A", "Source_Record_IDs": "PMID:1"},
        {"Alternative_Plant": "B", "Source_Record_IDs": ""},
    ])
    snap = compute_evidence_snapshot(df)
    assert snap["status"] == "computed"
    assert snap["evidence_snapshot_id"] is not None


# --- Full metadata shape ----------------------------------------------------

def test_build_decision_metadata_returns_all_ten_required_fields():
    df = _df([{"Alternative_Plant": "A", "Scientific_Triage_Status": "Shortlist",
                "Overall_Score": 80.0, "Source_Record_IDs": "PMID:1"}])
    meta = build_decision_metadata(
        df, indication="sleep", dosage_form="Infusion", market="EU",
        discovery_mode="indication",
    )
    required_fields = {
        "scoring_model_version", "evidence_snapshot_id", "normalization_version",
        "validation_version", "decision_timestamp", "discovery_mode",
        "indication", "dosage_form", "market", "candidate_set_fingerprint",
    }
    assert required_fields <= set(meta.keys())
    assert meta["normalization_version"] == NORMALIZATION_VERSION
    assert meta["validation_version"] == VALIDATION_VERSION
    assert meta["indication"] == "sleep"
    assert meta["dosage_form"] == "Infusion"
    assert meta["market"] == "EU"
    assert meta["discovery_mode"] == "indication"
