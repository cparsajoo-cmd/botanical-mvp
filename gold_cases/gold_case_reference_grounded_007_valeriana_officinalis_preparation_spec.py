"""
Gold Case 007 — Valeriana officinalis L., radix, PREPARATION_SPEC Domain

ReferenceDomain: PREPARATION_SPEC
AssertionType: PREPARATION_SPECIFICATION
AssertionState: PRESENT
ResolutionStatus: SELECTED (single EMA_HMPC reference)

SCOPE: validates the repository's first PREPARATION_SPEC domain case,
verifying that an authoritative EMA/HMPC specification of a herbal
preparation (dry extract, DER 3-7.4:1, extraction solvent ethanol 40-70%
(V/V)) can be extracted, resolved, and locked without semantic stretching.

CANDIDATE TAXON: Valeriana officinalis L.
PLANT PART: radix (root)
PREPARATION: dry extract, DER 3-7.4:1, extraction solvent ethanol 40-70% (V/V)
CLAIM TYPE: well-established use (Article 10a, Directive 2001/83/EC)
JURISDICTION: EU
GOVERNING SOURCE: EMA/HMPC Assessment Report on Valeriana officinalis L.,
radix (EMA/HMPC/150846/2015, final, adopted 2 February 2016)

WHY THIS CASE IS SUITABLE FOR A PREPARATION_SPEC VALIDATION
The EMA/HMPC monograph explicitly specifies, in the "Well-established use"
section, a single, unambiguous preparation: dry extract with a bounded DER
range (3-7.4:1) and a bounded extraction solvent range (ethanol 40-70%
(V/V)). This is a direct, affirmative regulatory assertion about what THE
herbal preparation is — exactly the kind of claim PREPARATION_SPEC domain
is designed to capture. No inference, no omission-reading, no fragmented
national determinations: one authoritative source, one preparation, one
clear specification.

LEAKAGE RULE 9.1: This file constructs and resolves the reference-truth
(Ground Truth) layer ONLY. No EngineEvidenceInput is attached here. Engine
evidence, execution, and locking happen in a separate file (case_007_engine_
evidence_run.py), following the file-separation convention Cases 003/006
already established.

validation_unit.indication: None (PREPARATION_SPEC claims are not indication-
dependent; the specification is identical regardless of which indication the
preparation is used for).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

from applicability_check import ApplicabilityResult, ReferenceDomain
from assertion_vocabulary import AssertionState, AssertionType, ExtractionConfidenceLevel
from gold_case import GoldCase, GoldCaseReference, RiskStratum
from reference_claim import ExtractionConfidence, NormalizedEvidenceText, ReferenceClaim
from reference_descriptor import ReferenceDescriptor
from resolved_expected_outcome import resolve_expected_outcomes
from validation_unit import PreparationSpec, ValidationUnit


# ===== Preparation (locked, identical in both ReferenceDescriptor and ValidationUnit) =====

_PREPARATION_LOCKED = PreparationSpec(
    dosage_form="Extract",
    der_min=3.0,
    der_max=7.4,
    solvent="ethanol 40-70% (V/V)",
    source_status=None,  # Locked per EMA spec; no Traditional Use (TU) dimension.
)


# ===== ValidationUnit =====

def _build_validation_unit() -> ValidationUnit:
    """The ONE PreparationSpec is locked identically in both the
    ReferenceDescriptor and the ValidationUnit — no inconsistency ever
    possible. Plant part is *radix* (root) only; no leaf/herb confusion.
    Jurisdiction is EU (EMA/HMPC source). indication is None — PREPARATION_SPEC
    claims are jurisdiction/preparation-specific, not indication-specific."""
    return ValidationUnit(
        taxon="Valeriana officinalis L.",
        plant_part="radix",
        preparation=_PREPARATION_LOCKED,
        population="Adults",
        route_of_administration="Oral",
        jurisdiction="EU",
        # LEFT UNSET (None) — PREPARATION_SPEC claims do not depend on indication.
        indication=None,
    )


# ===== ReferenceDescriptor =====

def _build_reference_descriptor() -> ReferenceDescriptor:
    """Governing source: EMA/HMPC Assessment Report on Valeriana officinalis
    L., radix. Published as EMA/HMPC/150846/2015, adopted 2 February 2016.
    Source type: EMA_HMPC (highest rank for PREPARATION_SPEC per
    reference_precedence.py). No same-rank competing source found.
    
    Scope fields are set to match the ValidationUnit exactly — applicability
    check compares these against the case's preparation/taxon/plant_part/etc.
    """
    return ReferenceDescriptor(
        reference_id="EMA_HMPC_150846_2015_valeriana_officinalis_radix",
        source_type="EMA_HMPC",
        version="final (adopted 2 February 2016)",
        document_date=date(2016, 2, 2),
        jurisdiction="EU",
        taxon="Valeriana officinalis L.",
        plant_part="radix",
        preparation=_PREPARATION_LOCKED,
        population="Adults",
        claim_type="well-established-use",
        # Scope: well-established use only — preparation is identical across
        # all indications within that scope (restlessness, nervousness, sleep
        # aid). No need to name each one here.
        indication_scope=[],
        route_scope=["Oral"],
        retracted_or_superseded=False,
    )


# ===== ReferenceClaim =====

def _build_reference_claim() -> ReferenceClaim:
    """Verbatim from EMA/HMPC/150846/2015, Assessment Report, section
    'Herbal preparation(s) — Well-established use':

    'Dry extract (DER 3-7.4:1), extraction solvent: ethanol 40-70% (V/V)'

    Source locator: page listing the well-established-use preparations.
    transformation_type: VERBATIM (no summarization, direct quote from the
    regulatory document listing authorized preparations).
    """
    return ReferenceClaim(
        domain=ReferenceDomain.PREPARATION_SPEC,
        assertion_type=AssertionType.PREPARATION_SPECIFICATION,
        subject="dry extract, DER 3-7.4:1, extraction solvent ethanol 40-70% (V/V)",
        assertion_state=AssertionState.PRESENT,
        severity=None,  # PREPARATION_SPEC claims do not carry severity.
        source_reference_id="EMA_HMPC_150846_2015_valeriana_officinalis_radix",
        source_locator=(
            "EMA/HMPC/150846/2015, Assessment Report on Valeriana officinalis L., "
            "radix, section 'Herbal preparation(s) — Well-established use'"
        ),
        evidence_text=NormalizedEvidenceText(
            original_text=(
                "Dry extract (DER 3-7.4:1), extraction solvent: ethanol 40-70% (V/V)"
            ),
            normalized_text=(
                "Dry extract (DER 3-7.4:1), extraction solvent: ethanol 40-70% (V/V)"
            ),
            transformation_type="VERBATIM",
            transformation_version="v1",
            source_locator=(
                "EMA/HMPC/150846/2015, Assessment Report, section "
                "'Herbal preparation(s) — Well-established use'"
            ),
        ),
        extraction_confidence=ExtractionConfidence(
            level=ExtractionConfidenceLevel.HIGH,
            basis="Verbatim excerpt from EMA/HMPC/150846/2015, final assessment report, section 'Herbal preparation(s) — Well-established use'",
            extractor_type="human-curator",
            extractor_version="v1",
        ),
    )


# ===== GoldCase Builder =====

def build_gold_case_refgrounded_007_valeriana_officinalis_preparation_spec() -> GoldCase:
    """Builds the case through resolved_outcomes only. Returns an UNLOCKED
    GoldCase (locked=False); lock_gold_case() is intentionally never called
    here — the same Leakage-Rule-9.1 file-separation convention Cases 003/006
    established. EngineEvidenceInput collection, execution, gate-agreement
    verification, and locking all happen in the separate
    case_007_engine_evidence_run.py, never in this file. validation_unit.
    indication is left at its default (None) — PREPARATION_SPEC is not
    indication-dependent. expected_output.expected_decision_direction is
    left at its default (None) — PREPARATION_SPEC is not in
    agreement_eligibility._ELIGIBLE_DOMAINS, so there is nothing for this
    case to derive a whole-case direction from under current protocol policy
    (§14.1).
    """
    unit = _build_validation_unit()
    reference_descriptor = _build_reference_descriptor()
    reference_claim = _build_reference_claim()

    from applicability_check import check_applicability
    
    reference = GoldCaseReference(
        reference=reference_descriptor,
        claims=[reference_claim],
    )
    reference.applicability_by_domain[ReferenceDomain.PREPARATION_SPEC] = check_applicability(
        reference_descriptor, unit, ReferenceDomain.PREPARATION_SPEC
    )

    case = GoldCase(
        case_id="refgrounded_007_valeriana_officinalis_preparation_spec",
        validation_unit=unit,
        references=[reference],
        engine_evidence=[],
        engine_evidence_origin=None,
        risk_strata=[],  # No SAFETY/INTERACTION risk stratification for PREPARATION_SPEC.
        kind="REFERENCE_GROUNDED",
        curation_status="REFERENCE_CURATED",
        locked=False,
    )

    # Resolve expected outcomes from the claim via reference_precedence.py.
    case = replace(case, resolved_outcomes=resolve_expected_outcomes(case))

    return case


if __name__ == "__main__":
    case = build_gold_case_refgrounded_007_valeriana_officinalis_preparation_spec()

    print(f"case_id: {case.case_id}")
    print(f"locked: {case.locked}")
    print(f"validation_unit.indication: {case.validation_unit.indication} (PREPARATION_SPEC-independent)")
    print(f"validation_unit.plant_part: {case.validation_unit.plant_part}")
    print(f"validation_unit.preparation: DER {case.validation_unit.preparation.der_min}-{case.validation_unit.preparation.der_max}, {case.validation_unit.preparation.solvent}")
    print()

    for outcome in case.resolved_outcomes:
        print(
            f"domain={outcome.domain!r} assertion_type={outcome.assertion_type!r} "
            f"resolution_status={outcome.resolution_status!r} "
            f"selected_reference_id={outcome.selected_reference_id!r}"
        )
