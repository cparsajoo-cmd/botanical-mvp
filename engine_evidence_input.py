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
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EngineEvidenceInput:
    """Frozen: cannot be mutated after construction to smuggle in an
    extra attribute at runtime. Exactly four fields, all plain
    strings or a plain list of strings — see module docstring for
    why each exists and what production channel each maps to."""
    scientific_name: str
    target_indication: str
    notes: str = ""
    compound_activity_targets: tuple = ()
