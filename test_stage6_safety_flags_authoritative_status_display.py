"""Regression tests for the final Stage 6 stabilization item: the authoritative
structured safety state (Safety_Assertion_Status) must control what
Safety_Flags renders, instead of unconditionally trusting whatever free text
the narrower attribution scanner (_clean_safety_flags_for_plant /
safety_interaction_attribution.extract_structured_safety_interactions)
happened to extract.

Root cause: that scanner classifies a whole free-text fragment as an
"adverse event" whenever it contains a bare trigger word (e.g. "nausea"),
even when the surrounding sentence is a therapeutic-benefit claim ("reduce
chemotherapy-induced nausea"). _safety_flags_display_for_plant() then
returned that fragment unconditionally whenever it was non-empty, regardless
of what the authoritative Safety_Assertion_Status actually said -- so a
NO_SAFETY_EVIDENCE_RETRIEVED candidate could still display prose that reads
like an adverse-event narrative, and a SAFETY_CONCERN_RETRIEVED candidate
could display generic efficacy prose instead of (or in place of an absent)
genuine safety narrative.

Fix (presentation-only, in candidate_shortlisting.py):
  - _safety_flags_display_for_plant() now branches on the authoritative
    Safety_Assertion_Status FIRST.
  - NO_SAFETY_EVIDENCE_RETRIEVED always renders the standardized message;
    the free-text scanner is not even consulted.
  - INTERACTION_SIGNAL_RETRIEVED only shows interaction-specific narrative
    (_clean_interaction_flags_for_plant, which correctly reads the
    Interaction_Flags column), never an unrelated adverse-event fragment.
  - A new generic-therapeutic-prose filter (_is_generic_therapeutic_fragment)
    keeps efficacy/benefit sentences ("is recognized to ease...", "reduce
    ...nausea", "used to treat...") out of what counts as a genuine
    adverse-event narrative for CONCERN/CONFLICTING/etc, without touching
    Safety_Assertion_Status, Safety_Data_Status, or any decision threshold.

None of this changes discovery scoring, candidate ranking, evidence
adjudication, Stage-5 mechanistic logic, or safety decision thresholds --
only what text is shown next to an already-computed authoritative status.
"""

import pandas as pd

import candidate_shortlisting as cs
from safety_assertion_engine import (
    SAFETY_STATUS_CONCERN,
    SAFETY_STATUS_CONFLICTING,
    SAFETY_STATUS_INTERACTION,
    SAFETY_STATUS_NO_EVIDENCE,
)


def _group(status, level="UNKNOWN", safety_flags="", interaction_flags=""):
    return pd.DataFrame([
        {
            "Alternative_Plant": "Test plant",
            "Safety_Flags": safety_flags,
            "Interaction_Flags": interaction_flags,
            "Safety_Assertion_Status": status,
            "Safety_Concern_Level": level,
            "Safety_Evidence_IDs": "S1",
        }
    ])


# ---------------------------------------------------------------------------
# 1. Cannabis-shaped case: no safety evidence + therapeutic abstract text
#    -> standardized no-safety-evidence message, never the abstract prose.
# ---------------------------------------------------------------------------

def test_no_safety_evidence_status_forces_standard_message_over_therapeutic_abstract():
    text = cs._safety_flags_display_for_plant(
        _group(
            SAFETY_STATUS_NO_EVIDENCE,
            level="UNKNOWN",
            safety_flags=(
                "Abstract The use of Cannabis sativa is currently recognized to "
                "ease certain types of chronic pain, reduce chemotherapy-induced "
                "nausea, and improve anxiety."
            ),
        ),
        "Cannabis sativa",
    )
    assert text == (
        "No attributable adverse-event narrative was extracted; no safety-"
        "relevant evidence was retrieved."
    )
    assert "chronic pain" not in text.lower()
    assert "nausea" not in text.lower()
    assert "anxiety" not in text.lower()


# ---------------------------------------------------------------------------
# 2. Moringa-shaped case: serious structured concern + nonsafety therapeutic
#    prose -> the therapeutic prose is excluded; standardized concern message
#    is shown instead (no genuine narrative survived the filter).
# ---------------------------------------------------------------------------

def test_serious_concern_excludes_generic_therapeutic_prose():
    text = cs._safety_flags_display_for_plant(
        _group(
            SAFETY_STATUS_CONCERN,
            level="SERIOUS",
            safety_flags=(
                "Moringa oleifera is traditionally used to treat diabetes, "
                "hypertension and improve inflammation in folk medicine."
            ),
        ),
        "Moringa oleifera",
    )
    assert "traditionally used" not in text.lower()
    assert "diabetes" not in text.lower()
    assert "structured safety concern is present" in text.lower()


def test_generic_therapeutic_fragment_helper_flags_benefit_prose_generically():
    # Deliberately no plant name in these examples -- the filter is generic.
    assert cs._is_generic_therapeutic_fragment(
        "The extract is currently recognized to ease chronic pain and reduce nausea."
    )
    assert cs._is_generic_therapeutic_fragment(
        "This preparation is traditionally used to treat inflammation."
    )
    assert cs._is_generic_therapeutic_fragment(
        "The compound has been shown to have therapeutic benefits for anxiety."
    )


# ---------------------------------------------------------------------------
# 3. A genuine hepatotoxicity/adverse-event narrative remains allowed.
# ---------------------------------------------------------------------------

def test_genuine_hepatotoxicity_narrative_still_displayed_for_concern_status():
    text = cs._safety_flags_display_for_plant(
        _group(
            SAFETY_STATUS_CONCERN,
            level="SERIOUS",
            safety_flags=(
                "Plantus testus caused hepatotoxicity in three patients "
                "following long-term high-dose use of the extract."
            ),
        ),
        "Plantus testus",
    )
    assert "hepatotoxicity" in text.lower()


def test_genuine_conflicting_evidence_narrative_still_displayed():
    text = cs._safety_flags_display_for_plant(
        _group(
            SAFETY_STATUS_CONFLICTING,
            level="MODERATE",
            safety_flags="Plantus testus caused severe allergic reactions in two patients.",
        ),
        "Plantus testus",
    )
    assert "allergic reaction" in text.lower()


# ---------------------------------------------------------------------------
# 4. A genuine interaction signal remains allowed.
# ---------------------------------------------------------------------------

def test_genuine_interaction_narrative_still_displayed():
    text = cs._safety_flags_display_for_plant(
        _group(
            SAFETY_STATUS_INTERACTION,
            level="MODERATE",
            safety_flags="No explicit adverse event narrative found.",
            interaction_flags=(
                "Plantus testus may interact with warfarin, potentiating "
                "bleeding risk."
            ),
        ),
        "Plantus testus",
    )
    assert "warfarin" in text.lower()
    assert "interact" in text.lower()


def test_interaction_status_never_falls_back_to_unrelated_adverse_fragment():
    # No genuine interaction narrative extracted -> standardized interaction
    # message, never an unrelated adverse-event sentence substituted in.
    text = cs._safety_flags_display_for_plant(
        _group(
            SAFETY_STATUS_INTERACTION,
            level="MODERATE",
            safety_flags="Mild nausea was reported in one participant.",
            interaction_flags="",
        ),
        "Test plant",
    )
    assert text == (
        "No attributable adverse-event narrative was extracted; an interaction-"
        "type safety signal is present — see Safety_Status_Rationale."
    )
    assert "nausea" not in text.lower()
