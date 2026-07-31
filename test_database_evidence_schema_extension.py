"""Tests for IMPLEMENTATION_PLAN.md Phase 2 changes to database.py:
the 14 new evidence_records fields and their extension of the existing
_OPTIONAL_EVIDENCE_COLUMNS schema-fallback mechanism (Task 10.2's
mechanism, not a new one).
"""

import unittest.mock as mock

import database


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeTable:
    def __init__(self, name, harness):
        self.name = name
        self.harness = harness
        self._pending_insert_payload = None

    def select(self, *a, **kw):
        return self

    def eq(self, *a, **kw):
        return self

    def limit(self, *a, **kw):
        return self

    def insert(self, payload):
        self._pending_insert_payload = payload
        return self

    def execute(self):
        return self.harness._execute(self.name, self._pending_insert_payload)


class FakeSupabase:
    """Minimal fluent-chain double for supabase-py, just enough to drive
    save_evidence_record(): every `select` (existing-source / existing-
    plant lookup) reports "not found" so the function always takes the
    create path, and every `insert` returns a canned id — except
    evidence_records inserts, which are recorded (and can be made to
    raise a PGRST204-shaped error, via evidence_insert_behavior) so
    tests can inspect exactly what payload this Phase 2 change sends."""

    def __init__(self, evidence_insert_behavior=None):
        self.inserted_evidence_payloads = []
        self.evidence_insert_behavior = evidence_insert_behavior

    def table(self, name):
        return _FakeTable(name, self)

    def _execute(self, name, insert_payload):
        if name in ("sources", "plants"):
            if insert_payload is None:
                return _FakeResult([])  # "not found" -> caller creates one
            return _FakeResult([{"id": 999}])
        if name == "evidence_records":
            if self.evidence_insert_behavior is not None:
                return self.evidence_insert_behavior(self, insert_payload)
            self.inserted_evidence_payloads.append(dict(insert_payload))
            return _FakeResult([{"id": 12345}])
        raise AssertionError(f"unexpected table {name!r} in test double")


def _base_record(**overrides):
    record = {
        "Scientific_Name": "Valeriana officinalis",
        "Source_URL": "https://pubmed.ncbi.nlm.nih.gov/12345/",
        "Source_Title": "A study",
        "Target_Indication": "sleep",
        "Dosage_Form": "Infusion",
    }
    record.update(overrides)
    return record


def test_phase2_identifier_fields_are_persisted_when_the_connector_provided_them():
    fake = FakeSupabase()
    with mock.patch("database.get_supabase_client", return_value=fake):
        database.save_evidence_record(_base_record(
            PMID="12345", DOI="10.1234/example", NCT_ID="NCT00000001",
        ))
    payload = fake.inserted_evidence_payloads[0]
    assert payload["pmid"] == "12345"
    assert payload["doi"] == "10.1234/example"
    assert payload["nct_id"] == "NCT00000001"


def test_phase2_fields_are_none_not_empty_string_when_the_connector_did_not_provide_them():
    # The core "never infer or fabricate" requirement: an unavailable
    # value must be distinguishable from a genuinely empty one.
    fake = FakeSupabase()
    with mock.patch("database.get_supabase_client", return_value=fake):
        database.save_evidence_record(_base_record())
    payload = fake.inserted_evidence_payloads[0]
    for field in (
        "pmid", "doi", "nct_id", "mechanism", "target",
        "administration_route", "plant_part", "extraction_method",
        "duration", "effect_size", "p_value", "adverse_events",
        "interactions_structured", "data_quality_score",
    ):
        assert payload[field] is None, f"{field} should be None, got {payload[field]!r}"


def test_effect_size_and_p_value_are_passed_through_as_structured_values_not_coerced():
    # Per the explicit Phase 2 constraint: effect_size/p_value must stay
    # structured (JSONB-shaped dicts here), never flattened to a bare number.
    fake = FakeSupabase()
    effect_size = {"type": "mean_difference", "value": -1.2, "unit": "points",
                    "ci_95": [-2.1, -0.3], "timepoint": "week 8"}
    p_value = {"raw_text": "p < 0.05", "operator": "<", "value": 0.05}
    with mock.patch("database.get_supabase_client", return_value=fake):
        database.save_evidence_record(_base_record(Effect_Size=effect_size, P_Value=p_value))
    payload = fake.inserted_evidence_payloads[0]
    assert payload["effect_size"] == effect_size
    assert payload["p_value"] == p_value


def test_all_phase2_columns_are_registered_in_the_optional_fallback_set():
    # Guards against a future Phase 2 field being added to the payload
    # dict but forgotten in the fallback set — which would make an
    # unmigrated table's insert fail outright instead of degrading.
    phase2_columns = {
        "pmid", "doi", "nct_id", "mechanism", "target",
        "administration_route", "plant_part", "extraction_method",
        "duration", "effect_size", "p_value", "adverse_events",
        "interactions_structured", "data_quality_score",
    }
    assert phase2_columns <= database._OPTIONAL_EVIDENCE_COLUMNS


def test_insert_degrades_gracefully_when_a_phase2_column_is_missing_on_an_unmigrated_table():
    def behavior(fake_self, payload):
        if "mechanism" in payload:
            raise Exception(
                "Could not find the 'mechanism' column of 'evidence_records' "
                "in the schema cache (PGRST204)"
            )
        fake_self.inserted_evidence_payloads.append(dict(payload))
        return _FakeResult([{"id": 777}])

    fake = FakeSupabase(evidence_insert_behavior=behavior)
    with mock.patch("database.get_supabase_client", return_value=fake):
        row_id = database.save_evidence_record(_base_record())
    assert row_id == 777
    assert "mechanism" not in fake.inserted_evidence_payloads[0]
    # every other Phase 2 field (which the fake table "has") still made it through
    assert "pmid" in fake.inserted_evidence_payloads[0]


def test_load_evidence_records_returns_none_for_absent_phase2_columns_not_empty_string():
    fake_response_item = {
        "plant_id": 1, "plants": {"scientific_name": "Valeriana officinalis", "common_name": ""},
        "sources": {}, "product_type": "", "dosage_form": "", "target_indication": "",
        "target_market": "",
        # Phase 2 columns simply absent from the response dict, exactly
        # like an unmigrated table or a PostgREST response that omits
        # unset keys — item.get() must return None, not "".
    }

    class _FakeResponse:
        data = [fake_response_item]

    class _FakeSelectChain:
        def select(self, *a, **kw):
            return self

        def execute(self):
            return _FakeResponse()

    class _FakeSupabaseRead:
        def table(self, name):
            return _FakeSelectChain()

    with mock.patch("database.get_supabase_client", return_value=_FakeSupabaseRead()):
        rows = database.load_evidence_records()
    assert rows.iloc[0]["PMID"] is None
    assert rows.iloc[0]["Effect_Size"] is None
