"""Tests for gold_case_serialization.py (Validation Architecture v3, Phase 2)."""

import json
from datetime import date, datetime

from applicability_check import ApplicabilityResult, ReferenceDomain, ApplicabilityDimension
from dataset_split import DatasetSplit, LeakageControl
from field_provenance import FieldProvenance, VerificationStatus
from gold_case import GoldCase, GoldCaseReference, ExpectedOutput, RiskStratum, DecisionDirection
from gold_case_serialization import gold_case_to_dict, gold_case_from_dict
from reference_descriptor import ReferenceDescriptor
from reference_precedence import ReferenceVerdict
from synthetic_validation_fixtures.fixtures import build_synthetic_gold_cases
from user_roles import ReviewerRole
from validation_unit import ValidationUnit, PreparationSpec, Dose


def test_minimal_case_round_trips():
    case = GoldCase(case_id="c1", validation_unit=ValidationUnit(taxon="X"))
    back = gold_case_from_dict(gold_case_to_dict(case))
    assert back == case


def test_full_case_round_trips():
    unit = ValidationUnit(
        taxon="Valeriana officinalis L.", taxon_synonyms=["Valeriana sp."],
        plant_part="root", preparation=PreparationSpec(dosage_form="Extract", solvent="ethanol 70%", der_min=4.0, der_max=7.0),
        dose=Dose(amount=300, unit="mg", frequency="daily"),
        duration="4 weeks", route_of_administration="Oral",
        indication="Sleep and relaxation", population="Adults", jurisdiction="Germany",
    )
    reference = ReferenceDescriptor(
        reference_id="ref1", source_type="EMA_HMPC", version="v1",
        document_date=date(2020, 1, 1), plant_part="root",
        indication_scope=["Sleep and relaxation"],
    )
    provenance = FieldProvenance(
        document_id="doc1", document_version="v1", locator="p.3",
        supported_field="expected_output.expected_decision_direction",
        extraction_date=date(2026, 1, 1), curator=ReviewerRole.PHARMACOGNOSIST,
        verification_status=VerificationStatus.CURATOR_VERIFIED,
    )
    gold_ref = GoldCaseReference(
        reference=reference,
        applicability_by_domain={
            ReferenceDomain.SAFETY: ApplicabilityResult(
                reference_id="ref1", domain=ReferenceDomain.SAFETY, applicable=True,
                failed_dimensions=[], detail={"preparation": "pass"},
            ),
        },
        verdict=ReferenceVerdict(reference_id="ref1", safety_severity="MODERATE", verdict_value="caution"),
        provenance=[provenance],
    )
    case = GoldCase(
        case_id="c1", validation_unit=unit,
        risk_strata=[RiskStratum.SAFETY_MODERATE, RiskStratum.VULNERABLE_POPULATION],
        references=[gold_ref],
        expected_output=ExpectedOutput(
            expected_gate_results={"safety": "PASSED"},
            expected_decision_direction=DecisionDirection.POSITIVE,
            expected_warnings=["Use with caution"],
            acceptable_decision_class_min="Early-stage candidate; more evidence needed",
            acceptable_decision_class_max="Strong R&D candidate",
        ),
        correct_abstention_expected=False,
        case_provenance=[provenance],
        dataset_split=DatasetSplit.LOCKED_HOLDOUT,
        leakage_control=LeakageControl(engine_output_observed_before_finalization=True, observed_at=datetime(2026, 1, 1, 12, 0, 0), case_modified_after_observation=False),
    )
    back = gold_case_from_dict(gold_case_to_dict(case))
    assert back == case


def test_serialized_dict_is_json_serializable():
    case = GoldCase(case_id="c1", validation_unit=ValidationUnit(taxon="X"))
    d = gold_case_to_dict(case)
    text = json.dumps(d)
    assert isinstance(text, str)


def test_all_synthetic_fixtures_round_trip():
    for case in build_synthetic_gold_cases():
        back = gold_case_from_dict(gold_case_to_dict(case))
        assert back == case, case.case_id


def test_deserialization_degrades_gracefully_on_missing_keys():
    back = gold_case_from_dict({"case_id": "minimal"})
    assert back.case_id == "minimal"
    assert back.risk_strata == []
    assert back.references == []


def test_deserialization_of_empty_dict_does_not_raise():
    back = gold_case_from_dict({})
    assert back.case_id is None


def test_applicability_by_domain_round_trips_correctly():
    ref = ReferenceDescriptor(reference_id="r1", source_type="EMA_HMPC", version="v1")
    gref = GoldCaseReference(
        reference=ref,
        applicability_by_domain={
            ReferenceDomain.SAFETY: ApplicabilityResult(
                reference_id="r1", domain=ReferenceDomain.SAFETY, applicable=False,
                failed_dimensions=[ApplicabilityDimension.PLANT_PART], detail={"plant_part": "mismatch"},
            ),
        },
    )
    case = GoldCase(case_id="c1", validation_unit=ValidationUnit(taxon="X"), references=[gref])
    back = gold_case_from_dict(gold_case_to_dict(case))
    result = back.references[0].applicability_by_domain[ReferenceDomain.SAFETY]
    assert result.applicable is False
    assert ApplicabilityDimension.PLANT_PART in result.failed_dimensions
