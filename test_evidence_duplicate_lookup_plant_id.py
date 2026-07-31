"""Regression tests for the post-Phase-2 architectural correctness fix:
database.save_evidence_record()'s duplicate-evidence lookup now includes
plant_id, so two different plants sharing the same source/indication/
dosage form are never collapsed into one evidence row.
"""

import unittest.mock as mock

import database


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _Chain:
    def __init__(self, table_name, harness):
        self.table_name = table_name
        self.harness = harness
        self.conditions = {}
        self.insert_payload = None

    def select(self, *a, **kw):
        return self

    def eq(self, field, value):
        self.conditions[field] = value
        return self

    def limit(self, *a, **kw):
        return self

    def insert(self, payload):
        self.insert_payload = payload
        return self

    def execute(self):
        return self.harness._execute(self.table_name, self.conditions, self.insert_payload)


class StatefulFakeSupabase:
    """A supabase-py double with real (in-memory) state for plants,
    sources, and evidence_records, so tests can drive save_evidence_record()
    through realistic create-then-lookup sequences instead of a single
    canned response."""

    def __init__(self):
        self._plants = {}     # scientific_name -> id
        self._sources = {}    # (url, title) -> id
        self._evidence = []   # list of dict rows, each with "id"
        self._next_id = 1

    def _new_id(self):
        i = self._next_id
        self._next_id += 1
        return i

    def table(self, name):
        return _Chain(name, self)

    def _execute(self, table_name, conditions, insert_payload):
        if insert_payload is not None:
            return self._insert(table_name, insert_payload)
        return self._select(table_name, conditions)

    def _insert(self, table_name, payload):
        if table_name == "plants":
            id_ = self._new_id()
            self._plants[payload.get("scientific_name", "")] = id_
            return _FakeResult([{"id": id_}])
        if table_name == "sources":
            id_ = self._new_id()
            self._sources[(payload.get("url", ""), payload.get("title", ""))] = id_
            return _FakeResult([{"id": id_}])
        if table_name == "evidence_records":
            id_ = self._new_id()
            row = dict(payload)
            row["id"] = id_
            self._evidence.append(row)
            return _FakeResult([{"id": id_}])
        raise AssertionError(f"unexpected insert into {table_name!r}")

    def _select(self, table_name, conditions):
        if table_name == "plants":
            name = conditions.get("scientific_name")
            id_ = self._plants.get(name)
            return _FakeResult([{"id": id_}] if id_ is not None else [])
        if table_name == "sources":
            url = conditions.get("url")
            title = conditions.get("title")
            for (u, t), id_ in self._sources.items():
                if url is not None and u == url:
                    return _FakeResult([{"id": id_}])
                if title is not None and t == title:
                    return _FakeResult([{"id": id_}])
            return _FakeResult([])
        if table_name == "evidence_records":
            for row in self._evidence:
                if all(row.get(k) == v for k, v in conditions.items()):
                    return _FakeResult([{"id": row["id"]}])
            return _FakeResult([])
        raise AssertionError(f"unexpected select on {table_name!r}")


def _record(scientific_name, indication="Type 2 diabetes", dosage_form="Oral",
            source_url="https://example.org/same-review-article"):
    return {
        "Scientific_Name": scientific_name,
        "Source_URL": source_url,
        "Source_Title": "Same review article",
        "Target_Indication": indication,
        "Dosage_Form": dosage_form,
    }


# Case 1 — same plant, same source, same indication, same dosage form ->
# the second save must return the SAME evidence row, not create a new one.
def test_case1_same_plant_same_source_indication_form_returns_existing_row():
    fake = StatefulFakeSupabase()
    with mock.patch("database.get_supabase_client", return_value=fake):
        first_id = database.save_evidence_record(_record("Morus alba"))
        second_id = database.save_evidence_record(_record("Morus alba"))
    assert first_id == second_id
    assert len(fake._evidence) == 1


# Case 2 — THE regression this fix exists for: a different plant sharing
# the same source/indication/dosage form must get its OWN evidence row.
def test_case2_different_plant_same_source_indication_form_creates_second_row():
    fake = StatefulFakeSupabase()
    with mock.patch("database.get_supabase_client", return_value=fake):
        morus_id = database.save_evidence_record(_record("Morus alba"))
        fenugreek_id = database.save_evidence_record(_record("Trigonella foenum-graecum"))
    assert morus_id != fenugreek_id
    assert len(fake._evidence) == 2
    plant_ids = {row["plant_id"] for row in fake._evidence}
    assert len(plant_ids) == 2


# Case 3 — same plant and source, different dosage form -> a second row.
def test_case3_different_dosage_form_creates_another_record():
    fake = StatefulFakeSupabase()
    with mock.patch("database.get_supabase_client", return_value=fake):
        oral_id = database.save_evidence_record(_record("Morus alba", dosage_form="Oral"))
        topical_id = database.save_evidence_record(_record("Morus alba", dosage_form="Topical"))
    assert oral_id != topical_id
    assert len(fake._evidence) == 2


# Case 4 — same plant and source, different indication -> a second row.
def test_case4_different_indication_creates_another_record():
    fake = StatefulFakeSupabase()
    with mock.patch("database.get_supabase_client", return_value=fake):
        diabetes_id = database.save_evidence_record(_record("Morus alba", indication="Type 2 diabetes"))
        metabolic_id = database.save_evidence_record(_record("Morus alba", indication="Metabolic syndrome"))
    assert diabetes_id != metabolic_id
    assert len(fake._evidence) == 2


def test_plant_id_is_actually_present_on_every_stored_evidence_row():
    # Guards against a regression where plant_id is resolved but never
    # actually included in the evidence_records insert payload.
    fake = StatefulFakeSupabase()
    with mock.patch("database.get_supabase_client", return_value=fake):
        database.save_evidence_record(_record("Morus alba"))
    assert fake._evidence[0]["plant_id"] is not None
