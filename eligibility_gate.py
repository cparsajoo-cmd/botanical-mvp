"""
Phase 4 — Eligibility Gate (Safety & Regulatory redesign).

WHAT THIS IS
A single, structured, pre-scoring eligibility layer that replaces the
pre-Phase-4 pattern where ``same_plant=True`` silently bypassed both
the hard safety gate and the hard regulatory gate
(``BotanicalRDCandidateEngine._hard_safety_gate`` /
``_hard_regulatory_gate`` in ``botanical_rd_candidate_engine.py``,
returning ``GateStatus.NOT_EVALUABLE`` — a status that, in every
downstream consumer, behaved identically to an affirmative PASS).

WHY A NEW, SELF-CONTAINED MODULE (Option B from the Phase 4 design
review, not Option A)
``data_contracts.py`` is already a large (600+ line), general-purpose
contract file for entities used across the whole platform (Plant,
Compound, ScientificEvidence, RegulatoryRecord, SafetyInteraction,
CandidateAssessment, ...) and is explicitly documented there as "the
shape data SHOULD have" independent of any one engine's internal
decision logic. The models here (``EligibilityStatus``,
``FindingScope``, ``SafetyFinding``, ``RegulatoryFinding``,
``EligibilityDecision``, ...) are specific to ONE decision — Phase 4's
pre-scoring eligibility gate — and are read almost nowhere except the
engine's own row-building loop, the shortlist's hard-stop check, and
the UI/report layers that must not contradict it. Adding six more
enums/dataclasses to ``data_contracts.py`` for a single consumer would
be coupling in the wrong direction: every future reader of
``data_contracts.py`` (a genuinely shared file) would have to
understand Phase-4-specific gate vocabulary that has nothing to do
with the rest of that file's entities. Keeping everything Phase-4-
specific in this one module, and importing it explicitly wherever it
is actually used, keeps the coupling local and makes the diff for this
phase self-contained in one new file plus the handful of call sites
that need it.

SCOPE / HONESTY ABOUT WHAT THIS CAN AND CANNOT DETERMINE (see the
Phase 4 audit)
The audit proved that today's live production data does NOT carry a
structured plant-part / preparation / dose / route / population match
between a documented risk and a specific candidate row — the
``SafetyInteraction`` dataclass in ``data_contracts.py`` already models
those fields but has zero live callers (only one Gold Case test
instantiates it). Given that, ``FindingScope``/``ContextRelevance``
values this module receives are, for every real production call site
today, the SAME honest default regardless of same_plant (correction
round fix — see below for why same_plant used to matter here and no
longer does):
  - BOTH a different alternative plant (same_plant=False) AND the
    reference plant matched to itself (same_plant=True) default to
    scope=UNKNOWN, relevance=UNKNOWN. Being a different plant is NOT,
    by itself, evidence that a documented hard term is species-wide or
    relevant to that specific candidate — "different plant" says
    nothing about WHICH part/preparation/dose/population/constituent a
    term actually applies to. An EARLIER version of this module
    defaulted same_plant=False to SPECIES_WIDE/RELEVANT (reasoning:
    "this is what the pre-Phase-4 hard gate already did for every
    non-self row") — that default was itself a fail-open gap the
    design review caught and this module no longer has: being
    different is not confirmation, and treating it as confirmation
    silently manufactured certainty the data doesn't support.
  - The only way this module ever reports a scope other than UNKNOWN
    is via the ``confirmed_scope``/``confirmed_context_relevance``
    parameters on ``classify_safety_finding()``/
    ``classify_regulatory_finding()`` (see below) — which the live
    production pipeline never passes today. So in practice EVERY live
    call gets scope=UNKNOWN, relevance=UNKNOWN, and a SEVERE/PROHIBITED
    finding resolves to EXPERT_REVIEW_REQUIRED, never an automatic
    NO_GO, until real structured context data exists.
This module's own decision function is intentionally naive about how
scope/relevance were derived — it only combines whatever
SafetyFinding/RegulatoryFinding it is given. A future improvement that
adds real plant-part/preparation matching only has to change how
findings are BUILT (the ``classify_*`` helpers below, via
``confirmed_scope``/``confirmed_context_relevance``), never this
module's core ``evaluate_eligibility()`` decision table.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, FrozenSet, Optional, Tuple

from assertion_vocabulary import SeverityLevel
from safety_assertion_engine import SafetyAssertion, SafetyConfidence, AssertionPolarity
from regulatory_scope_assessment import assess_regulatory_scope, detect_dose_threshold_violation


# ======================================================================
# Enums — controlled vocabularies. No free strings anywhere else in
# this module or its call sites; every status/severity/scope value is
# one of these.
# ======================================================================

class EligibilityStatus(str, Enum):
    """The single source of truth for whether/how a candidate row may
    be scored, ranked, and recommended. Decision_Class (legacy string
    field, kept for backward compatibility) is DERIVED from this, not
    the other way around — see ``botanical_rd_candidate_engine.py``'s
    ``_decision_class()``, which now evaluates eligibility first."""
    ELIGIBLE = "eligible"
    ELIGIBLE_WITH_RESTRICTIONS = "eligible_with_restrictions"
    INCOMPLETE = "incomplete"
    EXPERT_REVIEW_REQUIRED = "expert_review_required"
    NO_GO_SAFETY = "no_go_safety"
    NO_GO_REGULATORY = "no_go_regulatory"


# Statuses allowed into NORMAL ranking/recommendation/shortlist/report
# top-N. Everything else (INCOMPLETE, EXPERT_REVIEW_REQUIRED, the two
# NO_GO statuses) must be partitioned out of those views, though never
# deleted from audit-complete outputs (CSV export, Gate_Results).
NORMAL_RANKING_STATUSES = frozenset({
    EligibilityStatus.ELIGIBLE,
    EligibilityStatus.ELIGIBLE_WITH_RESTRICTIONS,
})

# Statuses that are a hard, non-compensatory stop: no score, market
# signal, or mechanistic plausibility may move a row out of these.
HARD_NO_GO_STATUSES = frozenset({
    EligibilityStatus.NO_GO_SAFETY,
    EligibilityStatus.NO_GO_REGULATORY,
})


class RankingPartition(str, Enum):
    """Correction round (2nd pass) — the structured, explicit source of
    truth for WHERE a row belongs in any ranked view, independent of
    its raw R&D_Opportunity_Score. Sorting by score alone (as the raw
    engine output DataFrame still does, for audit-completeness — see
    RANKING_PARTITION_SORT_ORDER below) can put a hard no-go row with a
    high raw score ahead of a genuinely eligible one; this partition is
    what every consumer that means "normal ranking" must sort/group by
    FIRST, score second."""
    NORMAL = "normal"
    PRELIMINARY_OR_EXPERT_REVIEW = "preliminary_or_expert_review"
    EXCLUDED_NO_GO = "excluded_no_go"


# Explicit, total sort order for RankingPartition — lower number sorts
# first (i.e. NORMAL rows always precede PRELIMINARY_OR_EXPERT_REVIEW,
# which always precedes EXCLUDED_NO_GO, regardless of raw score).
RANKING_PARTITION_SORT_ORDER = {
    RankingPartition.NORMAL: 0,
    RankingPartition.PRELIMINARY_OR_EXPERT_REVIEW: 1,
    RankingPartition.EXCLUDED_NO_GO: 2,
}


def ranking_partition_for(status: EligibilityStatus) -> RankingPartition:
    """The single function every consumer should call to turn an
    EligibilityStatus into a RankingPartition — so this mapping is
    defined exactly once."""
    if status in HARD_NO_GO_STATUSES:
        return RankingPartition.EXCLUDED_NO_GO
    if status in NORMAL_RANKING_STATUSES:
        return RankingPartition.NORMAL
    return RankingPartition.PRELIMINARY_OR_EXPERT_REVIEW



class ScoreValidity(str, Enum):
    """What a row's R&D_Opportunity_Score value actually MEANS. Kept
    as an explicit enum (never a bare string) precisely so no call
    site can invent its own ad hoc "valid"/"preliminary" spelling —
    see the Phase 4 design review's objection to free strings."""
    VALID = "valid"
    PRELIMINARY = "preliminary"
    AUDIT_ONLY = "audit_only"


class DataCompleteness(str, Enum):
    """Whether ENOUGH evidence text existed to evaluate safety/
    regulatory status at all for this row. This is deliberately coarse
    (COMPLETE / INCOMPLETE only) — see the module docstring's
    "SCOPE / HONESTY" section and ``RegulatoryDataStatus`` below for
    why finer distinctions (NO_EVIDENCE_FOUND vs SEARCH_NOT_PERFORMED
    vs SOURCE_UNAVAILABLE) are NOT modeled here: the audit proved that
    today's ingestion-layer provenance (``multi_source_collector.py``'s
    per-source error list) never reaches the evidence text this
    module's callers see, so any finer distinction here would be
    fabricated, not observed."""
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


class RegulatoryDataStatus(str, Enum):
    """What the regulatory classifier's INPUT looked like, as opposed
    to what it FOUND. Kept separate from the barrier-content
    classification itself (``regulatory_barrier_classifier.py``, left
    unmodified in Phase 4 — see the module docstring) so that "no
    barrier phrase matched" and "there was no text to search" are
    never collapsed into the same PASSED-equivalent outcome, which was
    the exact fail-open bug the audit proved
    (``test_regulatory_barrier_classifier_empty_text_vs_unrelated_text_both_clear``).
    """
    PROHIBITED = "prohibited"
    RESTRICTED = "restricted"
    CLEAR = "clear"
    INSUFFICIENT_DATA = "insufficient_data"


class SafetySeverity(str, Enum):
    NONE = "none"
    MINOR = "minor"
    MODERATE = "moderate"
    SEVERE = "severe"


class ContextRelevance(str, Enum):
    RELEVANT = "relevant"
    IRRELEVANT = "irrelevant"
    UNKNOWN = "unknown"


class FindingScope(str, Enum):
    """How broadly a documented safety/regulatory finding applies.
    UNKNOWN is not a residual/error value — it is the honest, expected
    value for every same_plant=True self-row today (see module
    docstring). Nothing in this module upgrades UNKNOWN into a more
    specific scope on its own."""
    SPECIES_WIDE = "species_wide"
    PLANT_PART_SPECIFIC = "plant_part_specific"
    PREPARATION_SPECIFIC = "preparation_specific"
    CONSTITUENT_SPECIFIC = "constituent_specific"
    POPULATION_SPECIFIC = "population_specific"
    DOSE_SPECIFIC = "dose_specific"
    UNKNOWN = "unknown"


# ======================================================================
# Findings — the two structured inputs evaluate_eligibility() combines.
# ======================================================================

@dataclass(frozen=True)
class SafetyFinding:
    severity: SafetySeverity
    scope: FindingScope
    context_relevance: ContextRelevance
    data_completeness: DataCompleteness
    same_plant: bool
    hit_terms: FrozenSet[str] = field(default_factory=frozenset)
    assertions: Tuple[SafetyAssertion, ...] = ()
    confidence: SafetyConfidence = SafetyConfidence.INSUFFICIENT
    evidence_conflict: bool = False
    severity_rule: str = "legacy-hard-term-policy"
    reason: str = ""
    evidence_ids: Tuple[str, ...] = ()


@dataclass(frozen=True)
class RegulatoryFinding:
    status: RegulatoryDataStatus
    scope: FindingScope
    context_relevance: ContextRelevance
    same_plant: bool
    barrier_types: FrozenSet[str] = field(default_factory=frozenset)
    reason: str = ""
    evidence_ids: Tuple[str, ...] = ()


@dataclass(frozen=True)
class EligibilityDecision:
    status: EligibilityStatus
    hard_no_go: bool
    gate_type: str  # "safety" | "regulatory" | "both" | "none"
    gate_reason: str
    gate_evidence_ids: Tuple[str, ...]
    safety_finding: SafetyFinding
    regulatory_finding: RegulatoryFinding
    data_completeness: DataCompleteness
    requires_expert_review: bool
    eligible_for_normal_ranking: bool
    score_validity: ScoreValidity

    @property
    def ranking_partition(self) -> "RankingPartition":
        """Computed, not stored — always derived from ``status`` via
        ``ranking_partition_for()`` so there is exactly one place this
        mapping is defined, never a second copy that could drift."""
        return ranking_partition_for(self.status)


# ======================================================================
# Finding constructors — turn today's actual engine signals
# (safety_flags string, HARD_SAFETY_TERMS hits, regulatory barrier
# types, same_plant, whether any evidence text existed) into the
# structured findings above. This is the ONLY place today's real
# scope/relevance policy defaults live — see the module docstring.
# ======================================================================

def classify_safety_finding(
    *,
    hit_terms: FrozenSet[str],
    has_evidence_text: bool,
    same_plant: bool,
    flagged_terms: Optional[FrozenSet[str]] = None,
    confirmed_scope: Optional[FindingScope] = None,
    confirmed_context_relevance: Optional[ContextRelevance] = None,
    evidence_ids: Tuple[str, ...] = (),
    assertions: Tuple[SafetyAssertion, ...] = (),
) -> SafetyFinding:
    """Builds a SafetyFinding from the same inputs the pre-Phase-4
    ``_hard_safety_gate()`` used (a hard-term hit and same_plant),
    plus two things Phase 4 adds:

    1. ``has_evidence_text``: whether any evidence text existed at all
       for this row. Pre-Phase-4, a row with zero evidence text and a
       row with evidence text that mentioned nothing concerning were
       indistinguishable (both PASSED) — proven by the audit as a
       fail-open gap; ``has_evidence_text`` closes it here by feeding
       DataCompleteness.INCOMPLETE instead of a silent PASS-equivalent
       when there was nothing to search in the first place.

    2. ``confirmed_scope`` / ``confirmed_context_relevance``: the ONLY
       way this function will ever report a scope other than UNKNOWN.
       Correction-round fix: being matched to a DIFFERENT alternative
       plant (same_plant=False) is NOT evidence that a finding is
       species-wide or relevant — "different plant" says nothing about
       WHICH part/preparation/dose/population/constituent a documented
       hard term actually applies to. Production today (see
       botanical_rd_candidate_engine.py's row-building loop) does not
       pass either override, because there is no real plant-part/
       preparation/dose/route/population-aware matching wired into the
       live evidence pipeline yet (verified by the Phase 4 audit) — so
       in practice EVERY live-pipeline call gets scope=UNKNOWN,
       relevance=UNKNOWN regardless of same_plant, and a SEVERE finding
       therefore resolves to EXPERT_REVIEW_REQUIRED, never an automatic
       NO_GO_SAFETY, until real structured context data exists. These
       two parameters exist so that (a) a FUTURE caller with genuine
       structured context data can supply a confirmed scope without
       this function's decision table changing, and (b) tests can
       exercise the SPECIES_WIDE/PLANT_PART_SPECIFIC/etc. branches
       explicitly, honestly labelled as synthetic overrides rather than
       something today's production can derive on its own.

    ``flagged_terms`` (optional): the FULL set of matched SAFETY_TERMS
    (the broader, non-hard vocabulary — see botanical_rd_candidate_engine
    .SAFETY_TERMS), used only to distinguish MINOR from NONE severity
    when ``hit_terms`` (the HARD_SAFETY_TERMS subset) is empty. Defaults
    to ``hit_terms`` itself when not given, so a caller that only has
    the hard-term signal still gets correct SEVERE/NONE behavior (no
    MINOR without this extra signal — see the production wiring note
    in classify_safety_finding's caller for which production path
    supplies it).
    """
    if flagged_terms is None:
        flagged_terms = hit_terms

    risk_assertions = tuple(
        a for a in assertions if a.polarity in {AssertionPolarity.RISK_PRESENT, AssertionPolarity.CONDITIONAL}
    )
    reassuring_assertions = tuple(a for a in assertions if a.polarity == AssertionPolarity.RISK_ABSENT)
    assertion_levels = {a.severity for a in risk_assertions}

    # Structured assertions are authoritative for semantic severity. Legacy
    # hard-term hits remain supported for backward compatibility, but a
    # serious assertion can no longer be downgraded merely because it did not
    # produce one of the old hard-keyword markers.
    if hit_terms or SeverityLevel.SERIOUS in assertion_levels:
        severity = SafetySeverity.SEVERE
    elif SeverityLevel.MODERATE in assertion_levels:
        severity = SafetySeverity.MODERATE
    elif flagged_terms or SeverityLevel.MINOR in assertion_levels:
        severity = SafetySeverity.MINOR
    else:
        severity = SafetySeverity.NONE

    rank = {SafetyConfidence.INSUFFICIENT: 0, SafetyConfidence.LOW: 1, SafetyConfidence.MODERATE: 2, SafetyConfidence.HIGH: 3}
    confidence_source = tuple(a for a in risk_assertions if a.severity == SeverityLevel.SERIOUS) or risk_assertions or assertions
    confidence = (
        max((a.evidence_strength for a in confidence_source), key=lambda x: rank[x])
        if confidence_source else SafetyConfidence.INSUFFICIENT
    )
    evidence_conflict = bool(risk_assertions and reassuring_assertions)
    serious_assertions = tuple(a for a in risk_assertions if a.severity == SeverityLevel.SERIOUS)
    assertion_evidence_ids = tuple(dict.fromkeys(a.evidence_record_id for a in assertions if a.evidence_record_id))
    evidence_ids = tuple(dict.fromkeys(tuple(evidence_ids) + assertion_evidence_ids))
    severity_rule = next((a.severity_rule for a in risk_assertions if a.severity == SeverityLevel.SERIOUS), "legacy-hard-term-policy")

    data_completeness = (
        DataCompleteness.COMPLETE if has_evidence_text else DataCompleteness.INCOMPLETE
    )

    if confirmed_scope is not None:
        scope = confirmed_scope
    elif serious_assertions:
        # Root-cause remediation: a serious structured assertion that carries
        # no candidate-limiting preparation/dose/route/population qualifier is
        # broad for the botanical record rather than unknowable by default.
        # If a qualifier exists, retain the narrowest honest structured scope
        # and require context matching before a hard no-go.
        _a = serious_assertions[0]
        if _a.affected_population:
            scope = FindingScope.POPULATION_SPECIFIC
        elif (
            (_a.dose_dependency and _a.dose_dependency != "unknown")
            or any(token in str(_a.source_sentence or "").lower() for token in ("dose", "doses", "dosage", "threshold"))
        ):
            scope = FindingScope.DOSE_SPECIFIC
        elif _a.preparation or _a.route:
            scope = FindingScope.PREPARATION_SPECIFIC
        else:
            scope = FindingScope.SPECIES_WIDE
    else:
        scope = FindingScope.UNKNOWN

    if confirmed_context_relevance is not None:
        relevance = confirmed_context_relevance
    elif serious_assertions and scope == FindingScope.SPECIES_WIDE:
        relevance = ContextRelevance.RELEVANT
    else:
        relevance = ContextRelevance.UNKNOWN

    same_plant_note = "Reference plant matched to itself; " if same_plant else ""
    if serious_assertions:
        kinds = ", ".join(sorted({a.assertion_type.value for a in serious_assertions}))
        reason = (
            f"{same_plant_note}Structured serious safety assertion(s) present: {kinds}. "
            f"Confidence={confidence.value}. "
            + ("Conflicting reassurance evidence is also present and has been retained; serious risk is not overwritten. " if evidence_conflict else "")
            + ("Scope/relevance is confirmed." if confirmed_scope is not None else
               "Scope/relevance to this specific candidate is not confirmed by structured plant-part/preparation/dose/route/population matching.")
        )
    elif hit_terms:
        reason = (
            f"{same_plant_note}Documented hard safety term(s) present: "
            f"{', '.join(sorted(hit_terms))}. Scope/relevance to this "
            f"specific candidate is "
            + ("confirmed." if confirmed_scope is not None else
               "not confirmed by any structured plant-part/preparation/"
               "dose/route/population/constituent match in current data.")
        )
    elif flagged_terms:
        reason = (
            f"{same_plant_note}Minor (non-hard) safety term(s) present: "
            f"{', '.join(sorted(flagged_terms))}."
        )
    elif has_evidence_text:
        reason = f"{same_plant_note}No documented safety term present."
    else:
        reason = f"{same_plant_note}No evidence text was available to evaluate safety for this row."

    return SafetyFinding(
        severity=severity,
        scope=scope,
        context_relevance=relevance,
        data_completeness=data_completeness,
        same_plant=same_plant,
        hit_terms=hit_terms,
        assertions=assertions,
        confidence=confidence,
        evidence_conflict=evidence_conflict,
        severity_rule=severity_rule,
        reason=reason,
        evidence_ids=evidence_ids,
    )


def classify_regulatory_finding(
    *,
    barrier_types: Optional[FrozenSet[str]],
    has_evidence_text: bool,
    same_plant: bool,
    confirmed_scope: Optional[FindingScope] = None,
    confirmed_context_relevance: Optional[ContextRelevance] = None,
    finding_text: str = "",
    candidate_dosage_form: str = "",
    candidate_context_text: str = "",
    evidence_ids: Tuple[str, ...] = (),
) -> RegulatoryFinding:
    """Builds a RegulatoryFinding from ``regulatory_barrier_classifier
    .classify_regulatory_barriers()``'s output plus ``has_evidence_text``/
    ``same_plant``.

    ``regulatory_barrier_classifier.py`` is left unmodified in Phase 4
    (per the design review: a text classifier cannot itself know
    whether an empty result means "checked, nothing found" or "never
    checked" — that distinction is exactly ``has_evidence_text``,
    supplied by the caller, not derived inside the classifier).

    Root-cause remediation (Reference-Grounded Validation v1, Problem
    C): two capabilities from ``regulatory_scope_assessment.py`` are
    layered in here, both purely additive and both scoped to only ever
    narrow an UNKNOWN default toward a more specific, evidence-grounded
    answer — never to invent a prohibition that ``barrier_types``
    itself did not already establish (except for the numeric
    dose-threshold path, which is its own independent detection because
    a dose limit is not expressible as a keyword/phrase at all):

    1. ``candidate_context_text`` (typically the candidate's own
       Target_Indication/question text) lets a documented PROHIBITED
       finding resolve its scope automatically: no qualifier at all in
       ``finding_text`` -> species-wide (mirrors
       ``classify_safety_finding``'s equivalent "no limiting qualifier
       -> broad by default" rule for serious safety assertions); a
       qualifier (plant part / preparation / named constituent) that is
       independently restated in the candidate's own context ->
       resolved and relevant; a qualifier that is NOT confirmed by the
       candidate context -> scope stays specific but relevance stays
       UNKNOWN, so the case still safely falls to
       EXPERT_REVIEW_REQUIRED rather than either extreme.
    2. When ``barrier_types`` is empty (no phrase-based barrier found)
       but ``finding_text`` contains a "must contain less than X units"
       -style numeric limit clause, ``detect_dose_threshold_violation``
       compares it against a numeric amount in ``candidate_context_text``.
       A confirmed violation becomes a "Dose-dependent regulatory
       restriction" PROHIBITED finding with DOSE_SPECIFIC/RELEVANT scope;
       a limit that cannot be compared (no candidate amount found)
       becomes RESTRICTED with unresolved relevance; a confirmed
       COMPLIANT amount raises no barrier at all.

    ``confirmed_scope``/``confirmed_context_relevance`` (an explicit
    override, still never supplied by the live production pipeline)
    take precedence over both of the above when given — see
    classify_safety_finding()'s docstring for the same pattern.
    """
    barrier_types = frozenset(barrier_types or frozenset())

    dose_finding = None
    if has_evidence_text and not barrier_types and finding_text:
        dose_finding = detect_dose_threshold_violation(finding_text, candidate_context_text)
        if dose_finding is not None and dose_finding.violates is not False:
            barrier_types = barrier_types | {"Dose-dependent regulatory restriction"}

    is_prohibited = "Prohibited / banned" in barrier_types or (
        dose_finding is not None and dose_finding.violates is True
    )
    is_restricted = bool(barrier_types) and not is_prohibited

    if not has_evidence_text:
        status = RegulatoryDataStatus.INSUFFICIENT_DATA
    elif is_prohibited:
        status = RegulatoryDataStatus.PROHIBITED
    elif is_restricted:
        status = RegulatoryDataStatus.RESTRICTED
    else:
        status = RegulatoryDataStatus.CLEAR

    scope = confirmed_scope if confirmed_scope is not None else FindingScope.UNKNOWN
    relevance = (
        confirmed_context_relevance if confirmed_context_relevance is not None
        else ContextRelevance.UNKNOWN
    )

    # Root-cause remediation for explicit route/preparation exceptions.  The
    # classifier already established that a prohibition exists; this block
    # only decides whether the source text makes that prohibition applicable
    # to the candidate context.  It never creates a prohibition by itself.
    _ft = str(finding_text or "").lower()
    _cdf = str(candidate_dosage_form or "").lower()
    _scope_kind_to_finding_scope = {
        "species_wide": FindingScope.SPECIES_WIDE,
        "constituent_specific": FindingScope.CONSTITUENT_SPECIFIC,
        "plant_part_specific": FindingScope.PLANT_PART_SPECIFIC,
        "preparation_specific": FindingScope.PREPARATION_SPECIFIC,
    }
    if status == RegulatoryDataStatus.PROHIBITED and confirmed_scope is None and _ft:
        if ("external use" in _ft or "topical" in _ft) and any(
            token in _cdf for token in ("oral", "internal", "capsule", "tablet", "extract")
        ):
            scope = FindingScope.PREPARATION_SPECIFIC
            relevance = ContextRelevance.RELEVANT
        elif dose_finding is not None and dose_finding.violates is True:
            scope = FindingScope.DOSE_SPECIFIC
            relevance = ContextRelevance.RELEVANT
        else:
            _assessment = assess_regulatory_scope(finding_text, candidate_context_text)
            if _assessment.scope == "species_wide":
                scope = FindingScope.SPECIES_WIDE
                relevance = ContextRelevance.RELEVANT
            elif _assessment.relevant is True:
                scope = _scope_kind_to_finding_scope.get(_assessment.scope, FindingScope.UNKNOWN)
                relevance = ContextRelevance.RELEVANT
            elif _assessment.scope in _scope_kind_to_finding_scope:
                # A qualifier was found but the candidate's own context
                # does not confirm it applies — stay honestly unresolved
                # (falls to EXPERT_REVIEW_REQUIRED), never guess either way.
                scope = _scope_kind_to_finding_scope[_assessment.scope]
    elif status == RegulatoryDataStatus.RESTRICTED and confirmed_scope is None and dose_finding is not None:
        scope = FindingScope.DOSE_SPECIFIC

    if status == RegulatoryDataStatus.INSUFFICIENT_DATA:
        reason = "No evidence text was available to evaluate regulatory status for this row."
    elif dose_finding is not None and "Dose-dependent regulatory restriction" in barrier_types:
        if dose_finding.violates:
            reason = (
                f"Documented regulatory dose limit of {dose_finding.limit_value:g}"
                f" {dose_finding.limit_unit} is exceeded by the candidate's declared"
                f" {dose_finding.actual_value:g} {dose_finding.actual_unit}."
            )
        else:
            reason = (
                f"Documented regulatory dose limit of {dose_finding.limit_value:g}"
                f" {dose_finding.limit_unit} found; no comparable candidate-declared"
                " amount could be confirmed."
            )
    elif is_prohibited:
        reason = "Documented regulatory finding: Prohibited / banned."
    elif is_restricted:
        reason = f"Documented regulatory finding(s): {', '.join(sorted(barrier_types))}."
    else:
        reason = "No documented regulatory barrier found in available evidence text."

    if same_plant and status in (RegulatoryDataStatus.PROHIBITED, RegulatoryDataStatus.RESTRICTED):
        reason = (
            "Reference plant matched to itself; " + reason +
            " Scope relative to the whole species vs. a trace constituent "
            "is not resolvable from current data."
        )

    return RegulatoryFinding(
        status=status,
        scope=scope,
        context_relevance=relevance,
        same_plant=same_plant,
        barrier_types=barrier_types,
        reason=reason,
        evidence_ids=evidence_ids,
    )



# ======================================================================
# The decision itself.
# ======================================================================

def evaluate_eligibility(
    safety: SafetyFinding,
    regulatory: RegulatoryFinding,
) -> EligibilityDecision:
    """Pure function: combines one SafetyFinding and one
    RegulatoryFinding into a single EligibilityDecision. Priority
    order (Phase 4 design review, section 5):

    1. NO_GO_REGULATORY  — a regulatory PROHIBITED finding with
       confirmed (SPECIES_WIDE) scope. Takes precedence as the FINAL
       status over a simultaneous safety no-go (a legal prohibition
       stops development on its own regardless of the safety
       picture) — but the safety finding's reason/evidence is still
       carried in gate_reason/gate_type ("both") and both findings
       remain on the returned decision object, never discarded.
    2. NO_GO_SAFETY      — a severe safety finding with confirmed
       (SPECIES_WIDE) scope OR confirmed-relevant context, and not
       already claimed by rule 1.
    3. EXPERT_REVIEW_REQUIRED — any of: a PROHIBITED regulatory
       finding with UNKNOWN scope; a severe safety finding with
       UNKNOWN scope (and relevance not confirmed IRRELEVANT).
       Deliberately NOT eligible and NOT no-go: today's data cannot
       confirm either way, and per the design review a same_plant
       hard-term hit with unknown scope must never resolve to ELIGIBLE
       by default.
    4. ELIGIBLE_WITH_RESTRICTIONS — a RESTRICTED regulatory finding,
       OR a severe safety finding whose scope/relevance is confirmed
       NOT to apply to this candidate (a real, not fabricated,
       clearance), OR a minor (non-hard) safety finding.
    5. INCOMPLETE — regulatory or safety DataCompleteness is
       INCOMPLETE (no evidence text existed) and nothing above
       already claimed a more specific status. Never resolves to
       ELIGIBLE — see the design review's explicit requirement that
       empty input must never look like a positive clearance.
    6. ELIGIBLE — default: no safety/regulatory concern found, and
       evidence text existed to have found one.
    """
    reg_prohibited_species_wide = (
        regulatory.status == RegulatoryDataStatus.PROHIBITED
        and (
            regulatory.scope == FindingScope.SPECIES_WIDE
            or (
                regulatory.scope != FindingScope.UNKNOWN
                and regulatory.context_relevance == ContextRelevance.RELEVANT
            )
        )
    )
    reg_prohibited_unknown_scope = (
        regulatory.status == RegulatoryDataStatus.PROHIBITED
        and not reg_prohibited_species_wide
    )
    safety_no_go = (
        safety.severity == SafetySeverity.SEVERE
        and (
            safety.scope == FindingScope.SPECIES_WIDE
            or safety.context_relevance == ContextRelevance.RELEVANT
        )
        and safety.scope != FindingScope.UNKNOWN
    )
    safety_unknown_scope_concern = (
        safety.severity == SafetySeverity.SEVERE
        and not safety_no_go
        and safety.context_relevance != ContextRelevance.IRRELEVANT
    )
    safety_confirmed_irrelevant = (
        safety.severity == SafetySeverity.SEVERE
        and safety.context_relevance == ContextRelevance.IRRELEVANT
    )
    data_incomplete = (
        safety.data_completeness == DataCompleteness.INCOMPLETE
        or regulatory.status == RegulatoryDataStatus.INSUFFICIENT_DATA
    )

    evidence_ids = tuple(dict.fromkeys(tuple(safety.evidence_ids) + tuple(regulatory.evidence_ids)))

    # 1) NO_GO_REGULATORY — final status even if safety is also no-go.
    if reg_prohibited_species_wide:
        gate_type = "both" if safety_no_go else "regulatory"
        reason = regulatory.reason if not safety_no_go else (
            regulatory.reason + " | Also: " + safety.reason
        )
        return EligibilityDecision(
            status=EligibilityStatus.NO_GO_REGULATORY,
            hard_no_go=True,
            gate_type=gate_type,
            gate_reason=reason,
            gate_evidence_ids=evidence_ids,
            safety_finding=safety,
            regulatory_finding=regulatory,
            data_completeness=DataCompleteness.COMPLETE if not data_incomplete else DataCompleteness.INCOMPLETE,
            requires_expert_review=True,
            eligible_for_normal_ranking=False,
            score_validity=ScoreValidity.AUDIT_ONLY,
        )

    # 2) NO_GO_SAFETY
    if safety_no_go:
        return EligibilityDecision(
            status=EligibilityStatus.NO_GO_SAFETY,
            hard_no_go=True,
            gate_type="safety",
            gate_reason=safety.reason,
            gate_evidence_ids=evidence_ids,
            safety_finding=safety,
            regulatory_finding=regulatory,
            data_completeness=DataCompleteness.COMPLETE if not data_incomplete else DataCompleteness.INCOMPLETE,
            requires_expert_review=True,
            eligible_for_normal_ranking=False,
            score_validity=ScoreValidity.AUDIT_ONLY,
        )

    # 3) EXPERT_REVIEW_REQUIRED
    if reg_prohibited_unknown_scope or safety_unknown_scope_concern:
        reasons = []
        if reg_prohibited_unknown_scope:
            reasons.append(regulatory.reason)
        if safety_unknown_scope_concern:
            reasons.append(safety.reason)
        return EligibilityDecision(
            status=EligibilityStatus.EXPERT_REVIEW_REQUIRED,
            hard_no_go=False,
            gate_type="both" if len(reasons) > 1 else ("regulatory" if reg_prohibited_unknown_scope else "safety"),
            gate_reason=" | ".join(reasons),
            gate_evidence_ids=evidence_ids,
            safety_finding=safety,
            regulatory_finding=regulatory,
            data_completeness=DataCompleteness.COMPLETE if not data_incomplete else DataCompleteness.INCOMPLETE,
            requires_expert_review=True,
            eligible_for_normal_ranking=False,
            score_validity=ScoreValidity.PRELIMINARY,
        )

    # 4) ELIGIBLE_WITH_RESTRICTIONS — a real regulatory restriction, or a
    # severe safety finding whose scope/relevance is CONFIRMED not to
    # apply to this candidate. MODERATE/MINOR non-hard findings remain
    # visible and traceable but do not automatically change eligibility.
    # MINOR safety findings are handled separately below (rule 6) — per the design review, a minor/non-
    # hard safety term is warning-only and stays ELIGIBLE by default,
    # not automatically restricted, unless project policy explicitly
    # decides otherwise for a specific term (not modeled here).
    if (
        regulatory.status == RegulatoryDataStatus.RESTRICTED
        or safety_confirmed_irrelevant
    ):
        reasons = [r for r in (safety.reason, regulatory.reason) if r]
        return EligibilityDecision(
            status=EligibilityStatus.ELIGIBLE_WITH_RESTRICTIONS,
            hard_no_go=False,
            gate_type="both" if (regulatory.status == RegulatoryDataStatus.RESTRICTED and safety.severity != SafetySeverity.NONE) else (
                "regulatory" if regulatory.status == RegulatoryDataStatus.RESTRICTED else "safety"
            ),
            gate_reason=" | ".join(reasons),
            gate_evidence_ids=evidence_ids,
            safety_finding=safety,
            regulatory_finding=regulatory,
            data_completeness=DataCompleteness.COMPLETE if not data_incomplete else DataCompleteness.INCOMPLETE,
            requires_expert_review=False,
            eligible_for_normal_ranking=True,
            score_validity=ScoreValidity.VALID if not data_incomplete else ScoreValidity.PRELIMINARY,
        )

    # 5) INCOMPLETE — no concern found, but not enough data to be sure.
    if data_incomplete:
        reasons = [r for r in (safety.reason, regulatory.reason) if r]
        return EligibilityDecision(
            status=EligibilityStatus.INCOMPLETE,
            hard_no_go=False,
            gate_type="none",
            gate_reason=" | ".join(reasons),
            gate_evidence_ids=evidence_ids,
            safety_finding=safety,
            regulatory_finding=regulatory,
            data_completeness=DataCompleteness.INCOMPLETE,
            requires_expert_review=False,
            eligible_for_normal_ranking=False,
            score_validity=ScoreValidity.PRELIMINARY,
        )

    # 6) ELIGIBLE — includes the MINOR-safety case: a warning-only,
    # non-hard safety term does not restrict normal ranking. It stays
    # fully traceable via Safety_Severity="minor" and gate_reason on
    # this same decision object — visible, but not gating.
    gate_reason = (
        safety.reason if safety.severity in (SafetySeverity.MINOR, SafetySeverity.MODERATE)
        else "No documented safety or regulatory concern found in available evidence."
    )
    return EligibilityDecision(
        status=EligibilityStatus.ELIGIBLE,
        hard_no_go=False,
        gate_type="safety" if safety.severity in (SafetySeverity.MINOR, SafetySeverity.MODERATE) else "none",
        gate_reason=gate_reason,
        gate_evidence_ids=evidence_ids,
        safety_finding=safety,
        regulatory_finding=regulatory,
        data_completeness=DataCompleteness.COMPLETE,
        requires_expert_review=False,
        eligible_for_normal_ranking=True,
        score_validity=ScoreValidity.VALID,
    )
