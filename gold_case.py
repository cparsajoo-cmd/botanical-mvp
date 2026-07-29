"""
Validation Architecture v3 — Phase 1: GoldCase.

WHAT THIS IS
The curated unit of Validation Architecture v2/v3's Gold Set — ties
together a ValidationUnit (the case being evaluated), a set of
references with their PER-DOMAIN applicability results, curated
expected outputs, risk stratification, and dataset-split bookkeeping.

WHY APPLICABILITY IS STORED PER-REFERENCE-PER-DOMAIN, NOT AS ONE
GLOBAL VALUE (v3 correction #5)
A single reference can be applicable for one domain (e.g. Identity/
Quality) and inapplicable for another (e.g. Safety, if it doesn't
cover the relevant population) against the exact same ValidationUnit.
v2's design collapsed this into one boolean per case; v3 corrects it —
see GoldCaseReference.applicability_by_domain below, a dict keyed by
applicability_check.ReferenceDomain.

WHAT THIS DOES NOT DO IN PHASE 1
- Does not run the real engine (Phase 2 — see
  validation_protocol_execution.py for the existing, unmodified bridge
  that Phase 2 will connect this to).
- Does not persist anywhere (Phase 2).
- Does not resolve precedence itself — reference_precedence.resolve_precedence()
  is a separate, callable-on-demand function; a GoldCase simply holds
  the raw material (references + applicability + verdicts) precedence
  resolution needs.

REFERENCE-GROUNDED VALIDATION: STRUCTURAL SEPARATION OF TRUTH FROM
ENGINE INPUT
GoldCaseReference.claims (list[ReferenceClaim]) is the REFERENCE-TRUTH
layer — what authoritative sources state, used only by the evaluator
(resolved_expected_outcome.resolve_expected_outcomes()) to compute
GoldCase.resolved_outcomes. GoldCase.engine_evidence
(list[engine_evidence_input.EngineEvidenceInput]) is the SEPARATE,
structurally distinct evidence a curator attaches for feeding the real
production engine (gold_case_execution.execute_gold_case_against_engine()
reads ONLY this field, never .references[].claims). The two may
legitimately describe the same underlying source text — a curator
copying a monograph's contraindication section into both a
ReferenceClaim.evidence_text AND an EngineEvidenceInput.notes is
expected and correct — but the ENGINE only ever sees the latter, and
EngineEvidenceInput's own frozen, minimal-field shape makes it
structurally impossible for a ReferenceClaim/ResolvedExpectedOutcome
object (or any of their structured fields like assertion_state,
severity, resolution_status) to reach the engine through this field.

RiskStratum enum values are the eleven strata approved in Validation
Architecture v2 (safety-serious, safety-moderate, conflicting-evidence,
preparation-mismatch, vulnerable-population, interaction,
incomplete-data, taxonomy-ambiguity, correct-abstention, no-reference,
clean-baseline). A GoldCase may carry more than one — risk_strata is a
list, not a single value, per that same approval.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from applicability_check import ApplicabilityResult, ReferenceDomain
from assertion_vocabulary import (
    CurationStatus, GoldCaseKind, TransformationType,
    is_curation_status_lock_eligible,
)
from dataset_split import DatasetSplit, LeakageControl
from field_provenance import FieldProvenance
from reference_claim import ReferenceClaim
from reference_descriptor import ReferenceDescriptor
from reference_precedence import ReferenceVerdict, ResolutionStatus
from validation_unit import ValidationUnit


class RiskStratum(str, Enum):
    SAFETY_SERIOUS = "Safety-Serious"
    SAFETY_MODERATE = "Safety-Moderate"
    CONFLICTING_EVIDENCE = "Conflicting-Evidence"
    PREPARATION_MISMATCH = "Preparation-Mismatch"
    VULNERABLE_POPULATION = "Vulnerable-Population"
    INTERACTION = "Interaction"
    INCOMPLETE_DATA = "Incomplete-Data"
    TAXONOMY_AMBIGUITY = "Taxonomy-Ambiguity"
    CORRECT_ABSTENTION = "Correct-Abstention"
    NO_REFERENCE = "No-Reference"
    CLEAN_BASELINE = "Clean-Baseline"


class DecisionDirection(str, Enum):
    POSITIVE = "Positive"
    NEGATIVE = "Negative"
    HOLD = "Hold"
    ABSTAIN = "Abstain"


@dataclass
class ExpectedOutput:
    """Curated ground truth for one GoldCase. acceptable_output_range
    is a RANGE (decision_class_min/max), not a single point value —
    per Validation Architecture v2's explicit correction that a single
    expected string is too brittle for a scoring engine with
    continuous inputs."""
    expected_gate_results: dict = field(default_factory=dict)  # gate_name -> "PASSED"|"FAILED"|"NOT_EVALUABLE"
    expected_decision_direction: Optional[DecisionDirection] = None
    expected_abstention_reason: Optional[str] = None  # required when direction == ABSTAIN
    expected_warnings: list = field(default_factory=list)
    acceptable_decision_class_min: Optional[str] = None
    acceptable_decision_class_max: Optional[str] = None


@dataclass
class GoldCaseReference:
    """One reference attached to a GoldCase, with its own
    per-domain applicability results and curated verdict — see module
    docstring for why applicability is per-reference-per-domain, not
    a single case-level value."""
    reference: ReferenceDescriptor
    applicability_by_domain: dict = field(default_factory=dict)  # ReferenceDomain -> ApplicabilityResult
    verdict: Optional[ReferenceVerdict] = None
    provenance: list = field(default_factory=list)  # list[FieldProvenance]
    claims: list = field(default_factory=list)  # list[ReferenceClaim] — v4: what this ONE source states

    def applicable_domains(self) -> list:
        """Convenience: which domains this reference is currently
        recorded as applicable for. Purely a read of already-computed
        ApplicabilityResult objects — never recomputes anything."""
        return [
            domain for domain, result in self.applicability_by_domain.items()
            if isinstance(result, ApplicabilityResult) and result.applicable
        ]


@dataclass
class GoldCase:
    """The complete curated unit. dataset_split defaults to
    DEVELOPMENT (see dataset_split.py) — a case only becomes
    LOCKED_HOLDOUT through an explicit operation, never by default.

    kind (v4 correction #4): explicit, stored — never inferred from
    case_id string prefix. Determines whether
    TransformationType.SUMMARIZED_BY_CURATOR is permitted anywhere in
    this case's claims (only for GoldCaseKind.SYNTHETIC).

    curation_status (v4 correction #1): a genuine lock prerequisite —
    see is_lockable() below — but never sufficient by itself.

    resolved_outcomes: populated by
    resolved_expected_outcome.resolve_expected_outcomes(self) — the
    final Gold truth is_lockable()/lock_gold_case() check against, not
    ExpectedOutput (which remains a separate, simpler summary field
    for display/non-locking purposes).

    locked/dataset_snapshot_hash: only ever set by lock_gold_case()
    below, never assigned directly — same convention
    validation_case_protocol.lock_protocol() already established.
    """
    case_id: str
    validation_unit: ValidationUnit
    risk_strata: list = field(default_factory=list)  # list[RiskStratum]
    references: list = field(default_factory=list)  # list[GoldCaseReference]
    expected_output: ExpectedOutput = field(default_factory=ExpectedOutput)
    correct_abstention_expected: bool = False
    case_provenance: list = field(default_factory=list)  # list[FieldProvenance], case-level claims
    dataset_split: DatasetSplit = DatasetSplit.DEVELOPMENT
    leakage_control: LeakageControl = field(default_factory=LeakageControl)
    kind: GoldCaseKind = GoldCaseKind.REFERENCE_GROUNDED
    curation_status: CurationStatus = CurationStatus.DRAFT
    resolved_outcomes: list = field(default_factory=list)  # list[ResolvedExpectedOutcome]
    engine_evidence: list = field(default_factory=list)  # list[EngineEvidenceInput] — see module docstring's structural-separation note
    locked: bool = False
    dataset_snapshot_hash: Optional[str] = None


class GoldCaseNotReadyError(Exception):
    """Raised by lock_gold_case() when is_lockable() returns False —
    carries the same reasons list as an attached .reasons attribute,
    mirroring validation_case_protocol.ProtocolNotReadyError's pattern."""


def _outcome_provenance_complete(gold_case: "GoldCase", outcome) -> list:
    """v4 correction #3 — outcome-SPECIFIC provenance validation.
    Returns a list of reasons (empty = complete) that outcome has a
    full trace to: its selected reference, the source claim behind it,
    that claim's source_locator, translation rule+version, and both
    policy versions. Checking that "a reference has SOME provenance"
    is explicitly insufficient per the approved correction — this
    checks the actual claim that PRODUCED this specific outcome."""
    reasons = []

    if not outcome.translation_rule_id or not outcome.translation_rule_version:
        reasons.append(
            f"{outcome.subject!r}/{outcome.domain.value}: missing translation_rule_id/version."
        )
    if not outcome.applicability_policy_version:
        reasons.append(f"{outcome.subject!r}/{outcome.domain.value}: missing applicability_policy_version.")
    if not outcome.precedence_policy_version:
        reasons.append(f"{outcome.subject!r}/{outcome.domain.value}: missing precedence_policy_version.")

    if outcome.resolution_status != ResolutionStatus.SELECTED:
        # No single selected reference/claim to trace for a non-SELECTED
        # outcome — is_lockable()'s resolution-status check handles this
        # case; provenance completeness is moot here.
        return reasons

    selected_gref = next(
        (g for g in gold_case.references if g.reference.reference_id == outcome.selected_reference_id),
        None,
    )
    if selected_gref is None:
        reasons.append(
            f"{outcome.subject!r}/{outcome.domain.value}: selected_reference_id "
            f"{outcome.selected_reference_id!r} not found among this case's references."
        )
        return reasons

    matching_claim = next(
        (c for c in selected_gref.claims
         if c.domain == outcome.domain and c.assertion_type == outcome.assertion_type),
        None,
    )
    if matching_claim is None:
        reasons.append(
            f"{outcome.subject!r}/{outcome.domain.value}: no matching source claim found "
            f"on reference {outcome.selected_reference_id!r}."
        )
    elif not matching_claim.source_locator:
        reasons.append(
            f"{outcome.subject!r}/{outcome.domain.value}: source claim on "
            f"{outcome.selected_reference_id!r} has no source_locator."
        )

    return reasons


def is_lockable(gold_case: GoldCase) -> tuple:
    """v4 corrections #1/#2/#3/#4 — the complete, explicit lock
    invariant checker. Returns (lockable, reasons). Never a string-enum
    ordering comparison anywhere in this function (v4 correction #1's
    "do not use string-enum ordering" applies to curation_status
    specifically, honored here via is_curation_status_lock_eligible()).
    """
    reasons = []

    # 1. Curation status — a real prerequisite, checked via explicit
    #    set membership, never ordering.
    if not is_curation_status_lock_eligible(gold_case.curation_status):
        reasons.append(
            f"curation_status {gold_case.curation_status.value!r} is not lock-eligible "
            f"(must be one of: {', '.join(s.value for s in sorted((s for s in CurationStatus if is_curation_status_lock_eligible(s)), key=lambda s: s.value))})."
        )

    # 2. At least one resolved outcome must exist.
    if not gold_case.resolved_outcomes:
        reasons.append("No resolved expected outcomes (resolve_expected_outcomes() has not been run, or found nothing).")

    for outcome in gold_case.resolved_outcomes:
        # 3. Every outcome must actually be SELECTED — a case with any
        #    unresolved outcome (CONFLICT/NO_APPLICABLE_REFERENCE/
        #    INSUFFICIENT_METADATA/HUMAN_REVIEW_REQUIRED) cannot lock.
        if outcome.resolution_status != ResolutionStatus.SELECTED:
            reasons.append(
                f"{outcome.subject!r}/{outcome.domain.value}: resolution_status is "
                f"{outcome.resolution_status.value!r}, not SELECTED."
            )
            continue

        # 4. Strengthened applicability check (v4 correction #2): not
        #    merely "applicability_by_domain is non-empty" — the EXACT
        #    domain must have been computed, the selected reference
        #    must be applicable for it, and the selected reference must
        #    actually exist among this case's references.
        selected_gref = next(
            (g for g in gold_case.references if g.reference.reference_id == outcome.selected_reference_id),
            None,
        )
        if selected_gref is None:
            reasons.append(
                f"{outcome.subject!r}/{outcome.domain.value}: selected_reference_id "
                f"{outcome.selected_reference_id!r} does not match any reference on this case."
            )
        else:
            applicability = selected_gref.applicability_by_domain.get(outcome.domain)
            if applicability is None:
                reasons.append(
                    f"{outcome.subject!r}/{outcome.domain.value}: applicability was never "
                    f"computed for this exact domain on the selected reference."
                )
            elif not applicability.applicable:
                reasons.append(
                    f"{outcome.subject!r}/{outcome.domain.value}: the reference selected by "
                    f"precedence is NOT applicable for this domain (applicability_by_domain "
                    f"disagrees with the resolution)."
                )

        # 5. Outcome-specific provenance completeness (v4 correction #3).
        reasons.extend(_outcome_provenance_complete(gold_case, outcome))

    # 6. Kind-vs-transformation-type check (v4 correction #4):
    #    SUMMARIZED_BY_CURATOR is only ever permitted for SYNTHETIC cases.
    if gold_case.kind != GoldCaseKind.SYNTHETIC:
        for gref in gold_case.references:
            for claim in gref.claims:
                if (
                    claim.evidence_text is not None
                    and claim.evidence_text.transformation_type == TransformationType.SUMMARIZED_BY_CURATOR
                ):
                    reasons.append(
                        f"Reference {gref.reference.reference_id!r} has a "
                        f"SUMMARIZED_BY_CURATOR claim, which is only permitted for "
                        f"GoldCaseKind.SYNTHETIC cases (this case's kind is "
                        f"{gold_case.kind.value!r})."
                    )

    return (len(reasons) == 0, reasons)


def lock_gold_case(gold_case: GoldCase) -> GoldCase:
    """Returns a NEW GoldCase with locked=True and a computed
    dataset_snapshot_hash, if and only if is_lockable() passes. Raises
    GoldCaseNotReadyError otherwise — never silently locks a partial
    case, same hard-refusal guarantee as
    validation_case_protocol.lock_protocol(). Never mutates the input
    in place.
    """
    from dataclasses import replace
    from dataset_canonicalization import hash_dataset

    lockable, reasons = is_lockable(gold_case)
    if not lockable:
        error = GoldCaseNotReadyError(
            f"Cannot lock GoldCase {gold_case.case_id!r}: {'; '.join(reasons)}"
        )
        error.reasons = reasons
        raise error

    locked_case = replace(gold_case, locked=True)
    locked_case = replace(locked_case, dataset_snapshot_hash=hash_dataset([locked_case]))
    return locked_case
