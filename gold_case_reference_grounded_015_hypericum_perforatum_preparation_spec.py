"""
Gold Case 015 — Hypericum perforatum L., herba, PREPARATION_SPEC.

Ground Truth is restricted to the preparation specification explicitly stated
in the final EMA/HMPC European Union herbal monograph, revision 1:

    Dry extract (DER 3-7:1), extraction solvent methanol 80% (V/V).

Governing source: EMA/HMPC/7695/2021, final European Union herbal monograph
on Hypericum perforatum L., herba, revision 1, first published 22 February
2023. The claim is preparation-specific only; no efficacy, safety, dose, or
engine-derived conclusion is imported into this file.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

from applicability_check import ReferenceDomain, check_applicability
from assertion_vocabulary import AssertionState, AssertionType, ExtractionConfidenceLevel
from gold_case import GoldCase, GoldCaseReference
from reference_claim import ExtractionConfidence, NormalizedEvidenceText, ReferenceClaim
from reference_descriptor import ReferenceDescriptor
from resolved_expected_outcome import resolve_expected_outcomes
from validation_unit import PreparationSpec, ValidationUnit


REFERENCE_ID = "EMA_HMPC_7695_2021_hypericum_perforatum_preparation_a"
SOURCE_DOCUMENT = "EMA/HMPC/7695/2021"
SOURCE_TITLE = (
    "European Union herbal monograph on Hypericum perforatum L., herba "
    "(well-established and traditional use), Revision 1"
)
SOURCE_LOCATOR = (
    "EMA/HMPC/7695/2021, section 2 'Qualitative and quantitative composition', "
    "well-established-use herbal preparation a, page 3/14"
)
PREPARATION_TEXT = (
    "Dry extract (DER 3-7:1), extraction solvent methanol 80% (V/V)"
)

_PREPARATION = PreparationSpec(
    dosage_form="Dry extract",
    solvent="methanol 80% (V/V)",
    der_min=3.0,
    der_max=7.0,
    source_status="concentrated",
)


def _build_validation_unit() -> ValidationUnit:
    return ValidationUnit(
        taxon="Hypericum perforatum L.",
        plant_part="herba",
        preparation=_PREPARATION,
        population="Adults and elderly",
        route_of_administration="Oral",
        indication=None,
        jurisdiction="EU",
    )


def _build_reference_descriptor() -> ReferenceDescriptor:
    return ReferenceDescriptor(
        reference_id=REFERENCE_ID,
        source_type="EMA_HMPC",
        version="Revision 1, final",
        document_date=date(2023, 2, 22),
        jurisdiction="EU",
        taxon="Hypericum perforatum L.",
        plant_part="herba",
        preparation=_PREPARATION,
        population="Adults and elderly",
        claim_type="well-established-use",
        indication_scope=[],
        route_scope=["Oral"],
        retracted_or_superseded=False,
    )


def _build_reference_claim() -> ReferenceClaim:
    return ReferenceClaim(
        domain=ReferenceDomain.PREPARATION_SPEC,
        assertion_type=AssertionType.PREPARATION_SPECIFICATION,
        subject=PREPARATION_TEXT,
        assertion_state=AssertionState.PRESENT,
        severity=None,
        source_reference_id=REFERENCE_ID,
        source_locator=SOURCE_LOCATOR,
        evidence_text=NormalizedEvidenceText(
            original_text=PREPARATION_TEXT,
            normalized_text=PREPARATION_TEXT,
            transformation_type="VERBATIM",
            transformation_version="v1",
            source_locator=SOURCE_LOCATOR,
        ),
        extraction_confidence=ExtractionConfidence(
            level=ExtractionConfidenceLevel.HIGH,
            basis=(
                "Exact preparation specification transcribed from the final "
                "EMA/HMPC monograph, section 2, well-established-use preparation a."
            ),
            extractor_type="human-curator",
            extractor_version="v1",
        ),
    )


def build_gold_case_refgrounded_015_hypericum_perforatum_preparation_spec() -> GoldCase:
    unit = _build_validation_unit()
    descriptor = _build_reference_descriptor()
    claim = _build_reference_claim()

    reference = GoldCaseReference(reference=descriptor, claims=[claim])
    reference.applicability_by_domain[ReferenceDomain.PREPARATION_SPEC] = check_applicability(
        descriptor, unit, ReferenceDomain.PREPARATION_SPEC
    )

    case = GoldCase(
        case_id="refgrounded_015_hypericum_perforatum_preparation_spec",
        validation_unit=unit,
        references=[reference],
        engine_evidence=[],
        engine_evidence_origin=None,
        risk_strata=[],
        kind="REFERENCE_GROUNDED",
        curation_status="REFERENCE_CURATED",
        locked=False,
    )
    return replace(case, resolved_outcomes=resolve_expected_outcomes(case))


if __name__ == "__main__":
    case = build_gold_case_refgrounded_015_hypericum_perforatum_preparation_spec()
    print(f"case_id: {case.case_id}")
    print(f"taxon: {case.validation_unit.taxon}")
    print(f"plant_part: {case.validation_unit.plant_part}")
    print(f"preparation: {PREPARATION_TEXT}")
    print(f"locked: {case.locked}")
    for outcome in case.resolved_outcomes:
        print(
            f"domain={outcome.domain!r} assertion_type={outcome.assertion_type!r} "
            f"assertion_state={outcome.assertion_state!r} "
            f"resolution_status={outcome.resolution_status!r} "
            f"selected_reference_id={outcome.selected_reference_id!r}"
        )
