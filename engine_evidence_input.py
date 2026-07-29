"""
Reference-Grounded Validation — EngineEvidenceInput.

WHAT THIS IS
The ONLY shape of evidence gold_case_execution.py may pass to the real
production engine. Frozen, and structurally incapable of holding a
ReferenceClaim or ResolvedExpectedOutcome — not because anything scans
its text for forbidden words (explicitly rejected — see below), but
because this dataclass simply has no field that could hold one. This
IS the leakage boundary the approved architecture requires: a
structural guarantee, checkable by introspecting the type itself
(dataclasses.fields()), not a runtime scan of string content.

WHY NOT TEXT SCANNING
Natural authoritative evidence legitimately contains words like
"serious," "contraindicated," or "prohibited" — a monograph section
saying "this is a serious risk in pregnancy" is exactly the kind of
real evidence text the engine is SUPPOSED to receive and interpret on
its own. Scanning for such words and blocking them would make it
impossible to feed the engine real safety-relevant text at all. The
correct guarantee is architectural: the type that reaches the engine
constructor has no field capable of carrying a ReferenceClaim/
ResolvedExpectedOutcome object or any of their structured fields
(assertion_state, severity, resolution_status, etc.) — only plain
natural-language text.

notes IS FREE TEXT ON PURPOSE
notes is exactly the field botanical_rd_candidate_engine.py's own
evidence_df["Notes"] column already expects (see
_collect_raw_evidence()) — this dataclass exists to be converted 1:1
into that DataFrame shape, nothing more.

compound_activity_targets IS A SEPARATE, REAL PRODUCTION CHANNEL —
NOT A TEST-ONLY SHORTCUT
Investigation while building the Safety-Serious test path found that
botanical_rd_candidate_engine.py's hard-safety-term detection
(HARD_SAFETY_TERMS) is NOT reachable through evidence_df["Notes"] free
text at all — SAFETY_TERMS (the vocabulary free text is scanned
against) and HARD_SAFETY_TERMS (the vocabulary that actually forces a
hard stop) have ZERO overlap by design (see
_build_compound_target_index()). HARD_SAFETY_TERMS is only ever
reachable via plant_compounds_df["target"] — a compound's documented
toxicological/pharmacological activity classification (the same
DB_ACTIVITY_SAFETY_TERMS vocabulary already used throughout this
platform, e.g. matching Dr. Duke's USDA phytochemical database's
activity fields). This is genuine, existing PRODUCTION structured
data, not a hack invented for testing — it is simply a DIFFERENT
production input channel than free-text literature evidence.
compound_activity_targets exposes this channel explicitly and
structurally (a list of plain strings) rather than as an undocumented
positional kwarg — still cannot hold a ReferenceClaim/
ResolvedExpectedOutcome object, for the same structural reason notes
cannot.

WHAT "REAL PRODUCTION CHANNEL" DOES NOT CLAIM (v4 correction #2)
The paragraph above is about the ENGINE side: plant_compounds_df["target"]
is a genuine, independently-sourced production column (Dr. Duke) when
the engine runs against live Supabase data. It is NOT a claim about
where any given GoldCase gets the values it puts into
compound_activity_targets. In the current GoldCase pipeline, those
values are supplied directly by a curator or fixture author — see
EngineEvidenceOrigin below — never fetched from Dr. Duke, ChEMBL, or
any other independent source, and never derived from this same case's
own ReferenceClaim/ResolvedExpectedOutcome/expected_output. A case
whose engine_evidence happens to describe the same fact as its
reference claims (e.g. both mention "Lithogenic") is curator
coincidence, not automated derivation — there is no code path in this
repository that takes a ReferenceClaim, ResolvedExpectedOutcome, or
ExpectedOutput and produces a compound_activity_targets value from it,
and none should be added: doing so would let a case's expected
answer manufacture its own engine input, defeating the point of an
independent gate check. See EngineEvidenceOrigin and
test_structural_leakage_boundary.py's factory-absence tests for the
structural side of this guarantee.
WHY target_indication IS OPTIONAL (Optional[str] = None)
Originally a required plain str. gold_case_execution.py's execution
architecture now distinguishes indication-DEPENDENT domains (e.g.
INDICATION_EVIDENCE, where the engine's candidate discovery and
evidence matching are genuinely indication-driven) from indication-
INDEPENDENT domains (e.g. SAFETY, where a contraindication/interaction
claim holds regardless of which indication the preparation is used
for — see gold_case_execution.py's INDICATION_INDEPENDENT_DOMAINS and
_requires_indication()). For an indication-independent case,
target_indication is genuinely inapplicable, not merely inconvenient
to supply — leaving it None is honest, not a workaround, and no
placeholder string (e.g. "indication-independent") is ever written
here in its place. When indication IS required by the case's domain,
callers must still supply a real value; this module does not enforce
that requirement itself (gold_case_execution.py does, per-domain) —
the same separation of concerns already used for dosage_form.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


@dataclass(frozen=True)
class EngineEvidenceInput:
    """Frozen: cannot be mutated after construction to smuggle in an
    extra attribute at runtime. Exactly four fields, all plain
    strings (or a plain list of strings) — see module docstring for
    why each exists and what production channel each maps to.
    target_indication is Optional[str] = None — see "WHY
    target_indication IS OPTIONAL" above; the other three fields are
    unchanged."""
    scientific_name: str
    target_indication: Optional[str] = None
    notes: str = ""
    compound_activity_targets: tuple = ()


class EngineEvidenceOrigin(str, Enum):
    """Provenance of a GoldCase's engine_evidence — see gold_case.py's
    GoldCase.engine_evidence_origin. Deliberately NOT a field on
    EngineEvidenceInput itself: EngineEvidenceInput's field set is a
    locked structural invariant (exactly four fields — see
    test_structural_leakage_boundary.py), and provenance is metadata
    ABOUT how a case's evidence was obtained, not part of what the
    engine consumes. Lives at the GoldCase level instead.

    Exactly three values, on purpose. There is deliberately no
    "REFERENCE_CLAIM_DERIVED" or similar member — see the module
    docstring's "WHAT 'REAL PRODUCTION CHANNEL' DOES NOT CLAIM"
    section. Adding one would document, not prevent, a leakage path;
    the absence is itself the guardrail this enum exists to express.
    """
    INDEPENDENT_PRODUCTION_SOURCE = "Independent production source"
    MANUAL_TEST_FIXTURE = "Manual test fixture"
    CURATOR_SUPPLIED = "Curator supplied"
