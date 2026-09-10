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

def test_u1_genuine_administration_verifies():
    result = ca.verify_pubmed_intervention_attribution(
        "Participants received Ficticus alpinum extract 300 mg daily.",
        scientific_name="Ficticus alpinum",
    )
    assert result["verified"] is True


def test_u2_negated_administration_does_not_verify():
    result = ca.verify_pubmed_intervention_attribution(
        "Participants received CBT rather than Ficticus alpinum extract.",
        scientific_name="Ficticus alpinum",
    )
    assert result["verified"] is False


def test_u3_historical_treatment_mention_does_not_verify():
    result = ca.verify_pubmed_intervention_attribution(
        "Patients received CBT; prior treatment with Ficticus alpinum extract was recorded.",
        scientific_name="Ficticus alpinum",
    )
    assert result["verified"] is False


def test_u4_exclusion_criterion_does_not_verify():
    result = ca.verify_pubmed_intervention_attribution(
        "Participants receiving Ficticus alpinum were excluded.",
        scientific_name="Ficticus alpinum",
    )
    assert result["verified"] is False


def test_u5_prior_literature_background_does_not_verify():
    result = ca.verify_pubmed_intervention_attribution(
        "Previous studies administered Ficticus alpinum for insomnia. "
        "In the present randomized trial participants received CBT.",
        scientific_name="Ficticus alpinum",
    )
    assert result["verified"] is False


def test_u6_genuine_randomized_botanical_arm_verifies():
    result = ca.verify_pubmed_intervention_attribution(
        "Participants were randomized to Ficticus alpinum extract or placebo.",
        scientific_name="Ficticus alpinum",
    )
    assert result["verified"] is True


def test_background_plus_administration_language_elsewhere_does_not_verify():
    # The exact combined example from the cahier: a background clause that
    # itself contains an administration-style word ("administered") must
    # still not verify, because it is historical/background language, not
    # the present study's actual arm.
    result = ca.verify_pubmed_intervention_attribution(
        "Although Ficticus alpinum has previously been administered for "
        "insomnia, participants in the present study received placebo and CBT.",
        scientific_name="Ficticus alpinum",
    )
    assert result["verified"] is False


def test_true_positives_from_first_pass_still_verify_after_defect_b_fix():
    for text in (
        "Participants received Ficticus alpinum extract 300 mg daily.",
        "Subjects were randomized to Ficticus alpinum extract or placebo.",
        "The intervention group received 500 mg of Ficticus alpinum twice daily.",
    ):
        assert ca.verify_pubmed_intervention_attribution(
            text, scientific_name="Ficticus alpinum"
        )["verified"] is True


def test_common_name_administration_verifies_with_mapping_supplied():
    result = ca.verify_pubmed_intervention_attribution(
        "Participants received lemon balm extract twice daily.",
        scientific_name="Melissa officinalis",
        common_name="lemon balm",
    )
    assert result["verified"] is True


def test_common_name_administration_fails_closed_without_mapping():
    # Documented limitation: without a supplied common-name mapping, this
    # cannot be verified from the scientific name alone.
    result = ca.verify_pubmed_intervention_attribution(
        "Participants received lemon balm extract twice daily.",
        scientific_name="Melissa officinalis",
    )
    assert result["verified"] is False


# =======================================================================
# Full pipeline invariant: retrieval -> attribution -> standardization ->
# persistence -> reload -> shortlisting/adjudication
# =======================================================================

def test_full_pipeline_invariant_verified_record_survives_round_trip_and_qualifies():
    # 1. Retrieval + attribution (as evidence_collector.py's PubMed path
    #    would produce for a genuinely relevant article).
    raw_text = (
        "A Randomized Trial of Ficticus alpinum Extract for Insomnia\n\n"
        "Participants were randomized to Ficticus alpinum extract 300 mg "
        "or placebo. The primary outcome was sleep onset latency, which "
        "improved significantly in the treatment group."
    )
    attribution = ca.verify_pubmed_intervention_attribution(
        raw_text, scientific_name="Ficticus alpinum"
    )
    assert attribution["verified"] is True

    extracted = {
        "Scientific_Name": "Ficticus alpinum",
        "Candidate_Attribution_Verified": attribution["verified"],
        "Candidate_Attribution_Basis": attribution["basis"],
        "Target_Indication": "sleep",
        "Primary_Outcome": "sleep onset latency",
        "Result_Direction": "positive",
        "Study_Type": "Randomized placebo-controlled clinical trial",
        "Source_Title": "A Randomized Trial of Ficticus alpinum Extract for Insomnia",
        "Notes": raw_text,
    }

    # 2. Standardization (preserves the new fields -- see
    #    evidence_standardizer.py's preserve-list).
    from evidence_standardizer import standardize_extracted_record
    standardized = standardize_extracted_record(
        extracted=extracted,
        source_metadata={
            "source_type": "PubMed", "source_title": extracted["Source_Title"],
            "source_url": "", "source_organization": "NCBI PubMed", "source_year": "",
        },
        allow_llm=False,
    )
    assert standardized["Candidate_Attribution_Verified"] is True

    # 3. Persistence (save).
    fake = FakeSupabase()
    with mock.patch("database.get_supabase_client", return_value=fake):
        database.save_evidence_record(standardized)
    saved_payload = fake.inserted_evidence_payloads[0]
    assert saved_payload["candidate_attribution_verified"] is True
    assert saved_payload["candidate_attribution_basis"] == attribution["basis"]

    # 4. Reload.
    class _SelectResult:
        data = [{
            "id": 55,
            "plant_id": 3,
            "plants": {"scientific_name": "Ficticus alpinum", "common_name": ""},
            "sources": {"source_type": "PubMed", "title": extracted["Source_Title"]},
            "candidate_attribution_verified": saved_payload["candidate_attribution_verified"],
            "candidate_attribution_basis": saved_payload["candidate_attribution_basis"],
            "target_indication": saved_payload["target_indication"],
            "primary_outcome": saved_payload["primary_outcome"],
            "result_direction": saved_payload["result_direction"],
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
    reloaded_row = rows.iloc[0]
    assert bool(reloaded_row["Candidate_Attribution_Verified"]) is True
    assert reloaded_row["Candidate_Attribution_Basis"] == attribution["basis"]

    # 5. Shortlisting/adjudication -- the reloaded row must still be
    #    candidate-specific and outcome-specific.
    assert _row_has_verified_candidate_attribution(reloaded_row) is True
    assert _row_has_indication_specific_outcome(reloaded_row, "sleep") is True

    df = pd.DataFrame([{
        "Alternative_Plant": "Ficticus alpinum",
        "Source_Record_IDs": "PIPE-1",
        "Indication_Match_Type": "explicit_field_overlap",
        "Primary_Outcome": reloaded_row["Primary_Outcome"],
        "Study_Design": reloaded_row["Study_Type"] if "Study_Type" in reloaded_row else "Randomized placebo-controlled clinical trial",
        "Evidence_Direction": reloaded_row["Result_Direction"],
        "Candidate_Attribution_Verified": reloaded_row["Candidate_Attribution_Verified"],
        "Candidate_Attribution_Basis": reloaded_row["Candidate_Attribution_Basis"],
    }])
    items = eae.build_adjudication_evidence_items(df, "Ficticus alpinum", "sleep", 25)
    assert len(items) == 1
    assert items[0]["candidate_specific"] is True
    assert items[0]["outcome_specific"] is True


def test_full_pipeline_invariant_unverified_record_stays_unverified_after_round_trip():
    # A record whose only botanical mention is background (the false-
    # positive pattern from Defect B) must remain unverified end to end.
    raw_text = (
        "Background: Ficticus alpinum is traditionally used for sleep. "
        "In this randomized trial, patients received cognitive behavioral "
        "therapy versus placebo. Sleep onset latency was the primary outcome."
    )
    attribution = ca.verify_pubmed_intervention_attribution(
        raw_text, scientific_name="Ficticus alpinum"
    )
    assert attribution["verified"] is False

    extracted = {
        "Scientific_Name": "Ficticus alpinum",
        "Candidate_Attribution_Verified": attribution["verified"],
        "Candidate_Attribution_Basis": attribution["basis"],
        "Target_Indication": "sleep",
        "Primary_Outcome": "sleep onset latency",
        "Result_Direction": "positive",
        "Source_Title": "A trial of CBT for insomnia",
        "Notes": raw_text,
    }

    from evidence_standardizer import standardize_extracted_record
    standardized = standardize_extracted_record(
        extracted=extracted,
        source_metadata={
            "source_type": "PubMed", "source_title": extracted["Source_Title"],
            "source_url": "", "source_organization": "NCBI PubMed", "source_year": "",
        },
        allow_llm=False,
    )
    assert standardized["Candidate_Attribution_Verified"] is False

    fake = FakeSupabase()
    with mock.patch("database.get_supabase_client", return_value=fake):
        database.save_evidence_record(standardized)
    saved_payload = fake.inserted_evidence_payloads[0]
    assert saved_payload["candidate_attribution_verified"] is False

    class _SelectResult:
        data = [{
            "id": 56,
            "plant_id": 4,
            "plants": {"scientific_name": "Ficticus alpinum", "common_name": ""},
            "sources": {},
            "candidate_attribution_verified": saved_payload["candidate_attribution_verified"],
            "candidate_attribution_basis": saved_payload["candidate_attribution_basis"],
            "primary_outcome": saved_payload["primary_outcome"],
            "result_direction": saved_payload["result_direction"],
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
    reloaded_row = rows.iloc[0]
    assert bool(reloaded_row["Candidate_Attribution_Verified"]) is False
    assert _row_has_verified_candidate_attribution(reloaded_row) is False
    assert _row_has_indication_specific_outcome(reloaded_row, "sleep") is False
