"""
Reference-Grounded Validation — GoldCase Execution.

WHY THIS DOES NOT ROUTE THROUGH validation_protocol_execution.py
validation_protocol_execution.execute_protocol_against_engine() requires
a LOCKED ValidationCaseProtocol, and ValidationCaseProtocol.lock_protocol()
hard-requires a real ExpertPanel — correct for a commercial validation
case, where a live expert panel is exactly what Appendix A demands. A
GoldCase is curated directly against authoritative references with NO
live expert panel required (Reference-Grounded Validation Principle —
see gold_case.CurationStatus). This module calls
BotanicalRDCandidateEngine directly, the same way
validation_protocol_execution.py itself does, without ever
constructing a ValidationCaseProtocol. validation_case_protocol.py is
untouched by this decision.

STRUCTURAL LEAKAGE BOUNDARY (v4 correction #1)
The ONLY evidence this function accepts is
list[engine_evidence_input.EngineEvidenceInput] — a frozen dataclass
with exactly three plain-string fields (scientific_name,
target_indication, notes). It is structurally impossible to pass a
ReferenceClaim or ResolvedExpectedOutcome through this parameter: no
such field exists on EngineEvidenceInput, so nothing about the
approved "reference truth" layer can reach the engine's actual
constructor call. This replaces the PRIOR (incorrect) design that
accepted a raw target= string as an ad hoc test-only trigger — that
parameter has been REMOVED entirely, not merely deprecated. Real
evidence must now flow as natural-language text in
EngineEvidenceInput.notes, exactly the way genuine evidence enters
production via evidence_df["Notes"] (see
botanical_rd_candidate_engine.py's _collect_raw_evidence()).

SINGLE-TAXON SCOPE, NEUTRAL ANCHOR (unchanged from the prior revision)
A GoldCase's ValidationUnit names exactly one taxon. This module runs
the engine with a fixed, neutral anchor taxon as the reference plant
and the GoldCase's real taxon as the alternative — NEVER a self-match
row, because botanical_rd_candidate_engine.py's same_plant exemption
would silently make the safety/regulatory gates NOT_EVALUABLE for a
self-matched row, defeating the entire point of a Safety-Serious
GoldCase. See test_gold_case_execution.py's
test_returned_row_uses_anchor_as_reference_and_taxon_as_alternative
for the regression lock on this.

WHAT THIS NEVER DOES
Never modifies botanical_rd_candidate_engine.py. Never computes a
metric itself (see evaluation_run.py). Never persists anything (see
gold_case_persistence.py / evaluation_run_persistence.py).

INDICATION-INDEPENDENT DOMAINS (architecture addition)
validation_unit.indication and EngineEvidenceInput.target_indication
used to be unconditionally required for every GoldCase, regardless of
domain. That was correct for ReferenceDomain.INDICATION_EVIDENCE
(where the engine's candidate discovery and evidence matching are
genuinely indication-driven) but wrong for a domain like SAFETY, whose
claims (e.g. a drug-interaction contraindication) hold regardless of
which indication the preparation is used for — see Case 006. Indication
is now required only when the case's own claims declare a domain in
INDICATION_REQUIRED_DOMAINS (see _requires_indication() below); this
is an explicit, reviewed WHITELIST of domains known to need it, not an
opt-out blacklist — an unrecognized or empty/mixed domain set fails
SAFE (indication still required), so this change can only ever WIDEN
what's optional for a domain explicitly reasoned about, never silently
narrow the requirement elsewhere. No placeholder indication string
(e.g. "indication-independent") is ever substituted; when indication
is not required, it is genuinely omitted (None / "" downstream), and
the engine is run via its own existing reference_plant= parameter
(see below), never via a modification to
botanical_rd_candidate_engine.py itself.
"""

from __future__ import annotations

import pandas as pd

from applicability_check import ReferenceDomain
from botanical_rd_candidate_engine import BotanicalRDCandidateEngine
from engine_evidence_input import EngineEvidenceInput
from gold_case import GoldCase


class GoldCaseNotExecutableError(Exception):
    """Raised when a GoldCase cannot be run — missing indication (for
    an indication-dependent domain), or missing preparation/
    dosage_form."""


# A fixed, neutral placeholder scientific name used ONLY as the
# reference-plant anchor for GoldCase execution — see module
# docstring. Deliberately unrealistic so it can never collide with a
# genuine GoldCase taxon.
_GOLD_CASE_ANCHOR_TAXON = "GoldSetExecutionAnchorPlant__DoNotUseAsRealTaxon"

# Explicit WHITELIST of domains that genuinely require
# validation_unit.indication / EngineEvidenceInput.target_indication —
# see module docstring's "INDICATION-INDEPENDENT DOMAINS" section. Any
# domain NOT in this set is treated as indication-independent ONLY
# when it is the case's SOLE domain (see _requires_indication()); an
# unknown/mixed/empty domain set still requires indication, by design.
INDICATION_REQUIRED_DOMAINS = frozenset({ReferenceDomain.INDICATION_EVIDENCE})


def _case_claim_domains(gold_case: GoldCase) -> set:
    """The set of ReferenceDomain values actually declared by this
    case's claims (across every GoldCaseReference). Protocol §3
    requires exactly one domain per case; this reads whatever the
    claims actually contain rather than assuming that invariant holds,
    so a case with zero or multiple domains is handled explicitly by
    the caller (_requires_indication()) rather than silently."""
    domains = set()
    for gref in gold_case.references:
        for claim in gref.claims:
            domains.add(claim.domain)
    return domains


def _requires_indication(gold_case: GoldCase) -> bool:
    """True unless every domain this case's claims declare is
    explicitly known NOT to require indication (i.e. is outside
    INDICATION_REQUIRED_DOMAINS) AND at least one such domain exists.
    A case with no claims at all, or whose declared domains include
    any INDICATION_REQUIRED_DOMAINS member, requires indication — this
    function only ever widens what counts as indication-independent
    for domains explicitly reasoned about; it never narrows the
    requirement by omission."""
    domains = _case_claim_domains(gold_case)
    if not domains:
        return True
    return bool(domains & INDICATION_REQUIRED_DOMAINS)


def _evidence_inputs_to_dataframe(evidence: list) -> pd.DataFrame:
    """The ONLY function that converts EngineEvidenceInput records
    into the DataFrame shape botanical_rd_candidate_engine.py's
    evidence_df parameter expects (Scientific_Name/Target_Indication/
    Notes). Reads exactly EngineEvidenceInput's plain-string fields —
    nothing else can reach this conversion, by construction of that
    frozen dataclass. target_indication=None becomes "" — the same
    "absent means empty string" convention already used elsewhere in
    this module for market (`unit.jurisdiction or ""`), never a
    fabricated placeholder."""
    if not evidence:
        return pd.DataFrame()
    return pd.DataFrame([
        {
            "Scientific_Name": item.scientific_name,
            "Target_Indication": item.target_indication or "",
            "Notes": item.notes,
            "Result_Direction": item.result_direction,
            "Safety_Signal": item.safety_signal,
            "Regulatory_Status": item.regulatory_status,
            "Regulatory_Authorization_Status": item.regulatory_authorization_status,
            "Regulatory_Evidence": item.regulatory_evidence,
        }
        for item in evidence
    ])


def execute_gold_case_against_engine(
    gold_case: GoldCase,
    evidence: list = None,
    compound_name: str = "primary_compound",
    compound_profiles_df: pd.DataFrame = None,
    scientific_evidence_df: pd.DataFrame = None,
    evidence_records_df: pd.DataFrame = None,
    use_live_search: bool = False,
) -> pd.DataFrame:
    """Runs BotanicalRDCandidateEngine.run() for exactly the one taxon
    named in gold_case.validation_unit, against a neutral anchor
    reference plant. Raises GoldCaseNotExecutableError if
    validation_unit lacks a dosage_form, or lacks an indication WHILE
    the case's domain requires one (see _requires_indication() /
    INDICATION_REQUIRED_DOMAINS above) — indication is no longer
    unconditionally required.

    evidence: list[EngineEvidenceInput] — the ONLY way real evidence
    text reaches the engine (see module docstring's leakage-boundary
    section). None/empty means the engine runs with no evidence at
    all for this taxon (a legitimate, meaningful case: it should
    produce NOT_EVALUABLE gates and a low-confidence/insufficient-
    evidence decision, not an error).

    compound_name is plumbing only (links the anchor and taxon rows
    via a shared compound so the engine treats them as comparable) —
    not part of ValidationUnit's approved 8-dimension schema, and
    never derived from anything in the reference-truth layer.

    Returns the engine's raw result_df, filtered to the single row
    where Reference_Plant is the anchor and Alternative_Plant is the
    GoldCase's own taxon (never the anchor's own self-match row).
    """
    unit = gold_case.validation_unit
    indication_required = _requires_indication(gold_case)

    if indication_required and not unit.indication:
        raise GoldCaseNotExecutableError(
            f"GoldCase {gold_case.case_id!r}: validation_unit.indication is not set "
            f"(required for this case's domain)."
        )
    dosage_form = unit.preparation.dosage_form if unit.preparation else None
    if not dosage_form:
        raise GoldCaseNotExecutableError(
            f"GoldCase {gold_case.case_id!r}: validation_unit.preparation.dosage_form is not set."
        )

    taxon_targets = []
    for item in (evidence or []):
        if item.scientific_name == unit.taxon:
            taxon_targets.extend(item.compound_activity_targets)
    target_value = "; ".join(dict.fromkeys(taxon_targets)) if taxon_targets else "unspecified"

    plant_compounds_df = pd.DataFrame([
        {
            "scientific_name": _GOLD_CASE_ANCHOR_TAXON,
            "compound_name": compound_name,
            "indication": unit.indication or "",
            "target": "unspecified",
            "common_name": "", "plant_part": "", "extraction_method": "",
        },
        {
            "scientific_name": unit.taxon,
            "compound_name": compound_name,
            "indication": unit.indication or "",
            "target": target_value,
            "common_name": "",
            "plant_part": unit.plant_part or "",
            "extraction_method": (unit.preparation.solvent if unit.preparation else "") or "",
        },
    ])

    evidence_df = _evidence_inputs_to_dataframe(evidence or [])

    # Isolation fix (2026-08-11): evidence_records_df was never pinned here
    # (no parameter existed for it at all), so the engine silently fetched
    # the real, live production `evidence_records` table instead of an
    # empty frame -- breaking this gold-case execution's seal even for
    # callers relying on the use_live_search=False default. See
    # run_final_reference_holdout_v1.py's 2026-08-11 comment for the full
    # mechanism. A new evidence_records_df parameter (same None-default,
    # same override style as compound_profiles_df/scientific_evidence_df)
    # is added rather than hardcoding empty, so a caller that genuinely
    # wants real data can still opt in explicitly.
    engine = BotanicalRDCandidateEngine(
        plant_compounds_df=plant_compounds_df,
        compound_profiles_df=compound_profiles_df if compound_profiles_df is not None else pd.DataFrame(),
        scientific_evidence_df=scientific_evidence_df if scientific_evidence_df is not None else pd.DataFrame(),
        evidence_records_df=evidence_records_df if evidence_records_df is not None else pd.DataFrame(),
        evidence_df=evidence_df,
        use_live_search=use_live_search,
    )

    if indication_required:
        result_df = engine.run(
            indication=unit.indication,
            dosage_form=dosage_form,
            market=unit.jurisdiction or "",
        )
    else:
        # Indication-independent domain (e.g. SAFETY): bypass the
        # indication-driven reference-plant discovery entirely via
        # BotanicalRDCandidateEngine.run()'s OWN existing
        # reference_plant= parameter, which matches by taxon name
        # across the candidate universe regardless of indication. This
        # is an already-existing engine capability being used as
        # intended, not a new one invented here, and
        # botanical_rd_candidate_engine.py itself is not modified.
        result_df = engine.run(
            indication=unit.indication or "",
            dosage_form=dosage_form,
            market=unit.jurisdiction or "",
            reference_plant=_GOLD_CASE_ANCHOR_TAXON,
        )

    return result_df[
        (result_df["Reference_Plant"] == _GOLD_CASE_ANCHOR_TAXON)
        & (result_df["Alternative_Plant"] == unit.taxon)
    ]


def platform_output_for_gold_case(result_df: pd.DataFrame) -> dict:
    """Extracts the compact platform-output view from
    execute_gold_case_against_engine()'s result. Returns an empty dict
    (not None, not a fabricated default) if result_df is empty.
    """
    if result_df is None or result_df.empty:
        return {}
    row = result_df.iloc[0]
    return {
        "final_decision_status": row.get("Final_Decision_Status"),
        "decision_class": row.get("Decision_Class"),
        "decision_class_ah": row.get("Decision_Class_AH"),
        "gate_results": row.get("Gate_Results"),
        "grade_certainty": row.get("GRADE_Certainty"),
        "rd_opportunity_score": row.get("R&D_Opportunity_Score"),
    }


class EvidenceChannelConflictError(Exception):
    """Raised by execute_gold_case_with_readiness_gate() when
    GoldCase.engine_evidence and the explicit evidence= parameter are
    both non-empty but not equal. Fails closed rather than silently
    preferring either channel — see that function's own docstring for
    why this class of bug (guard sees one evidence set, engine
    executes against a different one) must never be resolved by
    guessing which channel the caller "really meant"."""


def _resolve_effective_evidence(gold_case: GoldCase, evidence: list):
    """The ONE evidence value both assess_execution_readiness() and
    execute_gold_case_against_engine() will use — see
    execute_gold_case_with_readiness_gate()'s docstring for the full
    rule. `evidence=None` means "no explicit override was passed";
    an explicitly passed empty list ([]) is treated as no override
    either (there is nothing in it to conflict with), which is why
    "populated" below means non-empty, not merely not-None.
    """
    case_evidence = gold_case.engine_evidence or []

    if evidence is None:
        return case_evidence
    if not case_evidence:
        return evidence
    if not evidence:
        return case_evidence
    if evidence == case_evidence:
        return case_evidence

    raise EvidenceChannelConflictError(
        f"GoldCase {gold_case.case_id!r}: gold_case.engine_evidence "
        f"({len(case_evidence)} item(s)) and the explicit evidence= "
        f"parameter ({len(evidence)} item(s)) are both populated and "
        f"differ. Refusing to silently prefer either channel — pass "
        f"matching content on both, or populate only one."
    )


def execute_gold_case_with_readiness_gate(
    gold_case: GoldCase,
    dimension_assessments: tuple = (),
    evidence: list = None,
    compound_name: str = "primary_compound",
    compound_profiles_df: pd.DataFrame = None,
    scientific_evidence_df: pd.DataFrame = None,
    evidence_records_df: pd.DataFrame = None,
    use_live_search: bool = False,
):
    """Phase 3C — the single orchestration point: assess_execution_
    readiness() is called first; execute_gold_case_against_engine() is
    only ever called if that result is READY. No new decision layer —
    this function makes no readiness judgment of its own, it only
    enforces the existing execution_readiness.ExecutionReadiness
    decision. Not a redesign of either module.

    EVIDENCE-CHANNEL INVARIANT (fixes the gap found while
    characterizing Case 003's first execution): GoldCase.engine_evidence
    and this function's own `evidence=` parameter used to be read by
    two different places (the guard read only the former;
    execute_gold_case_against_engine() read only the latter), so
    populating only one produced a silently wrong result either way.
    _resolve_effective_evidence() now computes ONE effective_evidence
    value up front:
        - evidence=None                          -> gold_case.engine_evidence
        - evidence given, gold_case.engine_evidence empty -> evidence
        - both populated and equal                -> that shared value
        - both populated and different             -> EvidenceChannelConflictError (fail closed)
    Both the readiness assessment (via a case copy carrying
    effective_evidence — the original gold_case object is never
    mutated) and the actual engine call below use this SAME value, so
    the guard and the engine can never see different evidence again.

    Returns (ExecutionReadinessResult, result_df_or_None). result_df is
    None whenever decision != READY — the engine is never instantiated
    or run in that case.
    """
    from dataclasses import replace

    from execution_readiness import (
        ExecutionReadiness, ExecutionReadinessInput, assess_execution_readiness,
    )

    effective_evidence = _resolve_effective_evidence(gold_case, evidence)
    case_for_assessment = replace(gold_case, engine_evidence=effective_evidence)

    readiness = assess_execution_readiness(
        ExecutionReadinessInput(gold_case=case_for_assessment, dimension_assessments=dimension_assessments)
    )

    if readiness.decision != ExecutionReadiness.READY:
        return readiness, None

    result_df = execute_gold_case_against_engine(
        gold_case,
        evidence=effective_evidence,
        compound_name=compound_name,
        compound_profiles_df=compound_profiles_df,
        scientific_evidence_df=scientific_evidence_df,
        evidence_records_df=evidence_records_df,
        use_live_search=use_live_search,
    )
    return readiness, result_df
