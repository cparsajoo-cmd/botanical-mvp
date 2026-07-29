"""
Reference-Grounded Validation — ReferenceClaim.

WHAT THIS IS
What ONE specific reference states — the per-source layer, distinct
from ResolvedExpectedOutcome (resolved_expected_outcome.py), which is
the FINAL answer after applicability, precedence, and deterministic
translation across possibly several claims. A GoldCaseReference (see
gold_case.py) carries a list of these; a GoldCase carries the smaller
list of resolved outcomes derived from them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from applicability_check import ReferenceDomain
from assertion_vocabulary import (
    AssertionState, AssertionType, SeverityLevel,
    TransformationType, ExtractionConfidenceLevel,
)


@dataclass
class NormalizedEvidenceText:
    """v4 correction #4 (from the prior architecture revision) — a
    real (non-synthetic) GoldCase must trace to the authoritative
    source excerpt, not an internally generated paraphrase.
    transformation_type == SUMMARIZED_BY_CURATOR is only ever
    permitted when the owning GoldCase's kind is GoldCaseKind.SYNTHETIC
    — see gold_case.is_lockable() for where this is enforced."""
    original_text: str
    normalized_text: str
    transformation_type: TransformationType
    transformation_version: str
    source_locator: str


@dataclass
class ExtractionConfidence:
    """Honest categorical model — no uncalibrated pseudo-precise
    probability."""
    level: ExtractionConfidenceLevel
    basis: str
    extractor_type: str  # "human_curator" | "automated_nlp" | "hybrid"
    extractor_version: str


@dataclass
class ReferenceClaim:
    """What one reference states about one (domain, assertion_type,
    subject) combination. subject is stored here as originally
    written — normalization (subject_normalization.py) happens only
    at grouping time in resolved_expected_outcome.py, never mutating
    this record."""
    domain: ReferenceDomain
    assertion_type: AssertionType
    subject: str
    assertion_state: AssertionState
    severity: Optional[SeverityLevel] = None
    source_reference_id: str = ""
    source_locator: str = ""
    evidence_text: Optional[NormalizedEvidenceText] = None
    extraction_confidence: Optional[ExtractionConfidence] = None
