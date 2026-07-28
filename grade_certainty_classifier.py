"""
Task 2 — GRADE-style clinical-evidence certainty grading.

Closes the gap Appendix B/Chapter 7 of the whitepaper names explicitly:
"Clinical-evidence certainty (GRADE) — Designed only. evidence_confidence.py
explicitly documents that its output is 'not a true GRADE-style risk-of-bias
assessment'. No GRADE implementation exists in the codebase."

WHAT THIS MODULE IS
A GRADE-INFORMED certainty rating (High / Moderate / Low / Very Low) for
the evidence behind ONE evidence row, built entirely from signals this
engine already computes elsewhere — no new data collection, no new raw-
text pattern language beyond what evidence_confidence.py already detects:
  - Evidence_Hierarchy_Detail        (evidence_hierarchy_classifier.py)
  - the row's free evidence text     (blinding/placebo/sample-size
                                       markers, via evidence_confidence.py's
                                       methodological_quality_signals())
  - Has_Negative_Evidence            (negative_evidence_classifier.py)
  - Occurrence_Corroboration         (evidence_coverage.py's source-count
                                       parsing, via _extract_source_count())
  - Applicability_Classification     (standard_evidence_builder.py, reached
                                       here via the candidate's strongest
                                       applicability category)

WHAT THIS MODULE IS NOT — read before treating a "High" rating as
authoritative
This is NOT the real GRADE method. Formal GRADE certainty grading is
performed by a human methodologist (or a validated RoB 2 / ROBINS-I tool
applied to each included study) across a BODY of evidence for one
outcome, with full-text access to assess randomization adequacy,
allocation concealment, blinding of outcome assessors specifically,
attrition/incomplete-outcome-data handling, and selective-outcome
reporting — and, for imprecision/publication bias, the actual reported
confidence-interval width and a body-of-evidence-level publication-bias
assessment (e.g. a funnel plot or Egger's test). None of that is
available to this module, which sees a single evidence row's short
extracted text. This module instead uses five DECLARED, NAMED proxies
(below), and any domain it cannot honestly assess from that text is
marked "Not assessed" and contributes NO downgrade — an unassessed
domain must never be silently scored as "no concern". This mirrors the
same "absence of evidence is not evidence of absence" principle already
applied elsewhere in this pipeline (evidence_hierarchy_classifier.py's
None-vs-lowest-tier distinction; standard_evidence_builder.py's
"Not assessable" applicability category).

A GRADE_Certainty value from this module should be read as "implemented
with limitations" (repository-audit vocabulary — see the whitepaper's
Chapter 7 / Appendix B), not as a validated clinical-evidence-certainty
determination. It has not been checked against independent expert
GRADE ratings on any locked benchmark case.

GRADE APPLIES ONLY TO A BODY OF CLINICAL EVIDENCE
Per real GRADE methodology, certainty grading is meaningful only for
evidence answering a clinical/human-outcome question — typically
randomized trials or observational studies. It is not meaningful for
mechanistic/in-vitro evidence, animal models, occurrence/analytical-
chemistry data, or traditional-use/regulatory monographs, none of which
report a clinical outcome estimate GRADE's domains are built to qualify.
Evidence classified into one of those tiers (or with no classified tier
at all) returns "Not GRADE-applicable" rather than a fabricated rating.

STARTING CERTAINTY (by Evidence_Hierarchy_Detail — standard GRADE
convention: a body of evidence built from randomized trials starts
High; one built from observational studies starts Low):
    Systematic review / meta-analysis     -> High
    Clinical trial                        -> High
    Observational human evidence          -> Low
    (any other tier, or no tier at all)   -> Not GRADE-applicable

FIVE DOWNGRADE DOMAINS (each domain: not serious / serious [-1] /
very serious [-2] / not assessed [no downgrade, explicitly disclosed
in the rationale and in the returned domains dict]):

1. Risk of bias — ONLY assessed for the "Clinical trial" tier, using
   the blinding/placebo-control text markers evidence_confidence.py
   already detects, as a declared proxy for randomization/blinding
   quality (real RoB 2 also checks allocation concealment, attrition,
   and selective reporting, none of which this module can see from
   row text). Neither marker present -> serious. Not assessed for
   "Systematic review / meta-analysis" or "Observational human
   evidence" — a single row's text cannot characterize the risk of
   bias of an entire underlying body of evidence.

2. Imprecision — assessed for "Clinical trial" and "Observational
   human evidence", using the same sample-size text detector: no
   mention of at least 100 participants -> serious (GRADE's own
   convention treats an unclear or small sample as a caution, not a
   pass). Not assessed for "Systematic review / meta-analysis" —
   imprecision there is a pooled-estimate/confidence-interval-width
   question this module has no access to.

3. Inconsistency — assessed for every GRADE-applicable tier, using
   Has_Negative_Evidence: a documented negative/contradictory finding
   alongside otherwise-positive evidence for the same candidate is
   treated as a conflicting-body-of-evidence signal -> serious.

4. Indirectness — assessed for every GRADE-applicable tier, using the
   candidate's own strongest Applicability_Classification (already
   computed by standard_evidence_builder.py / _summarize_applicability()):
   "Partially applicable" -> serious; "Indirectly relevant" or
   "Not applicable" -> very serious; "Directly applicable" -> not
   serious. "Not assessable", missing, or None -> not assessed (never
   treated as favorable by default).

5. Publication bias — assessed for every GRADE-applicable tier, using
   Occurrence_Corroboration's already-parsed independent-source count
   as a declared proxy (a real publication-bias assessment needs a
   funnel plot or comparable test across a full body of evidence,
   which this module cannot perform): fewer than 2 independent
   sources -> serious.

TOTAL DOWNGRADE is the sum of every domain's downgrade (0 / -1 / -2;
"not assessed" domains contribute 0), applied to the starting
certainty's rank and floored at "Very Low" — certainty can drop but
never rise above its GRADE-convention starting tier.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from evidence_confidence import methodological_quality_signals
from evidence_coverage import _extract_source_count

NOT_GRADE_APPLICABLE = "Not GRADE-applicable"

_STARTING_CERTAINTY_BY_TIER: dict[str, str] = {
    "Systematic review / meta-analysis": "High",
    "Clinical trial": "High",
    "Observational human evidence": "Low",
}

# Tiers for which each domain is honestly assessable from a single
# row's text — see module docstring for why the other GRADE-applicable
# tier(s) are excluded per domain.
_RISK_OF_BIAS_ASSESSABLE_TIERS = {"Clinical trial"}
_IMPRECISION_ASSESSABLE_TIERS = {"Clinical trial", "Observational human evidence"}

_CERTAINTY_RANK: dict[str, int] = {
    "Very Low": 0,
    "Low": 1,
    "Moderate": 2,
    "High": 3,
}
_RANK_TO_CERTAINTY = {v: k for k, v in _CERTAINTY_RANK.items()}

_INDIRECTNESS_DOWNGRADE: dict[str, int] = {
    "Directly applicable": 0,
    "Partially applicable": 1,
    "Indirectly relevant": 2,
    "Not applicable": 2,
}


@dataclass
class GradeDomainRating:
    rating: str  # "Not serious" | "Serious" | "Very serious" | "Not assessed"
    downgrade: int  # 0, 1, or 2
    reason: str


@dataclass
class GradeCertaintyResult:
    certainty: str  # "High" | "Moderate" | "Low" | "Very Low" | NOT_GRADE_APPLICABLE
    rationale: str
    domains: dict = field(default_factory=dict)  # domain name -> GradeDomainRating

    def domains_as_text(self) -> dict:
        """CSV/Supabase-friendly flattening — dataclasses don't survive
        a round trip through pandas -> Supabase JSON columns as cleanly
        as plain dicts/strings do (same reasoning already applied to
        Gate_Results/Applicability_Summary elsewhere in this pipeline)."""
        return {
            name: {
                "rating": d.rating,
                "downgrade": d.downgrade,
                "reason": d.reason,
            }
            for name, d in self.domains.items()
        }


def _risk_of_bias_domain(tier: str, evidence_text: Optional[str]) -> GradeDomainRating:
    if tier not in _RISK_OF_BIAS_ASSESSABLE_TIERS:
        return GradeDomainRating(
            "Not assessed", 0,
            "A single evidence row's text cannot characterize the risk "
            "of bias of an entire body of evidence at this tier; not "
            "downgraded.",
        )
    signals = methodological_quality_signals(evidence_text)
    if signals["blinded"] or signals["placebo_controlled"]:
        return GradeDomainRating(
            "Not serious", 0,
            "Blinding and/or placebo-control mentioned in the evidence text.",
        )
    return GradeDomainRating(
        "Serious", 1,
        "No blinding or placebo-control mentioned in the evidence text "
        "(proxy only — allocation concealment, attrition and selective "
        "reporting are not assessed).",
    )


def _imprecision_domain(tier: str, evidence_text: Optional[str]) -> GradeDomainRating:
    if tier not in _IMPRECISION_ASSESSABLE_TIERS:
        return GradeDomainRating(
            "Not assessed", 0,
            "Imprecision at this tier is a pooled-estimate/confidence-"
            "interval question this module cannot assess from a single "
            "row's text; not downgraded.",
        )
    signals = methodological_quality_signals(evidence_text)
    if signals["large_sample"]:
        return GradeDomainRating(
            "Not serious", 0,
            "A sample size of at least 100 participants was mentioned.",
        )
    return GradeDomainRating(
        "Serious", 1,
        "No sample size of at least 100 participants was mentioned "
        "(unclear or small sample — proxy only, not a reported "
        "confidence-interval width).",
    )


def _inconsistency_domain(has_negative_evidence: bool) -> GradeDomainRating:
    if has_negative_evidence:
        return GradeDomainRating(
            "Serious", 1,
            "A documented negative/contradictory finding coexists with "
            "otherwise-positive evidence for this candidate.",
        )
    return GradeDomainRating(
        "Not serious", 0,
        "No documented negative/contradictory finding detected.",
    )


def _indirectness_domain(applicability_classification: Optional[str]) -> GradeDomainRating:
    if not applicability_classification or applicability_classification not in _INDIRECTNESS_DOWNGRADE:
        return GradeDomainRating(
            "Not assessed", 0,
            "No usable Applicability_Classification was available; not "
            "downgraded (an unassessed dimension is not treated as "
            "favorable).",
        )
    downgrade = _INDIRECTNESS_DOWNGRADE[applicability_classification]
    if downgrade == 0:
        return GradeDomainRating(
            "Not serious", 0,
            f"Applicability_Classification: {applicability_classification}.",
        )
    rating = "Very serious" if downgrade == 2 else "Serious"
    return GradeDomainRating(
        rating, downgrade,
        f"Applicability_Classification: {applicability_classification}.",
    )


def _publication_bias_domain(occurrence_corroboration: Optional[str]) -> GradeDomainRating:
    source_count = _extract_source_count(occurrence_corroboration or "")
    if source_count >= 2:
        return GradeDomainRating(
            "Not serious", 0,
            f"Corroborated by {source_count} independent source(s).",
        )
    return GradeDomainRating(
        "Serious", 1,
        "Fewer than two independent sources found for this candidate "
        "(proxy only — not a funnel-plot or body-of-evidence-level "
        "publication-bias test).",
    )


def classify_grade_certainty(
    evidence_hierarchy_detail: Optional[str],
    evidence_text: Optional[str] = None,
    has_negative_evidence: bool = False,
    occurrence_corroboration: Optional[str] = None,
    applicability_classification: Optional[str] = None,
) -> GradeCertaintyResult:
    """Returns a GradeCertaintyResult. See module docstring for the
    full, documented method this implements and its declared
    limitations. Never raises on missing/malformed inputs — mirrors
    the rest of this pipeline's "degrade to an explicit, disclosed
    state rather than crash or guess" convention.
    """
    starting_certainty = _STARTING_CERTAINTY_BY_TIER.get(evidence_hierarchy_detail)

    if starting_certainty is None:
        return GradeCertaintyResult(
            certainty=NOT_GRADE_APPLICABLE,
            rationale=(
                f"GRADE certainty grading applies to bodies of clinical "
                f"evidence (randomized trials or observational studies); "
                f"this row's Evidence_Hierarchy_Detail "
                f"({evidence_hierarchy_detail or 'Unclassified'}) is not "
                f"one of those tiers, so no certainty rating is assigned."
            ),
            domains={},
        )

    domains = {
        "risk_of_bias": _risk_of_bias_domain(evidence_hierarchy_detail, evidence_text),
        "imprecision": _imprecision_domain(evidence_hierarchy_detail, evidence_text),
        "inconsistency": _inconsistency_domain(has_negative_evidence),
        "indirectness": _indirectness_domain(applicability_classification),
        "publication_bias": _publication_bias_domain(occurrence_corroboration),
    }

    total_downgrade = sum(d.downgrade for d in domains.values())
    starting_rank = _CERTAINTY_RANK[starting_certainty]
    final_rank = max(0, starting_rank - total_downgrade)
    final_certainty = _RANK_TO_CERTAINTY[final_rank]

    serious_domains = [
        f"{name.replace('_', ' ')} ({d.rating.lower()})"
        for name, d in domains.items()
        if d.downgrade > 0
    ]
    not_assessed_domains = [
        name.replace("_", " ") for name, d in domains.items() if d.rating == "Not assessed"
    ]

    rationale_parts = [
        f"Starting certainty: {starting_certainty} "
        f"(Evidence_Hierarchy_Detail: {evidence_hierarchy_detail})."
    ]
    if serious_domains:
        rationale_parts.append(
            f"Downgraded for: {'; '.join(serious_domains)} "
            f"(total downgrade: {total_downgrade})."
        )
    else:
        rationale_parts.append("No downgrade domains triggered.")
    if not_assessed_domains:
        rationale_parts.append(
            f"Not assessed from available data: {', '.join(not_assessed_domains)}."
        )
    rationale_parts.append(
        "This is a GRADE-informed proxy rating, not a formal GRADE "
        "assessment — see grade_certainty_classifier.py's module "
        "docstring for the declared method and its limitations."
    )

    return GradeCertaintyResult(
        certainty=final_certainty,
        rationale=" ".join(rationale_parts),
        domains=domains,
    )
