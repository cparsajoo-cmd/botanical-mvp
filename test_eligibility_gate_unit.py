"""
Phase 4 — unit tests for eligibility_gate.py's pure decision logic.

These test the module in isolation (no engine, no DataFrame, no
Streamlit) — the model/policy described in the Phase 4 design review.
Wiring these into the live production path is covered separately by
test_phase4_eligibility_gate_desired_behavior.py.
"""
from __future__ import annotations

from eligibility_gate import (
    ContextRelevance,
    DataCompleteness,
    EligibilityStatus,
    FindingScope,
    RegulatoryDataStatus,
    RegulatoryFinding,
    SafetyFinding,
    SafetySeverity,
    ScoreValidity,
    classify_regulatory_finding,
    classify_safety_finding,
    evaluate_eligibility,
)


def _clear_reg(same_plant=False, has_evidence_text=True):
    return classify_regulatory_finding(
        barrier_types=frozenset(), has_evidence_text=has_evidence_text, same_plant=same_plant
    )


def _clear_safety(same_plant=False, has_evidence_text=True):
    return classify_safety_finding(
        hit_terms=frozenset(), has_evidence_text=has_evidence_text, same_plant=same_plant
    )


# --- 1. CONFIRMED relevant severe toxicity -> NO_GO_SAFETY -------------
# (Correction round: being a different alternative plant is NOT, by
# itself, evidence of species-wide/relevant scope — see module
# docstring. NO_GO_SAFETY now requires a CONFIRMED scope/relevance,
# supplied explicitly here via confirmed_scope/confirmed_context_relevance
# — exactly the honest, non-fabricated signal a future structured-data
# caller would supply. The live production pipeline never passes these
# today; see test_relevant_severe_toxicity_without_confirmed_scope_is_expert_review_not_no_go
# below for what production actually produces right now.)
def test_relevant_severe_toxicity_with_confirmed_scope_is_no_go_safety():
    safety = classify_safety_finding(
        hit_terms=frozenset({"teratogenic"}), has_evidence_text=True, same_plant=False,
        confirmed_scope=FindingScope.SPECIES_WIDE,
        confirmed_context_relevance=ContextRelevance.RELEVANT,
    )
    decision = evaluate_eligibility(safety, _clear_reg())
    assert decision.status == EligibilityStatus.NO_GO_SAFETY
    assert decision.hard_no_go is True
    assert decision.eligible_for_normal_ranking is False
    assert decision.score_validity == ScoreValidity.AUDIT_ONLY


# --- 1b. WITHOUT a confirmed scope, the exact same hit term must NOT
# resolve to NO_GO_SAFETY -- this is the actual current production
# behavior (no confirmed_scope/confirmed_context_relevance is ever
# passed by botanical_rd_candidate_engine.py's live row-building loop).
def test_relevant_severe_toxicity_without_confirmed_scope_is_expert_review_not_no_go():
    safety = classify_safety_finding(
        hit_terms=frozenset({"teratogenic"}), has_evidence_text=True, same_plant=False,
    )
    decision = evaluate_eligibility(safety, _clear_reg())
    assert decision.status == EligibilityStatus.EXPERT_REVIEW_REQUIRED
    assert decision.status != EligibilityStatus.NO_GO_SAFETY
    assert decision.status != EligibilityStatus.ELIGIBLE
    assert decision.eligible_for_normal_ranking is False


# --- 2. minor adverse effect -> warning only, still ELIGIBLE -----------
# (Correction round item 7: a minor/non-hard safety term is warning-
# only and must NOT automatically restrict eligibility. It stays fully
# traceable via Safety_Severity="minor" and gate_reason on the same
# decision, without gating normal ranking.)
def test_minor_adverse_effect_stays_eligible_not_restricted():
    safety = classify_safety_finding(
        hit_terms=frozenset(), flagged_terms=frozenset({"adverse"}),
        has_evidence_text=True, same_plant=False,
    )
    assert safety.severity == SafetySeverity.MINOR
    decision = evaluate_eligibility(safety, _clear_reg())
    assert decision.status == EligibilityStatus.ELIGIBLE
    assert decision.status != EligibilityStatus.ELIGIBLE_WITH_RESTRICTIONS
    assert decision.hard_no_go is False
    assert decision.eligible_for_normal_ranking is True
    assert "adverse" in decision.gate_reason.lower()


# --- 3. unknown safety scope + severe finding -> expert review ---------
def test_unknown_scope_severe_finding_requires_expert_review_not_pass():
    safety = classify_safety_finding(
        hit_terms=frozenset({"convulsant"}), has_evidence_text=True, same_plant=True
    )
    decision = evaluate_eligibility(safety, _clear_reg(same_plant=True))
    assert decision.status == EligibilityStatus.EXPERT_REVIEW_REQUIRED
    assert decision.status != EligibilityStatus.ELIGIBLE
    assert decision.eligible_for_normal_ranking is False
    assert decision.requires_expert_review is True


# --- 4. confirmed irrelevant preparation -> no automatic hard no-go ----
def test_confirmed_irrelevant_scope_does_not_auto_no_go():
    safety = SafetyFinding(
        severity=SafetySeverity.SEVERE, scope=FindingScope.PREPARATION_SPECIFIC,
        context_relevance=ContextRelevance.IRRELEVANT, data_completeness=DataCompleteness.COMPLETE,
        same_plant=True, hit_terms=frozenset({"hemolytic"}),
        reason="confirmed irrelevant to this preparation",
    )
    decision = evaluate_eligibility(safety, _clear_reg(same_plant=True))
    assert decision.status == EligibilityStatus.ELIGIBLE_WITH_RESTRICTIONS
    assert decision.hard_no_go is False


# --- 5. regulatory prohibition + SPECIES_WIDE -> NO_GO_REGULATORY ------
def test_species_wide_prohibition_is_no_go_regulatory():
    reg = RegulatoryFinding(
        status=RegulatoryDataStatus.PROHIBITED, scope=FindingScope.SPECIES_WIDE,
        context_relevance=ContextRelevance.RELEVANT, same_plant=False,
        barrier_types=frozenset({"Prohibited / banned"}), reason="species-wide ban",
    )
    decision = evaluate_eligibility(_clear_safety(), reg)
    assert decision.status == EligibilityStatus.NO_GO_REGULATORY
    assert decision.hard_no_go is True


# --- 6. regulatory prohibition + scope unknown -> expert review --------
def test_prohibition_with_unknown_scope_is_expert_review_not_no_go_or_eligible():
    reg = classify_regulatory_finding(
        barrier_types=frozenset({"Prohibited / banned"}), has_evidence_text=True, same_plant=True
    )
    decision = evaluate_eligibility(_clear_safety(same_plant=True), reg)
    assert decision.status == EligibilityStatus.EXPERT_REVIEW_REQUIRED
    assert decision.status not in (EligibilityStatus.NO_GO_REGULATORY, EligibilityStatus.ELIGIBLE)


# --- 7. restricted regulatory finding -> ELIGIBLE_WITH_RESTRICTIONS ----
def test_restricted_regulatory_finding_is_eligible_with_restrictions():
    reg = classify_regulatory_finding(
        barrier_types=frozenset({"Restricted access (prescription/controlled)"}),
        has_evidence_text=True, same_plant=False,
    )
    decision = evaluate_eligibility(_clear_safety(), reg)
    assert decision.status == EligibilityStatus.ELIGIBLE_WITH_RESTRICTIONS
    assert decision.eligible_for_normal_ranking is True


# --- 8. empty evidence + provenance unavailable -> INCOMPLETE ----------
def test_empty_evidence_is_incomplete_never_eligible():
    safety = classify_safety_finding(hit_terms=frozenset(), has_evidence_text=False, same_plant=False)
    reg = classify_regulatory_finding(barrier_types=None, has_evidence_text=False, same_plant=False)
    decision = evaluate_eligibility(safety, reg)
    assert decision.status == EligibilityStatus.INCOMPLETE
    assert decision.status != EligibilityStatus.ELIGIBLE
    assert decision.score_validity != ScoreValidity.VALID


# --- 9. hard no-go retains all Gate_Evidence_IDs ------------------------
def test_hard_no_go_retains_gate_evidence_ids():
    safety = classify_safety_finding(
        hit_terms=frozenset({"poison"}), has_evidence_text=True, same_plant=False,
        evidence_ids=("EV-1", "EV-2"),
    )
    decision = evaluate_eligibility(safety, _clear_reg())
    assert set(decision.gate_evidence_ids) == {"EV-1", "EV-2"}


# --- 10. simultaneous safety and regulatory failures retain both -------
# (CONFIRMED scope on both sides here, deliberately -- see test 1's
# comment on why an unconfirmed hit term alone no longer reaches this
# branch. This proves gate_reason/gate_evidence_ids still merge both
# findings even when they ARE both confirmed no-go.)
def test_simultaneous_failures_retain_both_reasons_and_ids():
    safety = classify_safety_finding(
        hit_terms=frozenset({"poison"}), has_evidence_text=True, same_plant=False,
        confirmed_scope=FindingScope.SPECIES_WIDE,
        confirmed_context_relevance=ContextRelevance.RELEVANT,
        evidence_ids=("EV-SAFETY",),
    )
    reg = RegulatoryFinding(
        status=RegulatoryDataStatus.PROHIBITED, scope=FindingScope.SPECIES_WIDE,
        context_relevance=ContextRelevance.RELEVANT, same_plant=False,
        barrier_types=frozenset({"Prohibited / banned"}), reason="prohibited",
        evidence_ids=("EV-REG",),
    )
    decision = evaluate_eligibility(safety, reg)
    assert decision.status == EligibilityStatus.NO_GO_REGULATORY  # regulatory wins as final status
    assert "poison" in decision.gate_reason.lower()
    assert "prohibited" in decision.gate_reason.lower()
    assert set(decision.gate_evidence_ids) == {"EV-SAFETY", "EV-REG"}
    assert decision.gate_type == "both"


# --- clean candidate -> ELIGIBLE ---------------------------------------
def test_clean_candidate_with_evidence_is_eligible():
    decision = evaluate_eligibility(_clear_safety(), _clear_reg())
    assert decision.status == EligibilityStatus.ELIGIBLE
    assert decision.eligible_for_normal_ranking is True
    assert decision.score_validity == ScoreValidity.VALID


# --- different plant part risk should not silently become "relevant" --
# (Correction round: documents the CORRECTED policy. Being matched to a
# DIFFERENT alternative plant is NOT evidence of species-wide/relevant
# scope on its own -- production today has no real plant-part/
# preparation/dose/route/population-aware matching (verified by the
# Phase 4 audit), so the honest default for BOTH same_plant=True and
# same_plant=False is UNKNOWN/UNKNOWN unless a caller explicitly
# confirms otherwise.)
def test_different_plant_hard_term_without_confirmation_defaults_to_unknown_scope():
    safety = classify_safety_finding(
        hit_terms=frozenset({"narcotic"}), has_evidence_text=True, same_plant=False
    )
    assert safety.scope == FindingScope.UNKNOWN
    assert safety.context_relevance == ContextRelevance.UNKNOWN


def test_same_plant_hard_term_also_defaults_to_unknown_scope():
    """Same default as the different-plant case above -- same_plant is
    no longer the deciding factor for scope/relevance at all; only
    confirmed_scope/confirmed_context_relevance are."""
    safety = classify_safety_finding(
        hit_terms=frozenset({"narcotic"}), has_evidence_text=True, same_plant=True
    )
    assert safety.scope == FindingScope.UNKNOWN
    assert safety.context_relevance == ContextRelevance.UNKNOWN
