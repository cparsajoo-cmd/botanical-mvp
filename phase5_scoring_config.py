"""Phase 5 — Scientific Score Calibration: single, central source for
every constant/threshold this phase introduces.

Every module that implements part of the Phase 5 architecture
(candidate_shortlisting.py, botanical_rd_candidate_engine.py,
standard_evidence_builder.py, evidence_consistency.py) imports its
weights/thresholds FROM HERE — none of them re-declares its own copy.
See PHASE5_SCORING_CALIBRATION_AUDIT_ADDENDUM.md for the full derivation
and rationale of every number below.

PROVISIONAL. NOT CLINICALLY VALIDATED. NOT STATISTICALLY CALIBRATED.
Every weight/threshold in this module is a deliberate, internally
consistent engineering choice made to satisfy the architectural
constraints in the addendum (unsigned Evidence Quality, tier precedence,
multiplicative combination, no routine clipping) — not a number derived
from clinical trial data, expert elicitation, or any statistical
calibration process. Treat every value here as subject to revision
before this becomes a production scoring authority a real R&D decision
should be based on without human review.
"""
from __future__ import annotations

PROVISIONAL_NOTICE = (
    "Provisional. Not clinically validated. Not statistically calibrated."
)

# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------
# Bumped whenever any weight, threshold, tier mapping, or formula in this
# module changes. Distinct from DECISION_ENGINE_VERSION (botanical_rd_
# candidate_engine.py), which tracks decision-tier boundaries, not
# Scientific Score component weights -- the main audit (§12) flagged
# these as two different things that should not be silently merged.
SCORING_MODEL_VERSION = "phase5-scientific-score-v1.0.0-provisional"

# ---------------------------------------------------------------------------
# Evidence tier precedence (addendum §1.3/§2 of correction round 6-7)
# ---------------------------------------------------------------------------
# Ordered highest-precedence-first. The highest non-empty tier among a
# de-duplicated evidence pool is the "primary tier" that establishes
# Direction_Factor/Evidence_Consistency_Factor/Plant_Applicability_Factor;
# lower tiers are diagnostic-only (Supporting_Evidence_Tiers_Present /
# Supporting_Evidence_Record_Count) and never change the primary tier's
# result, however many lower-tier records exist.
EVIDENCE_TIER_PRECEDENCE = ("A1", "A2", "A3", "B", "C")

# Maps candidate_shortlisting._evidence_quality()'s own
# row_hierarchy_points() label (the EXISTING, reused hierarchy
# classification -- not re-derived here) to one of the five tiers above.
HIERARCHY_LABEL_TO_TIER = {
    "review": "A1",
    "rct": "A2",
    "human": "A3",
    "animal": "B",
    "preclinical": "C",
    "analytical": "C",
    "unclassified": "C",
    "registry_no_results": "C",
}

# ---------------------------------------------------------------------------
# Direction / Consistency (addendum §1.3 Step 4, §2.1)
# ---------------------------------------------------------------------------
# Both factors are driven by the SAME Evidence_Consistency_Class
# (evidence_consistency.classify_evidence_consistency()) computed over the
# primary tier's own de-duplicated outcome counts -- one classification,
# two factor lookups, never two independently-computed judgments that
# could disagree.
CONSISTENT_POSITIVE = "CONSISTENT_POSITIVE"
MOSTLY_POSITIVE = "MOSTLY_POSITIVE"
MIXED = "MIXED"
MOSTLY_NULL = "MOSTLY_NULL"
CONSISTENT_NULL = "CONSISTENT_NULL"
MOSTLY_NEGATIVE = "MOSTLY_NEGATIVE"
INSUFFICIENT = "INSUFFICIENT"

DIRECTION_FACTORS = {
    CONSISTENT_POSITIVE: 1.00,
    MOSTLY_POSITIVE: 0.80,
    MIXED: 0.40,
    MOSTLY_NULL: 0.00,
    CONSISTENT_NULL: 0.00,
    MOSTLY_NEGATIVE: -0.20,
    INSUFFICIENT: 0.00,
}

CONSISTENCY_FACTORS = {
    CONSISTENT_POSITIVE: 1.00,
    MOSTLY_POSITIVE: 0.85,
    MIXED: 0.60,
    MOSTLY_NULL: 0.85,
    CONSISTENT_NULL: 1.00,
    MOSTLY_NEGATIVE: 0.85,
    INSUFFICIENT: 0.70,
}

# ---------------------------------------------------------------------------
# Applicability (addendum §3.4-§3.7)
# ---------------------------------------------------------------------------
MATCH = "MATCH"
PARTIAL = "PARTIAL"
UNKNOWN = "UNKNOWN"
MISMATCH = "MISMATCH"
NOT_APPLICABLE = "NOT_APPLICABLE"

APPLICABILITY_FACTORS = {
    MATCH: 1.00,
    PARTIAL: 0.80,
    UNKNOWN: 0.60,
    MISMATCH: 0.25,
    # NOT_APPLICABLE is intentionally absent: it is excluded from
    # aggregation entirely (never contributes a factor), per §3.5.
}

# When NO dimension is evaluable at all (every dimension NOT_APPLICABLE,
# or the target_context itself is materially incomplete) -- §3.5/§4.
APPLICABILITY_FACTOR_WHEN_NOTHING_EVALUABLE = 0.60
APPLICABILITY_CLASSIFICATION_WHEN_NOTHING_EVALUABLE = UNKNOWN
APPLICABILITY_COMPLETENESS_WHEN_NOTHING_EVALUABLE = "incomplete"

# Classification precedence (worst dimension status wins) -- §3.6.
APPLICABILITY_CLASSIFICATION_PRECEDENCE = (MISMATCH, UNKNOWN, PARTIAL, MATCH, NOT_APPLICABLE)

# Dimensions evaluated by evaluate_applicability() -- §3.4.
APPLICABILITY_DIMENSIONS = ("species", "plant_part", "preparation", "route", "dose", "indication")

# Dimensions that may resolve to PARTIAL in this phase (only Preparation
# has an explicit parent-category field proposed, §3.4/§correction-round-6
# item 5). Species/Plant Part/Route/Dose/Indication are MATCH/MISMATCH/
# UNKNOWN/NOT_APPLICABLE only.
DIMENSIONS_WITH_PARTIAL_SUPPORT = ("preparation",)

# ---------------------------------------------------------------------------
# Scientific_Evidence_Score range (addendum §1.5)
# ---------------------------------------------------------------------------
SCIENTIFIC_EVIDENCE_SCORE_FLOOR = -6.0
SCIENTIFIC_EVIDENCE_SCORE_CEILING = 30.0

# ---------------------------------------------------------------------------
# Market status points (addendum §10 / main audit §3.1 fix)
# ---------------------------------------------------------------------------
# "Unknown" / "Search not performed" / "Source unavailable" must not
# receive a positive default reward, and must never score above a
# verified positive finding -- fixed here to neutral 0.0 (was +3.0,
# which scored ABOVE "Verified marketed product" at +1.0 -- the
# confirmed defect in the main audit, §3.1).
MARKET_STATUS_POINTS = {
    "Verified marketed product": 1.0,
    "Regulatory monograph exists": 2.0,
    "Commercial evidence reported": 2.0,
    "No verified product found": 6.0,
    "Conflicting evidence": -2.0,
    "Search incomplete": 3.0,
    "Unknown": 0.0,
    "Search not performed": 0.0,
    "Source unavailable": 0.0,
}
