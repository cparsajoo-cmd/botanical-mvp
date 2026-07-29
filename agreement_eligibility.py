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
    EXPECTED_OUTPUT_MAPPING_MISMATCH = (
        "GoldCase.expected_output.expected_decision_direction disagrees with "
        "the direction the AssertionState-to-DecisionDirection mapping "
        "produces from Ground Truth — the manually supplied value is never "
        "silently trusted over, or silently repaired to match, the mapping"
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


class ExpectedOutputDirectionConflictError(Exception):
    """Raised by derive_expected_output_from_resolved_outcomes() when
    GoldCase.expected_output already carries a non-None
    expected_decision_direction that DISAGREES with the direction the
    AssertionState-to-DecisionDirection mapping would produce. Mirrors
    gold_case_execution.EvidenceChannelConflictError's fail-closed
    philosophy: never silently prefer the existing manually-supplied
    value over the mapping, and never silently overwrite the existing
    value with the mapping either."""


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
      4. That set value EXACTLY EQUALS the mapped direction from step
         2 — a manually supplied ExpectedOutput that disagrees with
         what Ground Truth's own mapping produces makes the case
         NOT_ELIGIBLE (reason EXPECTED_OUTPUT_MAPPING_MISMATCH), never
         silently trusted, and never silently repaired. This is what
         actually makes the mapping layer meaningful — without this
         check, evaluation_run.py would score whatever expected_output
         says, regardless of whether it agrees with the prospective
         mapping this module exists to define.

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

    expected_direction = gold_case.expected_output.expected_decision_direction
    if expected_direction is None:
        return AgreementEligibilityResult(
            case_id=gold_case.case_id, eligibility=AgreementEligibility.NOT_ELIGIBLE,
            reason=AgreementIneligibilityReason.EXPECTED_OUTPUT_NOT_SPECIFIED,
            mapped_direction=mapped_direction,
        )

    if expected_direction != mapped_direction:
        return AgreementEligibilityResult(
            case_id=gold_case.case_id, eligibility=AgreementEligibility.NOT_ELIGIBLE,
            reason=AgreementIneligibilityReason.EXPECTED_OUTPUT_MAPPING_MISMATCH,
            mapped_direction=mapped_direction,
            detail=(
                f"expected_output.expected_decision_direction={expected_direction!r} "
                f"!= mapped_direction={mapped_direction!r}"
            ),
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
    """Phase 2 — returns an ExpectedOutput with expected_decision_
    direction populated via map_assertion_state_to_direction(), when
    derivable from exactly one eligible-domain SELECTED outcome.

    Behavior, by case:
      - Not derivable (zero/multiple eligible outcomes, or an unmapped
        assertion_state): returns gold_case.expected_output completely
        UNCHANGED (same object) — never invents a direction.
      - Derivable, and gold_case.expected_output.expected_decision_
        direction is currently None: returns a NEW ExpectedOutput
        (dataclasses.replace; gold_case itself is never mutated) with
        the mapped direction populated.
      - Derivable, and the existing direction already EQUALS the
        mapped direction: returns gold_case.expected_output UNCHANGED
        (the same object, not a new equal-valued one) — nothing to do.
      - Derivable, but the existing direction CONFLICTS with the
        mapped direction: raises ExpectedOutputDirectionConflictError.
        Never silently overwrites the existing value, and never
        silently keeps it while pretending derivation succeeded —
        this is a real inconsistency the caller must resolve.

    Does NOT populate expected_gate_results — gate-level derivation
    would require a domain-to-gate correspondence table this phase
    does not implement (see the design document's open question on
    gate_level_agreement, §9/§3) — expected_gate_results remains
    curator-supplied only, exactly as before this module existed.
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

    existing_direction = gold_case.expected_output.expected_decision_direction

    if existing_direction is None:
        return replace(gold_case.expected_output, expected_decision_direction=mapped_direction)

    if existing_direction == mapped_direction:
        return gold_case.expected_output

    raise ExpectedOutputDirectionConflictError(
        f"GoldCase {gold_case.case_id!r}: existing expected_output."
        f"expected_decision_direction={existing_direction!r} conflicts with "
        f"the mapped direction={mapped_direction!r} derived from "
        f"assertion_state={eligible_outcomes[0].assertion_state!r}. Refusing "
        f"to silently overwrite or silently keep either value — resolve the "
        f"conflict explicitly before deriving."
    )
