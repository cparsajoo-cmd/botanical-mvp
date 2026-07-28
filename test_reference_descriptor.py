"""Tests for reference_descriptor.py (Validation Architecture v3, Phase 1)."""

from datetime import date

from reference_descriptor import ReferenceDescriptor
from validation_unit import PreparationSpec


def test_minimal_construction():
    ref = ReferenceDescriptor(reference_id="r1", source_type="EMA_HMPC", version="2018")
    assert ref.reference_id == "r1"
    assert ref.jurisdiction is None
    assert ref.retracted_or_superseded is False


def test_full_construction():
    ref = ReferenceDescriptor(
        reference_id="r1", source_type="EMA_HMPC", version="2018",
        document_date=date(2018, 3, 1), jurisdiction="Germany",
        taxon="Valeriana officinalis L.", plant_part="root",
        preparation=PreparationSpec(dosage_form="Infusion"),
        population="general", claim_type="traditional-use",
        indication_scope=["Sleep and relaxation"], route_scope=["Oral"],
    )
    assert ref.indication_scope == ["Sleep and relaxation"]
    assert ref.claim_type == "traditional-use"


def test_jurisdiction_none_means_international_scope():
    # Documented convention — see module docstring.
    ref = ReferenceDescriptor(reference_id="r1", source_type="WHO_MONOGRAPH", version="1")
    assert ref.jurisdiction is None


def test_indication_scope_and_route_scope_default_to_empty_lists():
    ref = ReferenceDescriptor(reference_id="r1", source_type="WHO_MONOGRAPH", version="1")
    assert ref.indication_scope == []
    assert ref.route_scope == []


def test_retracted_or_superseded_defaults_false():
    ref = ReferenceDescriptor(reference_id="r1", source_type="WHO_MONOGRAPH", version="1")
    assert ref.retracted_or_superseded is False
