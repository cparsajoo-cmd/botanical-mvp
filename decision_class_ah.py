"""
Phase 6 — A-H decision classification (audit section 4.7).

WHAT THIS IS
The 8-class taxonomy from audit 4.7 (A. Verified commercial route
through H. No-go/safety concern), computed as a NEW, additive
Decision_Class_AH column — the existing Decision_Class (Strong/
Promising/Early-stage/Low priority/Safety concern) is untouched.

WHY ADDITIVE, NOT A REPLACEMENT
Decision_Class currently drives everything downstream that reads it —
the UI's "Recommended" table filtering, the merge logic's
"tightest"/"weakest sub-row" comparisons (which use an explicit rank
order over the exact 5 existing strings), and the existing regression
tests. Swapping the fundamental classification scheme in the same
change that computes it is a bigger migration than one Phase-6 step
should be — audit 4.7 itself frames the A-H scheme as a "پیشنهاد"
(proposal) to design toward, not a same-day cutover. This module makes
that proposal concrete and inspectable side-by-side with the current
output, so it can be reviewed against real data before anything
downstream is asked to switch over to reading it instead.

HONESTY ABOUT THIS MAPPING
The rules below are a documented FIRST DRAFT, not a validated model —
audit 4.16 separately asks for calibration against expert-reviewed use
cases and a sensitivity analysis, neither of which has happened yet.
Every rule's reasoning is written out below specifically so it can be
challenged and adjusted; nothing here should be read as "this is
correct," only "this is what the current draft rule says and why."

THE EIGHT CLASSES (verbatim from audit 4.7)
    A. Verified commercial route
    B. Established scientific candidate
    C. Alternative-source R&D candidate
    D. Mechanism-based R&D candidate
    E. White-space opportunity
    F. Exploratory hypothesis
    G. Hold / insufficient evidence
    H. No-go / safety concern
"""

from __future__ import annotations

from typing import Optional

# Same thresholds evidence_confidence.py already uses for the
# high-opportunity/low-confidence mismatch note — reused here rather
# than re-declared, so the two modules can't silently drift apart.
from evidence_confidence import LOW_CONFIDENCE_THRESHOLD, HIGH_OPPORTUNITY_THRESHOLD

# A second, lower confidence line: above this (but below what
# evidence_confidence.py calls "low"), evidence is real but modest —
# e.g. a single observational study or in-vitro finding. Used to
# separate "genuinely no evidence" (G) from "some real but limited
# evidence" (D) below.
MODEST_CONFIDENCE_THRESHOLD = 30

# Minimum R&D_Opportunity_Score for a candidate to be worth framing as
# an R&D opportunity at all, rather than a hold. Matches
# _decision_class()'s own existing "Early-stage" floor in
# botanical_rd_candidate_engine.py, reused here for consistency rather
# than picked independently.
MINIMUM_OPPORTUNITY_THRESHOLD = 45


def classify_decision_ah(
    existing_decision_class: str,
    evidence_confidence: float,
    rd_opportunity_score: float,
    market_status: str,
    match_quality: str,
    same_plant: bool,
) -> str:
    """Maps existing per-row signals onto the A-H taxonomy. Order below
    is priority order — first matching rule wins.

    H. No-go / safety concern
       Rule: existing_decision_class is already "Safety concern...".
       Reasoning: the existing hard-safety-exclusion logic in
       _decision_class() is more thoroughly tested and reasoned-about
       (HARD_SAFETY_TERMS, the same-plant exemption) than anything this
       module would add — reuse it rather than re-deriving it.

    A. Verified commercial route
       Rule: market_status == "Verified marketed product".
       Reasoning: literally what class A means. Currently unreachable
       in practice — _market_status() never returns this string yet,
       since no real retail/patent verification is wired in (Phase 5) —
       kept here so the mapping is ready the moment that changes.

    F. Exploratory hypothesis
       Rule: evidence_confidence < LOW_CONFIDENCE_THRESHOLD AND
       rd_opportunity_score >= HIGH_OPPORTUNITY_THRESHOLD.
       Reasoning: exactly the mismatch evidence_confidence.py's
       confidence_adjusted_framing_note() already flags — audit 4.16's
       "opportunity بالا ولی evidence پایین باید Exploratory باشد،
       نه Strong Recommendation" is, verbatim, the definition of F.
       Checked BEFORE B/C/D deliberately: near-zero confidence means
       there ISN'T real evidence yet, regardless of what match_quality
       or same_plant happen to be — those signals shouldn't be able to
       upgrade a near-zero confidence candidate into a more established-
       sounding class just because the compound match itself is exact.

    B. Established scientific candidate
       Rule: same_plant AND evidence_confidence >=
       MODEST_CONFIDENCE_THRESHOLD (real evidence about the reference
       itself, not near-zero — the F check above already caught the
       near-zero case).
       Reasoning: a same-plant ("reference matched to itself") row IS
       evidence about the actual candidate under evaluation, not a
       comparison to an alternative — audit 4.7's class B ("شواهد
       مستقیم برای کاربرد وجود دارد، اما محصول تجاری verify نشده") is
       about the application itself, which same_plant rows represent.

    C. Alternative-source R&D candidate
       Rule: NOT same_plant, match_quality in
       {"exact", "target_verified"}, evidence_confidence >=
       MODEST_CONFIDENCE_THRESHOLD.
       Reasoning: audit 4.7's own definition of class C is "همان
       compound مؤثر یا compound بسیار مرتبط از نظر ساختار، target یا
       mechanism" — explicitly INCLUDES a very closely related
       compound (i.e. target_verified), not only an exact match. An
       earlier version of this rule required match_quality == "exact"
       only, which meant a target_verified match with STRONG evidence
       (confidence above MODEST_CONFIDENCE_THRESHOLD) matched neither
       this rule (wrong match_quality) nor D below (D requires LOW
       confidence) — it fell through every rule and landed in G/Hold,
       misclassifying a genuinely strong candidate as "insufficient
       evidence." Found via an end-to-end smoke test combining a real
       target_verified match with a high Evidence_Confidence, not by
       inspection — the unit tests alone hadn't covered that specific
       combination of match_quality and confidence level.

    D. Mechanism-based R&D candidate
       Rule: NOT same_plant, match_quality in
       {"exact", "target_verified"}, evidence_confidence below
       MODEST_CONFIDENCE_THRESHOLD (but at/above LOW_CONFIDENCE_THRESHOLD
       — below that, F already claimed it) and rd_opportunity_score at
       least MINIMUM_OPPORTUNITY_THRESHOLD.
       Reasoning: class D is explicitly for "evidence مستقیم بیماری
       محدود است، اما target/mechanism مشترک ... قابل‌ردیابی" — a real
       chemical/target link exists, direct disease evidence doesn't
       yet, and the opportunity score is moderate rather than
       suspiciously high (a suspiciously high score with this little
       evidence is F's territory, not D's).

    E. White-space opportunity
       Rule: market_status == "No verified product found" AND
       evidence_confidence >= MODEST_CONFIDENCE_THRESHOLD.
       Reasoning: class E requires an ACTUAL completed market search
       that came back empty, not merely "we don't know" — which is
       exactly why _market_status() (Phase 5) was rewritten to never
       return "No verified product found" unless a real search ran.
       Currently a dead code path for the same reason class A is: no
       real retail/patent search is wired in yet.

    G. Hold / insufficient evidence
       Default / fallback. Reasoning: audit 4.7's own definition
       ("اطلاعات ... کافی نیست") is itself the correct default for
       anything that doesn't clear one of the more specific bars above
       — G is deliberately the class every candidate falls into unless
       a more specific, better-evidenced claim can be made about it.
    """
    if "Safety concern" in existing_decision_class:
        return "H — No-go / safety concern"

    if market_status == "Verified marketed product":
        return "A — Verified commercial route"

    # Checked BEFORE B/C/D: if confidence is near-zero, there ISN'T
    # real evidence yet, regardless of same_plant/match_quality — a
    # near-zero-confidence, high-opportunity candidate must be flagged
    # as an exploratory mismatch, not miscategorized as an established
    # or mechanism-based candidate just because its match_quality
    # happens to be "exact"/"target_verified".
    if (
        evidence_confidence < LOW_CONFIDENCE_THRESHOLD
        and rd_opportunity_score >= HIGH_OPPORTUNITY_THRESHOLD
    ):
        return "F — Exploratory hypothesis"

    if same_plant and evidence_confidence >= MODEST_CONFIDENCE_THRESHOLD:
        return "B — Established scientific candidate"

    if (
        not same_plant
        and match_quality in {"exact", "target_verified"}
        and evidence_confidence >= MODEST_CONFIDENCE_THRESHOLD
    ):
        return "C — Alternative-source R&D candidate"

    if (
        not same_plant
        and match_quality in {"exact", "target_verified"}
        and evidence_confidence < MODEST_CONFIDENCE_THRESHOLD
        and rd_opportunity_score >= MINIMUM_OPPORTUNITY_THRESHOLD
    ):
        return "D — Mechanism-based R&D candidate"

    if (
        market_status == "No verified product found"
        and evidence_confidence >= MODEST_CONFIDENCE_THRESHOLD
    ):
        return "E — White-space opportunity"

    return "G — Hold / insufficient evidence"
