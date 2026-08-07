"""
Critical Safety False-Negative Remediation — Structured Interaction /
Contraindication Severity Classifier.

WHAT THIS IS
A generic, plant-agnostic, case-agnostic module that turns raw
evidence prose into a structured safety assertion:

    Safety Evidence (raw text)
      -> assertion language classification (contraindication / interaction
         relation / precaution / mechanism-only, negation-aware)
      -> high-risk drug-class detection (generic vocabulary)
      -> severity tier (reusing severity_assignment_policy.py's existing,
         already-approved SERIOUS-assignment rule)
      -> InteractionAssertionResult

This is the missing link the Case 006 (Hypericum perforatum) audit
identified: production evidence text plainly describing a serious,
clinically relevant drug interaction / contraindication (e.g. EMA
Section 4.3 "Contraindications" text) was extracted into
Interaction_Flags (see safety_interaction_attribution.py /
INTERACTION_TERMS in botanical_rd_candidate_engine.py) but that
extraction was never connected to anything that could force a hard
safety stop -- only Safety_Flags intersected with HARD_SAFETY_TERMS
(a DB-activity vocabulary: "lithogenic", "abortifacient", etc., see
botanical_rd_candidate_engine.DB_ACTIVITY_SAFETY_TERMS) could do that,
and that vocabulary structurally cannot contain drug-interaction or
contraindication language. This module is a THIRD, independent
channel -- it does not touch DB_ACTIVITY_SAFETY_TERMS, does not touch
SAFETY_TERMS, and does not touch eligibility_gate.py's decision table.
It only produces a new, narrowly-scoped hard-safety hit term
(HARD_GATE_SIGNAL_TERM) that botanical_rd_candidate_engine.py folds
into its existing Safety_Flags / HARD_SAFETY_TERMS intersection
mechanism -- the same mechanism every other hard-safety signal in this
platform already goes through.

WHY THIS DOES NOT VIOLATE THE EXISTING SAFETY_TERMS / HARD_SAFETY_TERMS
CAPABILITY BOUNDARY
engine_evidence_input.py and test_gold_case_execution.py document a
real, previously-approved boundary: free text scanned against
SAFETY_TERMS could not, by itself, force a hard stop; only
compound_activity_targets (a structured DB channel) could. That
boundary is preserved exactly as-is for DB_ACTIVITY_SAFETY_TERMS. What
this module adds is a NEW, third channel with its own, much narrower
and much more specific trigger condition: BOTH (a) explicit
contraindication/serious-interaction assertion language (not a bare
hazard word) AND (b) a recognized high-risk interacting drug class (or
an explicit named interacting substance) must be present in the same
sentence-level unit of text. A bare hazard word ("contraindicated in
pregnancy", with no drug/interaction language at all) still does
nothing here -- see test_structured_serious_interaction_gate_fix.py's
negative controls, which reuse the exact fixture
test_gold_case_execution.py::test_capability_boundary_notes_alone_cannot_trigger_hard_safety_gate
already uses, to prove this explicitly.

WHY REUSE severity_assignment_policy.py / assertion_vocabulary.py
RATHER THAN DUPLICATING THEM
Both modules are already generic, already reviewed, and import
NOTHING from gold_cases/ or any other Reference-Grounded Validation
file -- assertion_vocabulary.py has zero imports of its own, and
severity_assignment_policy.py imports only assertion_vocabulary.py.
Neither module holds any case-specific data (no PMIDs, no plant names,
no EMA document IDs) -- they are pure, versioned policy. Importing them
from production code is a forward dependency on a shared vocabulary
module, not a reverse dependency on validation infrastructure, and
creates no leakage risk: this module supplies the DRUG CLASSES its own
generic text-detection finds, exactly the same shape of input a
GoldCase curator supplies by hand today. The one rule
(assign_contraindication_severity) that decides SERIOUS vs "no rule
applies" is therefore never re-implemented or re-decided here --
production and validation now cite the exact same
SEVERITY_ASSIGNMENT_RULE_VERSION.

WHAT THIS MODULE DELIBERATELY DOES NOT DO
- No plant name, taxon, PMID, or EMA document ID appears anywhere in
  this file. Every pattern below is generic pharmacological-language
  vocabulary, applicable to any botanical, any source, any case.
- Does not upgrade a bare mechanism mention (CYP3A4 induction,
  P-glycoprotein substrate, "may affect drug metabolism") into a
  SERIOUS or even MODERATE severity by itself -- see
  InteractionSeverityTier.THEORETICAL_MECHANISTIC. A source has to
  actually assert a contraindication or an interaction relationship,
  not merely mention an enzyme, before severity is assigned.
- Does not decide applicability/scope (whether the finding actually
  applies to a specific candidate row's plant part / preparation /
  population). That remains eligibility_gate.py's job via
  FindingScope/ContextRelevance, entirely unmodified by this file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import FrozenSet, Tuple

from assertion_vocabulary import AssertionType, SeverityLevel
from severity_assignment_policy import (
    HighRiskInteractionDrugClass,
    assign_contraindication_severity,
)

INTERACTION_SEVERITY_CLASSIFIER_VERSION = "1.0.0"

# The single canonical term this module ever contributes to a hard
# hit-term set. Deliberately one stable string, not one string per
# drug class or per plant -- botanical_rd_candidate_engine.py adds
# this ONE term to HARD_SAFETY_TERMS, so this module's entire surface
# area for forcing a hard stop is this one constant.
HARD_GATE_SIGNAL_TERM = "structured_serious_drug_interaction_or_contraindication"


class InteractionSeverityTier(str, Enum):
    """The six-way distinction the Case 006 remediation explicitly
    requires (serious contraindication / serious high-risk interaction
    / moderate interaction / precaution-caution / theoretical-
    mechanistic / none). "Insufficient context" is deliberately NOT a
    tier here -- once a SERIOUS_* tier is produced, whether the
    candidate row's context (plant part/preparation/population) is
    confirmed relevant is eligibility_gate.py's job (FindingScope /
    ContextRelevance), not this module's; production never supplies a
    confirmed scope today, so a SERIOUS_* tier already resolves to
    EXPERT_REVIEW_REQUIRED rather than an automatic pass, honestly
    reflecting that missing context (see eligibility_gate.py's module
    docstring)."""
    SERIOUS_CONTRAINDICATION = "serious_contraindication"
    SERIOUS_HIGH_RISK_INTERACTION = "serious_high_risk_interaction"
    MODERATE_INTERACTION = "moderate_interaction"
    PRECAUTION_CAUTION = "precaution_caution"
    THEORETICAL_MECHANISTIC = "theoretical_mechanistic"
    NONE = "none"


# Tiers that must reach the eligibility gate as a non-compensable hard
# safety signal (SafetySeverity.SEVERE in eligibility_gate.py terms).
_HARD_TIERS = frozenset({
    InteractionSeverityTier.SERIOUS_CONTRAINDICATION,
    InteractionSeverityTier.SERIOUS_HIGH_RISK_INTERACTION,
})

# ======================================================================
# Vocabulary. Generic pharmacological-language patterns, no plant/case
# names anywhere.
# ======================================================================

# Explicit contraindication-strength assertion language -- several
# semantically-equivalent phrasings (Case 006 remediation requirement
# 4: wording robustness), not one hard-coded literal string.
_CONTRAINDICATION_PATTERNS = (
    r"\bcontraindicat(?:ed|ion|ions)\b",
    r"\bmust not be (?:co-?administered|combined|used concomitantly|"
    r"taken (?:together|concomitantly))\b",
    r"\bshould not be (?:co-?administered|combined|used concomitantly|"
    r"taken together)\b",
    r"\b(?:concomitant|concurrent) use\b.{0,100}?\b(?:is|should be|must be)"
    r"\s+(?:contraindicated|avoided)\b",
    r"\bdo not (?:use|take|combine|co-?administer)\s+"
    r"(?:concomitantly|together|with)\b",
    r"\bnot recommended for concomitant use\b",
    r"\bshould (?:not )?be avoided (?:in patients )?(?:taking|receiving|"
    r"using)\b",
)

# Weaker, relational interaction language -- an interaction is
# asserted, but not phrased as an outright prohibition.
_INTERACTION_RELATION_PATTERNS = (
    r"\binteract(?:s|ed|ion|ions)? with\b",
    r"\bdrug[- ]interaction(?:s)?\b",
    r"\bclinically (?:significant|relevant) interaction(?:s)?\b",
    r"\b(?:concomitant|concurrent) (?:use|administration) (?:with|of)\b",
    r"\bco[- ]administr(?:ation|ed) with\b",
    r"\bmay (?:increase|decrease|reduce|potentiate|lower|raise)\b.{0,60}"
    r"\b(?:plasma concentration|exposure|effect|efficacy|level|risk)s?\b",
    r"\breduc(?:e|es|ed|ing) (?:the )?(?:plasma concentration|"
    r"therapeutic effect|efficacy)\b",
)

# Precaution/monitoring-only language -- weaker still, informational.
_PRECAUTION_PATTERNS = (
    r"\bcaution (?:is )?(?:advised|recommended|required)\b",
    r"\bmay require dose adjustment\b",
    r"\bmonitor(?:ing)? (?:is )?(?:recommended|advised|required)\b",
    r"\bconsult (?:a |your )?(?:physician|doctor|healthcare provider)\b",
    r"\buse with caution\b",
)

# Mechanism-only language: an enzyme/transporter is named, but no
# avoid/interaction-relation language accompanies it. On its own this
# must never raise severity (Case 006 remediation requirement:
# "if source only reports CYP/P-gp mechanism ... engine must not
# raise severity without evidence").
_MECHANISTIC_ONLY_PATTERNS = (
    r"\bcyp\d[a-z]\d\b", r"\bcytochrome p ?450\b",
    r"\bp[- ]glycoprotein\b", r"\bp[- ]gp\b",
    r"\benzyme induc(?:tion|er|es|ed)\b",
    r"\benzyme inhibit(?:ion|or|s|ed)\b",
    r"\bhepatic (?:metaboli[sz]ing )?enzyme\b",
    r"\bpregnane x receptor\b", r"\bpxr\b",
)

# Negation cues that flip a nearby assertion from "present" to
# "explicitly absent" -- same proximity-based technique
# botanical_rd_candidate_engine.py's own _extract_flags_negation_aware
# already uses for SAFETY_TERMS/DB_ACTIVITY_SAFETY_TERMS, applied here
# independently (this module must not import from the engine, which
# imports it). Checked in the window immediately BEFORE a
# contraindication/interaction-relation match, not as a separate
# whole-sentence pattern -- "no known drug interactions have been
# reported" must not first match _INTERACTION_RELATION_PATTERNS'
# "drug interaction" and only then be second-guessed by an unrelated
# reassurance pattern; the two have to share the same match.
_NEGATION_CUES = (
    "no ", "not ", "no known ", "no documented ", "no reported ",
    "no clinically significant ", "did not ", "without ",
    "absence of ", "lack of ", "no evidence of ", "never observed",
)
_NEGATION_WINDOW = 40

# A small set of strong, standalone reassurance phrasings that do not
# depend on proximity to a specific contraindication/interaction match
# (e.g. "safe to use with" has no separate positive hit to be "near").
# These still only suppress a HIGH-RISK escalation for the unit they
# appear in -- see _classify_unit.
_STRONG_REASSURANCE_PATTERNS = (
    r"\bsafe (?:to use )?(?:when )?(?:co-?administered|combined) with\b",
    r"\bno contraindications? (?:were |are )?(?:identified|known|reported)\b",
)

# Generic high-risk interacting drug-class vocabulary. Maps directly
# onto severity_assignment_policy.HighRiskInteractionDrugClass -- no
# new severity concept is invented here, only detection of which
# already-approved class (if any) a piece of text names or describes.
_HIGH_RISK_CLASS_PATTERNS = {
    HighRiskInteractionDrugClass.ANTICOAGULANT: (
        r"\banticoagulant(?:s)?\b", r"\bantiplatelet(?:s)?\b",
        r"\bcoumarin(?:s|[- ]type)?\b", r"\bwarfarin\b",
    ),
    HighRiskInteractionDrugClass.TRANSPLANT_IMMUNOSUPPRESSANT: (
        r"\bimmunosuppressant(?:s)?\b", r"\bcyclosporine\b",
        r"\bciclosporin\b", r"\btacrolimus\b", r"\beverolimus\b",
        r"\bsirolimus\b", r"\btransplant rejection\b",
        r"\borgan transplant\b",
    ),
    HighRiskInteractionDrugClass.ANTIRETROVIRAL_THERAPY: (
        r"\bantiretroviral(?:s)?\b", r"\bprotease inhibitor(?:s)?\b",
        r"\bnucleoside reverse transcriptase inhibitor(?:s)?\b",
        r"\bnnrti(?:s)?\b", r"\bnrti(?:s)?\b",
        r"\bindinavir\b", r"\bfosamprenavir\b",
        r"\bhiv (?:medication|therapy|treatment)\b",
    ),
    HighRiskInteractionDrugClass.CYTOTOXIC_AGENT: (
        r"\bcytotoxic (?:agent|drug)(?:s)?\b",
        r"\bcytostatic (?:agent|drug)(?:s)?\b",
        r"\bchemotherap(?:y|eutic agent(?:s)?)\b",
        r"\birinotecan\b", r"\bimatinib\b",
    ),
    HighRiskInteractionDrugClass.NARROW_THERAPEUTIC_INDEX: (
        r"\bnarrow therapeutic index\b", r"\bdigoxin\b",
        r"\btheophylline\b", r"\bphenytoin\b", r"\blithium\b",
    ),
}

_APPLICABLE_ASSERTION_TYPES = frozenset({
    AssertionType.CONTRAINDICATION,
    AssertionType.INTERACTION,
})

_UNIT_SPLIT_RE = re.compile(r"(?<=[.;\n])\s+")


def _norm(text: object) -> str:
    return str(text or "").lower()


def _matches_any(text_norm: str, patterns: Tuple[str, ...]) -> str:
    for pattern in patterns:
        m = re.search(pattern, text_norm)
        if m:
            return m.group(0)
    return ""


def _matches_any_not_negated(text_norm: str, patterns: Tuple[str, ...]) -> str:
    """Like _matches_any, but discards a match preceded (within
    _NEGATION_WINDOW characters) by a negation cue -- "no known drug
    interactions", "did not interact with", "without contraindication".
    Tries every match position for every pattern, not just the first,
    so a negated first mention doesn't hide a genuine later one."""
    for pattern in patterns:
        for m in re.finditer(pattern, text_norm):
            window_start = max(0, m.start() - _NEGATION_WINDOW)
            preceding = text_norm[window_start:m.start()]
            if any(cue in preceding for cue in _NEGATION_CUES):
                continue
            return m.group(0)
    return ""


def _split_units(text_norm: str) -> Tuple[str, ...]:
    if not text_norm:
        return ()
    units = [u.strip() for u in _UNIT_SPLIT_RE.split(text_norm) if u.strip()]
    return tuple(units) if units else (text_norm,)


def _detect_drug_classes(text_norm: str) -> FrozenSet[HighRiskInteractionDrugClass]:
    found = set()
    for drug_class, patterns in _HIGH_RISK_CLASS_PATTERNS.items():
        if _matches_any(text_norm, patterns):
            found.add(drug_class)
    return frozenset(found)


@dataclass(frozen=True)
class InteractionAssertionResult:
    tier: InteractionSeverityTier
    assertion_type: AssertionType
    severity: SeverityLevel
    drug_classes: FrozenSet[HighRiskInteractionDrugClass] = field(default_factory=frozenset)
    matched_language: str = ""
    reason: str = ""


_NONE_RESULT = InteractionAssertionResult(
    tier=InteractionSeverityTier.NONE,
    assertion_type=AssertionType.INTERACTION,
    severity=SeverityLevel.NONE,
    reason="No drug-interaction or contraindication assertion detected.",
)


def _classify_unit(unit_norm: str) -> InteractionAssertionResult:
    strong_reassurance_hit = _matches_any(unit_norm, _STRONG_REASSURANCE_PATTERNS)
    if strong_reassurance_hit:
        return InteractionAssertionResult(
            tier=InteractionSeverityTier.NONE,
            assertion_type=AssertionType.INTERACTION,
            severity=SeverityLevel.NONE,
            matched_language=strong_reassurance_hit,
            reason=f"Explicit negation/reassurance present: {strong_reassurance_hit!r}.",
        )

    contraindication_hit = _matches_any_not_negated(unit_norm, _CONTRAINDICATION_PATTERNS)
    interaction_hit = _matches_any_not_negated(unit_norm, _INTERACTION_RELATION_PATTERNS)
    precaution_hit = _matches_any_not_negated(unit_norm, _PRECAUTION_PATTERNS)
    mechanistic_hit = _matches_any(unit_norm, _MECHANISTIC_ONLY_PATTERNS)

    if not (contraindication_hit or interaction_hit or precaution_hit or mechanistic_hit):
        return _NONE_RESULT

    drug_classes = _detect_drug_classes(unit_norm)

    if contraindication_hit:
        if drug_classes:
            severity = assign_contraindication_severity(
                AssertionType.CONTRAINDICATION, drug_classes,
            )
            if severity == SeverityLevel.SERIOUS:
                return InteractionAssertionResult(
                    tier=InteractionSeverityTier.SERIOUS_CONTRAINDICATION,
                    assertion_type=AssertionType.CONTRAINDICATION,
                    severity=SeverityLevel.SERIOUS,
                    drug_classes=drug_classes,
                    matched_language=contraindication_hit,
                    reason=(
                        "Explicit contraindication language "
                        f"({contraindication_hit!r}) combined with "
                        "high-risk interacting drug class(es): "
                        f"{', '.join(sorted(c.value for c in drug_classes))}."
                    ),
                )
        # Contraindication language present but no recognized
        # high-risk drug class in this vocabulary -- e.g. a
        # non-drug-interaction contraindication ("contraindicated in
        # pregnancy"), or an interacting substance outside this
        # module's generic vocabulary. Deliberately NOT auto-escalated
        # to SERIOUS: this policy only formalizes the high-risk-class
        # case (severity_assignment_policy.py's own documented scope).
        # Still surfaced as MODERATE so it stays visible, never
        # silently dropped.
        return InteractionAssertionResult(
            tier=InteractionSeverityTier.MODERATE_INTERACTION,
            assertion_type=AssertionType.CONTRAINDICATION,
            severity=SeverityLevel.MODERATE,
            drug_classes=drug_classes,
            matched_language=contraindication_hit,
            reason=(
                f"Contraindication language ({contraindication_hit!r}) "
                "present without a recognized high-risk interacting "
                "drug class."
            ),
        )

    if interaction_hit:
        if drug_classes:
            severity = assign_contraindication_severity(
                AssertionType.INTERACTION, drug_classes,
            )
            if severity == SeverityLevel.SERIOUS:
                return InteractionAssertionResult(
                    tier=InteractionSeverityTier.SERIOUS_HIGH_RISK_INTERACTION,
                    assertion_type=AssertionType.INTERACTION,
                    severity=SeverityLevel.SERIOUS,
                    drug_classes=drug_classes,
                    matched_language=interaction_hit,
                    reason=(
                        f"Interaction language ({interaction_hit!r}) combined "
                        "with high-risk interacting drug class(es): "
                        f"{', '.join(sorted(c.value for c in drug_classes))}."
                    ),
                )
        return InteractionAssertionResult(
            tier=InteractionSeverityTier.MODERATE_INTERACTION,
            assertion_type=AssertionType.INTERACTION,
            severity=SeverityLevel.MODERATE,
            drug_classes=drug_classes,
            matched_language=interaction_hit,
            reason=(
                f"Interaction language ({interaction_hit!r}) present without "
                "a recognized high-risk interacting drug class."
            ),
        )

    if precaution_hit:
        return InteractionAssertionResult(
            tier=InteractionSeverityTier.PRECAUTION_CAUTION,
            assertion_type=AssertionType.INTERACTION,
            severity=SeverityLevel.MINOR,
            matched_language=precaution_hit,
            reason=f"Precaution/monitoring-only language: {precaution_hit!r}.",
        )

    if mechanistic_hit:
        return InteractionAssertionResult(
            tier=InteractionSeverityTier.THEORETICAL_MECHANISTIC,
            assertion_type=AssertionType.INTERACTION,
            severity=SeverityLevel.NONE,
            matched_language=mechanistic_hit,
            reason=(
                f"Mechanism/enzyme-transporter mention only ({mechanistic_hit!r}); "
                "no contraindication or interaction-relation language present, "
                "so severity is not raised."
            ),
        )

    return _NONE_RESULT


_TIER_RANK = {
    InteractionSeverityTier.NONE: 0,
    InteractionSeverityTier.THEORETICAL_MECHANISTIC: 1,
    InteractionSeverityTier.PRECAUTION_CAUTION: 2,
    InteractionSeverityTier.MODERATE_INTERACTION: 3,
    InteractionSeverityTier.SERIOUS_HIGH_RISK_INTERACTION: 4,
    InteractionSeverityTier.SERIOUS_CONTRAINDICATION: 4,
}


def classify_interaction_assertion(text: object) -> InteractionAssertionResult:
    """The ONE function this module exists to provide. Pure,
    deterministic, generic: splits `text` into sentence-level units,
    classifies each independently (so a reassurance elsewhere in a
    long evidence blob cannot suppress a genuine warning), and returns
    the single most severe result found. Never raises; empty/None text
    returns the NONE tier."""
    text_norm = _norm(text)
    units = _split_units(text_norm)
    if not units:
        return _NONE_RESULT

    best = _NONE_RESULT
    for unit in units:
        result = _classify_unit(unit)
        if _TIER_RANK[result.tier] > _TIER_RANK[best.tier]:
            best = result
    return best


def hard_hit_terms_for(result: InteractionAssertionResult) -> FrozenSet[str]:
    """Returns the (at most one-element) frozenset of hard hit terms
    this result contributes. Only ever HARD_GATE_SIGNAL_TERM -- never
    a plant-specific or per-drug-class term -- so the caller's
    HARD_SAFETY_TERMS intersection mechanism stays generic."""
    if result.tier in _HARD_TIERS:
        return frozenset({HARD_GATE_SIGNAL_TERM})
    return frozenset()


def informational_terms_for(result: InteractionAssertionResult) -> Tuple[str, ...]:
    """Human-readable, non-hard descriptive terms for Safety_Flags /
    Rationale visibility -- never added to HARD_SAFETY_TERMS. Covers
    every non-NONE tier, including the hard ones (for traceability
    text), so a reviewer reading Safety_Flags always sees WHY, not
    just an opaque hard-stop."""
    if result.tier == InteractionSeverityTier.NONE:
        return ()
    classes = (
        ", ".join(sorted(c.value for c in result.drug_classes))
        if result.drug_classes else "unspecified"
    )
    label = {
        InteractionSeverityTier.SERIOUS_CONTRAINDICATION: "serious drug-interaction contraindication",
        InteractionSeverityTier.SERIOUS_HIGH_RISK_INTERACTION: "serious high-risk drug interaction",
        InteractionSeverityTier.MODERATE_INTERACTION: "moderate drug interaction",
        InteractionSeverityTier.PRECAUTION_CAUTION: "interaction precaution/caution",
        InteractionSeverityTier.THEORETICAL_MECHANISTIC: "theoretical/mechanistic interaction signal",
    }.get(result.tier)
    if label is None:
        return ()
    return (f"{label} ({classes})",)
