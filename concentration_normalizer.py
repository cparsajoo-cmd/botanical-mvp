"""
Phase 4 — concentration normalization (audit section 4.10).

WHAT THIS FIXES
The engine previously extracted concentration mentions from free text
with a flat set of regexes and joined whatever it found into one
display string (see the old _extract_concentration in
botanical_rd_candidate_engine.py) — "0.5%; 3 mg/g" with no indication
that a percentage-of-extract and a mg-per-gram-of-something are not on
the same basis and were never meant to be read side by side. Nothing
in the engine actually ran a NUMERIC cross-plant comparison on these
(scoring only checked "is a concentration mentioned at all" — see
_score_candidate), so no comparison bug ever silently produced a wrong
"Plant Y is richer" claim. The real risk was the DISPLAY: a person
reading two rows' Concentration_Info side by side has no way to know
the numbers aren't on the same footing.

WHAT THIS MODULE DOES
- Parses every value+unit mention in a text into a structured
  ParsedConcentration (value, unit, basis).
- Classifies the basis into the same buckets the audit asked for:
  mg/g dry weight, mg/g extract, % total extract, µg/mL infusion,
  mg per capsule, mg/g fresh weight — or "unknown" when the text gives
  a number but not enough context to know the basis.
- Refuses to call two concentrations comparable unless their basis
  matches exactly. are_comparable() returns False (never a guess) for
  any basis mismatch, including "one side unknown."
- format_concentration_info() builds the display string FOR the
  existing Concentration_Info column, grouped by basis, and explicitly
  prefixes "Not directly comparable —" whenever a single text mentions
  more than one distinct basis, so this becomes something the reader
  is told about instead of something they'd have to notice themselves.

WHAT THIS MODULE DOES NOT DO (yet)
- No unit conversion (e.g. mg/g dry weight -> mg/g fresh weight). That
  requires a moisture-content assumption this module refuses to guess;
  two dry/fresh-basis values stay "Not directly comparable" rather
  than being silently converted with a made-up ratio.
- Not wired into scoring. _score_candidate's existing "is a
  concentration mentioned at all" bonus is untouched by this module —
  changing how CONCENTRATION MAGNITUDE affects scoring is a separate,
  later decision.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


# =====================================================================
# Basis classification
# =====================================================================

# Each entry: (basis_label, regex for the UNIT part only, case-insensitive).
# Order matters — more specific patterns (e.g. "mg/100g") must be checked
# before more general ones (e.g. a bare "%") could ever misfire, though
# with distinct unit tokens like these there's no real overlap risk.
_BASIS_PATTERNS = [
    ("mg/g dry weight", r"mg\s*/\s*g\s*(?:dry|dw)\b"),
    ("mg/g fresh weight", r"mg\s*/\s*g\s*(?:fresh|fw)\b"),
    ("mg/g extract", r"mg\s*/\s*g\s*(?:extract|ext)\b"),
    ("mg/100g", r"mg\s*/\s*100\s*g\b"),
    ("mg/kg", r"mg\s*/\s*kg\b"),
    ("mg/g", r"mg\s*/\s*g\b"),  # basis (dry/fresh/extract) unstated
    ("\u00b5g/g", r"(?:\u00b5g|ug)\s*/\s*g\b"),
    ("\u00b5g/mL", r"(?:\u00b5g|ug)\s*/\s*m[lL]\b"),
    ("mg/mL", r"mg\s*/\s*m[lL]\b"),
    ("mg per capsule", r"mg\s*(?:per|/)\s*capsule\b"),
    ("mg per tablet", r"mg\s*(?:per|/)\s*tablet\b"),
    ("% total extract", r"%\s*(?:total\s*)?extract\b"),
    ("%", r"%"),  # basis (of what?) unstated
]

# Precompiled: value token immediately followed by one of the unit
# patterns above (allowing a little whitespace in between).
_VALUE_TOKEN = r"\d+(?:\.\d+)?"

_COMPILED_PATTERNS = [
    (basis, re.compile(rf"({_VALUE_TOKEN})\s*(?:{unit_pattern})", re.IGNORECASE))
    for basis, unit_pattern in _BASIS_PATTERNS
]

# Bases that are explicit about dry/fresh/extract footing — used to
# decide whether an "mg/g" match with unstated basis should be folded
# into one of these, versus kept as its own "mg/g (basis unstated)"
# bucket. Kept separate deliberately: assuming "mg/g" means "mg/g dry
# weight" is exactly the kind of silent assumption 4.10 asked to avoid.
EXPLICIT_BASIS_LABELS = {
    "mg/g dry weight", "mg/g fresh weight", "mg/g extract",
    "mg per capsule", "mg per tablet", "% total extract",
}


@dataclass
class ParsedConcentration:
    value: float
    unit: str  # e.g. "mg/g", "%", "\u00b5g/mL"
    basis: str  # e.g. "mg/g dry weight", "% total extract", "mg/g" (basis unstated), "%" (basis unstated)
    raw_text: str  # the exact substring matched, for traceability

    @property
    def basis_is_explicit(self) -> bool:
        return self.basis in EXPLICIT_BASIS_LABELS


def parse_concentration(text: Optional[str]) -> list[ParsedConcentration]:
    """Extracts every value+unit concentration mention in `text`, each
    tagged with its classified basis. Returns an empty list if nothing
    matches or `text` is empty."""
    if not text:
        return []

    results: list[ParsedConcentration] = []
    claimed_spans: list[tuple[int, int]] = []

    # Try more specific basis patterns first (e.g. "mg/g dry weight"
    # before the bare "mg/g" fallback) so a value isn't double-counted
    # under both the specific and the generic bucket.
    for basis, pattern in _COMPILED_PATTERNS:
        for match in pattern.finditer(text):
            span = match.span()
            if any(s < span[1] and span[0] < e for s, e in claimed_spans):
                continue  # overlaps a higher-priority match already taken
            claimed_spans.append(span)
            try:
                value = float(match.group(1))
            except ValueError:
                continue
            results.append(
                ParsedConcentration(
                    value=value,
                    unit=basis,
                    basis=basis,
                    raw_text=match.group(0).strip(),
                )
            )

    results.sort(key=lambda p: text.find(p.raw_text))
    return results


def are_comparable(a: ParsedConcentration, b: ParsedConcentration) -> bool:
    """True only if both concentrations are on the exact same, EXPLICIT
    basis. Deliberately conservative per 4.10: two "mg/g" values with
    unstated basis are NOT considered comparable to each other, since
    "unstated" isn't a guarantee they're the same thing — one could be
    dry-weight and the other extract-weight, just not labeled as such
    in the source text."""
    if a.basis != b.basis:
        return False
    return a.basis_is_explicit


def format_concentration_info(parsed: list[ParsedConcentration]) -> str:
    """Builds the Concentration_Info display string: groups mentions by
    basis, and if more than one distinct basis is present, prefixes an
    explicit warning rather than letting the reader assume the numbers
    sit side by side on equal footing."""
    if not parsed:
        return "Not clearly reported"

    by_basis: dict[str, list[ParsedConcentration]] = {}
    for p in parsed:
        by_basis.setdefault(p.basis, []).append(p)

    groups = []
    for basis, items in by_basis.items():
        values = "; ".join(sorted({item.raw_text for item in items}))
        groups.append(f"{values} ({basis})" if not items[0].basis_is_explicit else values)

    joined = " | ".join(groups)

    if len(by_basis) > 1:
        return f"Not directly comparable — mixed bases: {joined}"
    return joined
