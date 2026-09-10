"""Tests for the Problem 1 architectural fix: a canonical, evidence-grounded
Candidate_Intervention_Assertion replacing every prior PubMed text
heuristic (sentence-level cue co-occurrence, then bounded token-distance
relation checking -- both REMOVED from candidate_attribution.py; see its
module docstring).

Sections:
  1. CandidateInterventionAssertion.verified dataclass logic (pure, no text)
  2. assertion_from_structured_field -- unchanged ClinicalTrials.gov path
  3. assertion_from_llm_extraction -- span validation, role/polarity/
     temporality gating, model-invented-span protection
  4. assertion_from_deterministic_fast_path -- the two retained
     high-precision constructions only
  5. The 14 adversarial cases from the cahier
  6. 30 NEW adversarial sentences (not copied from any prompt)
  7. End-to-end: evidence_standardizer.py wiring with a mocked LLM call
  8. Critical end-to-end test: retrieval -> extraction -> standardization
     -> persistence -> reload -> shortlisting/adjudication

IMPORTANT CAVEAT ON SECTIONS 5-6: this sandboxed environment has no live
model access. Each case supplies a HAND-AUTHORED extraction payload
representing what a correctly-behaving extractor should return for that
sentence (decided independently of the verification formula, before
checking the result) -- this validates that the VERIFICATION LOGIC gates
correctly given a correct extraction, which is what this architecture
actually guarantees deterministically. Whether the live LLM extracts
correctly for a given sentence is a separate, real production concern
that live/shadow evaluation (the same pattern already used for this
project's semantic safety/regulatory gate -- see
shadow_semantic_gate_stress.py) would need to monitor; it is out of
scope for a unit-test suite with no model access, and is reported as a
limitation.
"""
import unittest.mock as mock

import pandas as pd

import candidate_intervention_assertion as cia
import database
import evidence_adjudication_engine as eae
import evidence_standardizer
import llm_extractor
from candidate_intervention_assertion import (
    CandidateInterventionAssertion,
    CandidateRole,
    InterventionPolarity,
    Temporality,
    assertion_from_deterministic_fast_path,
    assertion_from_llm_extraction,
    assertion_from_structured_field,
)
from candidate_shortlisting import (
    _row_has_indication_specific_outcome,
    _row_has_verified_candidate_attribution,
)
from test_database_evidence_schema_extension import FakeSupabase


# =======================================================================
# 1. Dataclass verification logic (pure)
# =======================================================================

def test_verified_true_only_for_intervention_positive_current_with_span():
    assertion = CandidateInterventionAssertion(
        candidate_role=CandidateRole.STUDIED_INTERVENTION,
        polarity=InterventionPolarity.POSITIVE,
        temporality=Temporality.CURRENT_STUDY,
        supporting_text="Participants received Ficticus alpinum extract.",
    )
    assert assertion.verified is True


def test_verified_true_for_studied_comparator_too():
    assertion = CandidateInterventionAssertion(
        candidate_role=CandidateRole.STUDIED_COMPARATOR,
        polarity=InterventionPolarity.POSITIVE,
        temporality=Temporality.CURRENT_STUDY,
        supporting_text="Ficticus alpinum served as the active comparator.",
    )
    assert assertion.verified is True


def test_verified_false_for_every_other_role():
    for role in (
        CandidateRole.CONCOMITANT_EXPOSURE, CandidateRole.PRIOR_EXPOSURE,
        CandidateRole.EXCLUDED_EXPOSURE, CandidateRole.BACKGROUND_MENTION,
        CandidateRole.UNKNOWN,
    ):
        assertion = CandidateInterventionAssertion(
            candidate_role=role,
            polarity=InterventionPolarity.POSITIVE,
            temporality=Temporality.CURRENT_STUDY,
            supporting_text="some verbatim span",
        )
        assert assertion.verified is False, role


def test_verified_false_when_polarity_negated():
    assertion = CandidateInterventionAssertion(
        candidate_role=CandidateRole.STUDIED_INTERVENTION,
        polarity=InterventionPolarity.NEGATED,
        temporality=Temporality.CURRENT_STUDY,
        supporting_text="were not randomized to Ficticus alpinum",
    )
    assert assertion.verified is False


def test_verified_false_when_temporality_prior():
    assertion = CandidateInterventionAssertion(
        candidate_role=CandidateRole.STUDIED_INTERVENTION,
        polarity=InterventionPolarity.POSITIVE,
        temporality=Temporality.PRIOR_OR_HISTORICAL,
        supporting_text="had previously received Ficticus alpinum",
    )
    assert assertion.verified is False


def test_verified_false_when_any_dimension_unknown():
    for kwargs in (
        {"candidate_role": CandidateRole.UNKNOWN},
        {"polarity": InterventionPolarity.UNKNOWN},
        {"temporality": Temporality.UNKNOWN},
    ):
        base = dict(
            candidate_role=CandidateRole.STUDIED_INTERVENTION,
            polarity=InterventionPolarity.POSITIVE,
            temporality=Temporality.CURRENT_STUDY,
            supporting_text="span",
        )
        base.update(kwargs)
        assert CandidateInterventionAssertion(**base).verified is False


def test_verified_false_when_supporting_text_empty():
    assertion = CandidateInterventionAssertion(
        candidate_role=CandidateRole.STUDIED_INTERVENTION,
        polarity=InterventionPolarity.POSITIVE,
        temporality=Temporality.CURRENT_STUDY,
        supporting_text="",
    )
    assert assertion.verified is False


def test_default_assertion_is_unverified():
    assert CandidateInterventionAssertion().verified is False


# =======================================================================
# 2. Structured-field path (unchanged, ClinicalTrials.gov)
# =======================================================================

def test_structured_field_genuine_intervention_verifies():
    assertion = assertion_from_structured_field(
        "Ficticus alpinum extract 300 mg", scientific_name="Ficticus alpinum",
    )
    assert assertion.verified is True
    assert assertion.candidate_role == CandidateRole.STUDIED_INTERVENTION
    assert assertion.extraction_method == "structured_field"


def test_structured_field_unrelated_intervention_does_not_verify():
    assertion = assertion_from_structured_field(
        "Cognitive behavioral therapy", scientific_name="Ficticus alpinum",
    )
    assert assertion.verified is False


# =======================================================================
# 3. LLM-extraction adapter -- span validation and role/polarity/
#    temporality gating
# =======================================================================

def test_llm_extraction_verified_with_valid_verbatim_span():
    source = "Background text. Participants received Ficticus alpinum extract daily. More text."
    data = {
        "candidate_intervention_role": "studied_intervention",
        "candidate_intervention_polarity": "positive",
        "candidate_intervention_temporality": "current_study",
        "candidate_intervention_supporting_text": "Participants received Ficticus alpinum extract daily.",
        "candidate_intervention_confidence": 0.95,
    }
    assertion = assertion_from_llm_extraction(data, source_text=source, scientific_name="Ficticus alpinum")
    assert assertion.verified is True
    assert assertion.extraction_method == "llm_semantic_extraction"


def test_llm_extraction_fails_closed_when_span_not_verbatim_in_source():
    # The model must NOT be allowed to invent an intervention: even a
    # role/polarity/temporality combination that would otherwise verify
    # must fail closed when its own quoted span does not exist in the
    # actual source text.
    source = "This article discusses general wellbeing topics only."
    data = {
        "candidate_intervention_role": "studied_intervention",
        "candidate_intervention_polarity": "positive",
        "candidate_intervention_temporality": "current_study",
        "candidate_intervention_supporting_text": "Participants received Ficticus alpinum extract daily.",
        "candidate_intervention_confidence": 0.95,
    }
    assertion = assertion_from_llm_extraction(data, source_text=source, scientific_name="Ficticus alpinum")
    assert assertion.verified is False


def test_llm_extraction_fails_closed_on_empty_span():
    source = "Participants received Ficticus alpinum extract daily."
    data = {
        "candidate_intervention_role": "studied_intervention",
        "candidate_intervention_polarity": "positive",
        "candidate_intervention_temporality": "current_study",
        "candidate_intervention_supporting_text": "",
    }
    assertion = assertion_from_llm_extraction(data, source_text=source, scientific_name="Ficticus alpinum")
    assert assertion.verified is False


def test_llm_extraction_fails_closed_on_unrecognized_enum_value():
    source = "Participants received Ficticus alpinum extract daily."
    data = {
        "candidate_intervention_role": "some_new_unrecognized_role",
        "candidate_intervention_polarity": "positive",
        "candidate_intervention_temporality": "current_study",
        "candidate_intervention_supporting_text": "Participants received Ficticus alpinum extract daily.",
    }
    assertion = assertion_from_llm_extraction(data, source_text=source, scientific_name="Ficticus alpinum")
    assert assertion.candidate_role == CandidateRole.UNKNOWN
    assert assertion.verified is False


def test_llm_extraction_handles_missing_payload_gracefully():
    assertion = assertion_from_llm_extraction(None, source_text="anything", scientific_name="Ficticus alpinum")
    assert assertion.verified is False


# =======================================================================
# 4. Deterministic fast path -- HIGH-PRECISION optimization only
# =======================================================================

def test_fast_path_retained_pattern_received_verifies():
    assertion = assertion_from_deterministic_fast_path(
        "Participants received Ficticus alpinum extract.",
        scientific_name="Ficticus alpinum",
    )
    assert assertion.verified is True
    assert assertion.extraction_method == "deterministic_fast_path"


def test_fast_path_retained_pattern_passive_administered_verifies():
    assertion = assertion_from_deterministic_fast_path(
        "Ficticus alpinum extract was administered to participants.",
        scientific_name="Ficticus alpinum",
    )
    assert assertion.verified is True


def test_fast_path_negation_guard_before_received():
    assertion = assertion_from_deterministic_fast_path(
        "Participants not received Ficticus alpinum extract.",
        scientific_name="Ficticus alpinum",
    )
    assert assertion.verified is False


def test_fast_path_negation_guard_before_administered():
    assertion = assertion_from_deterministic_fast_path(
        "Ficticus alpinum extract was not administered to participants.",
        scientific_name="Ficticus alpinum",
    )
    assert assertion.verified is False


def test_fast_path_unrecognized_construction_fails_closed():
    for text in (
        "Ficticus alpinum intervention was considered but not administered.",
        "Ficticus alpinum treatment was prohibited by the protocol.",
        "The Ficticus alpinum arm received 300 mg daily.",  # not in the 2 retained patterns
        "Participants were randomized to Ficticus alpinum extract or placebo.",  # demoted, needs LLM path
    ):
        assertion = assertion_from_deterministic_fast_path(text, scientific_name="Ficticus alpinum")
        assert assertion.verified is False, text


def test_fast_path_bare_compound_noun_shortcut_is_removed():
    # This exact shortcut ("BOTANICAL + treatment/intervention/
    # supplementation => verified") is what the cahier explicitly
    # required removing -- it is what let "Ficticus alpinum intervention
    # was considered but not administered" false-positive previously.
    assertion = assertion_from_deterministic_fast_path(
        "Ficticus alpinum treatment.", scientific_name="Ficticus alpinum",
    )
    assert assertion.verified is False


# =======================================================================
# 5. The 14 adversarial cases from the cahier (hand-authored correct
#    extraction payload per sentence; see module docstring caveat).
# =======================================================================

PROMPT_ADVERSARIAL_CASES = [
    # (sentence, role, polarity, temporality, expected_verified)
    ("Participants were not randomized to Ficticus alpinum extract.",
     CandidateRole.STUDIED_INTERVENTION, InterventionPolarity.NEGATED, Temporality.CURRENT_STUDY, False),
    ("Ficticus alpinum intervention was considered but not administered.",
     CandidateRole.EXCLUDED_EXPOSURE, InterventionPolarity.NEGATED, Temporality.CURRENT_STUDY, False),
    ("Ficticus alpinum treatment was prohibited by the protocol.",
     CandidateRole.EXCLUDED_EXPOSURE, InterventionPolarity.POSITIVE, Temporality.CURRENT_STUDY, False),
    ("Ficticus alpinum treatment history was recorded at baseline.",
     CandidateRole.PRIOR_EXPOSURE, InterventionPolarity.POSITIVE, Temporality.PRIOR_OR_HISTORICAL, False),
    ("Ficticus alpinum treatment was discontinued before enrollment.",
     CandidateRole.PRIOR_EXPOSURE, InterventionPolarity.POSITIVE, Temporality.PRIOR_OR_HISTORICAL, False),
    ("Ficticus alpinum supplementation was permitted as concomitant therapy "
     "while all participants received placebo.",
     CandidateRole.CONCOMITANT_EXPOSURE, InterventionPolarity.POSITIVE, Temporality.CURRENT_STUDY, False),
    ("Participants received placebo; Ficticus alpinum was administered in a prior study.",
     CandidateRole.PRIOR_EXPOSURE, InterventionPolarity.POSITIVE, Temporality.PRIOR_OR_HISTORICAL, False),
    ("Participants consumed Ficticus alpinum tea nightly for four weeks.",
     CandidateRole.STUDIED_INTERVENTION, InterventionPolarity.POSITIVE, Temporality.CURRENT_STUDY, True),
    ("Participants ingested Ficticus alpinum extract each evening.",
     CandidateRole.STUDIED_INTERVENTION, InterventionPolarity.POSITIVE, Temporality.CURRENT_STUDY, True),
    ("Participants were allocated to Ficticus alpinum extract or placebo.",
     CandidateRole.STUDIED_INTERVENTION, InterventionPolarity.POSITIVE, Temporality.CURRENT_STUDY, True),
    ("Participants received a standardized extract of Ficticus alpinum once daily.",
     CandidateRole.STUDIED_INTERVENTION, InterventionPolarity.POSITIVE, Temporality.CURRENT_STUDY, True),
    ("Participants received two capsules containing Ficticus alpinum extract daily.",
     CandidateRole.STUDIED_INTERVENTION, InterventionPolarity.POSITIVE, Temporality.CURRENT_STUDY, True),
    ("The Ficticus alpinum arm received 300 mg daily.",
     CandidateRole.STUDIED_INTERVENTION, InterventionPolarity.POSITIVE, Temporality.CURRENT_STUDY, True),
    ("Treatment consisted of Ficticus alpinum extract 300 mg daily.",
     CandidateRole.STUDIED_INTERVENTION, InterventionPolarity.POSITIVE, Temporality.CURRENT_STUDY, True),
]


def _assertion_for_case(sentence, role, polarity, temporality):
    data = {
        "candidate_intervention_role": role.value,
        "candidate_intervention_polarity": polarity.value,
        "candidate_intervention_temporality": temporality.value,
        "candidate_intervention_supporting_text": sentence,
        "candidate_intervention_confidence": 0.9,
    }
    return assertion_from_llm_extraction(data, source_text=sentence, scientific_name="Ficticus alpinum")


def test_prompt_adversarial_cases():
    mismatches = []
    for sentence, role, polarity, temporality, expected in PROMPT_ADVERSARIAL_CASES:
        actual = _assertion_for_case(sentence, role, polarity, temporality).verified
        if actual != expected:
            mismatches.append((sentence, expected, actual))
    assert not mismatches, "\n".join(
        f"expected={exp} actual={act} | {s}" for s, exp, act in mismatches
    )


# =======================================================================
# 6. 30 NEW adversarial sentences (not copied from any prompt), covering:
#    active administration, passive administration, consumed, ingested,
#    allocated, assigned, study arm descriptions, treatment consisted of,
#    prior treatment, medication history, washout, discontinuation,
#    prohibited use, excluded use, concomitant use, permitted background
#    therapy, negation, comparator, discussion/background, prior studies,
#    meta-analysis/review descriptions, eligibility criteria.
# =======================================================================

NEW_ADVERSARIAL_CASES = [
    # active administration
    ("Researchers administered Ficticus alpinum extract to all enrolled participants.",
     CandidateRole.STUDIED_INTERVENTION, InterventionPolarity.POSITIVE, Temporality.CURRENT_STUDY, True),
    # passive administration
    ("A standardized dose of Ficticus alpinum was administered every morning.",
     CandidateRole.STUDIED_INTERVENTION, InterventionPolarity.POSITIVE, Temporality.CURRENT_STUDY, True),
    # consumed
    ("Participants consumed Ficticus alpinum capsules with breakfast.",
     CandidateRole.STUDIED_INTERVENTION, InterventionPolarity.POSITIVE, Temporality.CURRENT_STUDY, True),
    # ingested
    ("Subjects ingested Ficticus alpinum tincture before bedtime.",
     CandidateRole.STUDIED_INTERVENTION, InterventionPolarity.POSITIVE, Temporality.CURRENT_STUDY, True),
    # allocated
    ("Patients were allocated to receive Ficticus alpinum or an identical placebo.",
     CandidateRole.STUDIED_INTERVENTION, InterventionPolarity.POSITIVE, Temporality.CURRENT_STUDY, True),
    # assigned
    ("Participants were assigned to the Ficticus alpinum group for eight weeks.",
     CandidateRole.STUDIED_INTERVENTION, InterventionPolarity.POSITIVE, Temporality.CURRENT_STUDY, True),
    # study arm description
    ("The Ficticus alpinum group showed improved sleep scores after four weeks.",
     CandidateRole.STUDIED_INTERVENTION, InterventionPolarity.POSITIVE, Temporality.CURRENT_STUDY, True),
    # study arm description (2)
    ("In the Ficticus alpinum arm, participants took two capsules nightly.",
     CandidateRole.STUDIED_INTERVENTION, InterventionPolarity.POSITIVE, Temporality.CURRENT_STUDY, True),
    # treatment consisted of
    ("Treatment in the active arm consisted of a daily Ficticus alpinum tablet.",
     CandidateRole.STUDIED_INTERVENTION, InterventionPolarity.POSITIVE, Temporality.CURRENT_STUDY, True),
    # prior treatment
    ("Several participants reported prior treatment with Ficticus alpinum before joining the study.",
     CandidateRole.PRIOR_EXPOSURE, InterventionPolarity.POSITIVE, Temporality.PRIOR_OR_HISTORICAL, False),
    # medication history
    ("Medication history revealed occasional Ficticus alpinum use in 8 participants.",
     CandidateRole.PRIOR_EXPOSURE, InterventionPolarity.POSITIVE, Temporality.PRIOR_OR_HISTORICAL, False),
    # washout
    ("A four-week washout of Ficticus alpinum preceded the intervention period.",
     CandidateRole.PRIOR_EXPOSURE, InterventionPolarity.POSITIVE, Temporality.PRIOR_OR_HISTORICAL, False),
    # discontinuation
    ("Ficticus alpinum was discontinued two weeks prior to baseline assessment.",
     CandidateRole.PRIOR_EXPOSURE, InterventionPolarity.POSITIVE, Temporality.PRIOR_OR_HISTORICAL, False),
    # prohibited use
    ("Use of Ficticus alpinum was strictly prohibited throughout the study period.",
     CandidateRole.EXCLUDED_EXPOSURE, InterventionPolarity.POSITIVE, Temporality.CURRENT_STUDY, False),
    # excluded use
    ("Current Ficticus alpinum users were excluded during screening.",
     CandidateRole.EXCLUDED_EXPOSURE, InterventionPolarity.POSITIVE, Temporality.CURRENT_STUDY, False),
    # concomitant use
    ("Concomitant Ficticus alpinum use was reported by 5% of participants.",
     CandidateRole.CONCOMITANT_EXPOSURE, InterventionPolarity.POSITIVE, Temporality.CURRENT_STUDY, False),
    # permitted background therapy
    ("Stable background therapy with Ficticus alpinum was permitted throughout the trial.",
     CandidateRole.CONCOMITANT_EXPOSURE, InterventionPolarity.POSITIVE, Temporality.CURRENT_STUDY, False),
    # negation
    ("Participants were never given Ficticus alpinum during the study.",
     CandidateRole.STUDIED_INTERVENTION, InterventionPolarity.NEGATED, Temporality.CURRENT_STUDY, False),
    # negation (2)
    ("No participant received Ficticus alpinum at any point in the trial.",
     CandidateRole.STUDIED_INTERVENTION, InterventionPolarity.NEGATED, Temporality.CURRENT_STUDY, False),
    # comparator
    ("Ficticus alpinum served as the active comparator against the investigational drug.",
     CandidateRole.STUDIED_COMPARATOR, InterventionPolarity.POSITIVE, Temporality.CURRENT_STUDY, True),
    # comparator (2)
    ("The comparator group received Ficticus alpinum while the treatment group received the new compound.",
     CandidateRole.STUDIED_COMPARATOR, InterventionPolarity.POSITIVE, Temporality.CURRENT_STUDY, True),
    # discussion/background
    ("The pharmacology of Ficticus alpinum is discussed extensively in the introduction.",
     CandidateRole.BACKGROUND_MENTION, InterventionPolarity.POSITIVE, Temporality.UNKNOWN, False),
    # prior studies
    ("Earlier studies of Ficticus alpinum reported mixed results for sleep quality.",
     CandidateRole.BACKGROUND_MENTION, InterventionPolarity.POSITIVE, Temporality.PRIOR_OR_HISTORICAL, False),
    # meta-analysis/review description
    ("This meta-analysis pooled six trials that administered Ficticus alpinum for insomnia.",
     CandidateRole.BACKGROUND_MENTION, InterventionPolarity.POSITIVE, Temporality.PRIOR_OR_HISTORICAL, False),
    # review description (2)
    ("A systematic review summarized evidence on Ficticus alpinum across 12 studies.",
     CandidateRole.BACKGROUND_MENTION, InterventionPolarity.POSITIVE, Temporality.UNKNOWN, False),
    # eligibility criteria
    ("Eligible participants had no contraindication to Ficticus alpinum and were enrolled.",
     CandidateRole.BACKGROUND_MENTION, InterventionPolarity.UNKNOWN, Temporality.UNKNOWN, False),
    # eligibility criteria (2, conditional/hypothetical)
    ("Inclusion criteria required willingness to take Ficticus alpinum if randomized to that arm.",
     CandidateRole.UNKNOWN, InterventionPolarity.UNKNOWN, Temporality.UNKNOWN, False),
    # genuine intervention with explicit dose
    ("Each participant received 500 mg of Ficticus alpinum extract twice daily for six weeks.",
     CandidateRole.STUDIED_INTERVENTION, InterventionPolarity.POSITIVE, Temporality.CURRENT_STUDY, True),
    # genuine passive with route
    ("Ficticus alpinum extract was administered orally to all study participants.",
     CandidateRole.STUDIED_INTERVENTION, InterventionPolarity.POSITIVE, Temporality.CURRENT_STUDY, True),
    # ambiguous/unclear background
    ("Ficticus alpinum was mentioned in the discussion section regarding mechanism.",
     CandidateRole.BACKGROUND_MENTION, InterventionPolarity.POSITIVE, Temporality.UNKNOWN, False),
]


def test_new_adversarial_cases():
    assert len(NEW_ADVERSARIAL_CASES) >= 30
    mismatches = []
    for sentence, role, polarity, temporality, expected in NEW_ADVERSARIAL_CASES:
        actual = _assertion_for_case(sentence, role, polarity, temporality).verified
        if actual != expected:
            mismatches.append((sentence, expected, actual))
    assert not mismatches, "\n".join(
        f"expected={exp} actual={act} | {s}" for s, exp, act in mismatches
    )


# =======================================================================
# 7. End-to-end: evidence_standardizer.py wiring with a mocked LLM call
#    (proves the actual code path, not just the assertion logic in
#    isolation).
# =======================================================================

def _fake_llm_result(role, polarity, temporality, supporting_text):
    return {
        "plant_scientific_name": "Ficticus alpinum",
        "evidence_type": "Randomized Controlled Trial",
        "study_model": "Human",
        "dosage_form": "capsule",
        "plant_part": "", "preparation": "extract", "preparation_category": "other",
        "administration_route": "oral", "dose": "300 mg", "dose_unit": "mg",
        "extraction_method": "", "duration": "8 weeks",
        "target_indication": "sleep", "dosage_form_relevance": "Direct",
        "population": "adults", "sample_size": "60", "comparator": "placebo",
        "main_outcome": "sleep onset latency", "result_direction": "Positive",
        "safety_signal": "None", "evidence_level": "High",
        "ema_relevance": "No", "who_relevance": "No", "escop_relevance": "No",
        "reason": "test fixture",
        "candidate_intervention_role": role,
        "candidate_intervention_polarity": polarity,
        "candidate_intervention_temporality": temporality,
        "candidate_intervention_supporting_text": supporting_text,
        "candidate_intervention_confidence": 0.9,
    }


def test_standardizer_wiring_true_positive_end_to_end(monkeypatch):
    sentence = "Participants received Ficticus alpinum extract 300 mg daily."
    fake_result = _fake_llm_result("studied_intervention", "positive", "current_study", sentence)
    monkeypatch.setattr(llm_extractor.llm_client, "call_structured_json", lambda **kwargs: fake_result)

    standardized = evidence_standardizer.standardize_extracted_record(
        extracted={
            "Scientific_Name": "Ficticus alpinum",
            "Notes": f"Background text. {sentence} More text.",
        },
        source_metadata={
            "source_type": "PubMed", "source_title": "A trial",
            "source_url": "", "source_organization": "NCBI PubMed", "source_year": "2024",
        },
        allow_llm=True,
    )
    assert standardized["Candidate_Attribution_Verified"] is True
    assert standardized["Candidate_Intervention_Role"] == "studied_intervention"


def test_standardizer_wiring_false_positive_end_to_end(monkeypatch):
    sentence = "Ficticus alpinum treatment was prohibited by the protocol."
    fake_result = _fake_llm_result("excluded_exposure", "positive", "current_study", sentence)
    monkeypatch.setattr(llm_extractor.llm_client, "call_structured_json", lambda **kwargs: fake_result)

    standardized = evidence_standardizer.standardize_extracted_record(
        extracted={
            "Scientific_Name": "Ficticus alpinum",
            "Notes": f"Background text. {sentence} More text.",
        },
        source_metadata={
            "source_type": "PubMed", "source_title": "A trial",
            "source_url": "", "source_organization": "NCBI PubMed", "source_year": "2024",
        },
        allow_llm=True,
    )
    assert standardized["Candidate_Attribution_Verified"] is False


def test_standardizer_wiring_llm_disabled_falls_back_to_fast_path():
    sentence = "Participants received Ficticus alpinum extract."
    standardized = evidence_standardizer.standardize_extracted_record(
        extracted={
            "Scientific_Name": "Ficticus alpinum",
            "Notes": sentence,
        },
        source_metadata={
            "source_type": "PubMed", "source_title": "A trial",
            "source_url": "", "source_organization": "NCBI PubMed", "source_year": "2024",
        },
        allow_llm=False,
    )
    assert standardized["Candidate_Attribution_Verified"] is True
    assert standardized["Candidate_Intervention_Extraction_Method"] == "deterministic_fast_path"


def test_standardizer_wiring_llm_unavailable_and_no_fast_path_match_fails_closed():
    standardized = evidence_standardizer.standardize_extracted_record(
        extracted={
            "Scientific_Name": "Ficticus alpinum",
            "Notes": "Ficticus alpinum treatment was prohibited by the protocol.",
        },
        source_metadata={
            "source_type": "PubMed", "source_title": "A trial",
            "source_url": "", "source_organization": "NCBI PubMed", "source_year": "2024",
        },
        allow_llm=False,
    )
    assert standardized["Candidate_Attribution_Verified"] is False


def test_standardizer_wiring_does_not_recompute_when_connector_already_set_it():
    # A structured-source connector (e.g. clinicaltrials_connector.py) that
    # already computed Candidate_Attribution_Verified must be authoritative
    # -- the LLM assertion pipeline must not run/overwrite it.
    standardized = evidence_standardizer.standardize_extracted_record(
        extracted={
            "Scientific_Name": "Ficticus alpinum",
            "Candidate_Attribution_Verified": True,
            "Candidate_Attribution_Basis": "full_binomial",
            "Notes": "irrelevant text",
        },
        source_metadata={
            "source_type": "ClinicalTrials.gov", "source_title": "A trial",
            "source_url": "", "source_organization": "ClinicalTrials.gov", "source_year": "2024",
        },
        allow_llm=False,
    )
    assert standardized["Candidate_Attribution_Verified"] is True
    assert standardized["Candidate_Attribution_Basis"] == "full_binomial"


# =======================================================================
# 8. Critical end-to-end test: retrieval -> extraction -> standardization
#    -> persistence -> reload -> shortlisting/adjudication
# =======================================================================

def test_critical_e2e_verified_record_survives_full_round_trip(monkeypatch):
    sentence = "Participants were randomized to Ficticus alpinum extract or placebo."
    fake_result = _fake_llm_result("studied_intervention", "positive", "current_study", sentence)
    monkeypatch.setattr(llm_extractor.llm_client, "call_structured_json", lambda **kwargs: fake_result)

    standardized = evidence_standardizer.standardize_extracted_record(
        extracted={
            "Scientific_Name": "Ficticus alpinum",
            "Notes": sentence,
            "Primary_Outcome": "sleep onset latency",
            "Result_Direction": "Positive",
        },
        source_metadata={
            "source_type": "PubMed", "source_title": "A randomized trial",
            "source_url": "", "source_organization": "NCBI PubMed", "source_year": "2024",
        },
        allow_llm=True,
    )
    assert standardized["Candidate_Attribution_Verified"] is True

    fake = FakeSupabase()
    with mock.patch("database.get_supabase_client", return_value=fake):
        database.save_evidence_record(standardized)
    saved_payload = fake.inserted_evidence_payloads[0]
    assert saved_payload["candidate_attribution_verified"] is True
    assert saved_payload["candidate_intervention_role"] == "studied_intervention"

    class _SelectResult:
        data = [{
            "id": 1, "plant_id": 1,
            "plants": {"scientific_name": "Ficticus alpinum", "common_name": ""},
            "sources": {},
            "candidate_attribution_verified": saved_payload["candidate_attribution_verified"],
            "candidate_attribution_basis": saved_payload["candidate_attribution_basis"],
            "candidate_intervention_role": saved_payload["candidate_intervention_role"],
            "candidate_intervention_polarity": saved_payload["candidate_intervention_polarity"],
            "candidate_intervention_temporality": saved_payload["candidate_intervention_temporality"],
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
    reloaded = rows.iloc[0]
    assert bool(reloaded["Candidate_Attribution_Verified"]) is True
    assert reloaded["Candidate_Intervention_Role"] == "studied_intervention"
    assert _row_has_verified_candidate_attribution(reloaded) is True
    assert _row_has_indication_specific_outcome(reloaded, "sleep") is True

    df = pd.DataFrame([{
        "Alternative_Plant": "Ficticus alpinum",
        "Source_Record_IDs": "E2E-1",
        "Indication_Match_Type": "explicit_field_overlap",
        "Primary_Outcome": reloaded["Primary_Outcome"],
        "Evidence_Direction": reloaded["Result_Direction"],
        "Candidate_Attribution_Verified": reloaded["Candidate_Attribution_Verified"],
    }])
    items = eae.build_adjudication_evidence_items(df, "Ficticus alpinum", "sleep", 25)
    assert items[0]["candidate_specific"] is True
    assert items[0]["outcome_specific"] is True


def test_critical_e2e_unverified_record_stays_unverified_full_round_trip(monkeypatch):
    sentence = "Ficticus alpinum treatment was prohibited by the protocol."
    fake_result = _fake_llm_result("excluded_exposure", "positive", "current_study", sentence)
    monkeypatch.setattr(llm_extractor.llm_client, "call_structured_json", lambda **kwargs: fake_result)

    standardized = evidence_standardizer.standardize_extracted_record(
        extracted={
            "Scientific_Name": "Ficticus alpinum",
            "Notes": sentence,
            "Primary_Outcome": "sleep onset latency",
            "Result_Direction": "Positive",
        },
        source_metadata={
            "source_type": "PubMed", "source_title": "A trial",
            "source_url": "", "source_organization": "NCBI PubMed", "source_year": "2024",
        },
        allow_llm=True,
    )
    assert standardized["Candidate_Attribution_Verified"] is False

    fake = FakeSupabase()
    with mock.patch("database.get_supabase_client", return_value=fake):
        database.save_evidence_record(standardized)
    saved_payload = fake.inserted_evidence_payloads[0]
    assert saved_payload["candidate_attribution_verified"] is False

    class _SelectResult:
        data = [{
            "id": 2, "plant_id": 2,
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
    reloaded = rows.iloc[0]
    assert bool(reloaded["Candidate_Attribution_Verified"]) is False
    assert _row_has_verified_candidate_attribution(reloaded) is False
    assert _row_has_indication_specific_outcome(reloaded, "sleep") is False
