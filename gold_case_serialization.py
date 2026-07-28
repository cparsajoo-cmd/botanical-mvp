"""
Validation Architecture v3 — Phase 2: GoldCase Serialization.

WHY A SEPARATE MODULE FROM gold_case.py
Same reasoning validation_case_protocol.py used for its own
protocol_to_dict()/protocol_from_dict() — kept alongside the
dataclasses there. Here it is a separate file instead, because
GoldCase's nested structure (references, each with per-domain
applicability results and provenance lists) is materially larger than
ValidationCaseProtocol's, and keeping serialization physically
separate makes both files easier to review independently.

ROUND-TRIP GUARANTEE
gold_case_from_dict(gold_case_to_dict(case)) reconstructs every field
Phase 1/2 currently define — see test_gold_case_serialization.py's
round-trip tests, including the full applicability_by_domain dict per
reference and every provenance record.
"""

from __future__ import annotations

from applicability_check import ApplicabilityDimension, ApplicabilityResult, ReferenceDomain
from dataset_split import DatasetSplit, LeakageControl
from field_provenance import FieldProvenance, VerificationStatus
from gold_case import GoldCase, GoldCaseReference, ExpectedOutput, RiskStratum, DecisionDirection
from reference_descriptor import ReferenceDescriptor
from reference_precedence import ReferenceVerdict
from user_roles import ReviewerRole
from validation_unit import ValidationUnit, PreparationSpec, Dose


def _prep_to_dict(prep):
    if prep is None:
        return None
    return {
        "dosage_form": prep.dosage_form, "solvent": prep.solvent,
        "der_min": prep.der_min, "der_max": prep.der_max,
        "source_status": prep.source_status,
    }


def _prep_from_dict(data):
    if data is None:
        return None
    return PreparationSpec(**data)


def _validation_unit_to_dict(unit: ValidationUnit) -> dict:
    dose = None
    if unit.dose is not None:
        dose = {"amount": unit.dose.amount, "unit": unit.dose.unit, "frequency": unit.dose.frequency}
    return {
        "taxon": unit.taxon,
        "taxon_synonyms": list(unit.taxon_synonyms),
        "plant_part": unit.plant_part,
        "preparation": _prep_to_dict(unit.preparation),
        "dose": dose,
        "duration": unit.duration,
        "route_of_administration": unit.route_of_administration,
        "indication": unit.indication,
        "population": unit.population,
        "jurisdiction": unit.jurisdiction,
    }


def _validation_unit_from_dict(data: dict) -> ValidationUnit:
    dose_data = data.get("dose")
    dose = Dose(**dose_data) if dose_data else None
    return ValidationUnit(
        taxon=data.get("taxon"),
        taxon_synonyms=list(data.get("taxon_synonyms") or []),
        plant_part=data.get("plant_part"),
        preparation=_prep_from_dict(data.get("preparation")),
        dose=dose,
        duration=data.get("duration"),
        route_of_administration=data.get("route_of_administration"),
        indication=data.get("indication"),
        population=data.get("population"),
        jurisdiction=data.get("jurisdiction"),
    )


def _reference_to_dict(ref: ReferenceDescriptor) -> dict:
    return {
        "reference_id": ref.reference_id, "source_type": ref.source_type,
        "version": ref.version,
        "document_date": ref.document_date.isoformat() if ref.document_date else None,
        "jurisdiction": ref.jurisdiction, "taxon": ref.taxon,
        "plant_part": ref.plant_part, "preparation": _prep_to_dict(ref.preparation),
        "population": ref.population, "claim_type": ref.claim_type,
        "indication_scope": list(ref.indication_scope), "route_scope": list(ref.route_scope),
        "retracted_or_superseded": ref.retracted_or_superseded,
    }


def _reference_from_dict(data: dict) -> ReferenceDescriptor:
    from datetime import date
    doc_date = data.get("document_date")
    return ReferenceDescriptor(
        reference_id=data.get("reference_id"), source_type=data.get("source_type"),
        version=data.get("version"),
        document_date=date.fromisoformat(doc_date) if doc_date else None,
        jurisdiction=data.get("jurisdiction"), taxon=data.get("taxon"),
        plant_part=data.get("plant_part"), preparation=_prep_from_dict(data.get("preparation")),
        population=data.get("population"), claim_type=data.get("claim_type"),
        indication_scope=list(data.get("indication_scope") or []),
        route_scope=list(data.get("route_scope") or []),
        retracted_or_superseded=bool(data.get("retracted_or_superseded", False)),
    )


def _provenance_to_dict(prov: FieldProvenance) -> dict:
    return {
        "document_id": prov.document_id, "document_version": prov.document_version,
        "locator": prov.locator, "supported_field": prov.supported_field,
        "extraction_date": prov.extraction_date.isoformat(),
        "curator": prov.curator.value if prov.curator else None,
        "verification_status": prov.verification_status.value,
    }


def _provenance_from_dict(data: dict) -> FieldProvenance:
    from datetime import date
    return FieldProvenance(
        document_id=data.get("document_id"), document_version=data.get("document_version"),
        locator=data.get("locator"), supported_field=data.get("supported_field"),
        extraction_date=date.fromisoformat(data["extraction_date"]),
        curator=ReviewerRole(data["curator"]) if data.get("curator") else None,
        verification_status=VerificationStatus(data.get("verification_status", VerificationStatus.UNVERIFIED.value)),
    )


def _applicability_result_to_dict(result: ApplicabilityResult) -> dict:
    return {
        "reference_id": result.reference_id, "domain": result.domain.value,
        "applicable": result.applicable,
        "failed_dimensions": [d.value for d in result.failed_dimensions],
        "detail": dict(result.detail),
    }


def _applicability_result_from_dict(data: dict) -> ApplicabilityResult:
    return ApplicabilityResult(
        reference_id=data.get("reference_id"), domain=ReferenceDomain(data.get("domain")),
        applicable=bool(data.get("applicable", False)),
        failed_dimensions=[ApplicabilityDimension(d) for d in data.get("failed_dimensions", [])],
        detail=dict(data.get("detail") or {}),
    )


def _gold_case_reference_to_dict(gref: GoldCaseReference) -> dict:
    return {
        "reference": _reference_to_dict(gref.reference),
        "applicability_by_domain": {
            domain.value: _applicability_result_to_dict(result)
            for domain, result in gref.applicability_by_domain.items()
        },
        "verdict": (
            {"reference_id": gref.verdict.reference_id, "safety_severity": gref.verdict.safety_severity, "verdict_value": gref.verdict.verdict_value}
            if gref.verdict is not None else None
        ),
        "provenance": [_provenance_to_dict(p) for p in gref.provenance],
    }


def _gold_case_reference_from_dict(data: dict) -> GoldCaseReference:
    verdict_data = data.get("verdict")
    verdict = ReferenceVerdict(**verdict_data) if verdict_data else None
    return GoldCaseReference(
        reference=_reference_from_dict(data["reference"]),
        applicability_by_domain={
            ReferenceDomain(domain_str): _applicability_result_from_dict(result_data)
            for domain_str, result_data in (data.get("applicability_by_domain") or {}).items()
        },
        verdict=verdict,
        provenance=[_provenance_from_dict(p) for p in data.get("provenance", [])],
    )


def _expected_output_to_dict(expected: ExpectedOutput) -> dict:
    return {
        "expected_gate_results": dict(expected.expected_gate_results),
        "expected_decision_direction": expected.expected_decision_direction.value if expected.expected_decision_direction else None,
        "expected_abstention_reason": expected.expected_abstention_reason,
        "expected_warnings": list(expected.expected_warnings),
        "acceptable_decision_class_min": expected.acceptable_decision_class_min,
        "acceptable_decision_class_max": expected.acceptable_decision_class_max,
    }


def _expected_output_from_dict(data: dict) -> ExpectedOutput:
    direction = data.get("expected_decision_direction")
    return ExpectedOutput(
        expected_gate_results=dict(data.get("expected_gate_results") or {}),
        expected_decision_direction=DecisionDirection(direction) if direction else None,
        expected_abstention_reason=data.get("expected_abstention_reason"),
        expected_warnings=list(data.get("expected_warnings") or []),
        acceptable_decision_class_min=data.get("acceptable_decision_class_min"),
        acceptable_decision_class_max=data.get("acceptable_decision_class_max"),
    )


def gold_case_to_dict(case: GoldCase) -> dict:
    """Full, JSON-safe serialization — round-trips exactly through
    gold_case_from_dict() below."""
    return {
        "case_id": case.case_id,
        "validation_unit": _validation_unit_to_dict(case.validation_unit),
        "risk_strata": [s.value for s in case.risk_strata],
        "references": [_gold_case_reference_to_dict(r) for r in case.references],
        "expected_output": _expected_output_to_dict(case.expected_output),
        "correct_abstention_expected": case.correct_abstention_expected,
        "case_provenance": [_provenance_to_dict(p) for p in case.case_provenance],
        "dataset_split": case.dataset_split.value,
        "leakage_control": {
            "engine_output_observed_before_finalization": case.leakage_control.engine_output_observed_before_finalization,
            "observed_at": case.leakage_control.observed_at.isoformat() if case.leakage_control.observed_at else None,
            "case_modified_after_observation": case.leakage_control.case_modified_after_observation,
        },
    }


def gold_case_from_dict(data: dict) -> GoldCase:
    """Inverse of gold_case_to_dict() above. Missing keys degrade to
    defaults, never raise — same backward-compatible convention as
    validation_case_protocol.protocol_from_dict()."""
    from datetime import datetime

    leakage_data = data.get("leakage_control") or {}
    observed_at = leakage_data.get("observed_at")
    leakage_control = LeakageControl(
        engine_output_observed_before_finalization=bool(leakage_data.get("engine_output_observed_before_finalization", False)),
        observed_at=datetime.fromisoformat(observed_at) if observed_at else None,
        case_modified_after_observation=bool(leakage_data.get("case_modified_after_observation", False)),
    )

    return GoldCase(
        case_id=data.get("case_id"),
        validation_unit=_validation_unit_from_dict(data.get("validation_unit") or {}),
        risk_strata=[RiskStratum(s) for s in data.get("risk_strata", [])],
        references=[_gold_case_reference_from_dict(r) for r in data.get("references", [])],
        expected_output=_expected_output_from_dict(data.get("expected_output") or {}),
        correct_abstention_expected=bool(data.get("correct_abstention_expected", False)),
        case_provenance=[_provenance_from_dict(p) for p in data.get("case_provenance", [])],
        dataset_split=DatasetSplit(data.get("dataset_split", DatasetSplit.DEVELOPMENT.value)),
        leakage_control=leakage_control,
    )
