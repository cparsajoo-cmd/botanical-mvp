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


# ---------------------------------------------------------------------
# Root-cause regression (2026-08-11): RGV v3's blind run showed
# rgv3_014_kratom_pain / rgv3_015_atractylis_traditional /
# rgv3_016_impila_traditional all regress from correct NO_GO_SAFETY to
# EXPERT_REVIEW_REQUIRED the moment the semantic (LLM) gate started
# contributing its own assertions alongside the deterministic ones.
#
# Root cause found by direct code trace: the two-key scope logic used
# only serious_assertions[0] -- an arbitrary, list-order-dependent
# pick -- to decide scope. Once the semantic gate's assertion(s) could
# appear before the deterministic one in the list, any incidental
# population/dose/preparation detail the LLM happened to mention (even
# non-narrowing context) silently shrank scope away from SPECIES_WIDE,
# defeating a previously-correct hard stop. Fixed to consider ALL
# serious assertions and take the widest (most conservative) scope any
# of them supports, so one assertion's incidental detail cannot erase
# another assertion's unqualified species-wide finding.
# ---------------------------------------------------------------------
from safety_assertion_engine import SafetyAssertion, SafetyAssertionType, AssertionPolarity, SafetyConfidence
from assertion_vocabulary import SeverityLevel


def _serious_assertion(**overrides):
    base = dict(
        assertion_type=SafetyAssertionType.ORGAN_TOXICITY,
        severity=SeverityLevel.SERIOUS,
        polarity=AssertionPolarity.RISK_PRESENT,
        evidence_strength=SafetyConfidence.HIGH,
        affected_population=(),
        dose_dependency="unknown",
        preparation="",
        route="",
        source_sentence="can cause seizures, coma, and death",
        provenance="deterministic",
    )
    base.update(overrides)
    return SafetyAssertion(**base)


def test_unqualified_deterministic_assertion_still_wins_species_wide_even_when_llm_assertion_is_listed_first():
    """Regression test: this exact ordering (LLM assertion first, then
    the unqualified deterministic one) is what broke kratom/atractylis/
    impila in the real v3 run."""
    llm_assertion = _serious_assertion(
        affected_population=("people using it for pain relief",),
        provenance="semantic_llm",
        evidence_strength=SafetyConfidence.MODERATE,
    )
    deterministic_assertion = _serious_assertion()  # unqualified -> species-wide
    safety = classify_safety_finding(
        hit_terms=frozenset(),
        has_evidence_text=True,
        same_plant=True,
        assertions=(llm_assertion, deterministic_assertion),
    )
    assert safety.scope == FindingScope.SPECIES_WIDE
    assert safety.context_relevance == ContextRelevance.RELEVANT

    reg = classify_regulatory_finding(barrier_types=frozenset(), has_evidence_text=False, same_plant=True)
    decision = evaluate_eligibility(safety, reg)
    assert decision.status == EligibilityStatus.NO_GO_SAFETY


def test_unqualified_assertion_wins_regardless_of_list_position():
    """Same as above but with the order reversed, proving the fix is not
    itself order-dependent in the other direction."""
    llm_assertion = _serious_assertion(
        affected_population=("people using it for pain relief",),
        provenance="semantic_llm",
    )
    deterministic_assertion = _serious_assertion()
    safety = classify_safety_finding(
        hit_terms=frozenset(),
        has_evidence_text=True,
        same_plant=True,
        assertions=(deterministic_assertion, llm_assertion),
    )
    assert safety.scope == FindingScope.SPECIES_WIDE


def test_all_assertions_population_qualified_stays_population_specific():
    """When EVERY serious assertion is genuinely population-qualified (no
    unqualified species-wide assertion exists anywhere in the list), the
    two-key policy must still withhold an automatic hard stop -- this is
    the case the original code was designed to protect."""
    a1 = _serious_assertion(affected_population=("pregnant women",), provenance="semantic_llm")
    a2 = _serious_assertion(affected_population=("pediatric patients",), provenance="semantic_llm")
    safety = classify_safety_finding(
        hit_terms=frozenset(), has_evidence_text=True, same_plant=True, assertions=(a1, a2),
    )
    assert safety.scope == FindingScope.POPULATION_SPECIFIC
    reg = classify_regulatory_finding(barrier_types=frozenset(), has_evidence_text=False, same_plant=True)
    decision = evaluate_eligibility(safety, reg)
    assert decision.status != EligibilityStatus.NO_GO_SAFETY


# ---------------------------------------------------------------------
# Second root-cause regression, found in the SAME v3 rerun after the fix
# above (2026-08-11): rgv3_014_kratom_pain alone still failed. Its real
# evidence text says "...states that overdose of kratom can result in
# seizures, coma, and death" -- the dose-keyword check used plain
# substring matching, so "dose" matched inside "overdose" and spuriously
# narrowed scope to DOSE_SPECIFIC even though no actual dose threshold is
# specified anywhere in the text. Fixed with a word-boundary regex.
# ---------------------------------------------------------------------
def test_overdose_in_source_sentence_does_not_spuriously_match_the_dose_keyword():
    assertion = _serious_assertion(
        source_sentence="states that overdose of kratom can result in seizures, coma, and death",
    )
    safety = classify_safety_finding(
        hit_terms=frozenset(), has_evidence_text=True, same_plant=True, assertions=(assertion,),
    )
    assert safety.scope == FindingScope.SPECIES_WIDE
    reg = classify_regulatory_finding(barrier_types=frozenset(), has_evidence_text=False, same_plant=True)
    decision = evaluate_eligibility(safety, reg)
    assert decision.status == EligibilityStatus.NO_GO_SAFETY


def test_a_genuine_standalone_dose_word_still_narrows_scope():
    """Non-regression: an actual dose-threshold mention must still narrow
    scope -- only the "overdose"-style false match was the bug."""
    assertion = _serious_assertion(
        source_sentence="serious toxicity was observed only above a dose of 500 mg per day",
    )
    safety = classify_safety_finding(
        hit_terms=frozenset(), has_evidence_text=True, same_plant=True, assertions=(assertion,),
    )
    assert safety.scope == FindingScope.DOSE_SPECIFIC
