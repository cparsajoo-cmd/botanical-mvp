"""
Task 13.2B — Presentation-Safe Evidence Detail Adapter.

WHAT THIS COVERS
standard_evidence_builder.build_scientific_evidence_presentation_payload()
— the reusable, stateless converter from {id: ScientificEvidence} into
{id: dict} suitable for a report template. No report generation, no
Streamlit wiring, no engine, no database — this file tests exactly one
pure function (plus its composition with Task 13.2A's
get_scientific_evidence_by_ids()).

HOW TO RUN
    pytest -q test_task13_2b_scientific_evidence_presentation.py
    (or `pytest -q` from the repo root — auto-discovered)
"""

import pandas as pd

from data_contracts import EvidenceApplicability, EvidenceHierarchyLevel, ScientificEvidence
from standard_evidence_builder import (
    build_scientific_evidence_presentation_payload,
    get_scientific_evidence_by_ids,
)
from test_task13_2a_scientific_evidence_lookup import _evidence_df


def _full_scientific_evidence(**overrides):
    defaults = dict(
        source_type="PubMed",
        doi_pmid_url="https://pubmed.ncbi.nlm.nih.gov/1/",
        study_type="Randomized Controlled Trial",
        population="human",
        comparator="placebo",
        outcome="improved sleep latency",
        applicability_classification=EvidenceApplicability.PARTIALLY_APPLICABLE,
        applicability_rationale="PARTIALLY_APPLICABLE: indication and dosage form match.",
        applicability_evaluated_dimensions=["indication", "dosage_form"],
        applicability_missing_dimensions=["plant_part"],
        applicability_detected_mismatches=[],
        evidence_hierarchy_level=EvidenceHierarchyLevel.TRADITIONAL_USE_MONOGRAPH,
        source_record_id="ev-1",
    )
    defaults.update(overrides)
    return ScientificEvidence(**defaults)


# ---------------------------------------------------------------------
# 1) Correct conversion of a complete ScientificEvidence.
# ---------------------------------------------------------------------

def test_correct_conversion_of_a_complete_scientific_evidence():
    evidence = _full_scientific_evidence()
    result = build_scientific_evidence_presentation_payload({"ev-1": evidence})

    payload = result["ev-1"]
    assert payload["evidence_record_id"] == "ev-1"
    assert payload["source_type"] == "PubMed"
    assert payload["study_type"] == "Randomized Controlled Trial"
    assert payload["population"] == "human"
    assert payload["applicability_classification"] == "Partially applicable"
    assert payload["applicability_rationale"] == "PARTIALLY_APPLICABLE: indication and dosage form match."
    assert payload["doi_pmid_url"] == "https://pubmed.ncbi.nlm.nih.gov/1/"


# ---------------------------------------------------------------------
# 2) Enum values render as user-facing .value strings.
# 3) No Python enum representation leaks into output.
# ---------------------------------------------------------------------

def test_enum_values_render_as_user_facing_value_strings_not_reprs():
    for member in EvidenceApplicability:
        evidence = _full_scientific_evidence(applicability_classification=member)
        result = build_scientific_evidence_presentation_payload({"ev-x": evidence})
        rendered = result["ev-x"]["applicability_classification"]

        assert rendered == member.value
        assert rendered != str(member)
        assert "EvidenceApplicability." not in rendered
        assert not rendered.startswith("<")  # rules out repr() form too


def test_no_enum_object_of_any_kind_appears_anywhere_in_output():
    evidence = _full_scientific_evidence()
    result = build_scientific_evidence_presentation_payload({"ev-1": evidence})
    for value in result["ev-1"].values():
        assert not hasattr(value, "value") or isinstance(value, str)


# ---------------------------------------------------------------------
# 4) Missing optional fields become None.
# ---------------------------------------------------------------------

def test_missing_optional_fields_become_none():
    bare = ScientificEvidence(source_type="ClinicalTrials.gov")  # everything else default
    result = build_scientific_evidence_presentation_payload({"ev-bare": bare})
    payload = result["ev-bare"]

    assert payload["source_type"] == "ClinicalTrials.gov"
    assert payload["study_type"] is None
    assert payload["population"] is None
    assert payload["applicability_classification"] is None
    assert payload["applicability_rationale"] is None
    assert payload["doi_pmid_url"] is None


# ---------------------------------------------------------------------
# 5) None, NaN, pd.NA, and empty strings are normalized.
# ---------------------------------------------------------------------

def test_none_nan_pdna_and_empty_strings_normalize_to_none():
    for missing_value in (None, float("nan"), pd.NA, "", "   ", "nan", "none"):
        evidence = _full_scientific_evidence(
            source_type=missing_value, population=missing_value,
        )
        result = build_scientific_evidence_presentation_payload({"ev-x": evidence})
        payload = result["ev-x"]
        assert payload["source_type"] is None, f"failed for {missing_value!r}"
        assert payload["population"] is None, f"failed for {missing_value!r}"


# ---------------------------------------------------------------------
# 6) Malformed entries are skipped without aborting valid entries.
# ---------------------------------------------------------------------

def test_malformed_entries_skipped_without_aborting_valid_entries():
    good = _full_scientific_evidence()
    mapping = {
        "ev-good-1": good,
        "ev-not-an-object": "this is a plain string, not ScientificEvidence",
        "ev-none-value": None,
        "ev-int-value": 42,
        float("nan"): good,      # malformed KEY, not value
        None: good,              # malformed KEY
        "": good,                # malformed KEY (empty string)
        "ev-good-2": _full_scientific_evidence(source_type="Europe PMC"),
    }
    result = build_scientific_evidence_presentation_payload(mapping)

    assert set(result.keys()) == {"ev-good-1", "ev-good-2"}
    assert result["ev-good-1"]["source_type"] == "PubMed"
    assert result["ev-good-2"]["source_type"] == "Europe PMC"


# ---------------------------------------------------------------------
# 7) Invalid or non-dict input returns {}.
# ---------------------------------------------------------------------

def test_invalid_or_non_dict_input_returns_empty_dict():
    for bad_input in (None, "not a dict", 42, ["a", "list"], {"a", "set"}, object()):
        assert build_scientific_evidence_presentation_payload(bad_input) == {}


def test_empty_dict_input_returns_empty_dict():
    assert build_scientific_evidence_presentation_payload({}) == {}


# ---------------------------------------------------------------------
# 8) Only the approved seven fields are exposed.
# ---------------------------------------------------------------------

def test_only_the_approved_seven_fields_are_exposed():
    evidence = _full_scientific_evidence()
    result = build_scientific_evidence_presentation_payload({"ev-1": evidence})
    payload = result["ev-1"]

    approved_fields = {
        "evidence_record_id", "source_type", "study_type", "population",
        "applicability_classification", "applicability_rationale", "doi_pmid_url",
    }
    assert set(payload.keys()) == approved_fields

    # Explicitly confirm fields that DO exist on ScientificEvidence but
    # were not approved for this payload never leak in.
    for forbidden_field in (
        "evidence_hierarchy_level", "comparator", "outcome", "sample_size",
        "dose", "duration", "risk_of_bias", "confidence_score",
        "applicability_evaluated_dimensions", "applicability_missing_dimensions",
        "applicability_detected_mismatches", "is_negative_or_contradictory",
    ):
        assert forbidden_field not in payload


# ---------------------------------------------------------------------
# 9) IDs remain unchanged.
# ---------------------------------------------------------------------

def test_ids_remain_unchanged():
    evidence = _full_scientific_evidence()
    mapping = {"ev-not-sequential-\U0001F48A": evidence, "42": evidence, "ev-7": evidence}
    result = build_scientific_evidence_presentation_payload(mapping)

    assert set(result.keys()) == set(mapping.keys())
    for key in result:
        assert result[key]["evidence_record_id"] == key


# ---------------------------------------------------------------------
# 10) Inputs are not mutated.
# ---------------------------------------------------------------------

def test_input_mapping_is_not_mutated():
    evidence = _full_scientific_evidence()
    mapping = {"ev-1": evidence, "ev-2": _full_scientific_evidence(source_type="Europe PMC")}
    mapping_keys_before = set(mapping.keys())
    mapping_id_before = id(mapping)

    build_scientific_evidence_presentation_payload(mapping)

    assert set(mapping.keys()) == mapping_keys_before
    assert id(mapping) == mapping_id_before
    assert mapping["ev-1"] is evidence  # same object, untouched


def test_scientific_evidence_objects_are_not_mutated():
    evidence = _full_scientific_evidence()
    snapshot = dict(
        source_type=evidence.source_type,
        applicability_classification=evidence.applicability_classification,
        applicability_rationale=evidence.applicability_rationale,
        doi_pmid_url=evidence.doi_pmid_url,
    )

    build_scientific_evidence_presentation_payload({"ev-1": evidence})

    assert evidence.source_type == snapshot["source_type"]
    assert evidence.applicability_classification == snapshot["applicability_classification"]
    assert evidence.applicability_rationale == snapshot["applicability_rationale"]
    assert evidence.doi_pmid_url == snapshot["doi_pmid_url"]
    # Still the real enum member on the object itself — only the
    # PRESENTATION copy is a plain string, the source object is untouched.
    assert isinstance(evidence.applicability_classification, EvidenceApplicability)


# ---------------------------------------------------------------------
# Composition: get_scientific_evidence_by_ids() -> presentation payload
# ---------------------------------------------------------------------

def test_composes_cleanly_with_get_scientific_evidence_by_ids():
    df = _evidence_df()
    looked_up = get_scientific_evidence_by_ids(["ev-1", "ev-2"], df)
    payload = build_scientific_evidence_presentation_payload(looked_up)

    assert set(payload.keys()) == {"ev-1", "ev-2"}
    assert payload["ev-1"]["source_type"] == "PubMed"
    assert payload["ev-1"]["applicability_classification"] == "Partially applicable"
    assert payload["ev-1"]["evidence_record_id"] == "ev-1"
