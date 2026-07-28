"""
Validation Architecture v3 — Phase 1: Field-level Provenance.

WHAT THIS IS
A record of exactly which document (and which version, which
locator within it) supports one specific extracted/curated field on a
GoldCase or ReferenceDescriptor. Mirrors this platform's existing
"never claim traceability merely through plant or compound names"
principle (see standard_evidence_builder.py) applied to Gold Set
curation instead of production evidence records.

curator IS A ROLE, NOT A PERSONAL NAME
Same reasoning as user_roles.py's ReviewerRole and
expert_sign_off.ExpertSignOff — see those modules' own docstrings.
This module deliberately reuses user_roles.ReviewerRole rather than
inventing a second role vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional

from user_roles import ReviewerRole


class VerificationStatus(str, Enum):
    UNVERIFIED = "Unverified"
    CURATOR_VERIFIED = "Curator verified"
    SECOND_REVIEWER_VERIFIED = "Second reviewer verified"


@dataclass
class FieldProvenance:
    """One provenance record — a GoldCase or GoldCaseReference (see
    gold_case.py) typically carries a LIST of these, one per curated
    claim, not a single aggregate provenance for the whole case."""
    document_id: str
    document_version: str
    locator: str  # exact page/section within the document
    supported_field: str  # which field this provenance backs, e.g. "expected_output.expected_decision_direction"
    extraction_date: date
    curator: Optional[ReviewerRole] = None
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
