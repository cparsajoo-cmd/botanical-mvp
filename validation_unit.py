"""
Validation Architecture v3 — Phase 1: ValidationUnit.

WHAT THIS IS
The preparation-level unit a GoldCase is evaluated against — the
8-dimension schema approved in Validation Architecture v2/v3: taxon,
plant part, preparation (dosage form/solvent/DER/source status), dose,
duration, route, indication, population, jurisdiction.

WHY reference_version IS NOT HERE (v3 correction #8)
A ValidationUnit describes WHAT is being evaluated (a real-world
preparation/indication/population combination) — it is not tied to
any one reference document's version. reference_version belongs on
ReferenceDescriptor (which reference, which edition) and
FieldProvenance (which document version supported which extracted
field) — see reference_descriptor.py and field_provenance.py. Putting
a version here would wrongly imply a ValidationUnit is itself
versioned by a single external document, when in practice several
differently-versioned references may all apply to the same unit.

WHAT THIS IS NOT
Not the same object as validation_case_protocol.DecisionContext.
DecisionContext describes a CASE-level intent (a validation protocol
being locked for a product/indication/market), at a level explicitly
looser than a single preparation. ValidationUnit is the finer-grained
object a GoldCase is scored against. The two are NOT merged — see
Phase 1 migration notes (this module makes zero changes to
validation_case_protocol.py).

taxon_synonyms IS METADATA ONLY (v3 correction #3 clarification) — it
exists purely to support synonym-resolution matching (see
taxonomy metrics in Validation Architecture v2 section 9). It is never
part of a ValidationUnit's identity/equality — two ValidationUnits
with the same taxon but different taxon_synonyms lists are still
considered the same unit for matching purposes elsewhere in this
pipeline. Canonicalization (dataset_canonicalization.py) deliberately
excludes it from the identity-relevant field set for the same reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PreparationSpec:
    """Preparation-specific detail — deliberately separate from the
    top-level dosage_form vocabulary used elsewhere in this platform
    (step_inputs.DOSAGE_FORMS), because a validation unit needs to
    express the exact extract ratio/solvent a reference document
    covers, not just a broad dosage-form category."""
    dosage_form: Optional[str] = None
    solvent: Optional[str] = None
    der_min: Optional[float] = None  # Drug-Extract-Ratio, lower bound
    der_max: Optional[float] = None
    source_status: Optional[str] = None  # e.g. "native" | "concentrated" | "other" (EMA/HMPC vocabulary)


@dataclass
class Dose:
    amount: Optional[float] = None
    unit: Optional[str] = None
    frequency: Optional[str] = None


@dataclass
class ValidationUnit:
    """The preparation-level object a GoldCase's expected output and
    every ReferenceDescriptor's applicability are evaluated against.
    See module docstring for the full reasoning behind each design
    choice below."""
    taxon: str
    taxon_synonyms: list = field(default_factory=list)  # metadata only — see module docstring
    plant_part: Optional[str] = None
    preparation: Optional[PreparationSpec] = None
    dose: Optional[Dose] = None
    duration: Optional[str] = None
    route_of_administration: Optional[str] = None
    indication: Optional[str] = None
    population: Optional[str] = None
    jurisdiction: Optional[str] = None
