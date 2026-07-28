"""
Task 6 — Validation Case Protocol (generic, parametric).

WHAT THIS IS
A structured, reusable template for "locking" a scientific validation
case, per the whitepaper's Appendix A / Chapter 3 (stage 1, "locking
the decision protocol") and Chapter 10's validation-programme
requirements. It is NOT specific to any one indication, product type,
or dosage form — the platform supports 7 product types x 28
indications x 12 dosage forms (see step_inputs.py), and a validation
case can be built for any combination of them, or any candidate set
the person running validation cares about.

WHY THIS MODULE EXISTS
Appendix A's own table (four illustrative example cases — sleep-
support infusion, constipation, cognitive health, healthy skin) was
never meant to be the platform's validation ROADMAP; it was meant to
show what "locked" versus "not ready" looks like for a few worked
examples. Nothing in the repository previously gave a person a
structured way to define and lock a DIFFERENT case (e.g. a topical
skin cosmetic, a joint-comfort capsule, a veterinary product) using
the same rigor. This module is that structure.

WHAT "LOCKING A PROTOCOL" MEANS (from the whitepaper, restated exactly)
"Each case requires a locked decision context (population, route,
dosage form, jurisdiction), a locked candidate set with documented
eligibility rules, a reference evidence corpus built independently of
the platform's own retrieval, and an independent reference assessment
from a qualified expert panel before the platform is run against a
fixed configuration." No ranking, recommendation, or performance
result may be attributed to the platform outside a documented,
versioned case execution against a LOCKED protocol — see lock_protocol()
below, which refuses to lock an incomplete case rather than silently
allowing a partial one to be treated as final.

WHAT THIS MODULE DOES NOT DO
- It does not run the engine, generate a candidate set automatically,
  or build a reference corpus itself. This is a protocol-definition
  and readiness-tracking structure, not a data-collection tool. Once a
  protocol is LOCKED, executing it against BotanicalRDCandidateEngine
  (and comparing to benchmark_harness.py's existing mechanics) is a
  separate, later step.
- It does not assess or improve scientific quality. A protocol can be
  fully "locked" by this module's own criteria while still being a
  scientifically weak case — locking only means the FOUR REQUIRED
  ELEMENTS above are present and documented, not that they are good.
  A qualified reviewer must still judge whether a locked protocol is
  actually sound.
- It intentionally stores expert-panel members by role/credentials,
  not by personal name, to avoid this template becoming a place where
  real individuals' identities are casually recorded outside a proper
  governance process.

DATACLASSES, NOT PYDANTIC — same reasoning as data_contracts.py:
python's built-in dataclasses need nothing extra and work in any
environment.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from enum import Enum
from typing import Optional


class ProtocolReadiness(str, Enum):
    """Mirrors Appendix A's own readiness vocabulary exactly, plus two
    states Appendix A's table didn't need to name because none of its
    four example cases were in them: NOT_STARTED (before a decision
    context exists at all) and LOCKED (the end state Appendix A
    describes but never reaches for any of its four examples)."""
    NOT_STARTED = "Not started"
    NOT_VALIDATION_READY = "Not validation-ready"
    CONDITIONALLY_READY = "Conditionally ready for protocol completion"
    LOCKED = "Locked"


@dataclass
class DecisionContext:
    """The four dimensions Appendix A requires to be locked before
    anything else: population, route, dosage form, jurisdiction — plus
    product_type/indication, which step_inputs.py's own Step 0 already
    treats as required decision-context fields for every ordinary
    platform run, so a validation case's decision context should be at
    least as specific as an ordinary run's.

    dosage_form/product_type/indication are free-text here (not the
    step_inputs.py Enums) deliberately: a validation case may test a
    NARROWER or DIFFERENTLY-WORDED slice than the UI's selectbox
    options (e.g. "adult, non-pregnant" population is narrower than
    the platform's own indication list captures), and hard-coding this
    module to the current UI's exact option lists would make it
    obsolete the moment those lists change.
    """
    population: Optional[str] = None
    route_of_administration: Optional[str] = None
    dosage_form: Optional[str] = None
    jurisdiction: Optional[str] = None
    product_type: Optional[str] = None
    indication: Optional[str] = None
    notes: Optional[str] = None

    def is_locked(self) -> bool:
        """All four Appendix-A-required dimensions must be non-empty.
        product_type/indication/notes are not required by Appendix A
        itself, so they are not part of this check."""
        return all([
            _non_empty(self.population),
            _non_empty(self.route_of_administration),
            _non_empty(self.dosage_form),
            _non_empty(self.jurisdiction),
        ])

    def missing_fields(self) -> list:
        required = {
            "population": self.population,
            "route_of_administration": self.route_of_administration,
            "dosage_form": self.dosage_form,
            "jurisdiction": self.jurisdiction,
        }
        return [name for name, value in required.items() if not _non_empty(value)]


@dataclass
class CandidateEligibilityRule:
    """One documented inclusion/exclusion rule — Appendix A requires
    "documented eligibility rules", not merely a list of candidate
    names with no stated reason for their inclusion."""
    rule: str
    rationale: Optional[str] = None


@dataclass
class LockedCandidateSet:
    """candidates: scientific names (or other stable identifiers) of
    every botanical candidate in scope for this case. eligibility_rules
    must be non-empty for the set to count as "documented" — an
    unexplained list of names does not satisfy Appendix A's
    requirement, even if the list itself is long."""
    candidates: list = field(default_factory=list)
    eligibility_rules: list = field(default_factory=list)  # list[CandidateEligibilityRule]
    exclusion_notes: Optional[str] = None

    def is_locked(self) -> bool:
        return len(self.candidates) > 0 and len(self.eligibility_rules) > 0

    def missing_fields(self) -> list:
        missing = []
        if not self.candidates:
            missing.append("candidates")
        if not self.eligibility_rules:
            missing.append("eligibility_rules")
        return missing


@dataclass
class ReferenceEvidenceCorpus:
    """Appendix A: "a reference evidence corpus built independently of
    the platform's own retrieval." built_independently_of_platform is
    a required, explicit affirmative flag rather than an assumption —
    a corpus is only valid for this purpose if it was NOT assembled by
    running the platform's own connectors/search and treating the
    result as the reference standard, since that would make the
    platform's own retrieval both the thing being tested and the
    reference it is tested against."""
    description: Optional[str] = None
    built_independently_of_platform: bool = False
    sources: list = field(default_factory=list)
    search_strategy: Optional[str] = None
    evidence_cutoff_date: Optional[date] = None
    corpus_size: Optional[int] = None

    def is_locked(self) -> bool:
        return (
            _non_empty(self.description)
            and self.built_independently_of_platform is True
            and len(self.sources) > 0
            and _non_empty(self.search_strategy)
            and self.evidence_cutoff_date is not None
        )

    def missing_fields(self) -> list:
        missing = []
        if not _non_empty(self.description):
            missing.append("description")
        if not self.built_independently_of_platform:
            missing.append("built_independently_of_platform")
        if not self.sources:
            missing.append("sources")
        if not _non_empty(self.search_strategy):
            missing.append("search_strategy")
        if self.evidence_cutoff_date is None:
            missing.append("evidence_cutoff_date")
        return missing


@dataclass
class ExpertPanelMember:
    """Stored by role/credentials, not personal name — see module
    docstring."""
    role: str
    credentials: Optional[str] = None


@dataclass
class ExpertPanel:
    """Appendix A: "an independent reference assessment from a
    qualified expert panel." members must be non-empty, and
    independence_statement must explicitly document that the panel's
    assessment was produced without seeing the platform's own output
    first — an expert panel that reviewed the platform's ranking
    before forming their own judgment is not independent, regardless
    of their individual qualifications."""
    members: list = field(default_factory=list)  # list[ExpertPanelMember]
    review_protocol: Optional[str] = None
    independence_statement: Optional[str] = None

    def is_locked(self) -> bool:
        return (
            len(self.members) > 0
            and _non_empty(self.review_protocol)
            and _non_empty(self.independence_statement)
        )

    def missing_fields(self) -> list:
        missing = []
        if not self.members:
            missing.append("members")
        if not _non_empty(self.review_protocol):
            missing.append("review_protocol")
        if not _non_empty(self.independence_statement):
            missing.append("independence_statement")
        return missing


@dataclass
class ValidationCaseProtocol:
    """The complete, lockable unit for one validation case. case_name
    is free text chosen by whoever defines the case (e.g. "Adult
    sleep-support herbal infusion (EU)", "Topical joint-comfort gel
    (US)", "Veterinary digestive support (Canada)") — this module
    places no restriction on which product/indication/dosage-form
    combination a case may target.

    locked / locked_date are only ever set by lock_protocol() below,
    never assigned directly — see that function's docstring for why.
    """
    case_name: str
    decision_context: DecisionContext = field(default_factory=DecisionContext)
    candidate_set: LockedCandidateSet = field(default_factory=LockedCandidateSet)
    reference_corpus: ReferenceEvidenceCorpus = field(default_factory=ReferenceEvidenceCorpus)
    expert_panel: ExpertPanel = field(default_factory=ExpertPanel)
    locked: bool = False
    locked_date: Optional[date] = None


def _non_empty(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and value.strip() == "":
        return False
    return True


# Ordered so a case failing an EARLIER element is reported against
# that element first, even if later elements also happen to be
# incomplete — matches Appendix A's own "Principal gap" column, which
# names the single most decision-relevant gap per case rather than
# listing every gap at once.
_ELEMENT_ORDER = [
    ("decision_context", "decision context (population, route, dosage form, jurisdiction)"),
    ("candidate_set", "candidate set with documented eligibility rules"),
    ("reference_corpus", "reference evidence corpus built independently of the platform"),
    ("expert_panel", "independent reference expert panel"),
]


def assess_readiness(protocol: ValidationCaseProtocol) -> ProtocolReadiness:
    """Returns the protocol's current readiness. Never mutates
    `protocol` and never sets its locked/locked_date fields — this is
    a read-only assessment, exactly like the rest of this pipeline's
    "assess separately from deciding" separation of layers principle
    (see doc2's Chapter 4)."""
    dc = protocol.decision_context
    if not any([
        _non_empty(dc.population), _non_empty(dc.route_of_administration),
        _non_empty(dc.dosage_form), _non_empty(dc.jurisdiction),
        _non_empty(dc.indication), _non_empty(dc.product_type),
    ]):
        return ProtocolReadiness.NOT_STARTED

    if not dc.is_locked():
        return ProtocolReadiness.NOT_VALIDATION_READY

    if (
        protocol.candidate_set.is_locked()
        and protocol.reference_corpus.is_locked()
        and protocol.expert_panel.is_locked()
    ):
        return ProtocolReadiness.LOCKED

    return ProtocolReadiness.CONDITIONALLY_READY


def gap_report(protocol: ValidationCaseProtocol) -> dict:
    """Structured, actionable gap report — the machine-checkable
    counterpart to Appendix A's "Principal gap" column. Returns:
      - readiness: ProtocolReadiness
      - principal_gap: str | None — the single most decision-relevant
        missing element (None only when readiness is LOCKED)
      - all_gaps: dict[str, list] — every incomplete element's own
        missing_fields(), for elements that aren't yet complete
    """
    readiness = assess_readiness(protocol)

    elements = {
        "decision_context": protocol.decision_context,
        "candidate_set": protocol.candidate_set,
        "reference_corpus": protocol.reference_corpus,
        "expert_panel": protocol.expert_panel,
    }

    all_gaps = {}
    for key, element in elements.items():
        if not element.is_locked():
            all_gaps[key] = element.missing_fields()

    principal_gap = None
    if readiness != ProtocolReadiness.LOCKED:
        for key, label in _ELEMENT_ORDER:
            if key in all_gaps:
                missing = ", ".join(all_gaps[key])
                principal_gap = f"{label} incomplete — missing: {missing}"
                break

    return {
        "readiness": readiness,
        "principal_gap": principal_gap,
        "all_gaps": all_gaps,
    }


class ProtocolNotReadyError(Exception):
    """Raised by lock_protocol() when a case does not yet satisfy all
    four Appendix-A-required elements. Deliberately a hard error, not
    a warning or a best-effort partial lock — Chapter 10's own
    requirement is that "no ranking, recommendation or performance
    result should be attributed to the platform outside a documented,
    versioned case execution," which only means something if locking
    is impossible to do halfway."""


def lock_protocol(protocol: ValidationCaseProtocol, locked_date: Optional[date] = None) -> ValidationCaseProtocol:
    """Returns a NEW ValidationCaseProtocol with locked=True and
    locked_date set, if and only if every required element is already
    complete. Raises ProtocolNotReadyError (with the same gap_report()
    detail attached) otherwise — this function never silently locks a
    partial protocol, and never mutates the input in place (the
    caller's original `protocol` object is left exactly as it was,
    matching this pipeline's "never overwrite source content" Evidence
    Intelligence Framework principle applied here to protocol
    definitions instead of evidence records).
    """
    report = gap_report(protocol)
    if report["readiness"] != ProtocolReadiness.LOCKED:
        error = ProtocolNotReadyError(
            f"Cannot lock '{protocol.case_name}': {report['principal_gap']}"
        )
        error.gap_report = report
        raise error

    return ValidationCaseProtocol(
        case_name=protocol.case_name,
        decision_context=protocol.decision_context,
        candidate_set=protocol.candidate_set,
        reference_corpus=protocol.reference_corpus,
        expert_panel=protocol.expert_panel,
        locked=True,
        locked_date=locked_date or date.today(),
    )


def to_appendix_row(protocol: ValidationCaseProtocol) -> dict:
    """Renders a protocol as one row in the exact {"Case", "Readiness",
    "Principal gap"} shape Appendix A's own table uses — so a set of
    ValidationCaseProtocol instances can be dropped straight into that
    appendix (or a successor document) without reformatting."""
    report = gap_report(protocol)
    return {
        "Case": protocol.case_name,
        "Readiness": report["readiness"].value,
        "Principal gap": report["principal_gap"] or "None — locked.",
    }


def protocol_completeness(protocol: ValidationCaseProtocol) -> dict:
    """Convenience wrapper around data_contracts.completeness_report()-
    style output, but computed against this module's OWN structural
    locking criteria (candidate_set needs BOTH candidates AND
    eligibility_rules to count, etc.) rather than a generic "is this
    field None" check, since a generic check can't see that e.g. a
    ReferenceEvidenceCorpus with sources but
    built_independently_of_platform=False is still not locked."""
    elements = {
        "decision_context": protocol.decision_context,
        "candidate_set": protocol.candidate_set,
        "reference_corpus": protocol.reference_corpus,
        "expert_panel": protocol.expert_panel,
    }
    locked_count = sum(1 for e in elements.values() if e.is_locked())
    total = len(elements)
    return {
        "locked_elements": locked_count,
        "total_elements": total,
        "completeness_score": round(100 * locked_count / total, 1) if total else 0.0,
        "elements_locked": {k: v.is_locked() for k, v in elements.items()},
    }
