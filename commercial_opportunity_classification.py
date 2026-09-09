"""Commercial_Opportunity_Class -- a single, interpretable investor-facing
label built ONLY from already-computed, already-tested fields.

WHAT THIS IS
market_intelligence_engine.py already computes real, deterministic
Commercial_Status_Overall / Commercial_Status_For_Indication /
Commercial_Novelty_Status / Indication_Market_Saturation values (see that
module's _commercial_novelty_status()/_commercial_positioning()). Those are
correct but are free-text sentences meant for a caption, not a short,
scannable, filterable label. This module adds ONE new column,
Commercial_Opportunity_Class, that maps those same signals -- plus the
existing safety/regulatory hard-stop signals (RD_Discovery_Lane,
Regulatory_Prohibition_Present, Safety_Concern_Level,
Safety_Assertion_Status) -- onto a small fixed vocabulary of investor
labels. It recomputes nothing: every input here already exists on the
report-ready row.

WHY A SEPARATE MODULE (same rationale as white_space_classifier.py)
Every signal this module reads is already computed elsewhere and already
feeds the existing Commercial_Novelty_Status/Commercial_Positioning
strings. Folding a 9-way classification into market_intelligence_engine.py
itself would mean re-deriving and re-verifying everything already tested
there. This reads already-computed values and adds one more column.

PRECEDENCE (first matching rule wins -- see classify_commercial_opportunity)
    1. SAFETY_DE_RISKING_REQUIRED   -- a serious/conflicting safety signal
                                        must be seen before any commercial
                                        framing (Section 19: "a regulatory
                                        prohibition or hard safety stop
                                        must not be presented as a
                                        commercial go recommendation").
    2. REGULATORY_CONSTRAINED       -- a real regulatory barrier exists.
    3. INSUFFICIENT_MARKET_DATA     -- commercial search never produced
                                        usable evidence on either axis.
                                        Never guessed from a missing value.
    4. CROWDED_MARKET               -- verified marketed for this
                                        indication AND saturation is HIGH.
    5. COMMERCIALLY_ESTABLISHED     -- verified marketed for this
                                        indication (saturation not HIGH,
                                        or not established).
    6/6b. EMERGING_/ESTABLISHED_BOTANICAL_NEW_INDICATION, else
          REPURPOSING_OPPORTUNITY  -- product(s) verified marketed
                                        OVERALL but NOT for this specific
                                        indication (see threshold note
                                        below).
    7. WHITE_SPACE_OPPORTUNITY      -- no verified product anywhere
                                        (overall or for this indication)
                                        AND real scientific signal exists
                                        for this candidate.
    (none / None)                   -- doesn't fit any of the above
                                        (e.g. commercial data is usable but
                                        ambiguous, or there is no
                                        scientific signal either --
                                        white_space_classifier.py's
                                        Scientific White Space/Data Gap
                                        already covers that case; this
                                        module does not duplicate it).

AN EXPLICIT, FLAGGED DESIGN CHOICE (Section 10: "choose the threshold
deliberately, document it, and test it")
The spec's 9-label vocabulary has two labels --
EMERGING_BOTANICAL_NEW_INDICATION and ESTABLISHED_BOTANICAL_NEW_INDICATION
-- whose intended distinction from each other, and from the simpler
REPURPOSING_OPPORTUNITY, is not itself fully specified. This module reads
them as a finer split of the same underlying case (a botanical with real
commercial presence generally, but not yet for the queried indication),
distinguished by how commercially established the botanical already is
overall, via Overall_Product_Hits:
    Overall_Product_Hits >= ESTABLISHED_OVERALL_PRODUCT_THRESHOLD (10)
        -> ESTABLISHED_BOTANICAL_NEW_INDICATION
    0 < Overall_Product_Hits < threshold
        -> EMERGING_BOTANICAL_NEW_INDICATION
    Overall_Product_Hits unusable/unknown (search ran but count isn't
    trustworthy, e.g. COMMERCIAL_PRESENCE_INDICATION_UNCLEAR)
        -> REPURPOSING_OPPORTUNITY (the safe, generic label -- this
           module never invents precision Commercial_Status_For_Indication
           itself doesn't have)
This is a judgment call, not a verified requirement -- flagged here and in
the delivery notes for architecture review, exactly like every other
interpretive decision in this codebase.
"""

from __future__ import annotations

from typing import Optional

try:
    from rd_discovery_classification import (
        DISCOVERY_LANE_REGULATORY_STOP,
        DISCOVERY_LANE_SAFETY_STOP,
    )
except ImportError:  # pragma: no cover - defensive only, module always present in-repo
    DISCOVERY_LANE_REGULATORY_STOP = "Regulatory Prohibition"
    DISCOVERY_LANE_SAFETY_STOP = "Not Currently Developable (Safety)"

OPP_SAFETY_DE_RISKING_REQUIRED = "SAFETY_DE_RISKING_REQUIRED"
OPP_REGULATORY_CONSTRAINED = "REGULATORY_CONSTRAINED"
OPP_INSUFFICIENT_MARKET_DATA = "INSUFFICIENT_MARKET_DATA"
OPP_CROWDED_MARKET = "CROWDED_MARKET"
OPP_COMMERCIALLY_ESTABLISHED = "COMMERCIALLY_ESTABLISHED"
OPP_ESTABLISHED_BOTANICAL_NEW_INDICATION = "ESTABLISHED_BOTANICAL_NEW_INDICATION"
OPP_EMERGING_BOTANICAL_NEW_INDICATION = "EMERGING_BOTANICAL_NEW_INDICATION"
OPP_REPURPOSING_OPPORTUNITY = "REPURPOSING_OPPORTUNITY"
OPP_WHITE_SPACE_OPPORTUNITY = "WHITE_SPACE_OPPORTUNITY"

ALL_COMMERCIAL_OPPORTUNITY_CLASSES = (
    OPP_SAFETY_DE_RISKING_REQUIRED,
    OPP_REGULATORY_CONSTRAINED,
    OPP_INSUFFICIENT_MARKET_DATA,
    OPP_CROWDED_MARKET,
    OPP_COMMERCIALLY_ESTABLISHED,
    OPP_ESTABLISHED_BOTANICAL_NEW_INDICATION,
    OPP_EMERGING_BOTANICAL_NEW_INDICATION,
    OPP_REPURPOSING_OPPORTUNITY,
    OPP_WHITE_SPACE_OPPORTUNITY,
)

# Deliberately chosen, adjustable, documented threshold (see module
# docstring). Not derived from any dataset; a round number picked to
# separate "a couple of niche listings" from "a genuinely established
# commercial botanical" for the purposes of this one label split only --
# it never feeds scoring.
ESTABLISHED_OVERALL_PRODUCT_THRESHOLD = 10

_SERIOUS_SAFETY_LEVELS = {"SERIOUS"}
_CONFLICTING_SAFETY_STATUSES = {"CONFLICTING_SAFETY_EVIDENCE"}

_VERIFIED_FOR_INDICATION = "VERIFIED_MARKETED_FOR_INDICATION"
_NO_PRODUCT_FOR_INDICATION = "NO_VERIFIED_PRODUCT_FOR_INDICATION_IN_COVERED_SOURCES"
_NO_PRODUCT_OVERALL = "NO_VERIFIED_PRODUCT_FOUND_IN_COVERED_SOURCES"
_VERIFIED_OVERALL = "VERIFIED_MARKETED"
_NO_SEARCH_SIGNAL = {"UNKNOWN", "NOT_REQUESTED", ""}


def _num_or_none(value) -> Optional[float]:
    if value is None:
        return None
    try:
        if isinstance(value, str) and not value.strip():
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _has_real_scientific_signal(row) -> bool:
    """Reuses whichever scientific-strength signal is already on the row --
    never recomputed. Discovery_Potential_Score / Evidence_Maturity_Score
    (rd_discovery_classification.py) are preferred; Scientific_Triage_Status
    != "Excluded" is the fallback for rows built without those columns.
    """
    for field in ("Discovery_Potential_Score", "Evidence_Maturity_Score"):
        value = _num_or_none(row.get(field))
        if value is not None and value > 0:
            return True
    triage = row.get("Scientific_Triage_Status")
    if triage is not None and str(triage).strip() and str(triage).strip() != "Excluded":
        return True
    return False


def classify_commercial_opportunity(row) -> Optional[str]:
    """Returns one of ALL_COMMERCIAL_OPPORTUNITY_CLASSES, or None if this
    row doesn't cleanly fit any of them. ``row`` may be a dict or a pandas
    Series (anything supporting ``.get``); every field read here is
    optional -- a missing field is treated as "unknown", never guessed.
    """
    rd_discovery_lane = row.get("RD_Discovery_Lane")
    safety_concern_level = str(row.get("Safety_Concern_Level", "") or "").strip().upper()
    safety_assertion_status = str(row.get("Safety_Assertion_Status", "") or "").strip()

    # 1) Safety must be seen before any commercial framing.
    if (
        rd_discovery_lane == DISCOVERY_LANE_SAFETY_STOP
        or safety_concern_level in _SERIOUS_SAFETY_LEVELS
        or safety_assertion_status in _CONFLICTING_SAFETY_STATUSES
    ):
        return OPP_SAFETY_DE_RISKING_REQUIRED

    # 2) Regulatory barrier.
    regulatory_prohibition = bool(row.get("Regulatory_Prohibition_Present", False))
    if rd_discovery_lane == DISCOVERY_LANE_REGULATORY_STOP or regulatory_prohibition:
        return OPP_REGULATORY_CONSTRAINED

    overall_status = str(row.get("Commercial_Status_Overall", "") or "").strip()
    indication_status = str(row.get("Commercial_Status_For_Indication", "") or "").strip()

    # 3) No usable commercial evidence on either axis -- never guessed.
    if overall_status in _NO_SEARCH_SIGNAL and indication_status in _NO_SEARCH_SIGNAL:
        return OPP_INSUFFICIENT_MARKET_DATA
    # A search ran but only produced an unclear/unverifiable read on the
    # indication axis (COMMERCIAL_PRESENCE_INDICATION_UNCLEAR and similar):
    # also insufficient for a confident classification -- this module never
    # invents precision the underlying search doesn't have.
    if indication_status not in (
        _VERIFIED_FOR_INDICATION, _NO_PRODUCT_FOR_INDICATION,
    ) and indication_status not in _NO_SEARCH_SIGNAL and overall_status in _NO_SEARCH_SIGNAL:
        return OPP_INSUFFICIENT_MARKET_DATA

    # 4/5) Already verified marketed for this exact indication.
    if indication_status == _VERIFIED_FOR_INDICATION:
        saturation = str(row.get("Indication_Market_Saturation", "") or "").strip().upper()
        if saturation == "HIGH":
            return OPP_CROWDED_MARKET
        return OPP_COMMERCIALLY_ESTABLISHED

    # 6) Marketed overall, but not verified for this specific indication --
    #    a repurposing-shaped opportunity. Sub-split by how commercially
    #    established the botanical already is overall (see module
    #    docstring for the documented, flagged threshold choice).
    if indication_status == _NO_PRODUCT_FOR_INDICATION and overall_status == _VERIFIED_OVERALL:
        overall_hits = _num_or_none(row.get("Overall_Product_Hits"))
        if overall_hits is not None and overall_hits >= ESTABLISHED_OVERALL_PRODUCT_THRESHOLD:
            return OPP_ESTABLISHED_BOTANICAL_NEW_INDICATION
        if overall_hits is not None and overall_hits > 0:
            return OPP_EMERGING_BOTANICAL_NEW_INDICATION
        return OPP_REPURPOSING_OPPORTUNITY

    # 7) Nothing verified anywhere -- a genuine commercial white space,
    #    but only worth the label if real science backs the candidate
    #    (otherwise this is a scientific gap, not a commercial finding --
    #    see white_space_classifier.py's Scientific White Space/Data Gap).
    if indication_status == _NO_PRODUCT_FOR_INDICATION and overall_status == _NO_PRODUCT_OVERALL:
        if _has_real_scientific_signal(row):
            return OPP_WHITE_SPACE_OPPORTUNITY
        return None

    return None


def add_commercial_opportunity_class(df):
    """Vectorized (row-wise, deterministic) helper: adds
    Commercial_Opportunity_Class to a copy of ``df``. Never mutates the
    input, never touches any existing column, never recomputes any
    upstream commercial/safety/regulatory field. Returns ``df`` unchanged
    (not a copy) if it isn't a usable DataFrame -- mirrors the
    defensive-return convention used throughout this codebase (see
    white_space_discovery_engine.py, rd_discovery_classification.py).
    """
    import pandas as pd  # local import matches this module's light footprint

    if not isinstance(df, pd.DataFrame) or df.empty:
        return df
    out = df.copy()
    out["Commercial_Opportunity_Class"] = [
        classify_commercial_opportunity(row) for _, row in out.iterrows()
    ]
    return out
