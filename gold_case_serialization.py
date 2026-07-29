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
from assertion_vocabulary import (
    AssertionState, AssertionType, CurationStatus, ExtractionConfidenceLevel,
    GoldCaseKind, SeverityLevel, TransformationType,
)
from dataset_split import DatasetSplit, LeakageControl
from engine_evidence_input import EngineEvidenceInput
from field_provenance import FieldProvenance, VerificationStatus
from gold_case import GoldCase, GoldCaseReference, ExpectedOutput, RiskStratum, DecisionDirection
from reference_claim import ReferenceClaim, NormalizedEvidenceText, ExtractionConfidence
from reference_descriptor import ReferenceDescriptor
from reference_precedence import ReferenceVerdict, ResolutionStatus
from resolved_expected_outcome import ResolvedExpectedOutcome
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


def _extraction_confidence_to_dict(conf):
    if conf is None:
        return None
    return {
        "level": conf.level.value, "basis": conf.basis,
        "extractor_type": conf.extractor_type, "extractor_version": conf.extractor_version,
    }


def _extraction_confidence_from_dict(data):
    if data is None:
        return None
    return ExtractionConfidence(
        level=ExtractionConfidenceLevel(data["level"]), basis=data.get("basis", ""),
        extractor_type=data.get("extractor_type", ""), extractor_version=data.get("extractor_version", ""),
    )


def _normalized_evidence_text_to_dict(text):
    if text is None:
        return None
    return {
        "original_text": text.original_text, "normalized_text": text.normalized_text,
        "transformation_type": text.transformation_type.value,
        "transformation_version": text.transformation_version,
        "source_locator": text.source_locator,
    }


def _normalized_evidence_text_from_dict(data):
    if data is None:
        return None
    return NormalizedEvidenceText(
        original_text=data.get("original_text", ""), normalized_text=data.get("normalized_text", ""),
        transformation_type=TransformationType(data["transformation_type"]),
        transformation_version=data.get("transformation_version", ""),
        source_locator=data.get("source_locator", ""),
    )


def _claim_to_dict(claim: ReferenceClaim) -> dict:
    return {
        "domain": claim.domain.value, "assertion_type": claim.assertion_type.value,
        "subject": claim.subject, "assertion_state": claim.assertion_state.value,
        "severity": claim.severity.value if claim.severity else None,
        "source_reference_id": claim.source_reference_id, "source_locator": claim.source_locator,
        "evidence_text": _normalized_evidence_text_to_dict(claim.evidence_text),
        "extraction_confidence": _extraction_confidence_to_dict(claim.extraction_confidence),
    }


def _claim_from_dict(data: dict) -> ReferenceClaim:
    severity = data.get("severity")
    return ReferenceClaim(
        domain=ReferenceDomain(data["domain"]), assertion_type=AssertionType(data["assertion_type"]),
        subject=data.get("subject", ""), assertion_state=AssertionState(data["assertion_state"]),
        severity=SeverityLevel(severity) if severity else None,
        source_reference_id=data.get("source_reference_id", ""), source_locator=data.get("source_locator", ""),
        evidence_text=_normalized_evidence_text_from_dict(data.get("evidence_text")),
        extraction_confidence=_extraction_confidence_from_dict(data.get("extraction_confidence")),
    )


def _resolved_outcome_to_dict(outcome: ResolvedExpectedOutcome) -> dict:
    return {
        "domain": outcome.domain.value, "subject": outcome.subject,
        "assertion_type": outcome.assertion_type.value,
        "assertion_state": outcome.assertion_state.value if outcome.assertion_state else None,
        "severity": outcome.severity.value if outcome.severity else None,
        "resolution_status": outcome.resolution_status.value,
        "selected_reference_id": outcome.selected_reference_id,
        "conflicting_reference_ids": list(outcome.conflicting_reference_ids),
        "translation_rule_id": outcome.translation_rule_id,
        "translation_rule_version": outcome.translation_rule_version,
        "precedence_policy_version": outcome.precedence_policy_version,
        "applicability_policy_version": outcome.applicability_policy_version,
        "subject_normalization_rule_version": outcome.subject_normalization_rule_version,
    }


def _resolved_outcome_from_dict(data: dict) -> ResolvedExpectedOutcome:
    assertion_state = data.get("assertion_state")
    severity = data.get("severity")
    return ResolvedExpectedOutcome(
        domain=ReferenceDomain(data["domain"]), subject=data.get("subject", ""),
        assertion_type=AssertionType(data["assertion_type"]),
        assertion_state=AssertionState(assertion_state) if assertion_state else None,
        severity=SeverityLevel(severity) if severity else None,
        resolution_status=ResolutionStatus(data.get("resolution_status", ResolutionStatus.NO_APPLICABLE_REFERENCE.value)),
        selected_reference_id=data.get("selected_reference_id"),
        conflicting_reference_ids=list(data.get("conflicting_reference_ids") or []),
        translation_rule_id=data.get("translation_rule_id", ""),
        translation_rule_version=data.get("translation_rule_version", ""),
        precedence_policy_version=data.get("precedence_policy_version", ""),
        applicability_policy_version=data.get("applicability_policy_version", ""),
        subject_normalization_rule_version=data.get("subject_normalization_rule_version", ""),
    )


def _engine_evidence_to_dict(item: EngineEvidenceInput) -> dict:
    return {
        "scientific_name": item.scientific_name, "target_indication": item.target_indication,
        "notes": item.notes, "compound_activity_targets": list(item.compound_activity_targets),
    }


def _engine_evidence_from_dict(data: dict) -> EngineEvidenceInput:
    return EngineEvidenceInput(
        scientific_name=data.get("scientific_name", ""), target_indication=data.get("target_indication", ""),
        notes=data.get("notes", ""), compound_activity_targets=tuple(data.get("compound_activity_targets") or ()),
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
        "claims": [_claim_to_dict(c) for c in gref.claims],
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
        claims=[_claim_from_dict(c) for c in data.get("claims", [])],
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
        "kind": case.kind.value,
        "curation_status": case.curation_status.value,
        "resolved_outcomes": [_resolved_outcome_to_dict(o) for o in case.resolved_outcomes],
        "engine_evidence": [_engine_evidence_to_dict(e) for e in case.engine_evidence],
        "locked": case.locked,
        "dataset_snapshot_hash": case.dataset_snapshot_hash,
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
        kind=GoldCaseKind(data.get("kind", GoldCaseKind.REFERENCE_GROUNDED.value)),
        curation_status=CurationStatus(data.get("curation_status", CurationStatus.DRAFT.value)),
        resolved_outcomes=[_resolved_outcome_from_dict(o) for o in data.get("resolved_outcomes", [])],
        engine_evidence=[_engine_evidence_from_dict(e) for e in data.get("engine_evidence", [])],
        locked=bool(data.get("locked", False)),
        dataset_snapshot_hash=data.get("dataset_snapshot_hash"),
    )
