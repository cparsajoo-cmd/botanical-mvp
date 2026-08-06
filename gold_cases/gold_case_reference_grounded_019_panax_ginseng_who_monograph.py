"""Gold Case 019 — Panax ginseng C.A. Meyer, WHO_MONOGRAPH coverage.

Coverage objective
------------------
Close the real WHO source gap identified by the Gold Corpus Coverage Audit
without changing production logic or adding a source-type rule.

Governing source
----------------
World Health Organization. WHO monographs on selected medicinal plants,
Volume 1. Geneva: WHO; 1999. Monograph: Radix Ginseng, pp. 168-177.
ISBN 9241545178.

The WHO monograph defines Radix Ginseng as the dried root of Panax ginseng
C.A. Meyer and, under "Uses supported by clinical data", describes its use
as a prophylactic/restorative agent for weakness, exhaustion, tiredness,
loss of concentration and convalescence.

This case deliberately does not invent one preparation, dose, route, or
population because the WHO monograph describes multiple dosage forms and
clinical contexts rather than one preparation-level intervention.
"""
from __future__ import annotations
from dataclasses import replace

from applicability_check import ReferenceDomain, check_applicability
from assertion_vocabulary import (
    AssertionState, AssertionType, CurationStatus,
    ExtractionConfidenceLevel, GoldCaseKind, TransformationType,
)
from gold_case import GoldCase, GoldCaseReference
from reference_claim import ExtractionConfidence, NormalizedEvidenceText, ReferenceClaim
from reference_descriptor import ReferenceDescriptor
from resolved_expected_outcome import resolve_expected_outcomes
from validation_unit import ValidationUnit

_REFERENCE_ID = "WHO_MONOGRAPHS_VOL1_1999_RADIX_GINSENG"
_CITATION = (
    "World Health Organization. WHO monographs on selected medicinal plants. "
    "Volume 1. Geneva: World Health Organization; 1999. Radix Ginseng, pp.168-177. "
    "ISBN 9241545178."
)
_SHORT_SOURCE_EXCERPT = (
    "Radix Ginseng is used as a prophylactic and restorative agent for enhancement of mental and physical capacities."
)
_SUBJECT = "weakness, exhaustion, tiredness and loss of concentration"


def _build_unit() -> ValidationUnit:
    return ValidationUnit(
        taxon="Panax ginseng C.A. Meyer",
        taxon_synonyms=["Panax schinseng Nees"],
        plant_part="root",
        preparation=None,
        dose=None,
        duration=None,
        route_of_administration=None,
        indication=_SUBJECT,
        population=None,
        jurisdiction="International",
    )


def _build_reference() -> ReferenceDescriptor:
    return ReferenceDescriptor(
        reference_id=_REFERENCE_ID,
        source_type="WHO_MONOGRAPH",
        version=_CITATION,
        document_date=None,
        jurisdiction=None,
        taxon="Panax ginseng C.A. Meyer",
        plant_part="root",
        preparation=None,
        population=None,
        claim_type=None,
        indication_scope=[_SUBJECT],
        route_scope=[],
        retracted_or_superseded=False,
    )


def _build_claim() -> ReferenceClaim:
    return ReferenceClaim(
        domain=ReferenceDomain.INDICATION_EVIDENCE,
        assertion_type=AssertionType.SUPPORTS_INDICATION,
        subject=_SUBJECT,
        assertion_state=AssertionState.PRESENT,
        severity=None,
        source_reference_id=_REFERENCE_ID,
        source_locator=(
            "WHO monographs on selected medicinal plants, Vol. 1, Radix Ginseng: "
            "Definition p.168; 'Uses supported by clinical data' p.172"
        ),
        evidence_text=NormalizedEvidenceText(
            original_text=_SHORT_SOURCE_EXCERPT,
            normalized_text=(
                "WHO supports Radix Ginseng as a prophylactic/restorative agent in "
                "weakness, exhaustion, tiredness and loss of concentration."
            ),
            transformation_type=TransformationType.NORMALIZED_TERMINOLOGY,
            transformation_version="case019-who-normalization-v1",
            source_locator="WHO Monographs Vol.1, Radix Ginseng, p.172",
        ),
        extraction_confidence=ExtractionConfidence(
            level=ExtractionConfidenceLevel.HIGH,
            basis=(
                "Direct WHO monograph wording under 'Uses supported by clinical data'; "
                "botanical identity and root part are explicitly defined in the same monograph."
            ),
            extractor_type="human_curator",
            extractor_version="case019-who-curation-v1",
        ),
    )


def build_gold_case_refgrounded_019_panax_ginseng_who_monograph() -> GoldCase:
    unit = _build_unit()
    descriptor = _build_reference()
    gref = GoldCaseReference(reference=descriptor, claims=[_build_claim()])
    gref.applicability_by_domain[ReferenceDomain.INDICATION_EVIDENCE] = check_applicability(
        descriptor, unit, ReferenceDomain.INDICATION_EVIDENCE
    )
    case = GoldCase(
        case_id="refgrounded_019_panax_ginseng_who_monograph",
        validation_unit=unit,
        references=[gref],
        engine_evidence=[],
        engine_evidence_origin=None,
        risk_strata=[],
        kind=GoldCaseKind.REFERENCE_GROUNDED,
        curation_status=CurationStatus.REFERENCE_CURATED,
        locked=False,
    )
    return replace(case, resolved_outcomes=resolve_expected_outcomes(case))


if __name__ == "__main__":
    c = build_gold_case_refgrounded_019_panax_ginseng_who_monograph()
    print(c.case_id)
    for o in c.resolved_outcomes:
        print(o.domain.value, o.assertion_type.value, o.assertion_state, o.resolution_status.value)
