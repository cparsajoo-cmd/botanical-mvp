"""
Critical Safety False-Negative Remediation — Serious Interaction /
Contraindication Gate regression tests (Case 006 / Hypericum
perforatum audit finding).

WHAT WAS BROKEN (verified by reading the code, not assumed)
botanical_rd_candidate_engine.py's hard safety stop was reachable only
via Safety_Flags ∩ HARD_SAFETY_TERMS, and HARD_SAFETY_TERMS was
exclusively DB_ACTIVITY_SAFETY_TERMS (compound-activity vocabulary:
"lithogenic", "abortifacient", etc. -- see that module's own
comments). Interaction_Flags (built from INTERACTION_TERMS: "cyp",
"anticoagulant", ...) was extracted and displayed but never fed into
any gating decision -- confirmed by inspection that the
`interaction_flags` parameter accepted by `_decision_class()` is never
referenced in that method's body. A source stating a genuine, serious,
high-risk drug-interaction contraindication (e.g. an EMA monograph's
Section 4.3, naming anticoagulants / immunosuppressants / protease
inhibitors / cytotoxic agents metabolised via CYP3A4/P-glycoprotein)
therefore fell straight through to ELIGIBLE with no gate ever firing.

THE FIX
interaction_severity_classifier.py adds a third, independent,
generic, text-based structured-assertion channel (Safety Evidence ->
assertion language -> drug-class detection -> severity via the
existing, unmodified severity_assignment_policy.py -> tier). It
contributes exactly ONE new hard-hit term
(HARD_GATE_SIGNAL_TERM) to botanical_rd_candidate_engine.HARD_SAFETY_TERMS,
reachable ONLY when BOTH explicit contraindication/serious-interaction
language AND a recognized high-risk interacting drug class are present
in the same sentence-level unit -- never from a bare hazard word. This
one addition automatically fixes every downstream consumer of
Safety_Flags (the row-level eligibility computation, _decision_class(),
_evaluate_gates(), _hard_safety_gate()) through the SAME
Safety_Flags-string mechanism every other hard-safety signal already
uses -- eligibility_gate.py's own decision table is untouched.

NO PLANT-SPECIFIC OR CASE-SPECIFIC HACK
Nowhere in interaction_severity_classifier.py or in these tests does a
plant name, taxon, PMID, or EMA document ID drive the logic. Every
fixture plant name below ("AltPlantSeriousInteraction",
"AltPlantAntiretroviral", ...) is a synthetic, throwaway identifier --
the classifier has no branch conditioned on any of them, only on the
generic assertion-language + drug-class vocabulary.
"""

import pandas as pd
import pytest

import botanical_rd_candidate_engine as eng
from data_contracts import GateStatus
from eligibility_gate import RankingPartition
from interaction_severity_classifier import (
    classify_interaction_assertion,
    hard_hit_terms_for,
    informational_terms_for,
    InteractionSeverityTier,
    HARD_GATE_SIGNAL_TERM,
)
from test_gate_layer import make_engine

# Real EMA-style contraindication text -- generic wording naming
# several of severity_assignment_policy.py's already-approved
# HighRiskInteractionDrugClass substances, mirroring the shape of
# Section 4.3 of the actual EU herbal monograph the Case 006 audit
# investigated. No document ID, PMID, or plant name is embedded in
# the classifier's own logic -- only this fixture's text uses them.
_SERIOUS_CONTRAINDICATION_TEXT = (
    "Concomitant use with coumarin-type anticoagulants, cyclosporine, "
    "everolimus, sirolimus, tacrolimus for systemic use, fosamprenavir, "
    "indinavir and other protease inhibitors, nucleoside reverse "
    "transcriptase inhibitors, irinotecan, imatinib and other cytostatic "
    "agents metabolised by CYP3A4, CYP2B6, CYP2C9, CYP2C19 or transported "
    "by P-glycoprotein is contraindicated."
)


def _reset_engine_globals():
    eng.SIMILAR_COMPOUND_GROUPS = {}
    eng.COMPOUND_TARGETS = {}


def _two_plant_rows(ref="RefPlant", alt="AltPlant"):
    return [
        dict(scientific_name=ref, compound_name="SharedCompound",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name=alt, compound_name="SharedCompound",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
    ]


def _run_with_notes(notes, ref="RefPlant", alt="AltPlant", evidence_record_id=None):
    _reset_engine_globals()
    rows = _two_plant_rows(ref=ref, alt=alt)
    ev = {
        "Scientific_Name": alt,
        "Target_Indication": "TestIndication",
        "Notes": notes,
    }
    if evidence_record_id is not None:
        ev["Evidence_Record_ID"] = evidence_record_id
    evidence_df = pd.DataFrame([ev])
    engine = make_engine(rows)
    engine.evidence_df = evidence_df
    result = engine.run(indication="TestIndication", dosage_form="Infusion", market="EU")
    return result[
        (result["Reference_Plant"] == ref) & (result["Alternative_Plant"] == alt)
    ].iloc[0]


# =======================================================================
# 1) REGRESSION -- Case 006 style false negative is fixed.
#    BEFORE this fix: this exact text produced Eligibility_Status ==
#    "eligible", Eligible_For_Normal_Ranking == True, and
#    Gate_Results["safety"]["status"] == GateStatus.PASSED (verified by
#    reverting interaction_severity_classifier.py's contribution to
#    HARD_SAFETY_TERMS locally and re-running this exact test during
#    development of this fix -- it failed with the false-negative
#    values just described). AFTER: as asserted below.
# =======================================================================

def test_case006_style_serious_contraindication_is_no_longer_a_false_negative():
    row = _run_with_notes(_SERIOUS_CONTRAINDICATION_TEXT, alt="AltPlantCase006Regression")

    # Was "eligible" / True / PASSED before this fix -- see module
    # docstring. Now: never ELIGIBLE, never PASSED.
    assert row["Eligibility_Status"] != "eligible"
    assert bool(row["Eligible_For_Normal_Ranking"]) is False
    assert row["Gate_Results"]["safety"]["status"] == GateStatus.FAILED

    # Missing-context requirement (item 6): production never confirms
    # scope, so this resolves to EXPERT_REVIEW_REQUIRED, not an
    # automatic NO_GO_SAFETY -- but it is never a silent PASS either.
    assert row["Eligibility_Status"] == "expert_review_required"
    assert row["Gate_Results"]["eligibility"]["status"] == "expert_review_required"
    assert row["Decision_Class"].startswith("Expert review required")

    # Non-compensation (item 5, ranking half): never lands in the
    # normal ranking partition regardless of score.
    assert row["Ranking_Partition"] == RankingPartition.PRELIMINARY_OR_EXPERT_REVIEW.value
    assert row["Ranking_Partition"] != RankingPartition.NORMAL.value

    # Traceable back to the structured signal, not a guess.
    assert HARD_GATE_SIGNAL_TERM in row["Safety_Flags"]


# =======================================================================
# 2) POSITIVE CONTROLS -- generic, non-Hypericum serious cases must
#    also be blocked/expert-reviewed. Two independent drug classes,
#    two independent synthetic plant names.
# =======================================================================

def test_positive_control_anticoagulant_interaction_is_expert_review_or_worse():
    row = _run_with_notes(
        "This extract must not be co-administered with anticoagulant "
        "medication due to a clinically significant increase in bleeding risk.",
        alt="AltPlantAnticoagulantInteraction",
    )
    assert row["Eligibility_Status"] != "eligible"
    assert bool(row["Eligible_For_Normal_Ranking"]) is False
    assert row["Gate_Results"]["safety"]["status"] == GateStatus.FAILED
    assert row["Ranking_Partition"] != RankingPartition.NORMAL.value


def test_positive_control_immunosuppressant_and_antiretroviral_contraindication_is_blocked():
    row = _run_with_notes(
        "Concurrent use with transplant immunosuppressants such as tacrolimus, "
        "or with antiretroviral protease inhibitors, should be avoided.",
        alt="AltPlantImmunosuppressantAntiretroviral",
    )
    assert row["Eligibility_Status"] != "eligible"
    assert bool(row["Eligible_For_Normal_Ranking"]) is False
    assert row["Gate_Results"]["safety"]["status"] == GateStatus.FAILED


# =======================================================================
# 3) NEGATIVE CONTROLS -- must NOT be auto-blocked. False positives on
#    mild/caution/theoretical/absent interactions are exactly what the
#    remediation must avoid.
# =======================================================================

def test_negative_control_mild_non_high_risk_interaction_stays_eligible():
    row = _run_with_notes(
        "This extract may interact with common over-the-counter antacids.",
        alt="AltPlantMildInteraction",
    )
    assert row["Eligibility_Status"] == "eligible"
    assert bool(row["Eligible_For_Normal_Ranking"]) is True
    assert row["Gate_Results"]["safety"]["status"] == GateStatus.PASSED
    assert HARD_GATE_SIGNAL_TERM not in row["Safety_Flags"]


def test_negative_control_caution_only_language_stays_eligible():
    row = _run_with_notes(
        "Caution is advised when using this product with other medications.",
        alt="AltPlantCautionOnly",
    )
    assert row["Eligibility_Status"] == "eligible"
    assert row["Gate_Results"]["safety"]["status"] == GateStatus.PASSED
    assert HARD_GATE_SIGNAL_TERM not in row["Safety_Flags"]


def test_negative_control_theoretical_mechanistic_only_stays_eligible():
    row = _run_with_notes(
        "The compound is a known inhibitor of CYP3A4 in vitro.",
        alt="AltPlantTheoreticalMechanistic",
    )
    assert row["Eligibility_Status"] == "eligible"
    assert row["Gate_Results"]["safety"]["status"] == GateStatus.PASSED
    assert HARD_GATE_SIGNAL_TERM not in row["Safety_Flags"]


def test_negative_control_no_interaction_stays_eligible():
    row = _run_with_notes(
        "No known drug interactions have been reported for this extract.",
        alt="AltPlantNoInteraction",
    )
    assert row["Eligibility_Status"] == "eligible"
    assert row["Gate_Results"]["safety"]["status"] == GateStatus.PASSED
    assert HARD_GATE_SIGNAL_TERM not in row["Safety_Flags"]


def test_negative_control_explicit_negation_not_contraindicated_stays_eligible():
    row = _run_with_notes(
        "This product is not contraindicated with anticoagulant therapy "
        "based on current data, and did not interact with warfarin in a "
        "controlled pharmacokinetic study.",
        alt="AltPlantExplicitNegation",
    )
    assert row["Eligibility_Status"] == "eligible"
    assert row["Gate_Results"]["safety"]["status"] == GateStatus.PASSED
    assert HARD_GATE_SIGNAL_TERM not in row["Safety_Flags"]


# =======================================================================
# 4) WORDING ROBUSTNESS -- several semantically-equivalent
#    contraindication/interaction phrasings, not one literal string.
# =======================================================================

@pytest.mark.parametrize("phrasing", [
    "concomitant use is contraindicated with cyclosporine and other "
    "transplant immunosuppressants",
    "must not be co-administered with cyclosporine or other transplant "
    "immunosuppressants",
    "should not be co-administered with cyclosporine, a transplant "
    "immunosuppressant",
    "concurrent use with cyclosporine, a transplant immunosuppressant, "
    "should be avoided",
    "do not combine with cyclosporine, a transplant immunosuppressant",
    "not recommended for concomitant use with cyclosporine, a transplant "
    "immunosuppressant",
])
def test_wording_robustness_across_equivalent_contraindication_phrasings(phrasing):
    result = classify_interaction_assertion(phrasing)
    assert result.tier == InteractionSeverityTier.SERIOUS_CONTRAINDICATION
    assert hard_hit_terms_for(result) == frozenset({HARD_GATE_SIGNAL_TERM})


# =======================================================================
# 5) NON-COMPENSATION -- a candidate with strong scientific/market
#    signal is still excluded from normal ranking when a serious
#    contraindication is present.
# =======================================================================

def test_non_compensation_high_signal_candidate_still_not_normal_ranking():
    _reset_engine_globals()
    rows = [
        dict(scientific_name="RefPlant", compound_name="SharedCompound",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="AltPlantHighSignalButSerious", compound_name="SharedCompound",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
    ]
    # Strong positive scientific signal (randomized controlled trial,
    # clear benefit) PLUS the serious contraindication in the same
    # evidence text -- proves score/evidence strength cannot buy an
    # exit from the hard gate.
    evidence_df = pd.DataFrame([{
        "Scientific_Name": "AltPlantHighSignalButSerious",
        "Target_Indication": "TestIndication",
        "Notes": (
            "A large randomized controlled trial in humans found a "
            "significant, clinically meaningful benefit for TestIndication "
            "with a well-established, EU-recognized regulatory market status. "
            + _SERIOUS_CONTRAINDICATION_TEXT
        ),
    }])
    engine = make_engine(rows)
    engine.evidence_df = evidence_df
    result = engine.run(indication="TestIndication", dosage_form="Infusion", market="EU")
    row = result[
        (result["Reference_Plant"] == "RefPlant")
        & (result["Alternative_Plant"] == "AltPlantHighSignalButSerious")
    ].iloc[0]

    assert row["Ranking_Partition"] != RankingPartition.NORMAL.value
    assert bool(row["Eligible_For_Normal_Ranking"]) is False
    assert row["Gate_Results"]["safety"]["status"] == GateStatus.FAILED


# =======================================================================
# 6) MISSING CONTEXT -- a serious assertion with unconfirmed scope
#    must never resolve to PASS/ELIGIBLE. Production never supplies a
#    confirmed scope today (see eligibility_gate.py), so every SERIOUS_*
#    tier necessarily lands here -- same assertion repeated explicitly
#    for traceability against the acceptance criteria.
# =======================================================================

def test_missing_context_never_resolves_to_eligible():
    row = _run_with_notes(_SERIOUS_CONTRAINDICATION_TEXT, alt="AltPlantMissingContext")
    assert row["Eligibility_Status"] in {"expert_review_required", "no_go_safety", "no_go_regulatory"}
    assert row["Eligibility_Status"] != "eligible"
    assert row["Eligibility_Status"] != "eligible_with_restrictions"


# =======================================================================
# 7) TRACEABILITY -- the gate outcome traces back to the specific
#    contributing EvidenceRecord, using the same
#    Safety_Gate_Evidence_IDs / Gate_Evidence_IDs mechanism
#    test_phase4_eligibility_gate_desired_behavior.py already
#    established for the structured-target channel.
# =======================================================================

def test_traceability_to_specific_evidence_record_id():
    _reset_engine_globals()
    rows = _two_plant_rows(alt="AltPlantTraceability")
    evidence_df = pd.DataFrame([
        {
            "Evidence_Record_ID": "EV-EFFICACY-001",
            "Scientific_Name": "AltPlantTraceability",
            "Target_Indication": "TestIndication",
            "Notes": "A randomized controlled trial found improved digestive comfort with no adverse events reported.",
        },
        {
            "Evidence_Record_ID": "EV-INTERACTION-002",
            "Scientific_Name": "AltPlantTraceability",
            "Target_Indication": "TestIndication",
            "Notes": _SERIOUS_CONTRAINDICATION_TEXT,
        },
    ])
    engine = make_engine(rows)
    engine.evidence_df = evidence_df
    result = engine.run(indication="TestIndication", dosage_form="Infusion", market="EU")
    row = result[
        (result["Reference_Plant"] == "RefPlant") & (result["Alternative_Plant"] == "AltPlantTraceability")
    ].iloc[0]

    assert row["Eligibility_Status"] == "expert_review_required"
    safety_ids = [x.strip() for x in str(row["Safety_Gate_Evidence_IDs"]).split(";") if x.strip()]
    assert safety_ids == ["EV-INTERACTION-002"]
    assert "EV-EFFICACY-001" not in safety_ids

    gate_ids = [x.strip() for x in str(row["Gate_Evidence_IDs"]).split(";") if x.strip()]
    assert "EV-INTERACTION-002" in gate_ids
    assert "EV-EFFICACY-001" not in gate_ids


# =======================================================================
# 8) SAFETY_TERMS / HARD_SAFETY_TERMS boundary -- the pre-existing
#    disjointness invariant (engine_evidence_input.py,
#    test_gold_case_execution.py) still holds for DB_ACTIVITY_SAFETY_TERMS;
#    the ONE new exception is HARD_GATE_SIGNAL_TERM, and it is reachable
#    only through the structured classifier, never a bare substring.
# =======================================================================

def test_hard_safety_terms_and_safety_terms_still_disjoint_except_for_structured_interaction_signal():
    overlap = eng.HARD_SAFETY_TERMS & set(eng.SAFETY_TERMS)
    assert overlap == set()
    assert HARD_GATE_SIGNAL_TERM in eng.HARD_SAFETY_TERMS
    assert eng.HARD_SAFETY_TERMS - {HARD_GATE_SIGNAL_TERM} == (
        set(eng.DB_ACTIVITY_SAFETY_TERMS) - {
            "emetic", "irritant",
            "carcinogenic", "mutagenic", "genotoxic",
            "hepatotoxic", "hepatotoxin", "nephrotoxic", "nephrotoxin",
            "cardiotoxic", "neurotoxic",
        }
    )


def test_capability_boundary_bare_hazard_word_still_cannot_trigger_hard_gate():
    """Same fixture as
    test_gold_case_execution.py::test_capability_boundary_notes_alone_cannot_trigger_hard_safety_gate
    -- proves the new channel does NOT loosen the existing boundary for
    non-drug-interaction hazard language. "Contraindicated in pregnancy"
    has no recognized high-risk drug class, so it must not reach
    HARD_GATE_SIGNAL_TERM."""
    result = classify_interaction_assertion(
        "Documented lithogenic activity; case reports describe kidney "
        "stone formation. Contraindicated in pregnancy. Serious risk."
    )
    assert result.tier != InteractionSeverityTier.SERIOUS_CONTRAINDICATION
    assert hard_hit_terms_for(result) == frozenset()


# =======================================================================
# 9) same_plant note (documented, known residual consideration -- see
#    the phase report). The legacy "safety" Gate_Results key is
#    intentionally NOT_EVALUABLE for a same_plant self-row (pre-existing,
#    unrelated design -- see _hard_safety_gate()'s own docstring); the
#    AUTHORITATIVE Eligibility_Status/Eligible_For_Normal_Ranking fields
#    are NOT same_plant-gated and still resolve correctly.
# =======================================================================

def test_same_plant_self_row_eligibility_status_still_correct_even_though_legacy_gate_is_not_evaluable():
    _reset_engine_globals()
    rows = [
        dict(scientific_name="SelfPlant", compound_name="OwnCompound",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
    ]
    evidence_df = pd.DataFrame([{
        "Scientific_Name": "SelfPlant",
        "Target_Indication": "TestIndication",
        "Notes": _SERIOUS_CONTRAINDICATION_TEXT,
    }])
    engine = make_engine(rows)
    engine.evidence_df = evidence_df
    result = engine.run(indication="TestIndication", dosage_form="Infusion", market="EU")
    self_row = result[
        (result["Reference_Plant"] == "SelfPlant") & (result["Alternative_Plant"] == "SelfPlant")
    ].iloc[0]

    # Legacy gate: documented, pre-existing same_plant exemption.
    assert self_row["Gate_Results"]["safety"]["status"] == GateStatus.NOT_EVALUABLE
    # Authoritative field: NOT same_plant-gated, correctly not eligible.
    assert self_row["Eligibility_Status"] != "eligible"
    assert bool(self_row["Eligible_For_Normal_Ranking"]) is False
