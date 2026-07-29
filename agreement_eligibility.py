"""
Prospective Claim-to-Decision Mapping — Phases 1 & 2.

WHAT THIS IS
The minimal infrastructure the design document ("Prospective
Claim-to-Decision Mapping Proposal") calls for: an AgreementEligibility
decision (mirroring execution_readiness.ExecutionReadiness's own
READY/DEFER/BLOCK pattern), the AssertionState -> DecisionDirection
mapping the whole proposal exists to formalize, and a pure helper that
derives GoldCase.expected_output.expected_decision_direction from
GoldCase.resolved_outcomes via that mapping.

WHAT THIS DELIBERATELY DOES NOT DO
- Does not hard-code a final answer for AssertionState.CONDITIONAL —
  see ConditionalMappingPolicy below. The design document's three
  options (A: unresolved, B: maps to HOLD, C: case-specific override)
  are all representable without changing this module's shape; only
  ADOPTED_CONDITIONAL_POLICY's value needs to change once a decision
  is made, and even that can be overridden per-call without editing
  this module at all.
- Does not modify gold_case.py, resolved_expected_outcome.py,
  evaluation_run.py's existing metric logic, botanical_rd_candidate_
  engine.py, VALIDATION_PROTOCOL.md, or any frozen GoldCase file.
- Does not enforce the "ExpectedOutput frozen before EngineEvidenceInput"
  execution-order requirement from the design document's §7 — nothing
  in the current data model timestamps when a field was set, so this
  cannot be checked programmatically without a schema change this
  phase does not authorize. It remains a process discipline, the same
  way Leakage Rule 9.1's ordering is process discipline, not a runtime
  check — documented here as a known limitation, not silently assumed
  solved.
- Domain eligibility is CURRENT PROTOCOL POLICY, not a permanent
  architectural limit: only ReferenceDomain.INDICATION_EVIDENCE is
  presently eligible for whole-case decision_direction_agreement (see
  _ELIGIBLE_DOMAINS below — a one-line change point, not a redesign,
  if a future Engine version changes this policy).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Optional

from applicability_check import ReferenceDomain
from assertion_vocabulary import AssertionState
from gold_case import DecisionDirection, ExpectedOutput, GoldCase
from reference_precedence import ResolutionStatus

# Current protocol policy (design doc §3) — not a permanent
# architectural constant. Change this set if a future Engine version
# incorporates additional domains directly into candidate-level
# decisions; nothing else in this module needs to change as a result.
_ELIGIBLE_DOMAINS = frozenset({ReferenceDomain.INDICATION_EVIDENCE})


class AgreementEligibility(str, Enum):
    ELIGIBLE = "Eligible"
    NOT_ELIGIBLE = "Not eligible"


class AgreementIneligibilityReason(str, Enum):
    NO_ELIGIBLE_DOMAIN_OUTCOME = (
        "No SELECTED resolved outcome exists in a domain currently "
        "eligible for whole-case agreement (see _ELIGIBLE_DOMAINS)"
    )
    AMBIGUOUS_MULTIPLE_OUTCOMES = (
        "More than one SELECTED resolved outcome exists in an eligible "
        "domain — whole-case mapping would be ambiguous"
    )
    ASSERTION_STATE_UNMAPPED = (
        "The outcome's AssertionState has no adopted DecisionDirection "
        "mapping under the current ConditionalMappingPolicy"
    )
    EXPECTED_OUTPUT_NOT_SPECIFIED = (
        "GoldCase.expected_output.expected_decision_direction is not set"
    )


class ConditionalMappingPolicy(str, Enum):
    """The three options from the design document's §4 — deliberately
    kept as data, not as separate code paths scattered elsewhere, so
    adopting one is a one-line change to ADOPTED_CONDITIONAL_POLICY
    below, not a refactor."""
    UNRESOLVED = "Unresolved (Option A)"       # CONDITIONAL never maps — the adopted default
    MAPS_TO_HOLD = "Maps to HOLD (Option B)"    # CONDITIONAL -> DecisionDirection.HOLD
    CASE_SPECIFIC = "Case-specific (Option C)"  # CONDITIONAL -> caller-supplied override only


# THE adopted policy, until the open design question (proposal §4/§9)
# is resolved. Deliberately the conservative option — see the design
# document for why this is not a recommendation, just the safe
# default in the absence of a decision.
ADOPTED_CONDITIONAL_POLICY = ConditionalMappingPolicy.UNRESOLVED


_DIRECT_MAPPING = {
    AssertionState.PRESENT: DecisionDirection.POSITIVE,
    AssertionState.ABSENT: DecisionDirection.NEGATIVE,
    # NOT_STATED and INSUFFICIENT are deliberately absent from this
    # dict — see map_assertion_state_to_direction()'s docstring.
}


def map_assertion_state_to_direction(
    state: AssertionState,
    conditional_policy: Optional[ConditionalMappingPolicy] = None,
    case_specific_override: Optional[DecisionDirection] = None,
) -> Optional[DecisionDirection]:
    """The ONE function this proposal's mapping infrastructure exists
    to provide. Returns None whenever no mapping applies — never
    guesses. PRESENT/ABSENT are unconditional (design doc §4, high
    confidence). NOT_STATED/INSUFFICIENT always return None (nothing
    to map — the source never gave a usable answer). CONDITIONAL's
    result depends on `conditional_policy` (defaults to
    ADOPTED_CONDITIONAL_POLICY if not given):
        UNRESOLVED     -> None
        MAPS_TO_HOLD   -> DecisionDirection.HOLD
        CASE_SPECIFIC  -> case_specific_override (which may itself be None)
    """
    policy = conditional_policy if conditional_policy is not None else ADOPTED_CONDITIONAL_POLICY

    if state in _DIRECT_MAPPING:
        return _DIRECT_MAPPING[state]

    if state == AssertionState.CONDITIONAL:
        if policy == ConditionalMappingPolicy.MAPS_TO_HOLD:
            return DecisionDirection.HOLD
        if policy == ConditionalMappingPolicy.CASE_SPECIFIC:
            return case_specific_override
        return None  # UNRESOLVED

    return None  # NOT_STATED, INSUFFICIENT, or any future AssertionState value


@dataclass(frozen=True)
class AgreementEligibilityResult:
    case_id: str
    eligibility: AgreementEligibility
    reason: Optional[AgreementIneligibilityReason] = None
    mapped_direction: Optional[DecisionDirection] = None
    detail: str = ""


def assess_agreement_eligibility(
    gold_case: GoldCase,
    conditional_policy: Optional[ConditionalMappingPolicy] = None,
    case_specific_override: Optional[DecisionDirection] = None,
) -> AgreementEligibilityResult:
    """Pure, non-mutating — same convention as dataset_split.assess_
    leakage() and execution_readiness.assess_execution_readiness().
    Never runs or observes the engine; only reads gold_case.
    resolved_outcomes and gold_case.expected_output.

    A case is ELIGIBLE iff:
      1. Exactly one SELECTED resolved outcome exists in a currently
         eligible domain (_ELIGIBLE_DOMAINS — presently just
         INDICATION_EVIDENCE, per current protocol policy).
      2. That outcome's assertion_state maps to a DecisionDirection
         under the given/adopted ConditionalMappingPolicy.
      3. GoldCase.expected_output.expected_decision_direction is set.
    Does NOT check that the mapped direction and the case's own
    expected_output agree with each other — that consistency check is
    a documented open question (design doc §9), not implemented here.

    NOTE ON EXECUTION ORDER (design doc §7): this function cannot
    verify that expected_output was set BEFORE EngineEvidenceInput
    existed — see this module's own docstring for why. Eligibility as
    computed here is necessary, not sufficient, for a fully unbiased
    agreement measurement.
    """
    eligible_outcomes = [
        o for o in gold_case.resolved_outcomes
        if o.domain in _ELIGIBLE_DOMAINS and o.resolution_status == ResolutionStatus.SELECTED
    ]

    if not eligible_outcomes:
        return AgreementEligibilityResult(
            case_id=gold_case.case_id, eligibility=AgreementEligibility.NOT_ELIGIBLE,
            reason=AgreementIneligibilityReason.NO_ELIGIBLE_DOMAIN_OUTCOME,
        )
    if len(eligible_outcomes) > 1:
        return AgreementEligibilityResult(
            case_id=gold_case.case_id, eligibility=AgreementEligibility.NOT_ELIGIBLE,
            reason=AgreementIneligibilityReason.AMBIGUOUS_MULTIPLE_OUTCOMES,
        )

    outcome = eligible_outcomes[0]
    mapped_direction = map_assertion_state_to_direction(
        outcome.assertion_state, conditional_policy=conditional_policy,
        case_specific_override=case_specific_override,
    )
    if mapped_direction is None:
        return AgreementEligibilityResult(
            case_id=gold_case.case_id, eligibility=AgreementEligibility.NOT_ELIGIBLE,
            reason=AgreementIneligibilityReason.ASSERTION_STATE_UNMAPPED,
            detail=f"assertion_state={outcome.assertion_state!r}",
        )

    if gold_case.expected_output.expected_decision_direction is None:
        return AgreementEligibilityResult(
            case_id=gold_case.case_id, eligibility=AgreementEligibility.NOT_ELIGIBLE,
            reason=AgreementIneligibilityReason.EXPECTED_OUTPUT_NOT_SPECIFIED,
            mapped_direction=mapped_direction,
        )

    return AgreementEligibilityResult(
        case_id=gold_case.case_id, eligibility=AgreementEligibility.ELIGIBLE,
        mapped_direction=mapped_direction,
    )


def derive_expected_output_from_resolved_outcomes(
    gold_case: GoldCase,
    conditional_policy: Optional[ConditionalMappingPolicy] = None,
    case_specific_override: Optional[DecisionDirection] = None,
) -> ExpectedOutput:
    """Phase 2 — returns a NEW ExpectedOutput (dataclasses.replace;
    gold_case and its existing expected_output are never mutated) with
    expected_decision_direction populated via
    map_assertion_state_to_direction(), when derivable from exactly
    one eligible-domain SELECTED outcome. If not derivable (zero or
    multiple eligible outcomes, or an unmapped assertion_state), the
    existing expected_output is returned completely unchanged — this
    function never clears or overwrites a value it can't confidently
    derive, and never invents a direction.

    This does NOT populate expected_gate_results — gate-level
    derivation would require a domain-to-gate correspondence table
    this phase does not implement (see the design document's open
    question on gate_level_agreement, §9/§3) — expected_gate_results
    remains curator-supplied only, exactly as before this module
    existed.
    """
    eligible_outcomes = [
        o for o in gold_case.resolved_outcomes
        if o.domain in _ELIGIBLE_DOMAINS and o.resolution_status == ResolutionStatus.SELECTED
    ]
    if len(eligible_outcomes) != 1:
        return gold_case.expected_output

    mapped_direction = map_assertion_state_to_direction(
        eligible_outcomes[0].assertion_state, conditional_policy=conditional_policy,
        case_specific_override=case_specific_override,
    )
    if mapped_direction is None:
        return gold_case.expected_output

    return replace(gold_case.expected_output, expected_decision_direction=mapped_direction)
