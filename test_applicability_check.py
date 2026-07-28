"""Tests for applicability_check.py (Validation Architecture v3, Phase 1).

Covers the corrected signature (v3 correction #1):
    check_applicability(reference, validation_unit, domain)
and each of the seven applicability dimensions failing independently.
"""

from datetime import date

from applicability_check import (
    check_applicability, ReferenceDomain, ApplicabilityDimension,
)
from reference_descriptor import ReferenceDescriptor
from validation_unit import ValidationUnit, PreparationSpec


def _base_unit(**overrides):
    defaults = dict(
        taxon="Valeriana officinalis L.", plant_part="root",
        preparation=PreparationSpec(dosage_form="Infusion", solvent="water"),
        population="Adults", jurisdiction="Germany",
        indication="Sleep and relaxation", route_of_administration="Oral",
    )
    defaults.update(overrides)
    return ValidationUnit(**defaults)


def _base_reference(**overrides):
    defaults = dict(
        reference_id="ref1", source_type="EMA_HMPC", version="v1",
        plant_part="root", preparation=PreparationSpec(dosage_form="Infusion", solvent="water"),
        population="general",
    )
    defaults.update(overrides)
    return ReferenceDescriptor(**defaults)


def test_fully_matching_reference_is_applicable():
    result = check_applicability(_base_reference(), _base_unit(), ReferenceDomain.SAFETY)
    assert result.applicable is True
    assert result.failed_dimensions == []


def test_result_carries_reference_id_and_domain():
    result = check_applicability(_base_reference(), _base_unit(), ReferenceDomain.SAFETY)
    assert result.reference_id == "ref1"
    assert result.domain == ReferenceDomain.SAFETY


# ---------------------------------------------------------------------
# Each of the seven dimensions, failing independently
# ---------------------------------------------------------------------

def test_preparation_dosage_form_mismatch_fails():
    ref = _base_reference(preparation=PreparationSpec(dosage_form="Tincture", solvent="water"))
    result = check_applicability(ref, _base_unit(), ReferenceDomain.SAFETY)
    assert result.applicable is False
    assert ApplicabilityDimension.PREPARATION in result.failed_dimensions


def test_preparation_der_range_no_overlap_fails():
    ref = _base_reference(preparation=PreparationSpec(dosage_form="Infusion", solvent="water", der_min=10, der_max=12))
    unit = _base_unit(preparation=PreparationSpec(dosage_form="Infusion", solvent="water", der_min=4, der_max=7))
    result = check_applicability(ref, unit, ReferenceDomain.SAFETY)
    assert ApplicabilityDimension.PREPARATION in result.failed_dimensions


def test_preparation_der_range_overlap_passes():
    ref = _base_reference(preparation=PreparationSpec(dosage_form="Infusion", solvent="water", der_min=4, der_max=8))
    unit = _base_unit(preparation=PreparationSpec(dosage_form="Infusion", solvent="water", der_min=6, der_max=10))
    result = check_applicability(ref, unit, ReferenceDomain.SAFETY)
    assert ApplicabilityDimension.PREPARATION not in result.failed_dimensions


def test_plant_part_mismatch_fails():
    ref = _base_reference(plant_part="leaf")
    result = check_applicability(ref, _base_unit(), ReferenceDomain.SAFETY)
    assert ApplicabilityDimension.PLANT_PART in result.failed_dimensions


def test_population_mismatch_fails():
    ref = _base_reference(population="Pediatric")
    result = check_applicability(ref, _base_unit(population="Adults"), ReferenceDomain.SAFETY)
    assert ApplicabilityDimension.POPULATION in result.failed_dimensions


def test_population_general_on_reference_always_passes():
    ref = _base_reference(population="general population")
    result = check_applicability(ref, _base_unit(population="Pregnant"), ReferenceDomain.SAFETY)
    assert ApplicabilityDimension.POPULATION not in result.failed_dimensions


def test_jurisdiction_mismatch_fails():
    ref = _base_reference(jurisdiction="France")
    result = check_applicability(ref, _base_unit(jurisdiction="Germany"), ReferenceDomain.SAFETY)
    assert ApplicabilityDimension.JURISDICTION in result.failed_dimensions


def test_jurisdiction_none_on_reference_always_passes():
    ref = _base_reference(jurisdiction=None)
    result = check_applicability(ref, _base_unit(jurisdiction="Germany"), ReferenceDomain.SAFETY)
    assert ApplicabilityDimension.JURISDICTION not in result.failed_dimensions


def test_claim_type_unrecognized_value_fails():
    ref = _base_reference(claim_type="made-up-claim-type")
    result = check_applicability(ref, _base_unit(), ReferenceDomain.SAFETY)
    assert ApplicabilityDimension.CLAIM_TYPE in result.failed_dimensions


def test_claim_type_recognized_value_passes():
    ref = _base_reference(claim_type="traditional-use")
    result = check_applicability(ref, _base_unit(), ReferenceDomain.SAFETY)
    assert ApplicabilityDimension.CLAIM_TYPE not in result.failed_dimensions


def test_source_date_retracted_fails():
    ref = _base_reference(retracted_or_superseded=True)
    result = check_applicability(ref, _base_unit(), ReferenceDomain.SAFETY)
    assert ApplicabilityDimension.SOURCE_DATE in result.failed_dimensions


def test_document_scope_indication_not_covered_fails():
    ref = _base_reference(indication_scope=["Some other indication"])
    result = check_applicability(ref, _base_unit(indication="Sleep and relaxation"), ReferenceDomain.SAFETY)
    assert ApplicabilityDimension.DOCUMENT_SCOPE in result.failed_dimensions


def test_document_scope_route_not_covered_fails():
    ref = _base_reference(route_scope=["Topical"])
    result = check_applicability(ref, _base_unit(route_of_administration="Oral"), ReferenceDomain.SAFETY)
    assert ApplicabilityDimension.DOCUMENT_SCOPE in result.failed_dimensions


def test_document_scope_empty_list_does_not_exclude():
    # An unpopulated scope list is not treated as "covers nothing".
    ref = _base_reference(indication_scope=[], route_scope=[])
    result = check_applicability(ref, _base_unit(), ReferenceDomain.SAFETY)
    assert ApplicabilityDimension.DOCUMENT_SCOPE not in result.failed_dimensions


# ---------------------------------------------------------------------
# Multi-dimension failure and detail reporting
# ---------------------------------------------------------------------

def test_multiple_dimensions_can_fail_simultaneously():
    ref = _base_reference(plant_part="leaf", population="Pediatric")
    result = check_applicability(ref, _base_unit(population="Adults"), ReferenceDomain.SAFETY)
    assert ApplicabilityDimension.PLANT_PART in result.failed_dimensions
    assert ApplicabilityDimension.POPULATION in result.failed_dimensions
    assert result.applicable is False


def test_detail_dict_has_entry_for_every_dimension():
    result = check_applicability(_base_reference(), _base_unit(), ReferenceDomain.SAFETY)
    assert set(result.detail.keys()) == {d.value for d in ApplicabilityDimension}


def test_domain_parameter_is_required_and_recorded():
    result_safety = check_applicability(_base_reference(), _base_unit(), ReferenceDomain.SAFETY)
    result_identity = check_applicability(_base_reference(), _base_unit(), ReferenceDomain.IDENTITY_QUALITY)
    assert result_safety.domain != result_identity.domain
