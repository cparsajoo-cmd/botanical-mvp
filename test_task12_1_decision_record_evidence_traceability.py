"""
Task 12.1 — Persist Candidate-Level Evidence Traceability.

WHAT THIS COVERS
decision_record_persistence._PERSISTED_RECORD_FIELDS' new
"applicability_summary" entry — the ONE change Task 12.1 makes. Reuses
test_decision_record_persistence.py's own fake Supabase client and
CandidateAssessment factory rather than duplicating them (same
fixtures, same table shape, same failure-safe assumptions already
locked by that file's own test suite).

WHAT THIS DELIBERATELY DOES NOT COVER
Evidence-to-gate causal attribution (out of scope, see this task's own
instructions) and full ScientificEvidence persistence (explicitly
rejected in the Task 12 audit §9) — no test here should be read as
covering either.

HOW TO RUN
    pytest -q test_task12_1_decision_record_evidence_traceability.py
    (or `pytest -q` from the repo root — auto-discovered)
"""

import json

import data_contracts as dc
from decision_record_persistence import (
    DECISION_RECORD_TABLE_NAME,
    _PERSISTED_RECORD_FIELDS,
    _serialize_record,
    persist_decision_record,
)
from test_decision_record_persistence import (
    _FakeSupabaseClient,
    _sample_candidate_assessment,
)


def _sample_applicability_summary(**overrides):
    defaults = dict(
        counts={
            "Directly applicable": 0,
            "Partially applicable": 1,
            "Indirectly relevant": 0,
            "Not assessable": 1,
            "Not applicable": 0,
        },
        total_evidence_items=2,
        assessable_items=1,
        not_assessable_items=1,
        strongest_category="Partially applicable",
        critical_mismatches=[],
        missing_dimensions=["plant_part", "extraction_or_solvent"],
        evidence_record_ids=["ev-101", "ev-102"],
        summary_rationale="2 evidence item(s) assessed for preparation applicability: "
                           "0 directly applicable, 1 partially applicable, 0 indirectly "
                           "relevant, 1 not assessable, 0 not applicable.",
    )
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------
# 1) applicability_summary is serialized.
# ---------------------------------------------------------------------

def test_applicability_summary_field_is_in_the_persisted_allowlist():
    assert "applicability_summary" in _PERSISTED_RECORD_FIELDS


def test_applicability_summary_is_serialized_by_serialize_record():
    summary = _sample_applicability_summary()
    record = _sample_candidate_assessment(applicability_summary=summary)
    serialized = _serialize_record(record)
    assert serialized["applicability_summary"] == summary


def test_applicability_summary_reaches_the_persisted_row(monkeypatch=None):
    summary = _sample_applicability_summary()
    records = [_sample_candidate_assessment(applicability_summary=summary)]
    client = _FakeSupabaseClient()

    persist_decision_record(records, indication="Liver support", supabase_client=client)

    persisted_row = client.store[DECISION_RECORD_TABLE_NAME][0]
    persisted_records = json.loads(persisted_row["records"])
    assert persisted_records[0]["applicability_summary"] == summary


# ---------------------------------------------------------------------
# 2) evidence_record_ids survive the persistence payload unchanged.
# ---------------------------------------------------------------------

def test_evidence_record_ids_survive_the_persistence_payload_unchanged():
    summary = _sample_applicability_summary(evidence_record_ids=["ev-1", "ev-2", "ev-3"])
    records = [_sample_candidate_assessment(applicability_summary=summary)]
    client = _FakeSupabaseClient()

    persist_decision_record(records, indication="Liver support", supabase_client=client)

    persisted_row = client.store[DECISION_RECORD_TABLE_NAME][0]
    persisted_records = json.loads(persisted_row["records"])
    assert persisted_records[0]["applicability_summary"]["evidence_record_ids"] == [
        "ev-1", "ev-2", "ev-3",
    ]


def test_evidence_record_ids_are_the_genuine_evidence_records_ids_not_recomputed():
    """This module must never re-derive evidence_record_ids — it only
    ever reads whatever CandidateAssessment.applicability_summary
    already held. Proven by round-tripping a set of ids that could not
    plausibly be produced by any computation this module performs
    (arbitrary, non-sequential, string-typed)."""
    arbitrary_ids = ["zz-not-sequential", "42", "ev-💊-unicode-id"]
    summary = _sample_applicability_summary(evidence_record_ids=arbitrary_ids)
    record = _sample_candidate_assessment(applicability_summary=summary)
    serialized = _serialize_record(record)
    assert serialized["applicability_summary"]["evidence_record_ids"] == arbitrary_ids


# ---------------------------------------------------------------------
# 3) Existing persisted fields remain unchanged.
# ---------------------------------------------------------------------

def test_existing_persisted_fields_remain_unchanged():
    expected_pre_task_12_1_fields = {
        "reference_plant", "reference_compound", "alternative_plant",
        "alternative_compound", "indication", "dosage_form", "target_market",
        "rd_opportunity_score", "decision_class", "evidence_confidence",
        "gate_results", "scoring_config_version",
    }
    assert expected_pre_task_12_1_fields.issubset(set(_PERSISTED_RECORD_FIELDS))
    # Six new fields added since (applicability_summary, Task 12.1;
    # decision_engine_version, Task 15; grade_certainty and
    # grade_certainty_rationale, closing the result_df ->
    # CandidateAssessment -> decision_records path for GRADE
    # certainty; score_breakdown and score_context, PHASE 2
    # review round issue 2 — score_breakdown is an existing
    # CandidateAssessment field persisted verbatim for the first time,
    # score_context is derived from it plus applicability_summary,
    # never a raw field read off the record — see
    # decision_record_persistence._build_score_context()),
    # nothing removed.
    assert set(_PERSISTED_RECORD_FIELDS) - expected_pre_task_12_1_fields == {
        "applicability_summary", "decision_engine_version",
        "grade_certainty", "grade_certainty_rationale",
        "score_breakdown", "score_context",
    }


def test_gate_results_and_other_existing_fields_still_persist_correctly_alongside_it():
    summary = _sample_applicability_summary()
    gate_results = {
        "safety": {"gate_name": "safety", "status": "passed", "reason": "x", "evidence": "y"},
    }
    records = [_sample_candidate_assessment(
        applicability_summary=summary,
        gate_results=gate_results,
        rd_opportunity_score=81.5,
        decision_class="Strong candidate",
    )]
    client = _FakeSupabaseClient()

    persist_decision_record(records, indication="Liver support", supabase_client=client)

    persisted_row = client.store[DECISION_RECORD_TABLE_NAME][0]
    persisted_records = json.loads(persisted_row["records"])
    row = persisted_records[0]
    assert row["gate_results"] == gate_results
    assert row["rd_opportunity_score"] == 81.5
    assert row["decision_class"] == "Strong candidate"
    assert row["applicability_summary"] == summary


# ---------------------------------------------------------------------
# 4) A record without applicability_summary serializes safely as None.
# ---------------------------------------------------------------------

def test_record_without_applicability_summary_serializes_as_none():
    record = _sample_candidate_assessment()  # applicability_summary left at its dataclass default
    assert record.applicability_summary is None
    serialized = _serialize_record(record)
    assert serialized["applicability_summary"] is None


def test_old_style_dict_record_without_applicability_summary_serializes_as_none():
    """Simulates a pre-Task-10.2/pre-Task-12.1 record shape passed as a
    plain dict (not a dataclass) with no applicability_summary key at
    all — must not raise, must degrade to None, same as every other
    missing key in this allowlist."""
    old_style_record = {
        "reference_plant": "Silybum marianum",
        "alternative_plant": "Allium cepa",
        "rd_opportunity_score": 50.0,
        "decision_class": "Early-stage candidate",
        # No "applicability_summary" key at all.
    }
    serialized = _serialize_record(old_style_record)
    assert serialized["applicability_summary"] is None


def test_old_decision_records_without_applicability_summary_remain_readable():
    """A row already persisted before Task 12.1 (its JSON blob's
    records simply lack the key) must load without error — proven by
    round-tripping json.loads/json.dumps on a pre-Task-12.1-shaped
    payload exactly as load_decision_record() would receive it."""
    pre_task_12_1_payload = json.dumps([{
        "reference_plant": "Silybum marianum",
        "alternative_plant": "Allium cepa",
        "rd_opportunity_score": 60.0,
        "decision_class": "Promising candidate",
        "gate_results": {"safety": {"gate_name": "safety", "status": "passed",
                                     "reason": "x", "evidence": "y"}},
        "scoring_config_version": "1.0-default",
        # No applicability_summary key — genuinely pre-Task-12.1 shape.
    }])
    loaded = json.loads(pre_task_12_1_payload)
    assert loaded[0].get("applicability_summary") is None
    assert loaded[0]["decision_class"] == "Promising candidate"


# ---------------------------------------------------------------------
# 5) No additional CandidateAssessment fields are persisted accidentally.
# ---------------------------------------------------------------------

def test_no_additional_candidate_assessment_fields_persisted_accidentally():
    """A CandidateAssessment with EVERY optional field populated (incl.
    fields never in the allowlist, like source_record_ids/
    evidence_gaps/rationale) must still only ever serialize the exact
    _PERSISTED_RECORD_FIELDS set — nothing more."""
    record = _sample_candidate_assessment(
        applicability_summary=_sample_applicability_summary(),
        source_record_ids=["https://pubmed.ncbi.nlm.nih.gov/1/"],
        evidence_gaps=["no dose data"],
        rationale="Some free-text rationale that must NOT leak into persistence.",
        scientific_rationale="Also must not leak.",
        white_space_type="E. White-space opportunity",
        candidate_evidence_strength_tier="High-priority evidence tier",
    )
    serialized = _serialize_record(record)
    assert set(serialized.keys()) == set(_PERSISTED_RECORD_FIELDS)
    assert "source_record_ids" not in serialized
    assert "rationale" not in serialized
    assert "scientific_rationale" not in serialized
    assert "white_space_type" not in serialized
    assert "candidate_evidence_strength_tier" not in serialized


def test_persisted_row_json_blob_contains_exactly_the_allowlisted_keys():
    records = [_sample_candidate_assessment(applicability_summary=_sample_applicability_summary())]
    client = _FakeSupabaseClient()
    persist_decision_record(records, indication="Liver support", supabase_client=client)

    persisted_row = client.store[DECISION_RECORD_TABLE_NAME][0]
    persisted_records = json.loads(persisted_row["records"])
    assert set(persisted_records[0].keys()) == set(_PERSISTED_RECORD_FIELDS)


# ---------------------------------------------------------------------
# Non-regression: this task touches persistence only. append-only
# behavior, table name, and the top-level row shape must be untouched.
# ---------------------------------------------------------------------

def test_append_only_behavior_unaffected_by_applicability_summary():
    records = [_sample_candidate_assessment(applicability_summary=_sample_applicability_summary())]
    client = _FakeSupabaseClient()
    persist_decision_record(records, indication="Liver support", analysis_id="fixed-id", supabase_client=client)
    persist_decision_record(records, indication="Liver support", analysis_id="fixed-id", supabase_client=client)
    assert len(client.store[DECISION_RECORD_TABLE_NAME]) == 2


def test_top_level_row_shape_unchanged():
    records = [_sample_candidate_assessment(applicability_summary=_sample_applicability_summary())]
    client = _FakeSupabaseClient()
    persist_decision_record(records, indication="Liver support", project_id="proj-1", supabase_client=client)

    persisted_row = client.store[DECISION_RECORD_TABLE_NAME][0]
    assert set(persisted_row.keys()) == {
        "analysis_id", "created_at", "scoring_config_version",
        "indication", "project_id", "candidate_count", "records",
    }
