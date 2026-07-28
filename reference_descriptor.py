"""
Validation Architecture v3 — Phase 1: ReferenceDescriptor.

WHAT THIS IS
The minimal, normalized metadata about ONE reference document (an
EMA/HMPC monograph, a WHO monograph, a systematic review, a national
regulatory record, etc.) that check_applicability() and
resolve_precedence() need — nothing about the document's actual
content/verdict lives here (that's ExpectedOutput, curated separately
per GoldCase-reference pairing — see gold_case.py).

WHY A SEPARATE OBJECT FROM ValidationUnit
ReferenceDescriptor describes a DOCUMENT's own scope (what it covers).
ValidationUnit describes the CASE being evaluated. Applicability is
the comparison between the two — see applicability_check.py. Keeping
them as two distinct objects (rather than reusing ValidationUnit's
own shape for references) is deliberate: a reference's scope fields
are close to, but not identical to, a ValidationUnit's dimensions
(e.g. indication_scope/route_scope are LISTS, since one monograph
typically covers several indications/routes at once — a single
ValidationUnit only ever names one).

reference_version LIVES HERE (v3 correction #8) — not on
ValidationUnit. A version identifies which edition of THIS document
is being referenced; FieldProvenance (field_provenance.py) then
records which specific extracted field, at which locator, that
version supported.

source_type VOCABULARY
Deliberately a plain string, not yet a formal Enum — reference_precedence.py's
domain-specific hierarchies (Phase 1) key off this string. Kept as a
free string in Phase 1 rather than a locked Enum so the five approved
hierarchies (identity/quality, indication/evidence, safety, regulatory
status, preparation spec) can each define their own ranked source_type
list without this module having to anticipate every possible source
type in advance. Callers are expected to use a small, documented
vocabulary — see reference_precedence.py's _DOMAIN_HIERARCHIES for the
values Phase 1 actually recognizes (e.g. "EMA_HMPC", "WHO_MONOGRAPH",
"ESCOP_MONOGRAPH", "COMMISSION_E", "PHARMACOPOEIA",
"SYSTEMATIC_REVIEW", "NATIONAL_REGULATORY"). An unrecognized
source_type is not an error here — it is resolved as
INSUFFICIENT_METADATA by reference_precedence.py, never silently
ranked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from validation_unit import PreparationSpec


@dataclass
class ReferenceDescriptor:
    """Normalized metadata about one reference document — see module
    docstring for what deliberately does NOT live here (the document's
    actual verdict/content, which is curated per GoldCase instead)."""
    reference_id: str
    source_type: str
    version: str
    document_date: Optional[date] = None
    jurisdiction: Optional[str] = None  # None = international/non-geographic scope

    # Scope metadata — compared against a ValidationUnit by
    # applicability_check.py. Deliberately LISTS where a ValidationUnit
    # has a single value (indication/route), since one document
    # typically covers several.
    taxon: Optional[str] = None
    plant_part: Optional[str] = None
    preparation: Optional[PreparationSpec] = None
    population: Optional[str] = None
    claim_type: Optional[str] = None  # e.g. "traditional-use" | "well-established-use"
    indication_scope: list = field(default_factory=list)
    route_scope: list = field(default_factory=list)

    retracted_or_superseded: bool = False
