"""
Architecture audit Q9 — "What is the estimated industrial feasibility?"

WHAT THIS FIXES
_extraction_fit_score() (in botanical_rd_candidate_engine.py) already
computes exactly the signal industrial feasibility needs — does a
reported extraction method match the target dosage form — but only
ever as an internal number folded into R&D_Opportunity_Score's
"Product-development fit" component. Nothing exposes it as its own
manufacturability judgment, and nothing combines it with whether real
concentration data exists (a method match with no known concentration
is a different feasibility picture than a method match WITH a
quantified concentration).

WHY THIS REUSES _extraction_fit_score() RATHER THAN RECOMPUTING FIT
This module takes the raw extraction-fit score as an input, computed
by calling the engine's OWN _extraction_fit_score() a second time (a
cheap, pure function — no side effects, no new logic) rather than
re-deriving extraction suitability from scratch, which would have been
duplicate logic.
"""

from __future__ import annotations

# _extraction_fit_score()'s own documented range: 3 when no extraction
# method is reported at all; up to a theoretical ~45 for a strong
# method-category + dosage-form match (though most single-category
# matches land around 16-26). Thresholds below are calibrated against
# that actual range, not against _score_candidate's separate min(18, ...)
# cap (which exists to bound ITS OWN weighted sum, not to define what
# "good extraction fit" means on its own terms).
NOT_ASSESSED_THRESHOLD = 3  # exactly _extraction_fit_score()'s "no method reported" value
LOW_FEASIBILITY_THRESHOLD = 14
MODERATE_FEASIBILITY_THRESHOLD = 20


def classify_industrial_feasibility(extraction_fit_score: float, has_concentration_data: bool) -> str:
    """Returns a categorical, explainable feasibility label — not a
    fabricated cost/yield estimate this codebase has no data to
    support, only what the existing extraction-fit and concentration
    signals actually justify saying."""
    if extraction_fit_score <= NOT_ASSESSED_THRESHOLD:
        return "Not assessed — no extraction method information available"

    if extraction_fit_score < LOW_FEASIBILITY_THRESHOLD:
        base = "Low feasibility — extraction method reported but poorly matched to the target dosage form"
    elif extraction_fit_score < MODERATE_FEASIBILITY_THRESHOLD:
        base = "Moderate feasibility — extraction method partially matches the target dosage form"
    else:
        base = "High feasibility — extraction method matches the target dosage form well"

    if not has_concentration_data:
        base += "; concentration not quantified, so scale-up yield is still unknown"

    return base
