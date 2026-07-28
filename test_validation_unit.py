"""Tests for validation_unit.py (Validation Architecture v3, Phase 1)."""

from validation_unit import ValidationUnit, PreparationSpec, Dose


def test_validation_unit_minimal_construction():
    unit = ValidationUnit(taxon="Valeriana officinalis L.")
    assert unit.taxon == "Valeriana officinalis L."
    assert unit.taxon_synonyms == []
    assert unit.plant_part is None
    assert unit.preparation is None


def test_validation_unit_full_construction():
    unit = ValidationUnit(
        taxon="Valeriana officinalis L.",
        taxon_synonyms=["Valeriana sp."],
        plant_part="root and rhizome",
        preparation=PreparationSpec(dosage_form="Dry extract", solvent="ethanol 70% V/V", der_min=4.0, der_max=7.0, source_status="native"),
        dose=Dose(amount=300, unit="mg", frequency="twice daily"),
        duration="up to 4 weeks",
        route_of_administration="Oral",
        indication="Sleep and relaxation",
        population="Adults",
        jurisdiction="Germany",
    )
    assert unit.preparation.der_min == 4.0
    assert unit.dose.amount == 300


def test_validation_unit_has_no_reference_version_field():
    # v3 correction #8 — reference_version must not exist on ValidationUnit.
    unit = ValidationUnit(taxon="X")
    assert not hasattr(unit, "reference_version")


def test_taxon_synonyms_defaults_to_empty_list_not_none():
    unit = ValidationUnit(taxon="X")
    assert unit.taxon_synonyms == []
    assert isinstance(unit.taxon_synonyms, list)


def test_preparation_spec_all_fields_optional():
    spec = PreparationSpec()
    assert spec.dosage_form is None
    assert spec.der_min is None


def test_dose_all_fields_optional():
    dose = Dose()
    assert dose.amount is None
