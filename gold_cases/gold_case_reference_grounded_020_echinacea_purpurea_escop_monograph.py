"""Gold Case 020 — Echinacea purpurea (L.) Moench, ESCOP_MONOGRAPH coverage.

Coverage objective
------------------
Close the real ESCOP governing-source gap identified by the Gold Corpus
Coverage Audit without changing production logic or source-precedence rules.

Governing source
----------------
European Scientific Cooperative on Phytotherapy (ESCOP). Echinaceae purpureae
herba (Purple Coneflower Herb). Online monograph summary. Published 2021.

The public ESCOP monograph page explicitly defines the herbal drug as the
flowering aerial parts of Echinacea purpurea (L.) Moench and explicitly lists
recurrent infections of the upper respiratory tract (common colds) among the
therapeutic indications.

This case deliberately does not invent one preparation, dose, route, duration,
or population because those details are not established by the public source
text used to ground this case.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date

from applicability_check import ReferenceDomain, check_applicability
from assertion_vocabulary import (
    AssertionState,
    AssertionType,
    CurationStatus,
    ExtractionConfidenceLevel,
    GoldCaseKind,
    TransformationType,
)
from gold_case import GoldCase, GoldCaseReference
from reference_claim import ExtractionConfidence, NormalizedEvidenceText, ReferenceClaim
from reference_descriptor import ReferenceDescriptor
from resolved_expected_outcome import resolve_expected_outcomes
from validation_unit import ValidationUnit

_REFERENCE_ID = "ESCOP_2021_ECHINACEAE_PURPUREAE_HERBA"
_CITATION = (
    "European Scientific Cooperative on Phytotherapy (ESCOP). "
    "Echinaceae purpureae herba (Purple Coneflower Herb). Online series. "
    "Exeter: ESCOP; 2021."
)
_SOURCE_URL = "https://www.escop.com/downloads/echinaceae-purpureae-herba-purple-coneflower-herb/"
_SUBJECT = "recurrent infections of the upper respiratory tract (common colds)"
_VERBATIM = (
    "The therapeutic indications are recurrent infections of the upper respiratory tract "
    "(common colds) and of the urogenital tract."
)


def _build_unit() -> ValidationUnit:
    return ValidationUnit(
        taxon="Echinacea purpurea (L.) Moench",
        taxon_synonyms=[],
        plant_part="flowering aerial parts",
        preparation=None,
        dose=None,
        duration=None,
        route_of_administration=None,
        indication=_SUBJECT,
        population=None,
        jurisdiction=None,
    )


def _build_reference() -> ReferenceDescriptor:
    return ReferenceDescriptor(
        reference_id=_REFERENCE_ID,
        source_type="ESCOP_MONOGRAPH",
        version=_CITATION,
        document_date=date(2021, 6, 9),
        jurisdiction=None,
        taxon="Echinacea purpurea (L.) Moench",
        plant_part="flowering aerial parts",
        preparation=None,
        population=None,
        claim_type=None,
        indication_scope=[_SUBJECT],
        route_scope=[],
        retracted_or_superseded=False,
    )


def _build_claim() -> ReferenceClaim:
    locator = f"ESCOP public monograph summary page, therapeutic indications section: {_SOURCE_URL}"
    return ReferenceClaim(
        domain=ReferenceDomain.INDICATION_EVIDENCE,
        assertion_type=AssertionType.SUPPORTS_INDICATION,
        subject=_SUBJECT,
        assertion_state=AssertionState.PRESENT,
        severity=None,
        source_reference_id=_REFERENCE_ID,
        source_locator=locator,
        evidence_text=NormalizedEvidenceText(
            original_text=_VERBATIM,
            normalized_text=_SUBJECT,
            transformation_type=TransformationType.VERBATIM,
            transformation_version="case020-escop-verbatim-v1",
            source_locator=locator,
        ),
        extraction_confidence=ExtractionConfidence(
            level=ExtractionConfidenceLevel.HIGH,
            basis=(
                "The public ESCOP monograph page directly states both the botanical drug "
                "definition and the therapeutic indication used by this case. No paywalled "
                "dose or preparation detail is inferred."
            ),
            extractor_type="human_curator",
            extractor_version="case020-escop-curation-v1",
        ),
    )


def build_gold_case_refgrounded_020_echinacea_purpurea_escop_monograph() -> GoldCase:
    unit = _build_unit()
    descriptor = _build_reference()
    gref = GoldCaseReference(reference=descriptor, claims=[_build_claim()])
    gref.applicability_by_domain[ReferenceDomain.INDICATION_EVIDENCE] = check_applicability(
        descriptor, unit, ReferenceDomain.INDICATION_EVIDENCE
    )
    case = GoldCase(
        case_id="refgrounded_020_echinacea_purpurea_escop_monograph",
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
    c = build_gold_case_refgrounded_020_echinacea_purpurea_escop_monograph()
    print(c.case_id)
    for o in c.resolved_outcomes:
        print(o.domain.value, o.assertion_type.value, o.assertion_state, o.resolution_status.value)
