"""Phase 2 — Evidence architecture / traceability tests.

Covers the 22 required-test list from the Phase 2 brief. Tests assert
expected scientific/behavioral outcomes (e.g. "these two records must be
treated as the same article"), not private implementation details.
"""

import pandas as pd
import pytest

from standard_evidence_schema import EvidenceRecord
from deduplication_engine import (
    compute_article_identity,
    compute_evidence_identity,
    normalize_doi,
    normalize_pmid,
    normalize_trial_registration,
    deduplicate_evidence,
    stable_identity_hash,
)
from score_breakdown_schema import (
    score_contribution_key,
    dedupe_score_contributions,
)


# ----------------------------------------------------------------------
# 1-7: EvidenceRecord construction / conversion / round-trip
# ----------------------------------------------------------------------

def test_1_evidence_record_creation_from_canonical_fields():
    rec = EvidenceRecord.from_canonical(
        doi="10.1000/xyz123",
        article_title="A trial of lemon balm",
        plant_species="Melissa officinalis",
        indication="Sleep support",
    )
    assert rec.doi == "10.1000/xyz123"
    assert rec.article_title == "A trial of lemon balm"
    assert rec.plant_species == "Melissa officinalis"


def test_2_optional_fields_have_safe_defaults_no_shared_mutable_state():
    a = EvidenceRecord()
    b = EvidenceRecord()
    assert a.doi is None
    assert a.first_author is None
    assert a.extra == {}
    # Mutating one instance's extra must never affect another's (no
    # shared mutable default).
    a.extra["x"] = 1
    assert b.extra == {}


def test_3_legacy_dict_to_evidence_record():
    legacy = {
        "DOI": "10.1/ABC",
        "PMID": "123456",
        "NCT_ID": "NCT01234567",
        "Source_Title": "Some Article",
        "Source_Year": "2020",
        "Source_Type": "PubMed",
        "Study_Type": "RCT",
        "Result_Direction": "Positive",
        "Evidence_Level": "High",
        "Scientific_Name": "Melissa officinalis",
        "Common_Name": "Lemon balm",
        "Dosage_Form": "Infusion",
        "Target_Indication": "Sleep support",
        "Population": "Adults",
        "Primary_Outcome": "Sleep latency",
        "Notes": "extraction text",
        "Evidence_Record_ID": "42",
    }
    rec = EvidenceRecord.from_legacy_dict(legacy)
    assert rec.doi == "10.1/ABC"
    assert rec.pmid == "123456"
    assert rec.trial_registration == "NCT01234567"
    assert rec.article_title == "Some Article"
    assert rec.study_design == "RCT"
    assert rec.evidence_direction == "Positive"
    assert rec.evidence_quality == "High"
    assert rec.plant_species == "Melissa officinalis"
    assert rec.evidence_record_id == "42"
    # Study_Type/Result_Direction/Evidence_Level must land on three
    # DIFFERENT fields, never merged (Phase 1 requirement).
    assert len({rec.study_design, rec.evidence_direction, rec.evidence_quality}) == 3


def test_4_evidence_record_to_legacy_dict():
    rec = EvidenceRecord(
        doi="10.1/abc", pmid="999", article_title="Title X",
        study_design="RCT", evidence_direction="Positive",
        evidence_quality="High", plant_species="Ginkgo biloba",
    )
    legacy = rec.to_legacy_dict()
    assert legacy["DOI"] == "10.1/abc"
    assert legacy["PMID"] == "999"
    assert legacy["Source_Title"] == "Title X"
    assert legacy["Study_Type"] == "RCT"
    assert legacy["Result_Direction"] == "Positive"
    assert legacy["Evidence_Level"] == "High"
    assert legacy["Scientific_Name"] == "Ginkgo biloba"


def test_5_serialization_to_json_safe_dict():
    rec = EvidenceRecord(doi="10.1/abc", extra={"Custom_Field": "value"})
    data = rec.to_dict()
    assert data["doi"] == "10.1/abc"
    assert data["extra"] == {"Custom_Field": "value"}
    import json
    json.dumps(data)  # must not raise


def test_6_deserialization_from_dict():
    data = {"doi": "10.1/abc", "plant_species": "Ginkgo biloba", "extra": {"K": "V"}}
    rec = EvidenceRecord.from_dict(data)
    assert rec.doi == "10.1/abc"
    assert rec.plant_species == "Ginkgo biloba"
    assert rec.extra == {"K": "V"}


def test_7_round_trip_legacy_dict_no_data_loss():
    legacy = {
        "DOI": "10.1/abc", "PMID": "1", "NCT_ID": "NCT00000001",
        "Source_Title": "T", "Source_Year": "2019", "Source_Type": "PubMed",
        "Study_Type": "RCT", "Result_Direction": "Positive",
        "Evidence_Level": "High", "Scientific_Name": "Panax ginseng",
        "Common_Name": "Ginseng", "Dosage_Form": "Capsule",
        "Target_Indication": "Fatigue", "Population": "Adults",
        "Primary_Outcome": "Fatigue score", "Notes": "text",
        "Some_Unmapped_Field": "kept",
    }
    rec = EvidenceRecord.from_legacy_dict(legacy)
    back = rec.to_legacy_dict()
    for key, value in legacy.items():
        assert back.get(key) == value, f"{key} lost in round-trip"


# ----------------------------------------------------------------------
# 8-14: article-identity / deduplication priority
# ----------------------------------------------------------------------

def test_8_dedup_same_doi_different_forms():
    r1 = {"DOI": "https://doi.org/10.1000/XYZ"}
    r2 = {"DOI": "doi:10.1000/xyz"}
    r3 = {"DOI": " 10.1000/xyz "}
    assert compute_article_identity(r1) == compute_article_identity(r2) == compute_article_identity(r3)


def test_9_no_dedup_different_doi():
    r1 = {"DOI": "10.1000/aaa"}
    r2 = {"DOI": "10.1000/bbb"}
    assert compute_article_identity(r1) != compute_article_identity(r2)


def test_10_dedup_same_pmid():
    r1 = {"PMID": "123456"}
    r2 = {"PMID": "PMID:123456"}
    assert compute_article_identity(r1) == compute_article_identity(r2)


def test_11_dedup_same_trial_registration():
    r1 = {"NCT_ID": "NCT01234567"}
    r2 = {"NCT_ID": "nct01234567"}
    r3 = {"NCT_ID": "NCT0001234567".replace("NCT000", "NCT")}  # sanity variant
    assert compute_article_identity(r1) == compute_article_identity(r2)
    assert normalize_trial_registration("NCT1234567") == normalize_trial_registration("NCT01234567")


def test_12_dedup_normalized_title_year_author():
    r1 = {"Source_Title": "A Randomized Trial of Lemon Balm!!", "Source_Year": "2020", "First_Author": "Smith J."}
    r2 = {"Source_Title": "a randomized trial of lemon balm", "Source_Year": "2020", "First_Author": "smith j"}
    assert compute_article_identity(r1) == compute_article_identity(r2)


def test_13_no_dedup_same_title_different_year_or_author():
    r1 = {"Source_Title": "Effects of Ginseng on Fatigue", "Source_Year": "2018", "First_Author": "Lee"}
    r2 = {"Source_Title": "Effects of Ginseng on Fatigue", "Source_Year": "2021", "First_Author": "Lee"}
    r3 = {"Source_Title": "Effects of Ginseng on Fatigue", "Source_Year": "2018", "First_Author": "Kim"}
    assert compute_article_identity(r1) != compute_article_identity(r2)
    assert compute_article_identity(r1) != compute_article_identity(r3)


def test_14_heuristic_fallback_is_deterministic():
    r = {"Source_URL": "https://example.com/article/1"}
    key1 = compute_article_identity(r)
    key2 = compute_article_identity(dict(r))
    assert key1 == key2
    assert key1[0] == "heuristic"


def test_14b_url_never_outranks_doi_pmid_nct():
    r = {"Source_URL": "https://example.com/a", "DOI": "10.1/z"}
    tier, _ = compute_article_identity(r)
    assert tier == "doi"


# ----------------------------------------------------------------------
# 15-16: article vs evidence identity distinction
# ----------------------------------------------------------------------

def test_15_pubmed_and_europepmc_same_article_identity():
    pubmed_row = {"PMID": "555555", "Source_Title": "T", "Source_Type": "PubMed"}
    europepmc_row = {"PMID": "555555", "DOI": None, "Source_Title": "T (Europe PMC copy)", "Source_Type": "Europe PMC"}
    assert compute_article_identity(pubmed_row) == compute_article_identity(europepmc_row)


def test_16_distinct_evidence_contexts_from_same_article_not_collapsed():
    base = {"DOI": "10.1/shared-review"}
    plant_a = dict(base, Scientific_Name="Morus alba", Target_Indication="Diabetes", Dosage_Form="Capsule")
    plant_b = dict(base, Scientific_Name="Trigonella foenum-graecum", Target_Indication="Diabetes", Dosage_Form="Capsule")
    # Same article...
    assert compute_article_identity(plant_a) == compute_article_identity(plant_b)
    # ...but different evidence contexts.
    assert compute_evidence_identity(plant_a) != compute_evidence_identity(plant_b)


# ----------------------------------------------------------------------
# 17-18: score contribution dedup guard
# ----------------------------------------------------------------------

def test_17_duplicate_score_contribution_not_double_counted():
    eid = compute_evidence_identity({"DOI": "10.1/x", "Scientific_Name": "Ginkgo biloba", "Target_Indication": "Memory"})
    contributions = [
        {"evidence_identity": eid, "component": "Evidence quality", "value": 3.0},
        {"evidence_identity": eid, "component": "Evidence quality", "value": 3.0},  # duplicate: PubMed + Europe PMC
    ]
    result = dedupe_score_contributions(contributions)
    assert len(result) == 1


def test_18_same_evidence_different_component_both_kept():
    eid = compute_evidence_identity({"DOI": "10.1/x", "Scientific_Name": "Ginkgo biloba", "Target_Indication": "Memory"})
    contributions = [
        {"evidence_identity": eid, "component": "Evidence quality", "value": 3.0},
        {"evidence_identity": eid, "component": "Mechanistic plausibility", "value": 1.0},
    ]
    result = dedupe_score_contributions(contributions)
    assert len(result) == 2


def test_18b_score_contribution_key_is_stable_and_deterministic():
    k1 = score_contribution_key("evidence::x", "Evidence quality")
    k2 = score_contribution_key("evidence::x", "Evidence quality")
    k3 = score_contribution_key("evidence::x", "Mechanistic plausibility")
    assert k1 == k2
    assert k1 != k3


# ----------------------------------------------------------------------
# 19: database ID / evidence_record_ids preserved
# ----------------------------------------------------------------------

def test_19_database_id_and_evidence_record_id_preserved_through_round_trip():
    legacy = {"Evidence_Record_ID": "789", "DOI": "10.1/x"}
    rec = EvidenceRecord.from_legacy_dict(legacy)
    assert rec.evidence_record_id == "789"
    back = rec.to_legacy_dict()
    assert back["Evidence_Record_ID"] == "789"


# ----------------------------------------------------------------------
# 20-21: backward compatibility of existing public functions / DataFrame path
# ----------------------------------------------------------------------

def test_20_deduplicate_evidence_backward_compatible_dataframe_shape():
    df = pd.DataFrame([
        {
            "Scientific_Name": "Melissa officinalis", "Target_Indication": "Sleep support",
            "Dosage_Form": "Infusion", "Source_URL": "https://pubmed.ncbi.nlm.nih.gov/12345",
            "Source_Title": "A randomized trial", "Notes": "", "Evidence_Score": 40,
            "Evidence_Quality_Score": 10,
        },
        {
            "Scientific_Name": "Melissa officinalis", "Target_Indication": "Sleep support",
            "Dosage_Form": "Infusion", "Source_URL": "https://pubmed.ncbi.nlm.nih.gov/12345",
            "Source_Title": "A randomized trial", "Notes": "", "Evidence_Score": 5,
            "Evidence_Quality_Score": 5,
        },
    ])
    out = deduplicate_evidence(df)
    assert isinstance(out, pd.DataFrame)
    assert len(out) == 1
    assert out.iloc[0]["Evidence_Score"] == 40


def test_21_dataframe_read_path_still_works_with_missing_new_columns():
    # A row shaped like an UNMIGRATED table (no DOI/PMID/NCT_ID columns
    # at all) must still dedup correctly via the heuristic tier.
    df = pd.DataFrame([
        {"Scientific_Name": "X", "Target_Indication": "Y", "Dosage_Form": "Z", "Source_URL": "u1"},
        {"Scientific_Name": "X", "Target_Indication": "Y", "Dosage_Form": "Z", "Source_URL": "u1"},
        {"Scientific_Name": "X", "Target_Indication": "Y", "Dosage_Form": "Z", "Source_URL": "u2"},
    ])
    out = deduplicate_evidence(df)
    assert len(out) == 2


# ----------------------------------------------------------------------
# Extra: normalization edge cases
# ----------------------------------------------------------------------

def test_normalize_doi_empty_never_valid_key():
    assert normalize_doi("") is None
    assert normalize_doi(None) is None
    assert normalize_doi("   ") is None


def test_normalize_pmid_empty_never_valid_key():
    assert normalize_pmid("") is None
    assert normalize_pmid(None) is None


def test_stable_identity_hash_deterministic_across_calls():
    assert stable_identity_hash("abc") == stable_identity_hash("abc")
    assert stable_identity_hash("abc") != stable_identity_hash("abd")


def test_evidence_record_id_extra_field_preserves_unknown_legacy_keys():
    legacy = {"Some_Totally_New_Field": "value123", "DOI": "10.1/x"}
    rec = EvidenceRecord.from_legacy_dict(legacy)
    assert rec.extra.get("Some_Totally_New_Field") == "value123"
    assert rec.to_legacy_dict().get("Some_Totally_New_Field") == "value123"


# ======================================================================
# PHASE 2 — REVIEW ROUND additions
# ======================================================================

import json as _json
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from standard_evidence_schema import canonicalize_evidence_record
from deduplication_engine import articles_equivalent
from score_breakdown_schema import score_contribution_key as _sck


# ---- Issue 1: canonical adapter genuinely wired into production ----

def test_issue1_canonicalize_evidence_record_is_actually_called_in_production_paths(monkeypatch):
    import standard_evidence_schema as ses_mod
    import evidence_standardizer as es_mod
    import deduplication_engine as dedup_mod

    calls = {"count": 0}
    real = ses_mod.canonicalize_evidence_record

    def spy(record):
        calls["count"] += 1
        return real(record)

    monkeypatch.setattr(ses_mod, "canonicalize_evidence_record", spy)
    monkeypatch.setattr(es_mod, "canonicalize_evidence_record", spy)
    monkeypatch.setattr(dedup_mod, "canonicalize_evidence_record", spy)

    # 1) standardize_extracted_record() boundary
    result = es_mod.standardize_extracted_record(
        extracted={"Notes": "text", "Source_Type": "PubMed"},
        source_metadata={"source_type": "PubMed"},
    )
    assert calls["count"] >= 1
    before_standardize = calls["count"]

    # 2) read-time deduplication boundary
    df = pd.DataFrame([
        {"Scientific_Name": "X", "Target_Indication": "Y", "Dosage_Form": "Z", "Source_URL": "u1"},
        {"Scientific_Name": "X", "Target_Indication": "Y", "Dosage_Form": "Z", "Source_URL": "u1"},
    ])
    dedup_mod.deduplicate_evidence(df)
    assert calls["count"] > before_standardize


def test_issue1_canonicalize_evidence_record_wired_into_save_evidence_record(monkeypatch):
    import database as db_mod

    calls = {"count": 0}
    real = db_mod.canonicalize_evidence_record

    def spy(record):
        calls["count"] += 1
        return real(record)

    monkeypatch.setattr(db_mod, "canonicalize_evidence_record", spy)

    class _FakeResult:
        def __init__(self, data):
            self.data = data

    class _FakeTable:
        def __init__(self, name):
            self.name = name
            self._is_select = False
            self._insert_payload = None

        def select(self, *a, **kw):
            self._is_select = True
            return self

        def eq(self, *a, **kw):
            return self

        def limit(self, *a, **kw):
            return self

        def insert(self, payload):
            self._insert_payload = payload
            return self

        def execute(self):
            if self._is_select:
                return _FakeResult([])
            if self.name in ("sources", "plants"):
                return _FakeResult([{"id": 1}])
            return _FakeResult([{"id": 999}])

    class _FakeSupabase:
        def table(self, name):
            return _FakeTable(name)

    monkeypatch.setattr(db_mod, "get_supabase_client", lambda: _FakeSupabase())

    db_mod.save_evidence_record({
        "Scientific_Name": "Ginkgo biloba", "Source_URL": "https://example.com/a",
        "Source_Title": "T", "Target_Indication": "Memory", "Dosage_Form": "Capsule",
    })
    assert calls["count"] >= 1


# ---- Issue 2 (review round 3, issue 3): honest candidate-level score context,
# NOT a fabricated per-component evidence attribution ----

def test_issue2_score_context_is_candidate_level_not_per_component():
    import decision_record_persistence as drp

    evidence_df = pd.DataFrame([
        {"Evidence_Record_ID": "1", "DOI": "10.1/shared", "Scientific_Name": "Ginkgo biloba",
         "Target_Indication": "Memory", "Dosage_Form": "Capsule"},
        {"Evidence_Record_ID": "2", "DOI": "10.1/shared", "Scientific_Name": "Ginkgo biloba",
         "Target_Indication": "Memory", "Dosage_Form": "Capsule"},  # same article, different DB row (2nd connector)
        {"Evidence_Record_ID": "3", "DOI": "10.1/different", "Scientific_Name": "Ginkgo biloba",
         "Target_Indication": "Memory", "Dosage_Form": "Capsule"},
    ])

    as_dict = {
        "score_breakdown": "Evidence quality: +3.0; Mechanistic plausibility: +1.0",
        "applicability_summary": {"evidence_record_ids": ["1", "2", "3"]},
    }

    context = drp._build_score_context(as_dict, evidence_df)

    # Explicit, honest structure — never per-component.
    assert context["attribution_level"] == "candidate"
    assert context["component_attribution_available"] is False
    assert context["score_breakdown"] == {"Evidence quality": 3.0, "Mechanistic plausibility": 1.0}
    # record #1 and #2 share an evidence_identity (same DOI/plant/indication/
    # dosage_form) -> deduped to one entry; record #3 is genuinely distinct.
    assert len(context["candidate_evidence_identities"]) == 2
    assert len(set(context["candidate_evidence_identities"])) == 2
    # This is a single candidate-level structure, not a list of
    # per-component entries — there is no "component" key anywhere.
    assert "component" not in context


def test_issue2_score_context_empty_when_no_score_breakdown():
    import decision_record_persistence as drp
    context = drp._build_score_context({}, None)
    assert context["score_breakdown"] == {}
    assert context["candidate_evidence_record_ids"] == []
    assert context["component_attribution_available"] is False


def test_issue2_dedupe_score_contributions_utility_kept_but_not_wired_to_scoring():
    """The original per-evidence/per-component guard utility remains
    available and tested (score_breakdown_schema.dedupe_score_contributions),
    but decision_record_persistence.py must NOT call it — using it would
    reintroduce exactly the fabricated component-level attribution this
    review round removed."""
    import decision_record_persistence as drp
    assert not hasattr(drp, "dedupe_score_contributions")


def test_issue2_persist_decision_record_produces_score_context_not_contributions(monkeypatch):
    import decision_record_persistence as drp

    class _FakeResult:
        def __init__(self, data):
            self.data = data

    class _FakeInsertTable:
        def __init__(self, store):
            self.store = store

        def insert(self, payload):
            self.store.append(payload)
            return self

        def execute(self):
            return _FakeResult([{"id": 1}])

    class _FakeClient:
        def __init__(self):
            self.store = []

        def table(self, name):
            return _FakeInsertTable(self.store)

    record = {
        "reference_plant": "Ginkgo biloba", "indication": "Memory",
        "score_breakdown": "Evidence quality: +3.0",
        "applicability_summary": {"evidence_record_ids": ["1"]},
    }
    client = _FakeClient()
    drp.persist_decision_record([record], indication="Memory", supabase_client=client)
    persisted = _json.loads(client.store[0]["records"])[0]
    assert "score_context" in persisted
    assert "score_contributions" not in persisted
    assert persisted["score_context"]["attribution_level"] == "candidate"
    assert persisted["score_context"]["component_attribution_available"] is False


# ---- Issue 3: finer evidence identity ----

def test_issue3_same_article_different_outcome_two_identities():
    base = {"DOI": "10.1/x", "Scientific_Name": "P", "Target_Indication": "I", "Dosage_Form": "D"}
    r1 = dict(base, Primary_Outcome="Sleep latency")
    r2 = dict(base, Primary_Outcome="Sleep quality")
    assert compute_evidence_identity(r1) != compute_evidence_identity(r2)


def test_issue3_same_outcome_different_direction_two_identities():
    base = {"DOI": "10.1/x", "Scientific_Name": "P", "Target_Indication": "I", "Dosage_Form": "D", "Primary_Outcome": "O"}
    r1 = dict(base, Result_Direction="Positive")
    r2 = dict(base, Result_Direction="Negative")
    assert compute_evidence_identity(r1) != compute_evidence_identity(r2)


def test_issue3_same_claim_formatting_difference_one_identity():
    base = {"DOI": "10.1/x", "Scientific_Name": "P", "Target_Indication": "I", "Dosage_Form": "D"}
    r1 = dict(base, Notes="Extract reduced sleep latency by 20%.")
    r2 = dict(base, Notes="  extract reduced sleep latency by 20%  ")
    assert compute_evidence_identity(r1) == compute_evidence_identity(r2)


def test_issue3_different_population_two_identities():
    base = {"DOI": "10.1/x", "Scientific_Name": "P", "Target_Indication": "I", "Dosage_Form": "D"}
    r1 = dict(base, Population="Adults")
    r2 = dict(base, Population="Children")
    assert compute_evidence_identity(r1) != compute_evidence_identity(r2)


def test_issue3_different_plant_part_not_collapsed():
    base = {"DOI": "10.1/x", "Scientific_Name": "P", "Target_Indication": "I", "Dosage_Form": "D"}
    r1 = dict(base, Plant_Part="Root")
    r2 = dict(base, Plant_Part="Leaf")
    assert compute_evidence_identity(r1) != compute_evidence_identity(r2)


# ---- Issue 4: fuzzy title matching ----

def test_issue4_close_titles_same_year_author_are_duplicate():
    a = {"Source_Title": "Effects of Ginkgo Biloba Extract on Cognitive Memory Function",
         "Source_Year": "2020", "First_Author": "Smith"}
    b = {"Source_Title": "Effects of Ginkgo Biloba Extract on Cognitive Memory Function.",
         "Source_Year": "2020", "First_Author": "Smith"}
    assert articles_equivalent(a, b) is True


def test_issue4_similar_title_different_year_not_duplicate():
    a = {"Source_Title": "Effects of Ginkgo Biloba Extract on Cognitive Memory Function",
         "Source_Year": "2020", "First_Author": "Smith"}
    b = {"Source_Title": "Effects of Ginkgo Biloba Extract on Cognitive Memory Function",
         "Source_Year": "2015", "First_Author": "Smith"}
    assert articles_equivalent(a, b) is False


def test_issue4_similar_title_different_author_not_duplicate():
    a = {"Source_Title": "Effects of Ginkgo Biloba Extract on Cognitive Memory Function",
         "Source_Year": "2020", "First_Author": "Smith"}
    b = {"Source_Title": "Effects of Ginkgo Biloba Extract on Cognitive Memory Function",
         "Source_Year": "2020", "First_Author": "Johnson"}
    assert articles_equivalent(a, b) is False


def test_issue4_short_generic_titles_never_fuzzy_deduplicated():
    a = {"Source_Title": "Ginkgo Review", "Source_Year": "2020"}
    b = {"Source_Title": "Ginkgo Reviews", "Source_Year": "2020"}
    assert articles_equivalent(a, b) is False


def test_issue4_subtitle_punctuation_difference_is_duplicate():
    a = {"Source_Title": "Ginkgo biloba and memory: a randomized controlled trial",
         "Source_Year": "2019"}
    b = {"Source_Title": "Ginkgo biloba and memory - a randomized controlled trial",
         "Source_Year": "2019"}
    assert articles_equivalent(a, b) is True


def test_issue4_strong_identifier_bypasses_fuzzy_matching():
    a = {"DOI": "10.1/a", "Source_Title": "Some Title About Ginkgo Extract Memory"}
    b = {"DOI": "10.1/b", "Source_Title": "Some Title About Ginkgo Extract Memory"}
    # Both have DOIs (different) -> equivalence decided EXACTLY by DOI,
    # never falls through to fuzzy title matching even though titles match.
    assert articles_equivalent(a, b) is False


# ---- Issue 5: insert-time uses title+year+author fallback too ----

def test_issue5_insert_time_dedups_two_connectors_same_title_year_author_no_ids():
    import database as db_mod

    class _FakeResult:
        def __init__(self, data):
            self.data = data

    class _FakeTable:
        def __init__(self, name, harness):
            self.name = name
            self.harness = harness
            self._filters = {}
            self._insert_payload = None
            self._is_select = False

        def select(self, *a, **kw):
            self._is_select = True
            return self

        def eq(self, field, value):
            self._filters[field] = value
            return self

        def limit(self, *a, **kw):
            return self

        def insert(self, payload):
            self._insert_payload = payload
            return self

        def execute(self):
            return self.harness._execute(self)

    class _Harness:
        def __init__(self):
            self.sources = []
            self.evidence = []
            self.plants = [{"id": 1, "scientific_name": "Ginkgo biloba"}]

        def table(self, name):
            return _FakeTable(name, self)

        def _execute(self, t):
            if t.name == "plants":
                if t._is_select:
                    return _FakeResult(self.plants)
                new_id = 1
                return _FakeResult([{"id": new_id}])
            if t.name == "sources":
                if t._is_select:
                    if "year" in t._filters:
                        return _FakeResult([
                            s for s in self.sources if s["year"] == t._filters["year"]
                        ])
                    return _FakeResult([])
                new_source = {"id": len(self.sources) + 1, "title": t._insert_payload["title"],
                              "year": t._insert_payload["year"]}
                self.sources.append(new_source)
                return _FakeResult([new_source])
            if t.name == "evidence_records":
                if t._is_select:
                    if "doi" in t._filters or "pmid" in t._filters or "nct_id" in t._filters:
                        return _FakeResult([])
                    matches = [
                        e for e in self.evidence
                        if e.get("source_id") == t._filters.get("source_id")
                        and e.get("plant_id") == t._filters.get("plant_id")
                        and e.get("target_indication") == t._filters.get("target_indication")
                        and e.get("dosage_form") == t._filters.get("dosage_form")
                    ]
                    return _FakeResult(matches)
                new_evidence = dict(t._insert_payload)
                new_evidence["id"] = len(self.evidence) + 100
                self.evidence.append(new_evidence)
                return _FakeResult([new_evidence])
            raise AssertionError(f"unexpected table {t.name}")

    harness = _Harness()
    monkeypatch_client = harness

    import unittest.mock as mock
    with mock.patch("database.get_supabase_client", return_value=monkeypatch_client):
        first_id = db_mod.save_evidence_record({
            "Scientific_Name": "Ginkgo biloba", "Source_URL": "https://pubmed.example/1",
            "Source_Title": "Ginkgo Biloba Extract Improves Memory in Older Adults",
            "Source_Year": "2019", "First_Author": "Smith",
            "Target_Indication": "Memory", "Dosage_Form": "Capsule",
        })
        second_id = db_mod.save_evidence_record({
            "Scientific_Name": "Ginkgo biloba", "Source_URL": "https://europepmc.example/2",
            "Source_Title": "Ginkgo Biloba Extract Improves Memory in Older Adults",
            "Source_Year": "2019", "First_Author": "Smith",
            "Target_Indication": "Memory", "Dosage_Form": "Capsule",
        })

    assert first_id == second_id
    assert len(harness.evidence) == 1


# ---- Issue 6: first_author alias/derivation ----

def test_issue6_first_author_direct_alias():
    rec = EvidenceRecord.from_legacy_dict({"First_Author": "Smith J"})
    assert rec.first_author == "Smith J"


def test_issue6_first_author_derived_from_authors_list_preserves_raw():
    rec = EvidenceRecord.from_legacy_dict({"Authors": ["Smith J", "Doe A"]})
    assert rec.first_author == "Smith J"
    assert rec.extra.get("Authors") == ["Smith J", "Doe A"]


def test_issue6_first_author_derived_from_authors_string():
    rec = EvidenceRecord.from_legacy_dict({"authors": "Smith J; Doe A; Lee K"})
    assert rec.first_author == "Smith J"
    assert rec.extra.get("authors") == "Smith J; Doe A; Lee K"


# ---- Issue 7: canonical round-trip data loss fixed ----

def test_issue7_canonical_to_legacy_to_canonical_round_trip_no_data_loss():
    original = EvidenceRecord(
        doi="10.1/x", first_author="Smith", preparation="Tincture", dose="500mg",
        article_title="T", plant_species="Ginkgo biloba",
    )
    legacy = original.to_legacy_dict()
    assert legacy.get("First_Author") == "Smith"
    assert legacy.get("Preparation") == "Tincture"
    assert legacy.get("Dose") == "500mg"

    round_tripped = EvidenceRecord.from_legacy_dict(legacy)
    assert round_tripped.first_author == "Smith"
    assert round_tripped.preparation == "Tincture"
    assert round_tripped.dose == "500mg"
    assert round_tripped.doi == "10.1/x"


def test_issue7_preparation_never_conflated_with_extraction_method():
    rec = EvidenceRecord.from_legacy_dict({"Preparation": "Infusion", "Extraction_Method": "Ethanol"})
    assert rec.preparation == "Infusion"
    # Extraction_Method has no canonical field mapping -> preserved in extra, untouched.
    assert rec.extra.get("Extraction_Method") == "Ethanol"


# ---- Issue 8: JSON-safe serialization ----

def test_issue8_nested_structures_datetime_and_set_are_json_safe():
    class Color(Enum):
        RED = "red"

    rec = EvidenceRecord(
        doi="10.1/x",
        extra={
            "when": datetime(2020, 1, 1, 12, 0, 0),
            "day": date(2020, 1, 1),
            "amount": Decimal("3.14"),
            "color": Color.RED,
            "tags": {"a", "b"},
            "nested": {"inner_list": [1, 2, {"deep": datetime(2021, 5, 5)}]},
        },
    )
    data = rec.to_dict()
    serialized = _json.dumps(data)  # must not raise
    reloaded = _json.loads(serialized)
    assert reloaded["extra"]["when"] == "2020-01-01T12:00:00"
    assert reloaded["extra"]["day"] == "2020-01-01"
    assert reloaded["extra"]["amount"] == 3.14
    assert reloaded["extra"]["color"] == "red"
    assert set(reloaded["extra"]["tags"]) == {"a", "b"}
    assert reloaded["extra"]["nested"]["inner_list"][2]["deep"] == "2021-05-05T00:00:00"


def test_issue8_unknown_object_type_falls_back_to_string():
    class Widget:
        def __str__(self):
            return "widget-instance"

    rec = EvidenceRecord(doi="10.1/x", extra={"thing": Widget()})
    data = rec.to_dict()
    assert data["extra"]["thing"] == "widget-instance"
    _json.dumps(data)  # must not raise


# ---- Issue 9: integration tests ----

def test_issue9_integration_connector_record_through_standardizer_to_canonical():
    import evidence_standardizer as es_mod

    connector_record = {
        "Scientific_Name": "Ginkgo biloba", "Source_Type": "Europe PMC",
        "Source_Title": "Ginkgo Extract and Memory", "Source_URL": "https://x",
        "Source_Year": "2021", "PMID": "PMID:777", "DOI": "https://doi.org/10.1/Y",
        "Notes": "text", "Target_Indication": "Memory", "Dosage_Form": "Capsule",
    }
    standardized = es_mod.standardize_extracted_record(
        extracted=connector_record,
        source_metadata={"source_type": "Europe PMC", "source_title": connector_record["Source_Title"],
                          "source_url": connector_record["Source_URL"], "source_year": "2021"},
    )
    canonical = EvidenceRecord.from_legacy_dict(standardized)
    assert canonical.pmid == "PMID:777"  # raw form preserved on the record; normalization happens in identity functions
    assert normalize_pmid(canonical.pmid) == "777"
    assert normalize_doi(canonical.doi) == "10.1/y"


def test_issue9_integration_pubmed_and_europepmc_same_article_one_identity():
    pubmed_style = {"PMID": "555", "Source_Title": "T", "Source_Type": "PubMed"}
    europepmc_style = {"PMID": "PMID:555", "Source_Title": "T", "Source_Type": "Europe PMC"}
    assert compute_article_identity(pubmed_style) == compute_article_identity(europepmc_style)


def test_issue9_integration_two_outcomes_survive_full_dedup_pass():
    df = pd.DataFrame([
        {"Scientific_Name": "Ginkgo biloba", "Target_Indication": "Memory", "Dosage_Form": "Capsule",
         "DOI": "10.1/shared", "Primary_Outcome": "Reaction time", "Evidence_Score": 10, "Evidence_Quality_Score": 5},
        {"Scientific_Name": "Ginkgo biloba", "Target_Indication": "Memory", "Dosage_Form": "Capsule",
         "DOI": "10.1/shared", "Primary_Outcome": "Recall accuracy", "Evidence_Score": 8, "Evidence_Quality_Score": 5},
    ])
    out = deduplicate_evidence(df)
    assert len(out) == 2


def test_issue9_integration_evidence_record_ids_preserved_after_serialization_and_persistence():
    import decision_record_persistence as drp
    import unittest.mock as mock

    class _FakeResult:
        def __init__(self, data):
            self.data = data

    class _FakeInsertTable:
        def __init__(self, store):
            self.store = store

        def insert(self, payload):
            self.store.append(payload)
            return self

        def execute(self):
            return _FakeResult([{"id": 1}])

    class _FakeClient:
        def __init__(self):
            self.store = []

        def table(self, name):
            return _FakeInsertTable(self.store)

    record = {
        "reference_plant": "Ginkgo biloba", "indication": "Memory",
        "applicability_summary": {"evidence_record_ids": ["10", "11"]},
    }
    client = _FakeClient()
    drp.persist_decision_record([record], indication="Memory", supabase_client=client)
    persisted = _json.loads(client.store[0]["records"])[0]
    assert persisted["applicability_summary"]["evidence_record_ids"] == ["10", "11"]


# ======================================================================
# PHASE 2 — REVIEW ROUND 3 additions
# ======================================================================

from deduplication_engine import evidence_contexts_equivalent


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeTable:
    def __init__(self, name, harness):
        self.name = name
        self.harness = harness
        self._filters = {}
        self._insert_payload = None
        self._is_select = False

    def select(self, *a, **kw):
        self._is_select = True
        return self

    def eq(self, field, value):
        self._filters[field] = value
        return self

    def limit(self, *a, **kw):
        return self

    def insert(self, payload):
        self._insert_payload = payload
        return self

    def execute(self):
        return self.harness._execute(self)


class _InsertTimeHarness:
    """Small in-memory fake Supabase client backing plants/sources/
    evidence_records, faithful enough to real save_evidence_record()'s
    query shapes (select+eq+limit, and insert) to exercise the actual
    two-phase insert-time dedup logic end-to-end, not just its helper
    functions in isolation."""

    def __init__(self):
        self.sources = []
        self.evidence = []
        self.plants = [{"id": 1, "scientific_name": "Ginkgo biloba"}]

    def table(self, name):
        return _FakeTable(name, self)

    def _execute(self, t):
        if t.name == "plants":
            if t._is_select:
                return _FakeResult(self.plants)
            return _FakeResult([{"id": 1}])

        if t.name == "sources":
            if t._is_select:
                if "year" in t._filters:
                    return _FakeResult([s for s in self.sources if s["year"] == t._filters["year"]])
                if "url" in t._filters:
                    return _FakeResult([s for s in self.sources if s.get("url") == t._filters["url"]])
                if "title" in t._filters:
                    return _FakeResult([s for s in self.sources if s.get("title") == t._filters["title"]])
                return _FakeResult([])
            new_source = {
                "id": len(self.sources) + 1,
                "title": t._insert_payload["title"],
                "year": t._insert_payload["year"],
                "url": t._insert_payload.get("url", ""),
            }
            self.sources.append(new_source)
            return _FakeResult([new_source])

        if t.name == "evidence_records":
            if t._is_select:
                if any(k in t._filters for k in ("doi", "pmid", "nct_id")):
                    key = "doi" if "doi" in t._filters else ("pmid" if "pmid" in t._filters else "nct_id")
                    matches = [
                        e for e in self.evidence
                        if e.get(key) == t._filters.get(key)
                        and e.get("plant_id") == t._filters.get("plant_id")
                        and e.get("target_indication") == t._filters.get("target_indication")
                        and e.get("dosage_form") == t._filters.get("dosage_form")
                    ]
                    return _FakeResult(matches)
                matches = [
                    e for e in self.evidence
                    if e.get("source_id") == t._filters.get("source_id")
                    and e.get("plant_id") == t._filters.get("plant_id")
                    and e.get("target_indication") == t._filters.get("target_indication")
                    and e.get("dosage_form") == t._filters.get("dosage_form")
                ]
                return _FakeResult(matches)
            new_evidence = dict(t._insert_payload)
            new_evidence["id"] = len(self.evidence) + 100
            self.evidence.append(new_evidence)
            return _FakeResult([new_evidence])

        raise AssertionError(f"unexpected table {t.name}")


def _save(harness, **overrides):
    import database as db_mod
    import unittest.mock as mock
    base = {
        "Scientific_Name": "Ginkgo biloba", "Source_URL": "https://example.com/1",
        "Source_Title": "Effects of Ginkgo Biloba Extract on Cognitive Memory Function",
        "Source_Year": "2020", "Target_Indication": "Memory", "Dosage_Form": "Capsule",
    }
    base.update(overrides)
    with mock.patch("database.get_supabase_client", return_value=harness):
        return db_mod.save_evidence_record(base)


# ---- Issue 1 (review round 3): insert-time must not collapse different Evidence ----

def test_r3_issue1_doi_same_outcome_different_both_inserted():
    harness = _InsertTimeHarness()
    id1 = _save(harness, DOI="10.1/x", Source_URL="https://a.example/1", Primary_Outcome="Reaction time")
    id2 = _save(harness, DOI="10.1/x", Source_URL="https://b.example/2", Primary_Outcome="Recall accuracy")
    assert id1 != id2
    assert len(harness.evidence) == 2


def test_r3_issue1_doi_same_direction_different_both_inserted():
    harness = _InsertTimeHarness()
    id1 = _save(harness, DOI="10.1/x", Source_URL="https://a.example/1", Result_Direction="Positive")
    id2 = _save(harness, DOI="10.1/x", Source_URL="https://b.example/2", Result_Direction="Negative")
    assert id1 != id2
    assert len(harness.evidence) == 2


def test_r3_issue1_pmid_same_population_different_both_inserted():
    harness = _InsertTimeHarness()
    id1 = _save(harness, PMID="777", Source_URL="https://a.example/1", Population="Adults")
    id2 = _save(harness, PMID="777", Source_URL="https://b.example/2", Population="Children")
    assert id1 != id2
    assert len(harness.evidence) == 2


def test_r3_issue1_nct_same_claim_formatting_different_one_record():
    harness = _InsertTimeHarness()
    id1 = _save(harness, NCT_ID="NCT01234567", Source_URL="https://a.example/1",
                Notes="Extract reduced sleep latency by 20%.")
    id2 = _save(harness, NCT_ID="NCT01234567", Source_URL="https://b.example/2",
                Notes="  extract reduced sleep latency by 20%  ")
    assert id1 == id2
    assert len(harness.evidence) == 1


def test_r3_issue1_doi_same_evidence_identity_fully_same_second_insert_skipped():
    harness = _InsertTimeHarness()
    id1 = _save(harness, DOI="10.1/x", Source_URL="https://a.example/1",
                Primary_Outcome="Reaction time", Result_Direction="Positive")
    id2 = _save(harness, DOI="10.1/x", Source_URL="https://b.example/2",
                Primary_Outcome="Reaction time", Result_Direction="Positive")
    assert id1 == id2
    assert len(harness.evidence) == 1


# ---- Issue 2 (review round 3): fuzzy read-time dedup must preserve Evidence identity ----

def _fuzzy_pair(**overrides_b):
    a = {
        "article_title": "Effects of Ginkgo Biloba Extract on Cognitive Memory Function",
        "publication_year": "2020", "plant_species": "Ginkgo biloba",
        "indication": "Memory", "dosage_form": "Capsule",
    }
    b = dict(a, article_title="Effects of Ginkgo Biloba Extract on Cognitive Memory Function.")
    b.update(overrides_b)
    return a, b


def test_r3_issue2_fuzzy_title_outcome_different_both_remain():
    a, b = _fuzzy_pair(outcome="Reaction time")
    a["outcome"] = "Recall accuracy"
    assert articles_equivalent(a, b) is True
    assert evidence_contexts_equivalent(a, b) is False


def test_r3_issue2_fuzzy_title_direction_different_both_remain():
    a, b = _fuzzy_pair(evidence_direction="Negative")
    a["evidence_direction"] = "Positive"
    assert articles_equivalent(a, b) is True
    assert evidence_contexts_equivalent(a, b) is False


def test_r3_issue2_fuzzy_title_population_different_both_remain():
    a, b = _fuzzy_pair(population="Children")
    a["population"] = "Adults"
    assert articles_equivalent(a, b) is True
    assert evidence_contexts_equivalent(a, b) is False


def test_r3_issue2_fuzzy_title_claim_same_punctuation_different_one_remains():
    a, b = _fuzzy_pair()
    a["supporting_sentence"] = "Extract reduced sleep latency by 20%."
    b["supporting_sentence"] = "extract reduced sleep latency by 20%"
    assert articles_equivalent(a, b) is True
    assert evidence_contexts_equivalent(a, b) is True


def test_r3_issue2_fuzzy_title_plant_part_different_both_remain():
    a, b = _fuzzy_pair(plant_part="Leaf")
    a["plant_part"] = "Root"
    assert articles_equivalent(a, b) is True
    assert evidence_contexts_equivalent(a, b) is False


def test_r3_issue2_full_dedup_pass_keeps_distinct_outcomes_no_strong_id():
    df = pd.DataFrame([
        {"Scientific_Name": "Ginkgo biloba", "Target_Indication": "Memory", "Dosage_Form": "Capsule",
         "Source_Title": "Effects of Ginkgo Biloba Extract on Cognitive Memory Function",
         "Source_Year": "2020", "Primary_Outcome": "Reaction time",
         "Evidence_Score": 10, "Evidence_Quality_Score": 5},
        {"Scientific_Name": "Ginkgo biloba", "Target_Indication": "Memory", "Dosage_Form": "Capsule",
         "Source_Title": "Effects of Ginkgo Biloba Extract on Cognitive Memory Function.",
         "Source_Year": "2020", "Primary_Outcome": "Recall accuracy",
         "Evidence_Score": 8, "Evidence_Quality_Score": 5},
    ])
    out = deduplicate_evidence(df)
    assert len(out) == 2


# ---- Issue 4 (review round 3): first-author honesty in insert-time fuzzy fallback ----

def test_r3_issue4_similar_title_same_year_different_author_both_verifiable_not_duplicate():
    a = {"article_title": "Effects of Ginkgo Biloba Extract on Cognitive Memory Function",
         "publication_year": "2020", "first_author": "Smith"}
    b = {"article_title": "Effects of Ginkgo Biloba Extract on Cognitive Memory Function",
         "publication_year": "2020", "first_author": "Johnson"}
    assert articles_equivalent(a, b) is False


def test_r3_issue4_existing_author_unretrievable_moderately_similar_title_not_duplicate():
    # Existing side (as insert-time always produces — sources has no
    # author column) has no first_author key at all. A moderately (but
    # not near-identical) similar title must NOT be treated as the same
    # article under the stricter unverified-author threshold.
    a = {"article_title": "Ginkgo Biloba Extract Improves Memory Performance In Older Adults",
         "publication_year": "2020", "first_author": "Smith"}
    b = {"article_title": "Ginkgo Biloba Extract And Cognitive Function In Elderly Subjects",
         "publication_year": "2020"}
    assert articles_equivalent(a, b) is False


def test_r3_issue4_punctuation_only_variation_long_title_same_year_duplicate_acceptable():
    a = {"article_title": "Effects of Ginkgo Biloba Extract on Cognitive Memory Function: A Randomized Trial",
         "publication_year": "2020", "first_author": "Smith"}
    b = {"article_title": "Effects of Ginkgo Biloba Extract on Cognitive Memory Function - A Randomized Trial",
         "publication_year": "2020"}
    assert articles_equivalent(a, b) is True


def test_r3_issue4_insert_time_author_check_documented_as_title_year_only():
    import database
    doc = database._find_existing_evidence_by_fuzzy_title.__doc__
    assert "author" in doc.lower()
    assert "no author column" in doc.lower() or "no author" in doc.lower()


# ---- Issue 5 (review round 3): explicit false-positive matrix ----

def test_r3_issue5_matrix_doi_exact_outcome_different_two_evidence():
    a = {"doi": "10.1/x", "outcome": "A"}
    b = {"doi": "10.1/x", "outcome": "B"}
    assert compute_article_identity(a)[0] == compute_article_identity(b)[0] == "doi"
    assert compute_evidence_identity(a) != compute_evidence_identity(b)


def test_r3_issue5_matrix_doi_exact_direction_different_two_evidence():
    a = {"doi": "10.1/x", "evidence_direction": "Positive"}
    b = {"doi": "10.1/x", "evidence_direction": "Negative"}
    assert compute_evidence_identity(a) != compute_evidence_identity(b)


def test_r3_issue5_matrix_pmid_exact_claim_same_one_evidence():
    a = {"pmid": "1", "supporting_sentence": "Reduces latency."}
    b = {"pmid": "1", "supporting_sentence": "reduces latency"}
    assert compute_evidence_identity(a) == compute_evidence_identity(b)


def test_r3_issue5_matrix_fuzzy_title_outcome_different_two_evidence():
    a, b = _fuzzy_pair()
    a["outcome"] = "A"
    b["outcome"] = "B"
    assert articles_equivalent(a, b) and not evidence_contexts_equivalent(a, b)


def test_r3_issue5_matrix_fuzzy_title_claim_same_one_evidence():
    a, b = _fuzzy_pair()
    a["supporting_sentence"] = "Reduces latency."
    b["supporting_sentence"] = "reduces latency"
    assert articles_equivalent(a, b) and evidence_contexts_equivalent(a, b)


def test_r3_issue5_matrix_title_year_similar_author_different_two_articles():
    a = {"article_title": "Effects of Ginkgo Biloba Extract on Cognitive Memory Function",
         "publication_year": "2020", "first_author": "Smith"}
    b = {"article_title": "Effects of Ginkgo Biloba Extract on Cognitive Memory Function",
         "publication_year": "2020", "first_author": "Johnson"}
    assert articles_equivalent(a, b) is False


def test_r3_issue5_matrix_url_same_population_different_two_evidence():
    a = {"article_identifier": "https://x.example/1", "population": "Adults"}
    b = {"article_identifier": "https://x.example/1", "population": "Children"}
    assert compute_article_identity(a) == compute_article_identity(b)
    assert compute_evidence_identity(a) != compute_evidence_identity(b)


# ======================================================================
# PHASE 2 — REVIEW ROUND 4: legacy URL/title source-reuse path bugfix
# ======================================================================

def test_r4_legacy_url_same_outcome_different_two_evidence_one_source():
    harness = _InsertTimeHarness()
    id1 = _save(harness, Source_URL="https://same.example/1", Primary_Outcome="Reaction time")
    id2 = _save(harness, Source_URL="https://same.example/1", Primary_Outcome="Recall accuracy")
    assert id1 != id2
    assert len(harness.evidence) == 2
    assert len(harness.sources) == 1


def test_r4_legacy_url_same_direction_different_two_evidence_one_source():
    harness = _InsertTimeHarness()
    id1 = _save(harness, Source_URL="https://same.example/1", Result_Direction="Positive")
    id2 = _save(harness, Source_URL="https://same.example/1", Result_Direction="Negative")
    assert id1 != id2
    assert len(harness.evidence) == 2
    assert len(harness.sources) == 1


def test_r4_legacy_url_same_population_different_two_evidence_one_source():
    harness = _InsertTimeHarness()
    id1 = _save(harness, Source_URL="https://same.example/1", Population="Adults")
    id2 = _save(harness, Source_URL="https://same.example/1", Population="Children")
    assert id1 != id2
    assert len(harness.evidence) == 2
    assert len(harness.sources) == 1


def test_r4_legacy_url_same_plant_part_different_two_evidence_one_source():
    harness = _InsertTimeHarness()
    id1 = _save(harness, Source_URL="https://same.example/1", Plant_Part="Leaf")
    id2 = _save(harness, Source_URL="https://same.example/1", Plant_Part="Root")
    assert id1 != id2
    assert len(harness.evidence) == 2
    assert len(harness.sources) == 1


def test_r4_legacy_url_same_context_fully_same_one_evidence():
    harness = _InsertTimeHarness()
    id1 = _save(harness, Source_URL="https://same.example/1",
                Primary_Outcome="Reaction time", Result_Direction="Positive")
    id2 = _save(harness, Source_URL="https://same.example/1",
                Primary_Outcome="Reaction time", Result_Direction="Positive")
    assert id1 == id2
    assert len(harness.evidence) == 1
    assert len(harness.sources) == 1


def test_r4_legacy_title_same_no_url_context_different_two_evidence_one_source():
    harness = _InsertTimeHarness()
    id1 = _save(harness, Source_URL="", Source_Title="A Unique Non-Generic Title About Ginkgo",
                Primary_Outcome="Reaction time")
    id2 = _save(harness, Source_URL="", Source_Title="A Unique Non-Generic Title About Ginkgo",
                Primary_Outcome="Recall accuracy")
    assert id1 != id2
    assert len(harness.evidence) == 2
    assert len(harness.sources) == 1


def test_r4_doi_path_still_passes_after_legacy_fix():
    harness = _InsertTimeHarness()
    id1 = _save(harness, DOI="10.1/x", Source_URL="https://a.example/1", Primary_Outcome="Reaction time")
    id2 = _save(harness, DOI="10.1/x", Source_URL="https://b.example/2", Primary_Outcome="Reaction time")
    assert id1 == id2
    assert len(harness.evidence) == 1


def test_r4_pmid_path_still_passes_after_legacy_fix():
    harness = _InsertTimeHarness()
    id1 = _save(harness, PMID="777", Source_URL="https://a.example/1")
    id2 = _save(harness, PMID="777", Source_URL="https://b.example/2")
    assert id1 == id2
    assert len(harness.evidence) == 1


def test_r4_nct_path_still_passes_after_legacy_fix():
    harness = _InsertTimeHarness()
    id1 = _save(harness, NCT_ID="NCT01234567", Source_URL="https://a.example/1")
    id2 = _save(harness, NCT_ID="NCT01234567", Source_URL="https://b.example/2")
    assert id1 == id2
    assert len(harness.evidence) == 1


def test_r4_regression_legacy_path_no_longer_dedupes_on_source_plant_indication_dosage_alone():
    """Explicit regression lock: the legacy URL/title source-reuse path
    must never again decide Evidence duplication using ONLY
    source_id + plant_id + indication + dosage_form (with no
    evidence-context comparison at all) — this was the exact bug found
    in the round-4 review. A same-source, same-plant, same-indication,
    same-dosage-form pair with a genuinely different scientific context
    (here: outcome) must NOT collapse to one evidence_records row."""
    harness = _InsertTimeHarness()
    id1 = _save(
        harness, Source_URL="https://same.example/regression",
        Target_Indication="Memory", Dosage_Form="Capsule", Primary_Outcome="Outcome A",
    )
    id2 = _save(
        harness, Source_URL="https://same.example/regression",
        Target_Indication="Memory", Dosage_Form="Capsule", Primary_Outcome="Outcome B",
    )
    # Same source_id + plant_id + indication + dosage_form on both calls
    # — if the legacy bug were still present, this would incorrectly
    # collapse to one row. It must not.
    assert id1 != id2
    assert len(harness.evidence) == 2
    assert harness.evidence[0]["source_id"] == harness.evidence[1]["source_id"]


# ======================================================================
# PHASE 2 — REVIEW ROUND 5: Dose / Preparation persistence + identity fix
# ======================================================================

def test_r5_doi_same_dose_same_context_one_evidence():
    harness = _InsertTimeHarness()
    id1 = _save(harness, DOI="10.1/x", Source_URL="https://a.example/1", Dose="500mg")
    id2 = _save(harness, DOI="10.1/x", Source_URL="https://b.example/2", Dose="500mg")
    assert id1 == id2
    assert len(harness.evidence) == 1


def test_r5_doi_same_dose_different_two_evidence():
    harness = _InsertTimeHarness()
    id1 = _save(harness, DOI="10.1/x", Source_URL="https://a.example/1", Dose="500mg")
    id2 = _save(harness, DOI="10.1/x", Source_URL="https://b.example/2", Dose="1000mg")
    assert id1 != id2
    assert len(harness.evidence) == 2


def test_r5_url_title_same_preparation_same_context_one_evidence():
    harness = _InsertTimeHarness()
    id1 = _save(harness, Source_URL="https://same.example/1", Preparation="Tincture")
    id2 = _save(harness, Source_URL="https://same.example/1", Preparation="Tincture")
    assert id1 == id2
    assert len(harness.evidence) == 1
    assert len(harness.sources) == 1


def test_r5_url_title_same_preparation_different_two_evidence():
    harness = _InsertTimeHarness()
    id1 = _save(harness, Source_URL="https://same.example/1", Preparation="Tincture")
    id2 = _save(harness, Source_URL="https://same.example/1", Preparation="Infusion")
    assert id1 != id2
    assert len(harness.evidence) == 2
    assert len(harness.sources) == 1


def test_r5_dose_and_preparation_both_retrieved_on_candidate_fetch():
    """After a real save_evidence_record() insert with both Dose and
    Preparation set, a subsequent identity candidate fetch must actually
    retrieve both values (not silently treat them as always-empty)."""
    import database as db_mod
    harness = _InsertTimeHarness()
    _save(harness, DOI="10.1/y", Source_URL="https://a.example/9",
          Dose="250mg", Preparation="Capsule extract")

    candidates = db_mod._fetch_evidence_identity_candidates(
        harness, 1, "Memory", "Capsule", "doi", "10.1/y",
    )
    assert candidates is not None
    assert len(candidates) == 1
    assert candidates[0].get("dose") == "250mg"
    assert candidates[0].get("preparation") == "Capsule extract"


def test_r5_preparation_and_extraction_method_remain_independent():
    harness = _InsertTimeHarness()
    id1 = _save(harness, Source_URL="https://same.example/ext",
                Preparation="Infusion", Extraction_Method="Ethanol")
    id2 = _save(harness, Source_URL="https://same.example/ext",
                Preparation="Infusion", Extraction_Method="Methanol")
    # Extraction_Method has no evidence_records column and is not part
    # of evidence_contexts_equivalent()'s dimensions — it must never be
    # able to force two rows apart (or together). Preparation matches
    # on both sides, so these still collapse to one Evidence.
    assert id1 == id2
    assert len(harness.evidence) == 1

    # And, going the other direction: identical Extraction_Method with
    # different Preparation must still be treated as two Evidence —
    # Preparation, not Extraction_Method, is the dimension that matters
    # for evidence identity.
    harness2 = _InsertTimeHarness()
    id3 = _save(harness2, Source_URL="https://same.example/ext2",
                Preparation="Infusion", Extraction_Method="Ethanol")
    id4 = _save(harness2, Source_URL="https://same.example/ext2",
                Preparation="Tincture", Extraction_Method="Ethanol")
    assert id3 != id4
    assert len(harness2.evidence) == 2


def test_r5_missing_optional_columns_deployment_falls_back_safely():
    """A deployment where dose/preparation (and plant_part) columns do
    not exist yet must degrade safely — never manufacture a false
    duplicate, and never raise."""
    import database as db_mod

    class _NoOptionalColumnsTable:
        def __init__(self, name, harness):
            self.name = name
            self.harness = harness
            self._filters = {}
            self._select_columns = []
            self._is_select = False

        def select(self, columns, *a, **kw):
            self._is_select = True
            self._select_columns = [c.strip() for c in columns.split(",")]
            return self

        def eq(self, field, value):
            self._filters[field] = value
            return self

        def limit(self, *a, **kw):
            return self

        def execute(self):
            missing = {"plant_part", "dose", "preparation"} & set(self._select_columns)
            if missing:
                raise Exception(
                    f"PGRST204: Could not find the '{sorted(missing)[0]}' column of "
                    "'evidence_records' in the schema cache"
                )
            row = {
                "id": 555, "population": "Adults", "primary_outcome": "Reaction time",
                "result_direction": "Positive", "study_type": "RCT", "notes": "",
            }
            return _FakeResult([row])

    class _Harness:
        def table(self, name):
            return _NoOptionalColumnsTable(name, self)

    harness = _Harness()
    candidates = db_mod._fetch_evidence_identity_candidates(
        harness, 1, "Memory", "Capsule", "doi", "10.1/old-deployment",
    )
    # Must not raise, must not return None (the query IS resolvable once
    # the optional columns are dropped), and must return the row with
    # the always-present dimensions intact.
    assert candidates is not None
    assert len(candidates) == 1
    assert candidates[0]["id"] == 555
    assert candidates[0].get("dose") is None
    assert candidates[0].get("preparation") is None
    assert candidates[0].get("plant_part") is None
    assert candidates[0].get("primary_outcome") == "Reaction time"


# ---- Round 4 tests must still pass unchanged after this round's edits ----

def test_r5_round4_regression_still_passes():
    harness = _InsertTimeHarness()
    id1 = _save(
        harness, Source_URL="https://same.example/regression2",
        Target_Indication="Memory", Dosage_Form="Capsule", Primary_Outcome="Outcome A",
    )
    id2 = _save(
        harness, Source_URL="https://same.example/regression2",
        Target_Indication="Memory", Dosage_Form="Capsule", Primary_Outcome="Outcome B",
    )
    assert id1 != id2
    assert len(harness.evidence) == 2
