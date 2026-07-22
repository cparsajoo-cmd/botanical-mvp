"""
Phase 4 — evidence hierarchy classification (audit section 4.14).

WHAT THIS FIXES
The engine's existing _evidence_level() (in botanical_rd_candidate_engine.py)
sorts evidence text into just 5 buckets, and lumps a Cochrane systematic
review, a single small RCT, and a cohort study into the SAME bucket
("Clinical / human evidence") — even though the audit's evidence
hierarchy (4.14) treats those as three different strength tiers. This
module classifies text into the full 8-tier hierarchy instead.

WHY A SEPARATE MODULE, NOT A REWRITE OF _evidence_level()
_evidence_level()'s 5-tier output ("Clinical / human evidence",
"Regulatory / monograph evidence", "Preclinical / mechanistic
evidence", "General literature signal", "No direct evidence") is
load-bearing: it's checked by exact string in _decision_class() (the
evidence-quality confidence caps, the needs_cap logic) and in
_score_candidate() (the evidence_points table). Changing what strings
that function returns would mean touching decision/scoring logic in
the same change — a bigger, riskier edit than one Phase-4 step should
be. This module is purely ADDITIVE: it classifies the same text more
finely and is surfaced as a new, separate output column
(Evidence_Hierarchy_Detail) alongside the existing Evidence_Level,
so nothing about current scoring or decision behavior changes yet.
Wiring the hierarchy INTO scoring/decision weights is a Phase 6 step,
done once the finer classification has been sanity-checked against
real data.

Returned values intentionally match the string values of
EvidenceHierarchyLevel in data_contracts.py (this module doesn't
import that file, to avoid an unnecessary coupling, but a caller that
wants the enum can do EvidenceHierarchyLevel(classify_evidence_hierarchy(text))).
"""

from __future__ import annotations

import re
from typing import Optional

# Ordered strongest to weakest. Checked in this order so that if a text
# mentions markers for more than one tier (e.g. a discussion section
# that mentions both a meta-analysis AND unrelated in-vitro work), the
# STRONGEST tier actually present wins, rather than whichever term
# happens to appear first in the text.
_TIERS = [
    ("Systematic review / meta-analysis", [
        "systematic review", "meta-analysis", "meta analysis",
    ]),
    ("Clinical trial", [
        "randomized controlled trial", "randomised controlled trial",
        "double-blind", "double blind", "placebo-controlled",
        "placebo controlled", "rct", "phase i trial", "phase ii trial",
        "phase iii trial", "clinicaltrials.gov",
    ]),
    ("Observational human evidence", [
        "cohort study", "case-control study", "observational study",
        "human trial", "human study", "clinical study",
    ]),
    ("Validated ex vivo / in vivo", [
        "ex vivo", "in vivo", "animal model", "mouse model", "rat model",
    ]),
    ("In vitro / mechanistic", [
        "in vitro", "mechanism of action", "signaling pathway",
        "receptor binding", "enzyme inhibition",
    ]),
    ("Traditional-use / regulatory monograph", [
        "ema", "hmpc", "hmcp", "escop", "who monograph", "monograph",
        "traditional use", "well-established use",
    ]),
    ("Occurrence / analytical chemistry only", [
        "hplc", "gc-ms", "gc/ms", "lc-ms", "high performance liquid chromatography",
        "gas chromatography", "phytochemical analysis", "compound identified",
        "concentration determined", "chromatographic analysis",
    ]),
]

# Same negation-cue list used by the engine's existing safety-flag
# extraction (_extract_flags_negation_aware) — "no clinical trials have
# been conducted" must not classify as Clinical trial evidence.
_NEGATION_CUES = (
    "no ", "not ", "lack of ", "lacks ", "insufficient ",
    "absence of ", "without ", "none found", "no evidence of ",
    "no direct ", "unproven", "unconfirmed", "no reported ",
)


def _has_term(text: str, terms: list[str]) -> bool:
    for term in terms:
        # Word-boundary match, not a bare substring search — short terms
        # like "ema" or "rct" otherwise match inside unrelated words
        # (e.g. "ema" inside "remain"). Same class of bug as the
        # engine's existing anti-X collision fix (DB_ACTIVITY_SAFETY_TERMS).
        pattern = re.compile(r"\b" + re.escape(term) + r"\b")
        for match in pattern.finditer(text):
            window_start = max(0, match.start() - 40)
            preceding = text[window_start:match.start()]
            if not any(cue in preceding[-25:] for cue in _NEGATION_CUES):
                return True
    return False


def classify_evidence_hierarchy(text: Optional[str]) -> Optional[str]:
    """Returns the strongest hierarchy tier whose markers are present in
    `text` (negation-aware), or None if no tier's markers are found —
    None deliberately does NOT mean "Computational hypothesis" (the
    weakest NAMED tier); it means "not enough signal to place this on
    the hierarchy at all," which is a distinct, weaker claim. Callers
    that need a single fallback string for display can do
    `classify_evidence_hierarchy(text) or "Unclassified"` explicitly,
    rather than this function silently picking a tier for them.
    """
    if not text:
        return None
    lowered = text.lower()
    for tier_label, terms in _TIERS:
        if _has_term(lowered, terms):
            return tier_label
    return None
