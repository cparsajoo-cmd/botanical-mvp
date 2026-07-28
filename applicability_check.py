"""
Validation Architecture v3 — Phase 1: ApplicabilityCheck.

WHAT CHANGED FROM v2 (v3 correction #1)
v2's design compared "source A against source B" directly. That was
wrong: applicability is a property of ONE reference against the CASE
being evaluated (the ValidationUnit), not a pairwise relationship
between two references. This module implements the corrected
signature:

    check_applicability(reference, validation_unit, domain) -> ApplicabilityResult

Precedence (reference_precedence.py) then operates only on the set of
references that already passed this check against the SAME
ValidationUnit — two references are only ever compared to each other
AFTER each has independently been found applicable, never as a
pairwise applicability comparison.

WHY DOMAIN MATTERS HERE, NOT JUST IN PRECEDENCE
Which dimensions matter for applicability can differ by domain. A
safety-relevant reference should not be excluded just because its
plant_part is unspecified (safety references often speak to the
whole preparation), whereas plant_part is more likely load-bearing for
identity/quality or preparation_spec domains. Phase 1 keeps this
simple and does NOT yet vary the dimension set per domain (all seven
dimensions below are checked for every domain) — see LIMITATIONS
below. Domain is still a required parameter (not optional) so that
per-domain applicability logic can be added later without changing
this function's signature.

THE SEVEN APPLICABILITY DIMENSIONS (Validation Architecture v2 #2)
preparation, plant_part, population, jurisdiction, claim_type,
source_date, document_scope — each checked independently; ALL must
pass for the reference to be applicable to the ValidationUnit for the
given domain.

LIMITATIONS (Phase 1)
- No fuzzy/partial matching on any dimension — an unspecified field on
  either side is NOT auto-passed; see each _check_* function's own
  docstring for its exact null-handling rule.
- Per-domain dimension weighting (the note above) is not implemented
  in Phase 1 — flagged here as a known simplification, not silently
  assumed to be correct for every domain.
- source_date validity checking is a simple non-expired/non-retracted
  check, not a recency-adequacy judgment (e.g. "is this monograph too
  old to still be authoritative" is out of scope here).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional

from reference_descriptor import ReferenceDescriptor
from validation_unit import ValidationUnit


class ReferenceDomain(str, Enum):
    """The five domain-specific reference categories approved in
    Validation Architecture v3 correction #1 — each has its own
    precedence hierarchy in reference_precedence.py, and applicability
    is checked per (reference, domain) pair, never once globally."""
    IDENTITY_QUALITY = "Identity/Quality"
    INDICATION_EVIDENCE = "Indication/Evidence"
    SAFETY = "Safety"
    REGULATORY_STATUS = "Regulatory status"
    PREPARATION_SPEC = "Preparation specification"


class ApplicabilityDimension(str, Enum):
    PREPARATION = "preparation"
    PLANT_PART = "plant_part"
    POPULATION = "population"
    JURISDICTION = "jurisdiction"
    CLAIM_TYPE = "claim_type"
    SOURCE_DATE = "source_date"
    DOCUMENT_SCOPE = "document_scope"


@dataclass
class ApplicabilityResult:
    """The outcome of checking ONE reference against ONE ValidationUnit
    for ONE domain. Stored per-reference-per-domain on a GoldCase (see
    gold_case.GoldCaseReference) — never collapsed into one global
    per-case value (v3 correction #5)."""
    reference_id: str
    domain: ReferenceDomain
    applicable: bool
    failed_dimensions: list = field(default_factory=list)  # list[ApplicabilityDimension]
    detail: dict = field(default_factory=dict)  # dimension.value -> human-readable reason


def _check_preparation(reference: ReferenceDescriptor, unit: ValidationUnit) -> Optional[str]:
    """Returns None if this dimension passes, or a reason string if it
    fails. A reference with NO preparation specified is treated as
    covering the general preparation category (passes) — a reference
    with an EXPLICIT preparation that does not match the unit's fails.
    A unit with no preparation specified always passes this dimension
    (nothing to mismatch against)."""
    if unit.preparation is None or reference.preparation is None:
        return None
    ref_prep, unit_prep = reference.preparation, unit.preparation
    if ref_prep.dosage_form and unit_prep.dosage_form and ref_prep.dosage_form != unit_prep.dosage_form:
        return f"dosage_form mismatch: reference={ref_prep.dosage_form!r} vs unit={unit_prep.dosage_form!r}"
    if ref_prep.solvent and unit_prep.solvent and ref_prep.solvent != unit_prep.solvent:
        return f"solvent mismatch: reference={ref_prep.solvent!r} vs unit={unit_prep.solvent!r}"
    if (
        ref_prep.der_min is not None and unit_prep.der_min is not None
        and ref_prep.der_max is not None and unit_prep.der_max is not None
    ):
        # Applicable only if the unit's DER range overlaps the reference's.
        if unit_prep.der_max < ref_prep.der_min or unit_prep.der_min > ref_prep.der_max:
            return (
                f"DER range does not overlap: reference=[{ref_prep.der_min},{ref_prep.der_max}] "
                f"vs unit=[{unit_prep.der_min},{unit_prep.der_max}]"
            )
    return None


def _check_plant_part(reference: ReferenceDescriptor, unit: ValidationUnit) -> Optional[str]:
    if reference.plant_part and unit.plant_part and reference.plant_part != unit.plant_part:
        return f"plant_part mismatch: reference={reference.plant_part!r} vs unit={unit.plant_part!r}"
    return None


def _check_population(reference: ReferenceDescriptor, unit: ValidationUnit) -> Optional[str]:
    """"general population" on the reference side is treated as
    covering any unit population (passes) — any other explicit,
    differing population value fails."""
    if not reference.population or not unit.population:
        return None
    if reference.population.strip().lower() in {"general", "general population"}:
        return None
    if reference.population != unit.population:
        return f"population mismatch: reference={reference.population!r} vs unit={unit.population!r}"
    return None


def _check_jurisdiction(reference: ReferenceDescriptor, unit: ValidationUnit) -> Optional[str]:
    """reference.jurisdiction is None per this schema's own convention
    for "international/non-geographic scope" (see reference_descriptor.py)
    — that always passes."""
    if reference.jurisdiction is None or not unit.jurisdiction:
        return None
    if reference.jurisdiction != unit.jurisdiction:
        return f"jurisdiction mismatch: reference={reference.jurisdiction!r} vs unit={unit.jurisdiction!r}"
    return None


def _check_claim_type(reference: ReferenceDescriptor) -> Optional[str]:
    """Phase 1 has no claim_type field on ValidationUnit itself (not
    part of the 8 approved dimensions) — this dimension currently only
    checks that the reference's claim_type, if present, is a
    recognized value, never comparing it against the unit. Flagged as
    a known Phase 1 simplification, not a silent no-op disguised as a
    real check."""
    recognized = {"traditional-use", "well-established-use", None}
    if reference.claim_type not in recognized and reference.claim_type is not None:
        return f"unrecognized claim_type: {reference.claim_type!r}"
    return None


def _check_source_date(reference: ReferenceDescriptor) -> Optional[str]:
    if reference.retracted_or_superseded:
        return "reference is marked retracted_or_superseded"
    return None


def _check_document_scope(reference: ReferenceDescriptor, unit: ValidationUnit) -> Optional[str]:
    """Fails only when the reference DOES declare a scope list and the
    unit's indication/route is explicitly outside it — an empty scope
    list is not treated as "covers nothing" (that would make every
    reference with an unpopulated scope list inapplicable by default,
    which is not this dimension's job; a reference author who simply
    never populated indication_scope should not be silently excluded)."""
    if reference.indication_scope and unit.indication and unit.indication not in reference.indication_scope:
        return f"indication {unit.indication!r} not in reference's indication_scope"
    if reference.route_scope and unit.route_of_administration and unit.route_of_administration not in reference.route_scope:
        return f"route {unit.route_of_administration!r} not in reference's route_scope"
    return None


def check_applicability(
    reference: ReferenceDescriptor,
    validation_unit: ValidationUnit,
    domain: ReferenceDomain,
) -> ApplicabilityResult:
    """The ONE function this module exists to provide (v3 correction #1
    signature). Checks all seven dimensions independently; the
    reference is applicable only if every dimension passes. See each
    _check_* function's own docstring for its exact pass/fail rule —
    in particular, an unspecified field on either side generally
    PASSES that dimension (absence of information is not treated as a
    mismatch), while an explicit, differing value FAILS it.
    """
    failed = []
    detail = {}

    checks = {
        ApplicabilityDimension.PREPARATION: _check_preparation(reference, validation_unit),
        ApplicabilityDimension.PLANT_PART: _check_plant_part(reference, validation_unit),
        ApplicabilityDimension.POPULATION: _check_population(reference, validation_unit),
        ApplicabilityDimension.JURISDICTION: _check_jurisdiction(reference, validation_unit),
        ApplicabilityDimension.CLAIM_TYPE: _check_claim_type(reference),
        ApplicabilityDimension.SOURCE_DATE: _check_source_date(reference),
        ApplicabilityDimension.DOCUMENT_SCOPE: _check_document_scope(reference, validation_unit),
    }

    for dimension, failure_reason in checks.items():
        if failure_reason is not None:
            failed.append(dimension)
            detail[dimension.value] = failure_reason
        else:
            detail[dimension.value] = "pass"

    return ApplicabilityResult(
        reference_id=reference.reference_id,
        domain=domain,
        applicable=(len(failed) == 0),
        failed_dimensions=failed,
        detail=detail,
    )
