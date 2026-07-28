"""Regression tests for validation_matrix.py (Task 7 — Validation
Coverage Matrix). See that module's docstring for the full documented
method and its declared limitations.
"""

import csv
import os
import tempfile

import validation_matrix as vm
from step_inputs import PRODUCT_TYPES, INDICATIONS, DOSAGE_FORMS, MARKETS
from validation_case_protocol import ProtocolReadiness, assess_readiness


# ---------------------------------------------------------------------
# Route / population derivation
# ---------------------------------------------------------------------

def test_route_of_administration_known_dosage_forms():
    assert vm._route_of_administration("Infusion") == "Oral"
    assert vm._route_of_administration("Cream") == "Topical"
    assert vm._route_of_administration("Mouthwash") == "Oromucosal"
    assert vm._route_of_administration("Nasal spray") == "Nasal"


def test_route_of_administration_every_real_dosage_form_has_a_mapping():
    # No dosage form step_inputs.py actually offers should silently
    # fall through to None.
    for dosage_form in DOSAGE_FORMS:
        assert vm._route_of_administration(dosage_form) is not None, dosage_form


def test_route_of_administration_unknown_form_returns_none():
    assert vm._route_of_administration("Not a real dosage form") is None


def test_population_veterinary_product_type_is_distinct():
    vet = vm._population_for_product_type("Veterinary botanical product")
    human = vm._population_for_product_type("Food supplement")
    assert "Veterinary" in vet
    assert "Human adults" in human
    assert vet != human


def test_population_every_real_product_type_has_a_value():
    for product_type in PRODUCT_TYPES:
        assert vm._population_for_product_type(product_type)


# ---------------------------------------------------------------------
# generate_decision_context
# ---------------------------------------------------------------------

def test_generate_decision_context_fills_all_four_required_dimensions():
    dc = vm.generate_decision_context(
        "Food supplement", "Sleep and relaxation", "Infusion", "European Union"
    )
    assert dc.is_locked() is True
    assert dc.dosage_form == "Infusion"
    assert dc.jurisdiction == "European Union"
    assert dc.product_type == "Food supplement"
    assert dc.indication == "Sleep and relaxation"


def test_generate_decision_context_every_real_dosage_form_locks_the_context():
    # Confirms the route-mapping coverage test above actually matters:
    # every real dosage form must produce a fully-locked DecisionContext.
    for dosage_form in DOSAGE_FORMS:
        dc = vm.generate_decision_context(
            "Food supplement", "Sleep and relaxation", dosage_form, "European Union"
        )
        assert dc.is_locked() is True, dosage_form


# ---------------------------------------------------------------------
# generate_matrix — full and filtered
# ---------------------------------------------------------------------

def test_generate_matrix_full_size_matches_real_option_list_lengths():
    protocols = vm.generate_matrix()
    expected = len(PRODUCT_TYPES) * len(INDICATIONS) * len(DOSAGE_FORMS) * len(MARKETS)
    assert len(protocols) == expected


def test_generate_matrix_filtered_on_one_axis():
    protocols = vm.generate_matrix(dosage_forms=["Cream"])
    expected = len(PRODUCT_TYPES) * len(INDICATIONS) * 1 * len(MARKETS)
    assert len(protocols) == expected
    assert all(p.decision_context.dosage_form == "Cream" for p in protocols)


def test_generate_matrix_filtered_on_all_four_axes_gives_one_protocol():
    protocols = vm.generate_matrix(
        product_types=["Cosmetic"],
        indications=["Skin inflammation"],
        dosage_forms=["Cream"],
        markets=["European Union"],
    )
    assert len(protocols) == 1
    dc = protocols[0].decision_context
    assert dc.product_type == "Cosmetic"
    assert dc.indication == "Skin inflammation"
    assert dc.dosage_form == "Cream"
    assert dc.jurisdiction == "European Union"


def test_generate_matrix_every_protocol_has_only_decision_context_populated():
    protocols = vm.generate_matrix(
        product_types=["Food supplement"], indications=["Sleep and relaxation"],
        dosage_forms=["Infusion"], markets=["European Union"],
    )
    protocol = protocols[0]
    assert protocol.candidate_set.candidates == []
    assert protocol.reference_corpus.description is None
    assert protocol.expert_panel.members == []
    assert protocol.locked is False


def test_generate_matrix_every_protocol_is_at_least_conditionally_ready():
    protocols = vm.generate_matrix(
        product_types=["Cosmetic"], indications=["Skin inflammation"],
        dosage_forms=["Cream"], markets=["European Union"],
    )
    for p in protocols:
        assert assess_readiness(p) == ProtocolReadiness.CONDITIONALLY_READY


def test_generate_matrix_this_is_not_infusion_only_or_sleep_only():
    # Direct regression against the exact concern this module exists
    # to address: the matrix must genuinely span non-infusion dosage
    # forms and non-sleep indications, not just the two demo scenarios.
    protocols = vm.generate_matrix()
    dosage_forms_seen = {p.decision_context.dosage_form for p in protocols}
    indications_seen = {p.decision_context.indication for p in protocols}
    assert "Cream" in dosage_forms_seen
    assert "Nasal spray" in dosage_forms_seen
    assert "Skin inflammation" in indications_seen
    assert "Urinary tract health" in indications_seen
    assert len(dosage_forms_seen) == len(DOSAGE_FORMS)
    assert len(indications_seen) == len(INDICATIONS)


# ---------------------------------------------------------------------
# matrix_readiness_summary
# ---------------------------------------------------------------------

def test_matrix_readiness_summary_all_conditionally_ready_for_a_fresh_matrix():
    protocols = vm.generate_matrix(
        product_types=["Food supplement"], indications=["Sleep and relaxation"],
        dosage_forms=["Infusion"], markets=["European Union"],
    )
    summary = vm.matrix_readiness_summary(protocols)
    assert summary["total"] == 1
    assert summary["counts"]["Conditionally ready for protocol completion"] == 1
    assert summary["counts"]["Locked"] == 0


def test_matrix_readiness_summary_percentages_sum_to_100():
    protocols = vm.generate_matrix(
        product_types=["Food supplement", "Cosmetic"],
        indications=["Sleep and relaxation"],
        dosage_forms=["Infusion"], markets=["European Union"],
    )
    summary = vm.matrix_readiness_summary(protocols)
    assert sum(summary["percentages"].values()) == 100.0


def test_matrix_readiness_summary_empty_list():
    summary = vm.matrix_readiness_summary([])
    assert summary["total"] == 0
    assert all(v == 0 for v in summary["counts"].values())


def test_matrix_readiness_summary_reflects_a_locked_case_mixed_in():
    from datetime import date
    from validation_case_protocol import (
        LockedCandidateSet, CandidateEligibilityRule, ReferenceEvidenceCorpus,
        ExpertPanel, ExpertPanelMember, lock_protocol,
    )
    protocols = vm.generate_matrix(
        product_types=["Food supplement"], indications=["Sleep and relaxation"],
        dosage_forms=["Infusion"], markets=["European Union"],
    )
    protocols[0].candidate_set = LockedCandidateSet(
        candidates=["Melissa officinalis"],
        eligibility_rules=[CandidateEligibilityRule("Documented use")],
    )
    protocols[0].reference_corpus = ReferenceEvidenceCorpus(
        description="desc", built_independently_of_platform=True,
        sources=["PubMed manual"], search_strategy="strategy",
        evidence_cutoff_date=date(2026, 1, 1),
    )
    protocols[0].expert_panel = ExpertPanel(
        members=[ExpertPanelMember("Pharmacognosist")],
        review_protocol="protocol", independence_statement="statement",
    )
    protocols[0] = lock_protocol(protocols[0])

    summary = vm.matrix_readiness_summary(protocols)
    assert summary["counts"]["Locked"] == 1


# ---------------------------------------------------------------------
# matrix_rows / CSV export
# ---------------------------------------------------------------------

def test_matrix_rows_shape():
    protocols = vm.generate_matrix(
        product_types=["Food supplement"], indications=["Sleep and relaxation"],
        dosage_forms=["Infusion"], markets=["European Union"],
    )
    rows = vm.matrix_rows(protocols)
    assert len(rows) == 1
    assert set(rows[0].keys()) == set(vm._CSV_FIELDNAMES)


def test_write_matrix_csv_round_trips():
    protocols = vm.generate_matrix(
        product_types=["Food supplement", "Cosmetic"],
        indications=["Sleep and relaxation"],
        dosage_forms=["Infusion"], markets=["European Union"],
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "matrix.csv")
        count = vm.write_matrix_csv(protocols, path)
        assert count == 2
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            read_rows = list(reader)
        assert len(read_rows) == 2
        assert set(read_rows[0].keys()) == set(vm._CSV_FIELDNAMES)


# ---------------------------------------------------------------------
# filter_matrix
# ---------------------------------------------------------------------

def test_filter_matrix_narrows_on_a_single_axis():
    protocols = vm.generate_matrix(
        indications=["Sleep and relaxation"], dosage_forms=["Infusion"],
        markets=["European Union"],
    )
    filtered = vm.filter_matrix(protocols, product_type="Cosmetic")
    assert len(filtered) == 1
    assert filtered[0].decision_context.product_type == "Cosmetic"


def test_filter_matrix_no_filters_returns_everything():
    protocols = vm.generate_matrix(
        indications=["Sleep and relaxation"], dosage_forms=["Infusion"],
        markets=["European Union"],
    )
    filtered = vm.filter_matrix(protocols)
    assert len(filtered) == len(protocols)


def test_filter_matrix_combining_axes():
    protocols = vm.generate_matrix(dosage_forms=["Cream"])
    filtered = vm.filter_matrix(
        protocols, product_type="Cosmetic", indication="Skin inflammation",
    )
    assert len(filtered) == len(MARKETS)
    assert all(p.decision_context.product_type == "Cosmetic" for p in filtered)
    assert all(p.decision_context.indication == "Skin inflammation" for p in filtered)


# ---------------------------------------------------------------------
# CLI (main())
# ---------------------------------------------------------------------

def test_main_usage_message_on_missing_args():
    assert vm.main([]) == 2
    assert vm.main(["notexport"]) == 2


def test_main_export_writes_file_and_returns_zero():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "cli.csv")
        rc = vm.main([
            "export", path,
            "--dosage-form", "Cream", "--market", "European Union",
        ])
        assert rc == 0
        assert os.path.exists(path)
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        expected = len(PRODUCT_TYPES) * len(INDICATIONS)
        assert len(rows) == expected
