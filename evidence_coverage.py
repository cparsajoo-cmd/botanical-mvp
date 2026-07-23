"""
Item 1 — Evidence Coverage (per-row tier).

WHAT THIS IS
Classifies every candidate row into one of four coverage tiers —
Preliminary / Partial Evidence / Broad Evidence / Decision-grade
Evidence — so a reviewer knows at a glance how much weight a given
recommendation can bear, before reading anything else about it.

WHY THIS NEEDS NO NEW DATA COLLECTION
Every input here already exists on the row by the time this runs:
- Occurrence_Corroboration (Gap 3) already counts how many INDEPENDENT
  sources back this specific candidate.
- Evidence_Confidence (Phase 6) already scores evidence strength.
- Evidence_Hierarchy_Detail (Phase 4) already classifies study type.

This is a combination function over those three, not a new evidence
engine — consistent with "use the existing architecture."

THE FOUR TIERS
    Preliminary        — 0-1 sources, low confidence. A single mention,
                          not yet a body of evidence.
    Partial Evidence    — 2+ sources OR moderate confidence, but not
                          both, and no strong hierarchy tier reached.
    Broad Evidence       — multiple independent sources AND at least
                          moderate confidence.
    Decision-grade       — multiple independent sources, high
                          confidence, AND a strong evidence hierarchy
                          tier (clinical trial or better) — the only
                          tier that should be treated as sufficient for
                          a real R&D decision without further study.

This is a first, documented, reversible calibration — same honesty
caveat as decision_class_ah.py and evidence_confidence.py: a starting
point to review against real runs, not a validated model.
"""

from __future__ import annotations

import re
from typing import Optional

# Reused from evidence_confidence.py rather than re-declared.
from evidence_confidence import LOW_CONFIDENCE_THRESHOLD

MODERATE_CONFIDENCE_THRESHOLD = 50
HIGH_CONFIDENCE_THRESHOLD = 65

DECISION_GRADE_HIERARCHY_TIERS = {
    "Systematic review / meta-analysis",
    "Clinical trial",
}

_SOURCE_COUNT_PATTERN = re.compile(r"Corroborated by (\d+) independent sources")


def _extract_source_count(occurrence_corroboration: str) -> int:
    if not occurrence_corroboration:
        return 0
    match = _SOURCE_COUNT_PATTERN.search(occurrence_corroboration)
    if match:
        return int(match.group(1))
    if "Single-source" in occurrence_corroboration:
        return 1
    return 0


def classify_evidence_coverage(
    occurrence_corroboration: str,
    evidence_confidence: float,
    evidence_hierarchy_detail: Optional[str],
) -> str:
    """Returns one of the four coverage tier labels."""
    source_count = _extract_source_count(occurrence_corroboration)
    multi_source = source_count >= 2

    if (
        multi_source
        and evidence_confidence >= HIGH_CONFIDENCE_THRESHOLD
        and evidence_hierarchy_detail in DECISION_GRADE_HIERARCHY_TIERS
    ):
        return "Decision-grade Evidence"

    if multi_source and evidence_confidence >= MODERATE_CONFIDENCE_THRESHOLD:
        return "Broad Evidence"

    if multi_source or evidence_confidence >= MODERATE_CONFIDENCE_THRESHOLD:
        return "Partial Evidence"

    return "Preliminary"
