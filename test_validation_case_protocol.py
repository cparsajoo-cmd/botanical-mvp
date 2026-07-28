"""Regression tests for validation_case_protocol.py (Task 6 — generic,
parametric Validation Case Protocol). See that module's docstring for
the full documented method and its declared limitations.
"""

from datetime import date

import pytest

from validation_case_protocol import (
    ValidationCaseProtocol, DecisionContext, LockedCandidateSet,
    CandidateEligibilityRule, ReferenceEvidenceCorpus, ExpertPanel,
    ExpertPanelMember, ProtocolReadiness, ProtocolNotReadyError,
    assess_readiness, gap_report, lock_protocol, to_appendix_row,
    protocol_completeness,
)


def _empty_protocol(name="Test case"):
    return ValidationCaseProtocol(case_name=name)


def _locked_decision_context():
    return DecisionContext(
        population="Adults",
        route_of_administration="Oral",
        dosage_form="Capsule",
        jurisdiction="European Union",
        product_type="Food supplement",
        indication="Joint & muscle comfort",
    )


def _locked_candidate_set():
    return LockedCandidateSet(
        candidates=["Boswellia serrata"],
        eligibility_rules=[CandidateEligibilityRule("Documented use", "EMA monograph")],
    )


def _locked_reference_corpus():
    return ReferenceEvidenceCorpus(
        description="Independent literature search",
        built_independently_of_platform=True,
        sources=["Cochrane Library"],
        search_strategy="joint pain AND boswellia",
        evidence_cutoff_date=date(2026, 1, 1),
    )


def _locked_expert_panel():
    return ExpertPanel(
        members=[ExpertPanelMember("Pharmacognosist")],
        review_protocol="Blinded review",
        independence_statement="Formed judgment before seeing platform output.",
    )


def _fully_locked_protocol(name="Test case"):
    return ValidationCaseProtocol(
        case_name=name,
        decision_context=_locked_decision_context(),
        candidate_set=_locked_candidate_set(),
        reference_corpus=_locked_reference_corpus(),
        expert_panel=_locked_expert_panel(),
    )


# ---------------------------------------------------------------------
# DecisionContext
# ---------------------------------------------------------------------

def test_decision_context_empty_is_not_locked():
    dc = DecisionContext()
    assert dc.is_locked() is False
    assert set(dc.missing_fields()) == {
        "population", "route_of_administration", "dosage_form", "jurisdiction",
    }


def test_decision_context_partial_is_not_locked():
    dc = DecisionContext(population="Adults", dosage_form="Capsule")
    assert dc.is_locked() is False
    assert set(dc.missing_fields()) == {"route_of_administration", "jurisdiction"}


def test_decision_context_all_four_required_fields_locks_it():
    dc = _locked_decision_context()
    assert dc.is_locked() is True
    assert dc.missing_fields() == []


def test_decision_context_whitespace_only_string_counts_as_missing():
    dc = DecisionContext(
        population="   ", route_of_administration="Oral",
        dosage_form="Capsule", jurisdiction="EU",
    )
    assert dc.is_locked() is False
    assert "population" in dc.missing_fields()


def test_decision_context_product_type_and_indication_not_required():
    # Only the four Appendix-A dimensions are required for is_locked();
    # product_type/indication are informational extras.
    dc = DecisionContext(
        population="Adults", route_of_administration="Oral",
        dosage_form="Capsule", jurisdiction="EU",
    )
    assert dc.is_locked() is True


# ---------------------------------------------------------------------
# LockedCandidateSet
# ---------------------------------------------------------------------

def test_candidate_set_empty_is_not_locked():
    cs = LockedCandidateSet()
    assert cs.is_locked() is False
    assert set(cs.missing_fields()) == {"candidates", "eligibility_rules"}


def test_candidate_set_candidates_without_eligibility_rules_is_not_locked():
    cs = LockedCandidateSet(candidates=["Plant A"])
    assert cs.is_locked() is False
    assert cs.missing_fields() == ["eligibility_rules"]


def test_candidate_set_eligibility_rules_without_candidates_is_not_locked():
    cs = LockedCandidateSet(eligibility_rules=[CandidateEligibilityRule("rule")])
    assert cs.is_locked() is False
    assert cs.missing_fields() == ["candidates"]


def test_candidate_set_both_present_is_locked():
    cs = _locked_candidate_set()
    assert cs.is_locked() is True
    assert cs.missing_fields() == []


# ---------------------------------------------------------------------
# ReferenceEvidenceCorpus
# ---------------------------------------------------------------------

def test_reference_corpus_default_is_not_locked():
    corpus = ReferenceEvidenceCorpus()
    assert corpus.is_locked() is False


def test_reference_corpus_not_independent_is_not_locked_even_if_everything_else_present():
    corpus = ReferenceEvidenceCorpus(
        description="desc", built_independently_of_platform=False,
        sources=["PubMed"], search_strategy="strategy",
        evidence_cutoff_date=date(2026, 1, 1),
    )
    assert corpus.is_locked() is False
    assert "built_independently_of_platform" in corpus.missing_fields()


def test_reference_corpus_all_fields_present_is_locked():
    corpus = _locked_reference_corpus()
    assert corpus.is_locked() is True
    assert corpus.missing_fields() == []


def test_reference_corpus_missing_cutoff_date_is_not_locked():
    corpus = ReferenceEvidenceCorpus(
        description="desc", built_independently_of_platform=True,
        sources=["PubMed"], search_strategy="strategy",
    )
    assert corpus.is_locked() is False
    assert "evidence_cutoff_date" in corpus.missing_fields()


# ---------------------------------------------------------------------
# ExpertPanel
# ---------------------------------------------------------------------

def test_expert_panel_default_is_not_locked():
    panel = ExpertPanel()
    assert panel.is_locked() is False
    assert set(panel.missing_fields()) == {
        "members", "review_protocol", "independence_statement",
    }


def test_expert_panel_missing_independence_statement_is_not_locked():
    panel = ExpertPanel(
        members=[ExpertPanelMember("Toxicologist")],
        review_protocol="Some protocol",
    )
    assert panel.is_locked() is False
    assert panel.missing_fields() == ["independence_statement"]


def test_expert_panel_fully_specified_is_locked():
    panel = _locked_expert_panel()
    assert panel.is_locked() is True


# ---------------------------------------------------------------------
# assess_readiness — the four-state ladder
# ---------------------------------------------------------------------

def test_readiness_not_started_when_nothing_defined():
    protocol = _empty_protocol()
    assert assess_readiness(protocol) == ProtocolReadiness.NOT_STARTED


def test_readiness_not_started_even_with_only_indication_but_no_context_dims():
    protocol = _empty_protocol()
    protocol.decision_context = DecisionContext(indication="Sleep and relaxation")
    # indication alone doesn't satisfy is_locked(), but it DOES mean
    # something was started, so this must NOT be NOT_STARTED —
    # verifying the distinction between "nothing entered anywhere" and
    # "some field entered, but not enough".
    assert assess_readiness(protocol) == ProtocolReadiness.NOT_VALIDATION_READY


def test_readiness_not_validation_ready_when_context_incomplete():
    protocol = _empty_protocol()
    protocol.decision_context = DecisionContext(population="Adults")
    assert assess_readiness(protocol) == ProtocolReadiness.NOT_VALIDATION_READY


def test_readiness_conditionally_ready_when_context_locked_but_rest_isnt():
    protocol = _empty_protocol()
    protocol.decision_context = _locked_decision_context()
    assert assess_readiness(protocol) == ProtocolReadiness.CONDITIONALLY_READY


def test_readiness_conditionally_ready_when_only_one_remaining_element_missing():
    protocol = _empty_protocol()
    protocol.decision_context = _locked_decision_context()
    protocol.candidate_set = _locked_candidate_set()
    protocol.reference_corpus = _locked_reference_corpus()
    # expert_panel still empty
    assert assess_readiness(protocol) == ProtocolReadiness.CONDITIONALLY_READY


def test_readiness_locked_when_all_four_elements_complete():
    protocol = _fully_locked_protocol()
    assert assess_readiness(protocol) == ProtocolReadiness.LOCKED


def test_assess_readiness_never_mutates_the_protocol():
    protocol = _empty_protocol()
    assess_readiness(protocol)
    assert protocol.locked is False
    assert protocol.locked_date is None


# ---------------------------------------------------------------------
# gap_report
# ---------------------------------------------------------------------

def test_gap_report_principal_gap_follows_element_order_decision_context_first():
    protocol = _empty_protocol()
    protocol.decision_context = DecisionContext(population="Adults")
    report = gap_report(protocol)
    assert "decision context" in report["principal_gap"]


def test_gap_report_principal_gap_moves_to_candidate_set_once_context_locked():
    protocol = _empty_protocol()
    protocol.decision_context = _locked_decision_context()
    report = gap_report(protocol)
    assert "candidate set" in report["principal_gap"]


def test_gap_report_principal_gap_none_when_locked():
    protocol = _fully_locked_protocol()
    report = gap_report(protocol)
    assert report["principal_gap"] is None
    assert report["readiness"] == ProtocolReadiness.LOCKED


def test_gap_report_all_gaps_only_lists_incomplete_elements():
    protocol = _empty_protocol()
    protocol.decision_context = _locked_decision_context()
    protocol.candidate_set = _locked_candidate_set()
    report = gap_report(protocol)
    assert "decision_context" not in report["all_gaps"]
    assert "candidate_set" not in report["all_gaps"]
    assert "reference_corpus" in report["all_gaps"]
    assert "expert_panel" in report["all_gaps"]


# ---------------------------------------------------------------------
# lock_protocol — the hard, no-partial-lock guarantee
# ---------------------------------------------------------------------

def test_lock_protocol_raises_on_incomplete_protocol():
    protocol = _empty_protocol()
    with pytest.raises(ProtocolNotReadyError):
        lock_protocol(protocol)


def test_lock_protocol_error_carries_gap_report():
    protocol = _empty_protocol()
    try:
        lock_protocol(protocol)
        assert False, "should have raised"
    except ProtocolNotReadyError as e:
        assert hasattr(e, "gap_report")
        assert e.gap_report["readiness"] != ProtocolReadiness.LOCKED


def test_lock_protocol_succeeds_on_complete_protocol():
    protocol = _fully_locked_protocol()
    locked = lock_protocol(protocol, locked_date=date(2026, 6, 1))
    assert locked.locked is True
    assert locked.locked_date == date(2026, 6, 1)


def test_lock_protocol_defaults_locked_date_to_today():
    protocol = _fully_locked_protocol()
    locked = lock_protocol(protocol)
    assert locked.locked_date == date.today()


def test_lock_protocol_never_mutates_the_original_input():
    protocol = _fully_locked_protocol()
    lock_protocol(protocol)
    assert protocol.locked is False
    assert protocol.locked_date is None


def test_lock_protocol_returns_a_distinct_object():
    protocol = _fully_locked_protocol()
    locked = lock_protocol(protocol)
    assert locked is not protocol


# ---------------------------------------------------------------------
# to_appendix_row / protocol_completeness
# ---------------------------------------------------------------------

def test_to_appendix_row_shape_matches_appendix_a_table():
    protocol = _empty_protocol("Some case")
    row = to_appendix_row(protocol)
    assert set(row.keys()) == {"Case", "Readiness", "Principal gap"}
    assert row["Case"] == "Some case"


def test_to_appendix_row_locked_case_shows_none_gap():
    protocol = _fully_locked_protocol("Locked case")
    row = to_appendix_row(protocol)
    assert row["Readiness"] == "Locked"
    assert row["Principal gap"] == "None — locked."


def test_protocol_completeness_zero_for_empty_protocol():
    result = protocol_completeness(_empty_protocol())
    assert result["locked_elements"] == 0
    assert result["completeness_score"] == 0.0


def test_protocol_completeness_100_for_fully_locked_protocol():
    result = protocol_completeness(_fully_locked_protocol())
    assert result["locked_elements"] == 4
    assert result["completeness_score"] == 100.0
    assert all(result["elements_locked"].values())


def test_protocol_completeness_partial():
    protocol = _empty_protocol()
    protocol.decision_context = _locked_decision_context()
    protocol.candidate_set = _locked_candidate_set()
    result = protocol_completeness(protocol)
    assert result["locked_elements"] == 2
    assert result["completeness_score"] == 50.0


# ---------------------------------------------------------------------
# Genericity: this module must work identically for ANY case, not
# just a sleep-support infusion — exercised here with a deliberately
# different product type, dosage form, and jurisdiction.
# ---------------------------------------------------------------------

def test_works_for_a_non_infusion_non_sleep_case():
    protocol = ValidationCaseProtocol(
        case_name="Veterinary digestive-support powder (Canada)",
        decision_context=DecisionContext(
            population="Adult dogs",
            route_of_administration="Oral",
            dosage_form="Powder",
            jurisdiction="Canada",
            product_type="Veterinary botanical product",
            indication="Digestive comfort",
        ),
        candidate_set=LockedCandidateSet(
            candidates=["Matricaria chamomilla"],
            eligibility_rules=[CandidateEligibilityRule("Documented veterinary use")],
        ),
        reference_corpus=ReferenceEvidenceCorpus(
            description="Independent veterinary literature search",
            built_independently_of_platform=True,
            sources=["CAB Abstracts"],
            search_strategy="chamomile AND canine AND digestive",
            evidence_cutoff_date=date(2026, 1, 1),
        ),
        expert_panel=ExpertPanel(
            members=[ExpertPanelMember("Veterinary pharmacologist")],
            review_protocol="Independent review",
            independence_statement="No exposure to platform output before review.",
        ),
    )
    assert assess_readiness(protocol) == ProtocolReadiness.LOCKED
    locked = lock_protocol(protocol)
    assert locked.locked is True
