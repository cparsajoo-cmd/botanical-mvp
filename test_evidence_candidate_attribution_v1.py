"""Regression tests for Problem 1 -- incorrect evidence attribution / source
relevance.

These tests are deliberately GENERAL: fictional botanicals and indications
are used throughout so nothing here depends on a hardcoded plant-name
blacklist. Each test corresponds to one of the cahier's required cases
(A-F), plus direct unit coverage of the new candidate_attribution.py module
and the two real connectors whose unscoped queries / blind attribution
stamping were the confirmed root cause.
"""
import pandas as pd

import candidate_attribution as ca
import evidence_adjudication_engine as eae
from candidate_shortlisting import (
    _row_has_indication_specific_outcome,
    _row_has_verified_candidate_attribution,
)


# ---------------------------------------------------------------------
# Unit coverage of the new general verification primitive
# ---------------------------------------------------------------------

def test_full_binomial_present_is_verified():
    result = ca.verify_candidate_attribution(
        "A randomized trial of Ficticus alpinum extract for exercise recovery.",
        scientific_name="Ficticus alpinum",
    )
    assert result["verified"] is True
    assert result["basis"] == "full_binomial"


def test_common_name_present_is_verified_with_whole_word_matching():
    result = ca.verify_candidate_attribution(
        "Effects of lemon verbena tea on sleep onset in adults.",
        scientific_name="Aloysia citrodora",
        common_name="lemon verbena",
    )
    assert result["verified"] is True
    assert result["basis"] == "common_name"


def test_different_species_binomial_does_not_false_match():
    # Prior real production bug: "lemon" (Citrus limon) must not false-match
    # inside "lemon verbena" (Aloysia citrodora), a different species. The
    # full scientific binomial of the candidate must not be considered
    # present merely because a different, textually-similar species' common
    # name appears in the record.
    result = ca.verify_candidate_attribution(
        "A trial of lemon verbena extract for anxiety.",
        scientific_name="Citrus limon",
    )
    assert result["verified"] is False


def test_multi_word_common_name_requires_every_word_present():
    # A multi-word common name ("lemon balm") is a much more specific
    # candidate-attribution signal than a single generic word ("lemon")
    # would be; every word of it must be present as whole words.
    result = ca.verify_candidate_attribution(
        "A trial of lemon verbena extract for anxiety.",
        scientific_name="Melissa officinalis",
        common_name="lemon balm",
    )
    assert result["verified"] is False


# ---------------------------------------------------------------------
# Case F -- insufficient metadata must fail closed, never become confident
# ---------------------------------------------------------------------

def test_no_text_available_fails_closed_not_direct():
    result = ca.verify_candidate_attribution("", scientific_name="Ficticus alpinum")
    assert result["verified"] is False
    assert result["basis"] == ""


def test_adjudication_downgrades_record_with_insufficient_metadata():
    df = pd.DataFrame([{
        "Alternative_Plant": "Ficticus alpinum",
        "Source_Record_IDs": "F-1",
        "Indication_Match_Type": "explicit_field_overlap",
        "Primary_Outcome": "sleep quality",
        "Candidate_Attribution_Verified": False,  # connector could not establish attribution
    }])
    items = eae.build_adjudication_evidence_items(df, "Ficticus alpinum", "sleep", 25)
    assert len(items) == 1
    assert items[0]["candidate_specific"] is False
    assert items[0]["outcome_specific"] is False


# ---------------------------------------------------------------------
# Cases A and D -- candidate mismatch (source not about the candidate plant,
# or belongs to another botanical entirely)
# ---------------------------------------------------------------------

def test_case_a_unrelated_trial_stamped_with_candidate_name_is_downgraded():
    # Mirrors the real Melissa officinalis / congenital-heart-disease case:
    # a trial genuinely about an unrelated condition that a loosely-scoped
    # connector query happened to return and stamp with the candidate's name.
    row_text = (
        "A Pragmatic Clinical Trial of the WE BEAT Well-Being Education "
        "Program in Adolescent Congenital Heart Disease"
    )
    attribution = ca.verify_candidate_attribution(row_text, scientific_name="Ficticus alpinum")
    assert attribution["verified"] is False

    df = pd.DataFrame([{
        "Alternative_Plant": "Ficticus alpinum",
        "Source_Record_IDs": "A-1",
        "Indication_Match_Type": "explicit_field_overlap",
        "Primary_Outcome": "sleep quality",
        "Candidate_Attribution_Verified": attribution["verified"],
        "Candidate_Attribution_Basis": attribution["basis"],
    }])
    items = eae.build_adjudication_evidence_items(df, "Ficticus alpinum", "sleep", 25)
    assert items[0]["outcome_specific"] is False


def test_case_d_source_belonging_to_another_botanical_is_downgraded():
    # A paper about a genuinely different species that shares a compound
    # with the candidate must not become candidate-specific evidence merely
    # because of that shared chemistry.
    row_text = "Rosmarinic acid content and antioxidant activity in Rosmarinus officinalis leaf extracts."
    attribution = ca.verify_candidate_attribution(row_text, scientific_name="Ficticus alpinum")
    assert attribution["verified"] is False

    row = pd.Series({"Candidate_Attribution_Verified": False})
    assert _row_has_verified_candidate_attribution(row) is False
    assert _row_has_indication_specific_outcome(row, "sleep") is False


# ---------------------------------------------------------------------
# Cases B and C -- outcome mismatch (candidate correctly identified, but the
# study does not evaluate the queried indication/outcome)
# ---------------------------------------------------------------------

def test_case_b_physical_performance_study_is_not_sleep_evidence():
    row = pd.Series({
        "Candidate_Attribution_Verified": True,
        "Primary_Outcome": "football player physical performance and decision-making speed",
    })
    assert _row_has_verified_candidate_attribution(row) is True
    assert _row_has_indication_specific_outcome(row, "sleep") is False


def test_case_c_tinnitus_trial_is_not_sleep_evidence():
    row = pd.Series({
        "Candidate_Attribution_Verified": True,
        "Primary_Outcome": "tinnitus severity and loudness matching",
    })
    assert _row_has_verified_candidate_attribution(row) is True
    assert _row_has_indication_specific_outcome(row, "sleep") is False


# ---------------------------------------------------------------------
# Case E -- a genuinely relevant human trial (candidate = intervention AND
# queried indication = measured outcome) MUST still qualify.
# ---------------------------------------------------------------------

def test_case_e_genuinely_relevant_trial_still_qualifies():
    row = pd.Series({
        "Candidate_Attribution_Verified": True,
        "Primary_Outcome": "sleep onset latency and total sleep time",
    })
    assert _row_has_verified_candidate_attribution(row) is True
    assert _row_has_indication_specific_outcome(row, "sleep") is True

    df = pd.DataFrame([{
        "Alternative_Plant": "Ficticus alpinum",
        "Source_Record_IDs": "E-1",
        "Indication_Match_Type": "explicit_field_overlap",
        "Primary_Outcome": "sleep onset latency and total sleep time",
        "Study_Design": "Randomized double-blind placebo-controlled clinical trial",
        "Evidence_Direction": "positive",
        "Candidate_Attribution_Verified": True,
        "Candidate_Attribution_Basis": "full_binomial",
    }])
    items = eae.build_adjudication_evidence_items(df, "Ficticus alpinum", "sleep", 25)
    assert len(items) == 1
    assert items[0]["candidate_specific"] is True
    assert items[0]["outcome_specific"] is True
    assert items[0]["human_animal_in_vitro"] == "HUMAN"


# ---------------------------------------------------------------------
# Backward compatibility -- rows/fixtures that never populated the new
# field must behave exactly as before this fix (additive, opt-in gate).
# ---------------------------------------------------------------------

def test_absent_attribution_field_preserves_legacy_behavior():
    row = pd.Series({"Primary_Outcome": "sleep onset latency"})
    assert _row_has_verified_candidate_attribution(row) is True
    assert _row_has_indication_specific_outcome(row, "sleep") is True


# ---------------------------------------------------------------------
# Connector-level root-cause coverage: the query itself must be scoped, and
# attribution must be computed from the source's OWN content.
# ---------------------------------------------------------------------

def test_clinicaltrials_connector_query_is_and_scoped_not_free_text(monkeypatch):
    import clinicaltrials_connector as ctc

    captured = {}

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"studies": []}

    def _fake_get(url, params=None, timeout=None):
        captured["params"] = params
        return _FakeResponse()

    monkeypatch.setattr(ctc.requests, "get", _fake_get)
    ctc.search_clinicaltrials("Ficticus alpinum", "sleep")
    query_term = captured["params"]["query.term"]
    # Both terms must be quoted phrases joined with AND -- not a bare,
    # unscoped space-joined free-text search (the confirmed root cause).
    assert query_term == '"Ficticus alpinum" AND "sleep"'


def test_clinicaltrials_connector_marks_unrelated_result_unverified(monkeypatch):
    import clinicaltrials_connector as ctc

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "studies": [
                    {
                        "protocolSection": {
                            "identificationModule": {
                                "nctId": "NCT00000000",
                                "briefTitle": (
                                    "A Pragmatic Clinical Trial of the WE BEAT "
                                    "Well-Being Education Program in Adolescent "
                                    "Congenital Heart Disease"
                                ),
                            },
                            "statusModule": {"overallStatus": "Completed"},
                            "designModule": {"studyType": "Interventional", "phases": []},
                            "conditionsModule": {"conditions": ["Congenital Heart Disease"]},
                            "armsInterventionsModule": {"interventions": [
                                {"name": "Well-Being Education Program"}
                            ]},
                            "outcomesModule": {"primaryOutcomes": [
                                {"measure": "Quality of life score"}
                            ]},
                        }
                    }
                ]
            }

    def _fake_get(url, params=None, timeout=None):
        return _FakeResponse()

    monkeypatch.setattr(ctc.requests, "get", _fake_get)
    records = ctc.search_clinicaltrials("Ficticus alpinum", "sleep")
    assert len(records) == 1
    assert records[0]["Candidate_Attribution_Verified"] is False


def test_clinicaltrials_connector_marks_genuine_match_verified(monkeypatch):
    import clinicaltrials_connector as ctc

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "studies": [
                    {
                        "protocolSection": {
                            "identificationModule": {
                                "nctId": "NCT11111111",
                                "briefTitle": "Ficticus alpinum extract for insomnia",
                            },
                            "statusModule": {"overallStatus": "Completed"},
                            "designModule": {"studyType": "Interventional", "phases": []},
                            "conditionsModule": {"conditions": ["Insomnia"]},
                            "armsInterventionsModule": {"interventions": [
                                {"name": "Ficticus alpinum extract"}
                            ]},
                            "outcomesModule": {"primaryOutcomes": [
                                {"measure": "Sleep onset latency"}
                            ]},
                        }
                    }
                ]
            }

    def _fake_get(url, params=None, timeout=None):
        return _FakeResponse()

    monkeypatch.setattr(ctc.requests, "get", _fake_get)
    records = ctc.search_clinicaltrials("Ficticus alpinum", "sleep")
    assert len(records) == 1
    assert records[0]["Candidate_Attribution_Verified"] is True
