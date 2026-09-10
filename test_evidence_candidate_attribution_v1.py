"""Regression tests for Problem 1 -- incorrect evidence attribution / source
relevance, including the remaining defects identified after the first pass:

1. Mere plant-name mention (anywhere in a record) is not intervention
   attribution -- verification must be scoped to intervention/exposure text.
2. Missing Candidate_Attribution_Verified must fail CLOSED (unverified),
   never fail open (silently trusted).
3. The requested/query indication must never be stamped into a field that
   downstream code reads as a source-reported fact.

These tests are deliberately GENERAL: fictional botanicals and indications
are used throughout so nothing here depends on a hardcoded plant-name
blacklist.
"""
import pandas as pd

import candidate_attribution as ca
import evidence_adjudication_engine as eae
from candidate_shortlisting import (
    _row_has_indication_specific_outcome,
    _row_has_verified_candidate_attribution,
)


# ---------------------------------------------------------------------
# Unit coverage of the core name-matching primitive (still general;
# unchanged from the first pass -- what changed is what text callers are
# allowed to feed it, covered by the tests below).
# ---------------------------------------------------------------------

def test_full_binomial_present_is_verified_when_text_is_intervention_scoped():
    result = ca.verify_intervention_attribution(
        "Participants received Ficticus alpinum extract 300 mg daily.",
        scientific_name="Ficticus alpinum",
    )
    assert result["verified"] is True
    assert result["basis"] == "full_binomial"


def test_different_species_binomial_does_not_false_match():
    # Prior real production bug: "lemon" (Citrus limon) must not false-match
    # inside "lemon verbena" (Aloysia citrodora), a different species.
    result = ca.verify_intervention_attribution(
        "Participants received lemon verbena extract capsules.",
        scientific_name="Citrus limon",
    )
    assert result["verified"] is False


def test_multi_word_common_name_requires_every_word_present():
    result = ca.verify_intervention_attribution(
        "Participants received lemon verbena extract capsules.",
        scientific_name="Melissa officinalis",
        common_name="lemon balm",
    )
    assert result["verified"] is False


def test_no_text_available_fails_closed_not_direct():
    result = ca.verify_intervention_attribution("", scientific_name="Ficticus alpinum")
    assert result["verified"] is False
    assert result["basis"] == ""


# ---------------------------------------------------------------------
# Test 1 -- background mention only must NOT verify attribution
# ---------------------------------------------------------------------

def test_1_background_mention_only_does_not_verify_pubmed_attribution():
    raw_text = (
        "Background: Ficticus alpinum is traditionally used for sleep. "
        "In this randomized trial, patients received cognitive behavioral "
        "therapy versus placebo. Sleep onset latency was the primary outcome."
    )
    result = ca.verify_pubmed_intervention_attribution(raw_text, scientific_name="Ficticus alpinum")
    assert result["verified"] is False


def test_1_administration_sentence_without_candidate_name_is_excluded():
    # Sanity check on the underlying heuristic: the administration-cue
    # sentence here names the comparator, not the candidate, so narrowing
    # to that sentence correctly still finds no candidate mention.
    context = ca.administration_context_text(
        "Ficticus alpinum is traditionally used for sleep. "
        "Patients received cognitive behavioral therapy versus placebo."
    )
    assert "ficticus" not in context.lower()
    assert "received" in context.lower()


# ---------------------------------------------------------------------
# Test 2 -- ClinicalTrials.gov condition/title mention only, unrelated
# intervention, must NOT verify.
# ---------------------------------------------------------------------

def test_2_clinicaltrials_condition_mention_only_is_unverified(monkeypatch):
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
                                "nctId": "NCT22222222",
                                "briefTitle": "Ficticus alpinum use and sleep habits survey",
                            },
                            "statusModule": {"overallStatus": "Completed"},
                            "designModule": {"studyType": "INTERVENTIONAL", "phases": []},
                            "conditionsModule": {"conditions": ["Insomnia", "Ficticus alpinum users"]},
                            "armsInterventionsModule": {"interventions": [
                                {"name": "Cognitive behavioral therapy", "description": "CBT sessions"}
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
    assert records[0]["Candidate_Attribution_Verified"] is False


# ---------------------------------------------------------------------
# Test 3 -- actual botanical intervention must verify.
# ---------------------------------------------------------------------

def test_3_actual_botanical_intervention_verifies(monkeypatch):
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
                                "nctId": "NCT33333333",
                                "briefTitle": "A trial of an herbal extract for insomnia",
                            },
                            "statusModule": {"overallStatus": "Completed"},
                            "designModule": {"studyType": "INTERVENTIONAL", "phases": []},
                            "conditionsModule": {"conditions": ["Insomnia"]},
                            "armsInterventionsModule": {"interventions": [
                                {"name": "Ficticus alpinum extract", "description": "300 mg standardized extract"}
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
    assert records[0]["Candidate_Attribution_Basis"] == "full_binomial"


# ---------------------------------------------------------------------
# Test 4 -- missing Candidate_Attribution_Verified must NOT become verified
# outcome-specific direct evidence (fail closed, remaining defect 2).
# ---------------------------------------------------------------------

def test_4_missing_attribution_field_fails_closed():
    row = pd.Series({"Primary_Outcome": "sleep onset latency"})
    # No Candidate_Attribution_Verified key at all -- a legacy row.
    assert _row_has_verified_candidate_attribution(row) is False
    assert _row_has_indication_specific_outcome(row, "sleep") is False


def test_4_adjudication_missing_attribution_field_fails_closed():
    df = pd.DataFrame([{
        "Alternative_Plant": "Ficticus alpinum",
        "Source_Record_IDs": "L-1",
        "Indication_Match_Type": "explicit_field_overlap",
        "Primary_Outcome": "sleep onset latency and total sleep time",
        "Study_Design": "Randomized double-blind placebo-controlled clinical trial",
        "Evidence_Direction": "positive",
        # Candidate_Attribution_Verified deliberately absent -- legacy row.
    }])
    items = eae.build_adjudication_evidence_items(df, "Ficticus alpinum", "sleep", 25)
    assert len(items) == 1
    assert items[0]["candidate_specific"] is False
    assert items[0]["outcome_specific"] is False


# ---------------------------------------------------------------------
# Test 5 -- explicit False must never become direct/outcome-specific.
# ---------------------------------------------------------------------

def test_5_explicit_false_never_direct():
    row = pd.Series({
        "Candidate_Attribution_Verified": False,
        "Primary_Outcome": "sleep onset latency",
    })
    assert _row_has_verified_candidate_attribution(row) is False
    assert _row_has_indication_specific_outcome(row, "sleep") is False

    df = pd.DataFrame([{
        "Alternative_Plant": "Ficticus alpinum",
        "Source_Record_IDs": "N-1",
        "Indication_Match_Type": "explicit_field_overlap",
        "Primary_Outcome": "sleep onset latency",
        "Candidate_Attribution_Verified": False,
    }])
    items = eae.build_adjudication_evidence_items(df, "Ficticus alpinum", "sleep", 25)
    assert items[0]["candidate_specific"] is False
    assert items[0]["outcome_specific"] is False


# ---------------------------------------------------------------------
# Test 6 -- requested indication must not overwrite / fabricate the
# source-reported indication/outcome.
# ---------------------------------------------------------------------

def test_6_requested_indication_does_not_overwrite_source_reported_condition(monkeypatch):
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
                                "nctId": "NCT44444444",
                                "briefTitle": "Ficticus alpinum extract for tinnitus",
                            },
                            "statusModule": {"overallStatus": "Completed"},
                            "designModule": {"studyType": "INTERVENTIONAL", "phases": []},
                            "conditionsModule": {"conditions": ["Tinnitus"]},
                            "armsInterventionsModule": {"interventions": [
                                {"name": "Ficticus alpinum extract", "description": "extract capsule"}
                            ]},
                            "outcomesModule": {"primaryOutcomes": [
                                {"measure": "Tinnitus loudness matching"}
                            ]},
                        }
                    }
                ]
            }

    def _fake_get(url, params=None, timeout=None):
        return _FakeResponse()

    monkeypatch.setattr(ctc.requests, "get", _fake_get)
    records = ctc.search_clinicaltrials("Ficticus alpinum", "sleep")
    record = records[0]
    # The requested indication is preserved as query CONTEXT only...
    assert record["Requested_Target_Indication"] == "sleep"
    # ...and must never overwrite the source's own reported condition.
    assert record["Target_Indication"] == "Tinnitus"
    assert record["Detected_Indications"] == "Tinnitus"
    assert "sleep" not in record["Target_Indication"].lower()

    # Candidate attribution is genuinely verified (real intervention)...
    assert record["Candidate_Attribution_Verified"] is True
    # ...but that must not make this sleep-specific evidence: the record's
    # own outcome is tinnitus, not sleep.
    row = pd.Series(record)
    assert _row_has_indication_specific_outcome(row, "sleep") is False


# ---------------------------------------------------------------------
# Test 7 -- common-name genuine intervention; fail closed without a
# reliable common-name mapping.
# ---------------------------------------------------------------------

def test_7_common_name_intervention_verifies_when_common_name_is_supplied():
    result = ca.verify_intervention_attribution(
        "Participants received lemon balm extract 500 mg twice daily.",
        scientific_name="Melissa officinalis",
        common_name="lemon balm",
    )
    assert result["verified"] is True
    assert result["basis"] == "common_name"


def test_7_common_name_only_mention_fails_closed_without_mapping():
    # Documented limitation: when the caller has no common-name mapping to
    # supply (common_name=""), a trial that only used the common name in
    # its intervention field cannot be verified from the scientific name
    # alone -- and correctly fails closed rather than guessing a fuzzy
    # cross-species match.
    result = ca.verify_intervention_attribution(
        "Participants received lemon balm extract 500 mg twice daily.",
        scientific_name="Melissa officinalis",
    )
    assert result["verified"] is False


# ---------------------------------------------------------------------
# Cases B and C from the first pass -- outcome mismatch must still be
# caught (unaffected by these fixes; genuine intervention, wrong outcome).
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
# Case E from the first pass -- a genuinely relevant human trial (verified
# candidate = intervention AND queried indication = measured outcome) MUST
# still qualify. Re-asserted here against the new fail-closed default.
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
# Replaces the first pass's test_absent_attribution_field_preserves_
# legacy_behavior, which asserted the (now-corrected) fail-open behavior.
# That test enforced scientifically incorrect behavior -- see remaining
# defect 2 -- and is replaced, not merely deleted, by the assertions below
# and by test_4_missing_attribution_field_fails_closed above.
# ---------------------------------------------------------------------

def test_absent_attribution_field_cannot_qualify_as_verified_direct_evidence():
    row = pd.Series({"Primary_Outcome": "sleep onset latency"})
    assert _row_has_verified_candidate_attribution(row) is False
    assert _row_has_indication_specific_outcome(row, "sleep") is False
