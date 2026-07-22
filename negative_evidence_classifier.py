"""
Phase 4 — negative/contradictory evidence detection (audit section 4.15).

WHAT THIS FIXES
The engine currently has no concept of a study's OUTCOME DIRECTION at
all — only study TYPE (is this a clinical trial? in vitro? a
monograph?). That means a failed RCT ("no significant difference from
placebo") and a successful RCT currently classify identically as
"Clinical trial" / "Clinical / human evidence" and contribute the same
positive signal. Nothing distinguishes "this was studied and it
didn't work" from "this was studied and it worked" — which is exactly
the confirmation-bias risk the audit flagged (4.15): only positive
findings were ever effectively visible.

This module detects the specific negative-finding categories the audit
named — failed trial, null result, contradictory study, toxicity
finding, retraction, poor-quality study, insufficient dosage-form
relevance — the same way evidence_hierarchy_classifier.py detects
study type: negation-aware phrase matching, word-boundary safe.

WHAT THIS MODULE DOES NOT DO (yet)
Detection and classification only — this does not change how
_score_candidate or _decision_class weigh a candidate. A text
containing "failed to demonstrate efficacy" will, after this module is
wired into the engine, be visibly flagged as negative evidence in a
new output column — but it does not yet suppress the score/evidence-
level boost that same text's study-type markers ("randomized
controlled trial") would still separately earn. Correcting the actual
scoring behavior for a study that failed is a Phase 6 (scoring
validation) decision, made deliberately separate from "make this
visible at all," which is what audit 4.15 asked for as the immediate
fix: "must be stored and displayed."
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# Ordered by specificity — retraction and toxicity findings are checked
# first since they're the most unambiguous and most safety-critical to
# never miss; "poor quality" and "insufficient relevance" are checked
# last since their phrasing is the most generic and most likely to
# overlap with other categories' wording.
_NEGATIVE_FINDING_TYPES = [
    ("Retraction", [
        "retracted", "retraction", "article was withdrawn",
        "paper was withdrawn", "study was withdrawn",
    ]),
    ("Toxicity finding", [
        "study was terminated due to toxicity", "terminated early due to safety",
        "discontinued due to adverse events", "halted due to safety concerns",
        "stopped early due to toxicity",
    ]),
    ("Failed trial", [
        "failed to demonstrate", "failed to show", "failed to meet its primary endpoint",
        "did not meet the primary endpoint", "trial failed",
        "was not superior to placebo", "not statistically superior to placebo",
    ]),
    ("Null result", [
        "no significant difference", "no statistically significant difference",
        "not statistically significant", "no significant effect",
        "null result", "no significant improvement",
    ]),
    ("Contradictory study", [
        "contradicts", "contradict", "contradicted", "contradictory to",
        "contradictory findings", "conflicting results", "conflicting evidence",
        "inconsistent with prior",
    ]),
    ("Poor-quality study", [
        "high risk of bias", "poor methodological quality", "low-quality evidence",
        "significant methodological limitations", "underpowered study",
        "small sample size limits", "inconclusive due to study design",
    ]),
    ("Insufficient dosage-form relevance", [
        "not applicable to this dosage form", "route of administration differs",
        "not relevant to the selected dosage form", "different preparation method limits relevance",
    ]),
]

# A negation immediately before a negative-finding phrase flips its
# meaning back to neutral/positive — "did not fail to demonstrate
# efficacy" (double negative, awkward but real in paraphrased text) or
# "no retraction has been issued" must not be flagged as the negative
# finding they mention. Deliberately the SAME cue list used elsewhere
# in this codebase (evidence_hierarchy_classifier.py,
# botanical_rd_candidate_engine.py's own safety-flag extraction) for
# consistency.
_NEGATION_CUES = (
    "no ", "not ", "lack of ", "lacks ", "insufficient evidence of ",
    "absence of ", "without ", "none found", "no evidence of ",
    "unproven", "unconfirmed",
)


@dataclass
class NegativeEvidenceResult:
    is_negative: bool
    finding_types: list[str] = field(default_factory=list)
    matched_phrases: list[str] = field(default_factory=list)


def _matches(text: str, terms: list[str]) -> list[str]:
    matched = []
    for term in terms:
        pattern = re.compile(r"\b" + re.escape(term) + r"\b")
        for match in pattern.finditer(text):
            window_start = max(0, match.start() - 40)
            preceding = text[window_start:match.start()]
            if not any(cue in preceding[-30:] for cue in _NEGATION_CUES):
                matched.append(term)
                break  # one confirmed hit per term is enough
    return matched


def classify_negative_evidence(text: Optional[str]) -> NegativeEvidenceResult:
    """Scans `text` for the negative-finding categories from audit 4.15.
    A single text can match more than one category (e.g. a retracted
    trial that also reported a null result) — all matches are returned,
    not just the first."""
    if not text:
        return NegativeEvidenceResult(is_negative=False)

    lowered = text.lower()
    finding_types = []
    matched_phrases = []

    for label, terms in _NEGATIVE_FINDING_TYPES:
        hits = _matches(lowered, terms)
        if hits:
            finding_types.append(label)
            matched_phrases.extend(hits)

    return NegativeEvidenceResult(
        is_negative=bool(finding_types),
        finding_types=finding_types,
        matched_phrases=matched_phrases,
    )
