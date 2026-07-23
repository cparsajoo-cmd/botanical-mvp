"""
Candidate Evidence Strength (was misleadingly named "Evidence Coverage").

NAMING CORRECTION (external review, this session)
This module was originally called "Evidence Coverage" and its output
column "Evidence_Coverage_Tier" — but "coverage" is a claim about how
much of the search space was actually searched (sources planned,
queried, succeeded, failed, records retrieved), which this module has
never measured and still doesn't. What it actually measures is how
strong the evidence is FOR THIS ONE CANDIDATE, given what evidence
happens to already be attached to its row (source count, confidence,
hierarchy tier). Those are genuinely different claims — a candidate
can have "strong" evidence by this measure while the underlying
scientific search that found it was tiny, and a reader seeing
"Broad Evidence" or "Decision-grade Evidence" could reasonably (and
wrongly) infer the search itself was broad.

Renamed accordingly:
    Evidence_Coverage_Tier        -> Candidate_Evidence_Strength_Tier
    classify_evidence_coverage()  -> classify_candidate_evidence_strength()
    "Decision-grade Evidence"     -> "High-priority evidence tier"
      (also softened — see below)

WHAT STILL DOESN'T EXIST: SYSTEM-LEVEL SEARCH COVERAGE
A true Search_Coverage_Status — sources planned/attempted/succeeded/
failed, query used, records retrieved, date range — would need Step 2's
already-collected session data (research_engine.py's sources_checked/
errors/saved_records) threaded into this engine, which currently never
happens (flagged, not solved, in the prior architecture audit). This
module does not attempt that; it only stops mis-naming what it already
does.

WHY "Decision-grade" WAS TOO STRONG
The top tier required 2+ independent sources, confidence >= 65, and a
clinical-trial-or-better hierarchy tier — real signals, but none of
them assess study quality, sample size, risk of bias, botanical
authentication, extract standardization, dose comparability, endpoint
validity, or replication. Two independent case reports and a small
trial could clear this bar without being sufficient for an actual
industrial decision. "High-priority evidence tier" claims exactly what
this module can verify — worth prioritizing for review — without
implying the harder scientific-quality questions have been answered.

WHY THIS NEEDS NO NEW DATA COLLECTION
Every input here already exists on the row by the time this runs:
- Occurrence_Corroboration (Gap 3) already counts how many INDEPENDENT
  sources back this specific candidate.
- Evidence_Confidence (Phase 6) already scores evidence strength.
- Evidence_Hierarchy_Detail (Phase 4) already classifies study type.

This is a combination function over those three, not a new evidence
engine.

THE FOUR TIERS
    Preliminary               — 0-1 sources, low confidence. A single
                                 mention, not yet a body of evidence.
    Partial Evidence           — 2+ sources OR moderate confidence, but
                                 not both, and no strong hierarchy tier
                                 reached.
    Broad Evidence              — multiple independent sources AND at
                                 least moderate confidence.
    High-priority evidence tier — multiple independent sources, high
                                 confidence, AND a strong evidence
                                 hierarchy tier (clinical trial or
                                 better) — worth prioritizing for
                                 expert review, not a substitute for
                                 that review.

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

HIGH_PRIORITY_HIERARCHY_TIERS = {
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


def classify_candidate_evidence_strength(
    occurrence_corroboration: str,
    evidence_confidence: float,
    evidence_hierarchy_detail: Optional[str],
) -> str:
    """Returns one of the four candidate-level evidence-strength tier
    labels. NOT a measure of how much of the scientific/commercial
    literature was actually searched — see module docstring."""
    source_count = _extract_source_count(occurrence_corroboration)
    multi_source = source_count >= 2

    if (
        multi_source
        and evidence_confidence >= HIGH_CONFIDENCE_THRESHOLD
        and evidence_hierarchy_detail in HIGH_PRIORITY_HIERARCHY_TIERS
    ):
        return "High-priority evidence tier"

    if multi_source and evidence_confidence >= MODERATE_CONFIDENCE_THRESHOLD:
        return "Broad Evidence"

    if multi_source or evidence_confidence >= MODERATE_CONFIDENCE_THRESHOLD:
        return "Partial Evidence"

    return "Preliminary"
