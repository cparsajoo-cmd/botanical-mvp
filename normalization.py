"""
Independent text/taxon normalization utilities.

WHY THIS EXISTS AS A SEPARATE, INDEPENDENTLY-WRITTEN MODULE
execution_readiness.py's seed-data collision check needs to reproduce
the same string-normalization behavior BotanicalRDCandidateEngine
applies internally (its private _norm/_norm_taxon static/class
methods) when it looks up seed_data.SLEEP_TEA_EVIDENCE by plant name.

The readiness guard is a separate governance layer sitting IN FRONT OF
engine execution — it must not import or depend on a private
(underscore-prefixed) method of botanical_rd_candidate_engine.py,
since that creates a hidden coupling: an internal engine refactor could
silently break the guard with no import-level signal, and
botanical_rd_candidate_engine.py must never be modified for this
program (see VALIDATION_PROTOCOL.md's founding constraint).

So this module reimplements the same two functions independently, from
scratch, not by importing or delegating to the engine. Byte-for-byte
behavioral parity with the engine's actual _norm/_norm_taxon is
guaranteed by test_normalization_matches_engine.py, which imports the
engine's private methods ONLY in test code (never in this module or in
execution_readiness.py) and asserts identical output across a fixed
case list. If the engine's normalization ever changes, that test — not
this module's own logic — is what will catch the drift.

CHANGE DISCIPLINE
If botanical_rd_candidate_engine.py's _norm/_norm_taxon are ever
changed, this module must be updated to match AND
test_normalization_matches_engine.py must be re-run to confirm parity.
This module's own logic is never "corrected" independently of that
comparison.
"""

from __future__ import annotations

import re

_MISSING_TOKENS = {"nan", "none", "null"}

# Same infraspecific-rank/hybrid-marker tokens the engine's _norm_taxon
# strips, mirrored here independently (see module docstring).
_TAXON_STRIP_PATTERN = re.compile(r"\b(x|subsp|ssp|nothosubsp|var|f|cv)\b\.?")


def normalize_text(value) -> str:
    """Lowercase, whitespace-collapsed normalization. Mirrors
    BotanicalRDCandidateEngine._norm()'s behavior (verified by
    test_normalization_matches_engine.py) without importing it."""
    if value is None:
        return ""

    text = str(value).strip().lower()

    if text in _MISSING_TOKENS:
        return ""

    return re.sub(r"\s+", " ", text)


def normalize_taxon(value) -> str:
    """Like normalize_text(), but also strips the hybrid marker
    ("×"/standalone "x") and infraspecific rank abbreviations
    (subsp./ssp./var./f./cv./nothosubsp.) that a database's full
    taxonomic name carries but an everyday working name usually won't.
    Mirrors BotanicalRDCandidateEngine._norm_taxon()'s behavior
    (verified by test_normalization_matches_engine.py) without
    importing it."""
    text = normalize_text(value)
    text = text.replace("×", " x ")
    text = _TAXON_STRIP_PATTERN.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()
