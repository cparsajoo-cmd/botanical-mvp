"""Tests for field_provenance.py (Validation Architecture v3, Phase 1)."""

from datetime import date

from field_provenance import FieldProvenance, VerificationStatus
from user_roles import ReviewerRole


def test_minimal_construction_defaults_to_unverified():
    prov = FieldProvenance(
        document_id="doc1", document_version="v1", locator="p.4",
        supported_field="expected_output.expected_decision_direction",
        extraction_date=date(2026, 1, 1),
    )
    assert prov.verification_status == VerificationStatus.UNVERIFIED
    assert prov.curator is None


def test_full_construction():
    prov = FieldProvenance(
        document_id="doc1", document_version="v2", locator="section 3.2",
        supported_field="validation_unit.indication",
        extraction_date=date(2026, 2, 1),
        curator=ReviewerRole.PHARMACOGNOSIST,
        verification_status=VerificationStatus.SECOND_REVIEWER_VERIFIED,
    )
    assert prov.curator == ReviewerRole.PHARMACOGNOSIST
    assert prov.verification_status == VerificationStatus.SECOND_REVIEWER_VERIFIED


def test_curator_is_a_role_not_a_free_text_name():
    # curator must be a ReviewerRole enum member (or None), never an
    # arbitrary string — this test documents the type expectation.
    prov = FieldProvenance(
        document_id="doc1", document_version="v1", locator="p.1",
        supported_field="x", extraction_date=date(2026, 1, 1),
        curator=ReviewerRole.REGULATORY_PROFESSIONAL,
    )
    assert isinstance(prov.curator, ReviewerRole)
