"""
Phase 3B-C — Execution Readiness / Contamination Guard.

WHAT THIS DECIDES, AND WHAT IT DOES NOT (Responsibility boundary)
This module decides exactly one thing: whether a GoldCase is currently
permitted to proceed to gold_case_execution.execute_gold_case_against_
engine(), and why or why not. It does NOT decide scientific
correctness, does NOT compute or alter resolved_outcomes, does NOT run
or instantiate BotanicalRDCandidateEngine, does NOT assign
DatasetSplit, and does NOT replace dataset_split.assess_leakage()
(which governs a different question — whether an already-executed,
already-locked case is safe as holdout; this guard runs strictly
BEFORE that, as a pre-execution gate). It is read-only over a GoldCase
and the small set of engine-adjacent lookup tables named below.
assess_execution_readiness() is pure and non-mutating — same
convention as dataset_split.assess_leakage().

WHY GoldCase ALONE IS NOT ENOUGH INPUT
GoldCase has no field for curator judgments about whether a piece of
Engine Evidence is scope-equivalent (preparation/population/route) to
its ValidationUnit — and this module does not add one (that would be
an unrequested schema change, and conflates "case truth" with
"execution-governance metadata", two things this design deliberately
keeps separate). Callers must supply those judgments explicitly via
ExecutionReadinessInput.dimension_assessments — the guard never
infers equivalence by comparing plain strings on its own.

WHY NORMALIZATION IS INDEPENDENTLY IMPLEMENTED, NOT IMPORTED FROM THE
ENGINE
See normalization.py's own module docstring. This module calls only
normalization.normalize_text()/normalize_taxon() — never
botanical_rd_candidate_engine.BotanicalRDCandidateEngine._norm or
._norm_taxon. Parity between the two is guaranteed by
test_normalization_matches_engine.py, not by shared code.

DECISION MODEL
    READY  — no known blocking or deferring condition found.
    DEFER  — a currently-missing-or-unresolved condition (more
             evidence, a curator judgment, a normalization risk) could
             resolve this later without anything about the case being
             wrong. Recoverable by addition, not by change.
    BLOCK  — a positively confirmed, structural problem. Recoverable
             only by changing something about the case's current
             construction (different evidence, different taxon
             string, etc.), never merely by waiting or supplying more
             of the same kind of information.

Precedence: every triggered ReadinessReasonCode is collected (a case
can show several simultaneously); the overall decision is the most
severe tier among them (BLOCK > DEFER > READY) — see _decide() below,
never an early-exit chain of scattered ifs.

DECISION MATRIX (exhaustive)
    Ground Truth incomplete/unresolved (is_lockable()==False) -> BLOCK
    No engine evidence supplied                                -> DEFER
    Engine evidence source-overlaps Ground Truth's own source   -> BLOCK
    Any required dimension (Preparation/Population/Route)
        not supplied at all, or explicitly UNKNOWN               -> DEFER
    Any required dimension = MISMATCH                            -> BLOCK
    Dimension = ACCEPTABLE_EQUIVALENCE with no justification.rationale
                                                                  -> DEFER
    Seed-data collision CONFIRMED (matches under the
        normalization the engine's real lookup actually uses)    -> BLOCK
    Seed-data collision RISK only (matches under an alternate
        normalization, not today's actual lookup)                -> DEFER
    None of the above                                            -> READY

KNOWN LIMITATION — ENGINE-EVIDENCE SOURCE-OVERLAP DETECTION
EngineEvidenceInput is a frozen, four-plain-field dataclass (see
engine_evidence_input.py) with no field capable of citing a source
document — by design, for the same structural-leakage-boundary reason
documented there. This guard therefore detects overlap only
heuristically: whether the selected Ground-Truth reference's
reference_id (or a distinguishing numeric fragment of it) appears as a
substring of any supplied EngineEvidenceInput.notes text. This is a
best-effort check, not a rigorous one — a genuinely independent
evidence source citing the SAME underlying fact in different words
would not be caught by this. A future, more rigorous version would
need a curator-attested evidence-source-citation field, which does not
exist today and is not added here.

KNOWN LIMITATION — AUTHORITY-CITATION SUFFIXES ARE INVISIBLE TO SEED-
DATA COLLISION DETECTION (found while writing
test_normalization_matches_engine.py, not assumed)
normalize_taxon()/BotanicalRDCandidateEngine._norm_taxon() strip only
hybrid markers and infraspecific-rank tokens (x/subsp/ssp/nothosubsp/
var/f/cv) — NOT taxonomic authority citations such as "L." (Linnaeus).
An earlier round of this validation program incorrectly assumed
"Melissa officinalis L." would collide with the seed key "Melissa
officinalis" under taxon-normalization; verified, it does not, under
either normalize_text() or normalize_taxon(). This means a taxon
string differing from a SLEEP_TEA_EVIDENCE key only by an authority
citation currently produces NEITHER a CONFIRMED nor a RISK signal from
this guard — a real, disclosed coverage gap, not a safe outcome to
rely on. Extending _seed_collision_status() with an authority-citation
-stripping normalization is a reasonable future improvement, but is
NOT implemented here (that would mean this guard's own "risk" category
starts flagging things the engine's actual current code cannot
reach — a different, weaker guarantee than the CONFIRMED category
intentionally provides, and worth a separate explicit decision, not a
quiet addition).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from gold_case import GoldCase, is_lockable
from normalization import normalize_taxon, normalize_text
from reference_precedence import ResolutionStatus
from seed_data import SLEEP_TEA_EVIDENCE


class ScopeDimension(str, Enum):
    PREPARATION = "Preparation"
    POPULATION = "Population"
    ROUTE = "Route"


class ScopeEquivalence(str, Enum):
    EXACT = "Exact"
    ACCEPTABLE_EQUIVALENCE = "Acceptable equivalence"
    MISMATCH = "Mismatch"
    UNKNOWN = "Unknown"


class ExecutionReadiness(str, Enum):
    READY = "Ready"
    DEFER = "Defer"
    BLOCK = "Block"


class ReadinessReasonCode(str, Enum):
    GROUND_TRUTH_INCOMPLETE = "Ground Truth incomplete: resolved_outcomes missing, unresolved, or not SELECTED (is_lockable() failed)"
    NO_ENGINE_EVIDENCE = "No engine evidence supplied"
    ENGINE_EVIDENCE_SOURCE_OVERLAP = "Engine evidence appears to trace to the Ground Truth's own governing source"
    PREPARATION_MISMATCH = "Preparation dimension assessed as Mismatch"
    POPULATION_MISMATCH = "Population dimension assessed as Mismatch"
    ROUTE_MISMATCH = "Route dimension assessed as Mismatch"
    DIMENSION_UNKNOWN = "One or more required dimensions not supplied or assessed as Unknown"
    EQUIVALENCE_JUSTIFICATION_INCOMPLETE = "A dimension assessed Acceptable-equivalence lacks a rationale"
    SEED_DATA_COLLISION_CONFIRMED = "Taxon collides with a seed-evidence key under the normalization the engine's real lookup actually uses today"
    SEED_DATA_COLLISION_RISK = "Taxon would collide with a seed-evidence key under a plausible alternate normalization, though not today's actual lookup"
    # No GUARD_NOT_YET_RUN member — the absence of a prior
    # ExecutionReadinessResult is an orchestration-layer precondition
    # failure, never a reason a completed assessment reports about
    # itself.


_DIMENSION_MISMATCH_REASON = {
    ScopeDimension.PREPARATION: ReadinessReasonCode.PREPARATION_MISMATCH,
    ScopeDimension.POPULATION: ReadinessReasonCode.POPULATION_MISMATCH,
    ScopeDimension.ROUTE: ReadinessReasonCode.ROUTE_MISMATCH,
}

_REQUIRED_DIMENSIONS = (ScopeDimension.PREPARATION, ScopeDimension.POPULATION, ScopeDimension.ROUTE)

_BLOCK_REASONS = frozenset({
    ReadinessReasonCode.GROUND_TRUTH_INCOMPLETE,
    ReadinessReasonCode.ENGINE_EVIDENCE_SOURCE_OVERLAP,
    ReadinessReasonCode.PREPARATION_MISMATCH,
    ReadinessReasonCode.POPULATION_MISMATCH,
    ReadinessReasonCode.ROUTE_MISMATCH,
    ReadinessReasonCode.SEED_DATA_COLLISION_CONFIRMED,
})


@dataclass(frozen=True)
class EquivalenceJustification:
    """Structured rationale for a ScopeEquivalence.ACCEPTABLE_EQUIVALENCE
    judgment — a bare free string was judged insufficient (see design
    review). reference_id/source_locator are optional: some
    equivalence judgments are operational (e.g. "tea-bag brewed as
    infusion is the same preparation category"), not directly drawn
    from a single document — but `rationale` itself is always
    required wherever a justification is required at all (see
    _decide()'s EQUIVALENCE_JUSTIFICATION_INCOMPLETE check)."""
    rationale: str
    reference_id: str = ""
    source_locator: str = ""
    curator: str = ""


@dataclass(frozen=True)
class DimensionAssessment:
    dimension: ScopeDimension
    equivalence: ScopeEquivalence
    justification: Optional[EquivalenceJustification] = None
    detail: str = ""


@dataclass(frozen=True)
class ExecutionReadinessInput:
    """Separate from GoldCase on purpose — see module docstring's
    'WHY GoldCase ALONE IS NOT ENOUGH INPUT'."""
    gold_case: GoldCase
    dimension_assessments: tuple = ()  # tuple[DimensionAssessment, ...]


@dataclass(frozen=True)
class ExecutionReadinessResult:
    case_id: str
    decision: ExecutionReadiness
    reasons: tuple = ()                # tuple[ReadinessReasonCode, ...]
    dimension_assessments: tuple = ()  # tuple[DimensionAssessment, ...], passthrough for traceability
    detail: str = ""


def _ground_truth_ok(gold_case: GoldCase) -> bool:
    """Reuses gold_case.is_lockable() rather than reimplementing its
    checks — see module docstring."""
    lockable, _reasons = is_lockable(gold_case)
    return lockable


def _seed_collision_status(taxon: str) -> tuple:
    """Returns (confirmed: bool, risk: bool). CONFIRMED means the
    taxon collides with a seed_data.SLEEP_TEA_EVIDENCE key under
    normalize_text() — the same normalization the engine's real,
    current plant-keyed lookup actually applies (see
    normalization.py's module docstring). RISK means it does NOT
    collide under normalize_text(), but WOULD under normalize_taxon()
    — a plausible alternate/future normalization, not today's actual
    lookup. Never both True at once."""
    text_key = normalize_text(taxon)
    taxon_key = normalize_taxon(taxon)

    confirmed = any(normalize_text(seed_key) == text_key for seed_key in SLEEP_TEA_EVIDENCE)
    if confirmed:
        return True, False

    risk = any(normalize_taxon(seed_key) == taxon_key for seed_key in SLEEP_TEA_EVIDENCE)
    return False, risk


def _engine_evidence_source_overlap(gold_case: GoldCase) -> bool:
    """Best-effort heuristic only — see module docstring's KNOWN
    LIMITATION section. Checks whether any SELECTED resolved
    outcome's selected_reference_id (or a distinguishing digit run
    within it, e.g. an EMA/HMPC document number) appears as a
    substring of any supplied EngineEvidenceInput.notes text."""
    if not gold_case.engine_evidence:
        return False

    selected_reference_ids = [
        outcome.selected_reference_id
        for outcome in gold_case.resolved_outcomes
        if outcome.resolution_status == ResolutionStatus.SELECTED and outcome.selected_reference_id
    ]
    if not selected_reference_ids:
        return False

    notes_blob = normalize_text(
        " ".join(item.notes for item in gold_case.engine_evidence if item.notes)
    )
    if not notes_blob:
        return False

    for reference_id in selected_reference_ids:
        ref_key = normalize_text(reference_id)
        if ref_key and ref_key in notes_blob:
            return True
        # Distinguishing numeric fragments (e.g. "196745" from an
        # EMA/HMPC id) catch a citation even if the full reference_id
        # string isn't reproduced verbatim.
        for fragment in ref_key.split("_"):
            if len(fragment) >= 5 and fragment.isdigit() and fragment in notes_blob:
                return True

    return False


def _decide(
    ground_truth_ok: bool,
    evidence_present: bool,
    evidence_overlaps_source: bool,
    dimension_assessments: tuple,
    seed_confirmed: bool,
    seed_risk: bool,
) -> tuple:
    """The one place the decision matrix is expressed — see module
    docstring's DECISION MATRIX. Returns (ExecutionReadiness,
    tuple[ReadinessReasonCode, ...]). Collects every triggered reason
    before deciding the tier; never stops at the first match."""
    reasons = []

    if not ground_truth_ok:
        reasons.append(ReadinessReasonCode.GROUND_TRUTH_INCOMPLETE)

    if not evidence_present:
        reasons.append(ReadinessReasonCode.NO_ENGINE_EVIDENCE)

    if evidence_overlaps_source:
        reasons.append(ReadinessReasonCode.ENGINE_EVIDENCE_SOURCE_OVERLAP)

    assessed_dimensions = {da.dimension for da in dimension_assessments}
    for dimension in _REQUIRED_DIMENSIONS:
        if dimension not in assessed_dimensions:
            reasons.append(ReadinessReasonCode.DIMENSION_UNKNOWN)

    for da in dimension_assessments:
        if da.equivalence == ScopeEquivalence.MISMATCH:
            reasons.append(_DIMENSION_MISMATCH_REASON[da.dimension])
        elif da.equivalence == ScopeEquivalence.UNKNOWN:
            reasons.append(ReadinessReasonCode.DIMENSION_UNKNOWN)
        elif da.equivalence == ScopeEquivalence.ACCEPTABLE_EQUIVALENCE:
            if not (da.justification and da.justification.rationale.strip()):
                reasons.append(ReadinessReasonCode.EQUIVALENCE_JUSTIFICATION_INCOMPLETE)

    if seed_confirmed:
        reasons.append(ReadinessReasonCode.SEED_DATA_COLLISION_CONFIRMED)
    elif seed_risk:
        reasons.append(ReadinessReasonCode.SEED_DATA_COLLISION_RISK)

    if any(r in _BLOCK_REASONS for r in reasons):
        return ExecutionReadiness.BLOCK, tuple(reasons)
    if reasons:
        return ExecutionReadiness.DEFER, tuple(reasons)
    return ExecutionReadiness.READY, ()


def assess_execution_readiness(readiness_input: ExecutionReadinessInput) -> ExecutionReadinessResult:
    """The ONE function this module exists to provide. Pure,
    non-mutating. Never instantiates or calls BotanicalRDCandidateEngine
    in any way — reads only readiness_input.gold_case and
    seed_data.SLEEP_TEA_EVIDENCE, and normalizes via normalization.py
    (never the engine's private methods)."""
    gold_case = readiness_input.gold_case

    ground_truth_ok = _ground_truth_ok(gold_case)
    evidence_present = bool(gold_case.engine_evidence)
    evidence_overlaps_source = _engine_evidence_source_overlap(gold_case)
    seed_confirmed, seed_risk = _seed_collision_status(gold_case.validation_unit.taxon)

    decision, reasons = _decide(
        ground_truth_ok=ground_truth_ok,
        evidence_present=evidence_present,
        evidence_overlaps_source=evidence_overlaps_source,
        dimension_assessments=readiness_input.dimension_assessments,
        seed_confirmed=seed_confirmed,
        seed_risk=seed_risk,
    )

    return ExecutionReadinessResult(
        case_id=gold_case.case_id,
        decision=decision,
        reasons=reasons,
        dimension_assessments=readiness_input.dimension_assessments,
    )
