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
from dataset_split import DatasetSplit, LeakageControl
from field_provenance import FieldProvenance
from reference_descriptor import ReferenceDescriptor
from reference_precedence import ReferenceVerdict
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
    LOCKED_HOLDOUT through an explicit operation, never by default."""
    case_id: str
    validation_unit: ValidationUnit
    risk_strata: list = field(default_factory=list)  # list[RiskStratum]
    references: list = field(default_factory=list)  # list[GoldCaseReference]
    expected_output: ExpectedOutput = field(default_factory=ExpectedOutput)
    correct_abstention_expected: bool = False
    case_provenance: list = field(default_factory=list)  # list[FieldProvenance], case-level claims
    dataset_split: DatasetSplit = DatasetSplit.DEVELOPMENT
    leakage_control: LeakageControl = field(default_factory=LeakageControl)
