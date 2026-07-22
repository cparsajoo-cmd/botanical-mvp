"""
Phase 6 — Evidence Confidence, separated from R&D Opportunity (audit 4.16).

WHY THIS IS A SEPARATE MODULE, NOT A CHANGE TO _score_candidate()
_score_candidate() in botanical_rd_candidate_engine.py already computes
one number (R&D_Opportunity_Score) that blends chemical-link strength,
evidence quality, product-development fit, novelty, market signal, and
safety penalties together. That formula is exercised by ~10 existing
regression tests that check both absolute thresholds (e.g. score >= 78
means "Strong") and relative orderings (e.g. a rare compound must
outscore a common one). Reworking that formula to also produce a
second number, in the same change, would mean re-deriving and
re-verifying every one of those tests' expectations at once — a much
bigger, riskier edit than one Phase-6 step should be.

Instead: this module computes Evidence_Confidence independently, from
signals the engine ALREADY computes per-row (Evidence_Hierarchy_Detail,
Evidence_Level, Has_Negative_Evidence — all wired in Phase 4). It's
wired into the engine as a new, additive column, exactly like
Evidence_Hierarchy_Detail and Has_Negative_Evidence were. R&D_Opportunity_Score
itself is untouched by this module.

WEIGHTS (documented here, not scattered across the file — audit 4.16:
"تمام weightها مستند شوند")

Base confidence by evidence hierarchy tier (0-100), following the
exact order audit 4.14 specified — including that traditional-use/
regulatory monograph evidence ranks BELOW in-vitro/mechanistic
evidence in that ordering, which is why its score here is lower too,
even though a regulatory monograph can feel more "official":
    Systematic review / meta-analysis          100
    Clinical trial                               85
    Observational human evidence                 65
    Validated ex vivo / in vivo                  50
    In vitro / mechanistic                       35
    Traditional-use / regulatory monograph       20
    Occurrence / analytical chemistry only       10
    (no tier classified)                          0

Fallback, when the fine-grained classifier found no tier but the
coarser Evidence_Level (Phase-1-era, 5-bucket) DID find something —
this keeps a text that only matched the coarser classifier's broader
terms from being scored as zero-confidence:
    Clinical / human evidence                    55
    Regulatory / monograph evidence               40
    Preclinical / mechanistic evidence            25
    General literature signal                     10
    No direct evidence                             0

Negative-evidence penalty: a documented negative/contradictory finding
(Phase 4, audit 4.15) multiplies the base score by 0.4 — substantially
undercutting confidence without zeroing it outright, since a single
negative finding can coexist with other, separately-positive evidence
about the same plant/compound in the same evidence pool. This is a
documented, named constant (NEGATIVE_EVIDENCE_CONFIDENCE_MULTIPLIER)
so it can be revisited/calibrated later rather than being a magic
number buried in a formula.

WHAT THIS MODULE DOES NOT DO (yet)
- Not calibrated against expert-reviewed use cases (audit 4.16's
  "score را با expert-reviewed use cases calibrate شود" and "sensitivity
  analysis انجام شود") — the numbers above are a first, documented,
  reversible starting point, not a validated model.
- Does not change Decision_Class. See
  confidence_adjusted_framing_note() for the one place this DOES
  surface in decision framing — as an additive note, not a change to
  the existing Decision_Class value.
"""

from __future__ import annotations

from typing import Optional

CONFIDENCE_BY_HIERARCHY_TIER: dict[Optional[str], float] = {
    "Systematic review / meta-analysis": 100,
    "Clinical trial": 85,
    "Observational human evidence": 65,
    "Validated ex vivo / in vivo": 50,
    "In vitro / mechanistic": 35,
    "Traditional-use / regulatory monograph": 20,
    "Occurrence / analytical chemistry only": 10,
}

CONFIDENCE_BY_EVIDENCE_LEVEL_FALLBACK: dict[str, float] = {
    "Clinical / human evidence": 55,
    "Regulatory / monograph evidence": 40,
    "Preclinical / mechanistic evidence": 25,
    "General literature signal": 10,
    "No direct evidence": 0,
}

NEGATIVE_EVIDENCE_CONFIDENCE_MULTIPLIER = 0.4

# Below this Evidence_Confidence, a high R&D_Opportunity_Score must not
# be presented as a strong recommendation without an explicit note —
# audit 4.16's "opportunity بالا ولی evidence پایین باید Exploratory
# باشد". Both thresholds are named constants, not magic numbers.
LOW_CONFIDENCE_THRESHOLD = 30
HIGH_OPPORTUNITY_THRESHOLD = 62


def compute_evidence_confidence(
    evidence_hierarchy_detail: Optional[str],
    evidence_level: str,
    has_negative_evidence: bool,
) -> float:
    """Returns a 0-100 confidence score. See module docstring for the
    documented weight tables this is built from."""
    base = CONFIDENCE_BY_HIERARCHY_TIER.get(evidence_hierarchy_detail)
    if base is None:
        base = CONFIDENCE_BY_EVIDENCE_LEVEL_FALLBACK.get(evidence_level, 0)

    if has_negative_evidence:
        base = base * NEGATIVE_EVIDENCE_CONFIDENCE_MULTIPLIER

    return round(min(100.0, max(0.0, base)), 1)


def confidence_adjusted_framing_note(
    rd_opportunity_score: Optional[float],
    evidence_confidence: Optional[float],
) -> Optional[str]:
    """Returns an explicit warning string when a candidate has a high
    opportunity score but low evidence confidence — the exact mismatch
    audit 4.16 named. Returns None when no warning applies. This is
    surfaced as an ADDITIONAL column (Confidence_Note) alongside the
    existing Decision_Class, not a replacement for it — changing what
    Decision_Class itself means is a separate, larger migration."""
    if rd_opportunity_score is None or evidence_confidence is None:
        return None
    if (
        evidence_confidence < LOW_CONFIDENCE_THRESHOLD
        and rd_opportunity_score >= HIGH_OPPORTUNITY_THRESHOLD
    ):
        return (
            f"Exploratory — R&D_Opportunity_Score ({rd_opportunity_score}) is high, "
            f"but Evidence_Confidence ({evidence_confidence}) is low. Treat as an "
            f"exploratory hypothesis, not a strong recommendation, until stronger "
            f"evidence is available."
        )
    return None
