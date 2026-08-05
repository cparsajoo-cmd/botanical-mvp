"""Phase 3 — persistence round-trip and optional-column-fallback tests
for source_authority / source_authority_score / source_authority_reason
on evidence_records, using the same FakeSupabase double pattern as
test_database_evidence_schema_extension.py.
"""
import unittest.mock as mock

import database
from test_database_evidence_schema_extension import FakeSupabase, _FakeResult, _base_record


def test_source_authority_fields_are_persisted_when_present():
    fake = FakeSupabase()
    with mock.patch("database.get_supabase_client", return_value=fake):
        database.save_evidence_record(_base_record(
            Source_Authority="EMA HMPC Monograph",
            Source_Authority_Score=1.0,
            Source_Authority_Reason="Matched EMA/HMPC monograph terminology.",
        ))
    payload = fake.inserted_evidence_payloads[0]
    assert payload["source_authority"] == "EMA HMPC Monograph"
    assert payload["source_authority_score"] == 1.0
    assert payload["source_authority_reason"] == "Matched EMA/HMPC monograph terminology."


def test_source_authority_fields_are_none_not_fabricated_when_absent():
    fake = FakeSupabase()
    with mock.patch("database.get_supabase_client", return_value=fake):
        database.save_evidence_record(_base_record())
    payload = fake.inserted_evidence_payloads[0]
    assert payload["source_authority"] is None
    assert payload["source_authority_score"] is None
    assert payload["source_authority_reason"] is None


def test_legacy_source_authority_weight_key_still_persists_via_score_redirect():
    """Backward compatibility: an old-style record that only sets the
    pre-Phase-3 "Source_Authority_Weight" key must still end up
    persisted — into the new numeric field, its correct semantic home
    (see standard_evidence_schema.py's _LEGACY_FIELD_MAP comment)."""
    fake = FakeSupabase()
    with mock.patch("database.get_supabase_client", return_value=fake):
        database.save_evidence_record(_base_record(Source_Authority_Weight=0.95))
    payload = fake.inserted_evidence_payloads[0]
    assert payload["source_authority_score"] == 0.95


def test_source_authority_registered_in_optional_fallback_set():
    assert "source_authority" in database._OPTIONAL_EVIDENCE_COLUMNS
    assert "source_authority_score" in database._OPTIONAL_EVIDENCE_COLUMNS
    assert "source_authority_reason" in database._OPTIONAL_EVIDENCE_COLUMNS


def test_insert_degrades_gracefully_when_source_authority_columns_absent():
    """Simulates an unmigrated table (0007 not yet applied): PostgREST
    rejects the row for the unknown 'source_authority' column, and the
    insert must retry without it rather than failing outright."""
    attempts = []

    def behavior(fake_self, payload):
        attempts.append(dict(payload))
        if "source_authority" in payload:
            raise Exception("PGRST204: Could not find the 'source_authority' column of 'evidence_records' in the schema cache")
        if "source_authority_score" in payload:
            raise Exception("PGRST204: Could not find the 'source_authority_score' column of 'evidence_records' in the schema cache")
        if "source_authority_reason" in payload:
            raise Exception("PGRST204: Could not find the 'source_authority_reason' column of 'evidence_records' in the schema cache")
        fake_self.inserted_evidence_payloads.append(dict(payload))
        return _FakeResult([{"id": 42}])

    fake = FakeSupabase(evidence_insert_behavior=behavior)
    with mock.patch("database.get_supabase_client", return_value=fake):
        row_id = database.save_evidence_record(_base_record(
            Source_Authority="WHO Monograph",
            Source_Authority_Score=0.97,
            Source_Authority_Reason="matched",
        ))
    assert row_id == 42
    # Retried three times (one per missing optional column) before
    # succeeding, and the final successful attempt has none of the three.
    assert len(attempts) == 4
    final = attempts[-1]
    assert "source_authority" not in final
    assert "source_authority_score" not in final
    assert "source_authority_reason" not in final


def test_load_evidence_records_reads_source_authority_columns_back():
    fake = FakeSupabase()

    class _SelectResult:
        data = [{
            "id": 1,
            "plant_id": 7,
            "plants": {"scientific_name": "Matricaria chamomilla", "common_name": "Chamomile"},
            "sources": {"source_type": "Regulatory", "title": "HMPC monograph"},
            "source_authority": "EMA HMPC Monograph",
            "source_authority_score": 1.0,
            "source_authority_reason": "Matched EMA/HMPC monograph terminology.",
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
    assert rows.iloc[0]["Source_Authority"] == "EMA HMPC Monograph"
    assert rows.iloc[0]["Source_Authority_Score"] == 1.0
    assert rows.iloc[0]["Source_Authority_Reason"] == "Matched EMA/HMPC monograph terminology."


def test_load_evidence_records_degrades_to_none_when_columns_absent_on_read():
    class _SelectResultNoAuthorityColumns:
        data = [{
            "id": 2,
            "plant_id": 8,
            "plants": {"scientific_name": "Melissa officinalis", "common_name": "Lemon balm"},
            "sources": {},
            # No source_authority* keys at all — unmigrated table.
        }]

    class _FakeLoadTable:
        def select(self, *a, **kw):
            return self

        def execute(self):
            return _SelectResultNoAuthorityColumns()

    class _FakeLoadClient:
        def table(self, name):
            return _FakeLoadTable()

    with mock.patch("database.get_supabase_client", return_value=_FakeLoadClient()):
        rows = database.load_evidence_records()
    assert rows.iloc[0]["Source_Authority"] is None
    assert rows.iloc[0]["Source_Authority_Score"] is None
    assert rows.iloc[0]["Source_Authority_Reason"] is None
