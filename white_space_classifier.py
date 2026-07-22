"""
Gap 4 — White Space is 5 distinct concepts, not 1 (architecture audit).

WHAT THIS IS
Before this module, exactly one "white space"-flavored signal existed
in the whole pipeline: Decision_Class_AH's class E ("White-space
opportunity"). The audit named 5 genuinely different concepts that
were all being collapsed into that one label (or into "we don't know",
via Market_Status's neutral defaults). This module classifies every
row into one of:

    Data Gap                    — we don't have enough data to say
                                   anything on ANY axis. Not a finding.
    Scientific White Space      — a real evidence search ran; no
                                   meaningful scientific evidence exists
                                   for this application.
    Commercial White Space      — a real commercial/product search
                                   completed; no verified product found.
    Regulatory White Space      — no monograph/traditional-use
                                   recognition exists for this use.
    Industrial R&D White Space  — the combination that's actually
                                   investable: real scientific promise
                                   DOES exist (this is NOT a Scientific
                                   White Space), but no commercial
                                   product and/or no regulatory
                                   recognition exists yet. This is the
                                   only one of the five that argues FOR
                                   R&D investment; the other four are
                                   diagnostic, not recommendations.
    (none)                      — a positive signal exists on at least
                                   one relevant axis; not a white-space
                                   candidate at all.

WHY A SEPARATE MODULE, NOT A CHANGE TO _market_status() OR _decision_class()
Every signal this module reads (Evidence_Confidence, Market_Status,
whether a live search ran) is already computed elsewhere and already
feeds Decision_Class/Decision_Class_AH. Folding a 5-way classification
into either of those functions would mean re-deriving and re-verifying
everything downstream of them (the same reason decision_class_ah.py
was built as its own module in Phase 6 rather than rewriting
_decision_class()). This reads already-computed values and adds one
more classification column — Decision_Class and Decision_Class_AH are
untouched.

HONESTY ABOUT THE ARCHITECTURAL LIMIT THIS RUNS INTO
Commercial White Space and Regulatory White Space are, in the current
architecture, both derived from the SAME single Market_Status field
(_market_status() in botanical_rd_candidate_engine.py returns one
string, not independent commercial/regulatory sub-results). That
function's "Commercial White Space" signal ("No verified product
found") is honestly still a dead code path today — see
_market_status()'s and _search_retail_products()'s own docstrings — no
real per-row retail/patent search is wired in yet. This module doesn't
paper over that: Commercial White Space stays correctly unreachable
until that search is actually wired in, exactly like Decision_Class_AH's
class A/E already are. Regulatory White Space IS reachable today,
because "no monograph found" only requires checking the ABSENCE of a
signal _market_status() already reliably detects (EMA/traditional-use
mentions), not a search that hasn't been built yet.
"""

from __future__ import annotations

from typing import Optional

# Reused from evidence_confidence.py rather than re-declared, so the
# two modules can't silently drift on what "low confidence" means.
from evidence_confidence import LOW_CONFIDENCE_THRESHOLD

# Market_Status values that mean "nothing was actually looked at",
# as opposed to "we looked and found nothing" — must match
# _market_status()'s actual vocabulary exactly (audit 4.6/4.7, Gap 2).
NO_SEARCH_MARKET_STATES = {"Search not performed", "Unknown", "Source unavailable"}

POSITIVE_REGULATORY_STATES = {"Regulatory monograph exists", "Traditional-use status"}

COMMERCIAL_WHITE_SPACE_STATE = "No verified product found"


def classify_white_space(
    evidence_confidence: float,
    market_status: str,
    use_live_search: bool,
) -> Optional[str]:
    """Returns one of the 5 white-space type labels, or None if this
    row isn't a white-space candidate at all (a positive signal exists
    on at least one relevant axis). Priority order below — first
    matching rule wins.
    """
    no_scientific_search = not use_live_search and evidence_confidence == 0
    no_market_search_signal = market_status in NO_SEARCH_MARKET_STATES

    # 1) Data Gap: nothing was looked at, on any axis. This is the
    #    "we don't know" case, and must never be reported as a finding
    #    of any kind — that's exactly the failure mode audit Gap 4
    #    named ("White Space simply because nothing was found").
    if no_scientific_search and no_market_search_signal:
        return "Data Gap"

    # A single, reused bar for "there IS real scientific signal here" —
    # used both to define Scientific White Space (its absence, when a
    # live search ran) and to gate Industrial R&D White Space (its
    # presence). Using one consistent threshold instead of two
    # different conditions (an earlier draft used a bare
    # "evidence_confidence > 0" for the Industrial check, which let
    # even a confidence of 1 override a legitimate standalone
    # Regulatory/Commercial White Space finding — caught by this
    # module's own test suite) keeps the five labels mutually
    # consistent with each other.
    real_scientific_signal = evidence_confidence >= LOW_CONFIDENCE_THRESHOLD

    scientific_white_space = use_live_search and not real_scientific_signal
    commercial_white_space = market_status == COMMERCIAL_WHITE_SPACE_STATE
    regulatory_white_space = (
        market_status not in POSITIVE_REGULATORY_STATES
        and not no_market_search_signal
    )

    # 2) Industrial R&D White Space: the one label that actually
    #    argues FOR investment — real scientific promise (evidence
    #    confidence clears the same bar Scientific White Space's
    #    absence is defined by) combined with an open commercial and/or
    #    regulatory space. Checked before the individual
    #    Commercial/Regulatory checks below so a genuinely investable
    #    candidate gets the more specific, more useful label instead of
    #    a narrower diagnostic one.
    if real_scientific_signal and (commercial_white_space or regulatory_white_space):
        return "Industrial R&D White Space"

    if scientific_white_space:
        return "Scientific White Space"

    if commercial_white_space:
        return "Commercial White Space"

    if regulatory_white_space:
        return "Regulatory White Space"

    return None
