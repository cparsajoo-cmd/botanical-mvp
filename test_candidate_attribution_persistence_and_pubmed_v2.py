"""Regression tests for Problem 1's two remaining defects found after the
prior pass:

  Defect A -- Candidate_Attribution_Verified/_Basis were computed by
  connectors and preserved by evidence_standardizer.py, but silently
  dropped by database.py's save_evidence_record()/load_evidence_records(),
  so the field vanished on a save -> reload round trip and fail-closed
  logic then treated genuinely verified records as unverified.

  Defect B -- verify_pubmed_intervention_attribution() still verified
  whenever an administration cue and the candidate's name shared a
  sentence, even when that sentence actually negated the administration,
  described prior/historical exposure, or described an exclusion
  criterion.

Fictional botanicals/indications are used throughout so nothing here
depends on a hardcoded plant-name blacklist.
"""
import unittest.mock as mock

import pandas as pd

import candidate_attribution as ca
import database
import evidence_adjudication_engine as eae
from candidate_shortlisting import (
    _row_has_indication_specific_outcome,
    _row_has_verified_candidate_attribution,
)
from test_database_evidence_schema_extension import FakeSupabase, _FakeResult, _base_record


# =======================================================================
# Persistence round trip (Defect A)
# =======================================================================

# ---- P4: the save payload actually carries the fields --------------

def test_p4_save_evidence_record_sends_attribution_fields_in_payload_when_true():
    fake = FakeSupabase()
    with mock.patch("database.get_supabase_client", return_value=fake):
        database.save_evidence_record(_base_record(
            Candidate_Attribution_Verified=True,
            Candidate_Attribution_Basis="full_binomial",
        ))
    payload = fake.inserted_evidence_payloads[0]
    assert payload["candidate_attribution_verified"] is True
    assert payload["candidate_attribution_basis"] == "full_binomial"


def test_p4_save_evidence_record_sends_false_explicitly_not_as_none_or_empty():
    fake = FakeSupabase()
    with mock.patch("database.get_supabase_client", return_value=fake):
        database.save_evidence_record(_base_record(
            Candidate_Attribution_Verified=False,
        ))
    payload = fake.inserted_evidence_payloads[0]
    assert payload["candidate_attribution_verified"] is False


def test_p4_save_evidence_record_sends_none_when_absent_never_true():
    fake = FakeSupabase()
    with mock.patch("database.get_supabase_client", return_value=fake):
        database.save_evidence_record(_base_record())
    payload = fake.inserted_evidence_payloads[0]
    assert payload["candidate_attribution_verified"] is None
    assert payload["candidate_attribution_basis"] is None


def test_candidate_attribution_registered_in_optional_fallback_set():
    assert "candidate_attribution_verified" in database._OPTIONAL_EVIDENCE_COLUMNS
    assert "candidate_attribution_basis" in database._OPTIONAL_EVIDENCE_COLUMNS


def test_insert_degrades_gracefully_and_warns_when_attribution_columns_absent(capsys):
    """Simulates an unmigrated table (0011 not yet applied): PostgREST
    rejects the row for the unknown columns, the insert retries without
    them, and the fallback's existing print() makes that observable."""
    attempts = []

    def behavior(fake_self, payload):
        attempts.append(dict(payload))
        if "candidate_attribution_verified" in payload:
            raise Exception(
                "PGRST204: Could not find the 'candidate_attribution_verified' "
                "column of 'evidence_records' in the schema cache"
            )
        if "candidate_attribution_basis" in payload:
            raise Exception(
                "PGRST204: Could not find the 'candidate_attribution_basis' "
                "column of 'evidence_records' in the schema cache"
            )
        fake_self.inserted_evidence_payloads.append(dict(payload))
        return _FakeResult([{"id": 77}])

    fake = FakeSupabase(evidence_insert_behavior=behavior)
    with mock.patch("database.get_supabase_client", return_value=fake):
        row_id = database.save_evidence_record(_base_record(
            Candidate_Attribution_Verified=True,
            Candidate_Attribution_Basis="full_binomial",
        ))
    assert row_id == 77
    final = attempts[-1]
    assert "candidate_attribution_verified" not in final
    assert "candidate_attribution_basis" not in final
    # The missing-schema condition must be observable, not silent.
    printed = capsys.readouterr().out
    assert "candidate_attribution_verified" in printed
    assert "candidate_attribution_basis" in printed


# ---- P1: True round trip --------------------------------------------

def test_p1_true_round_trips_through_save_and_load():
    fake = FakeSupabase()
    with mock.patch("database.get_supabase_client", return_value=fake):
        database.save_evidence_record(_base_record(
            Candidate_Attribution_Verified=True,
            Candidate_Attribution_Basis="full_binomial",
        ))
    saved_payload = fake.inserted_evidence_payloads[0]

    class _SelectResult:
        data = [{
            "id": 1,
            "plant_id": 7,
            "plants": {"scientific_name": "Ficticus alpinum", "common_name": ""},
            "sources": {"source_type": "PubMed", "title": "A study"},
            "candidate_attribution_verified": saved_payload["candidate_attribution_verified"],
            "candidate_attribution_basis": saved_payload["candidate_attribution_basis"],
        }]

    class _FakeLoadTable:
        def select(self, *a, **kw):
            return self

        def execute(self):
            return _SelectResult()

    class _FakeLoadClient:
        def table(self, name):
            return _FakeLoadTable()

    with mock.patch("database.get_supabase_client", return_value=_FakeLoadClient()):
        rows = database.load_evidence_records()
    assert bool(rows.iloc[0]["Candidate_Attribution_Verified"]) is True
    assert rows.iloc[0]["Candidate_Attribution_Basis"] == "full_binomial"


# ---- P2: False round trip --------------------------------------------

def test_p2_false_round_trips_through_save_and_load():
    fake = FakeSupabase()
    with mock.patch("database.get_supabase_client", return_value=fake):
        database.save_evidence_record(_base_record(
            Candidate_Attribution_Verified=False,
        ))
    saved_payload = fake.inserted_evidence_payloads[0]

    class _SelectResult:
        data = [{
            "id": 2,
            "plant_id": 8,
            "plants": {"scientific_name": "Ficticus alpinum", "common_name": ""},
            "sources": {},
            "candidate_attribution_verified": saved_payload["candidate_attribution_verified"],
            "candidate_attribution_basis": saved_payload["candidate_attribution_basis"],
        }]

    class _FakeLoadTable:
        def select(self, *a, **kw):
            return self

        def execute(self):
            return _SelectResult()

    class _FakeLoadClient:
        def table(self, name):
            return _FakeLoadTable()

    with mock.patch("database.get_supabase_client", return_value=_FakeLoadClient()):
        rows = database.load_evidence_records()
    assert bool(rows.iloc[0]["Candidate_Attribution_Verified"]) is False


# ---- P3: missing/legacy row remains unverified ------------------------

def test_p3_legacy_row_with_no_attribution_columns_loads_as_missing_and_stays_unverified():
    class _SelectResultLegacy:
        data = [{
            "id": 3,
            "plant_id": 9,
            "plants": {"scientific_name": "Ficticus alpinum", "common_name": ""},
            "sources": {},
            # No candidate_attribution_* keys at all -- unmigrated/legacy row.
        }]

    class _FakeLoadTable:
        def select(self, *a, **kw):
            return self

        def execute(self):
            return _SelectResultLegacy()

    class _FakeLoadClient:
        def table(self, name):
            return _FakeLoadTable()

    with mock.patch("database.get_supabase_client", return_value=_FakeLoadClient()):
        rows = database.load_evidence_records()
    row = rows.iloc[0]
    assert row["Candidate_Attribution_Verified"] is None
    # Fail closed: this must NOT qualify as verified direct human evidence.
    assert _row_has_verified_candidate_attribution(row) is False
    assert _row_has_indication_specific_outcome(row, "sleep") is False


# =======================================================================
# PubMed intervention-attribution false positives (Defect B)

# =======================================================================
# PubMed candidate-intervention attribution (Defect B) -- SUPERSEDED.
#
# ARCHITECTURE NOTE: the tests previously here (test_u1..test_u6,
# test_background_plus_administration_language_elsewhere_does_not_verify,
# test_true_positives_from_first_pass_still_verify_after_defect_b_fix,
# test_common_name_administration_*, and the two full-pipeline-invariant
# tests) all exercised candidate_attribution.verify_pubmed_intervention_
# attribution(), a bounded token-distance heuristic. Independent
# adversarial testing found that whole approach remained structurally
# brittle regardless of how many phrases/patterns were added, and it was
# REMOVED (see candidate_attribution.py's module docstring) in favor of a
# canonical Candidate_Intervention_Assertion derived from structured LLM
# extraction with a verbatim-span check (candidate_intervention_
# assertion.py), with a very conservative deterministic fast path as a
# fallback only.
#
# Every scenario these tests covered -- genuine administration, negation,
# historical/prior treatment, exclusion, background/review literature,
# common-name administration, and the full retrieval -> extraction ->
# standardization -> persistence -> reload -> shortlisting/adjudication
# pipeline invariant -- is re-covered, against the NEW architecture, in
# test_candidate_intervention_assertion_v1.py.
# =======================================================================
