"""Single source of truth for Score_Breakdown parsing and section-name
constants.

Consumers: scoring_sensitivity_report.py, structured_rationale.py,
comparative_rationale.py. IMPLEMENTATION_PLAN.md Phase 1.

Score_Breakdown has two legitimate shapes in this codebase:
  - the compound-substitution engine (botanical_rd_candidate_engine.py's
    _format_score_breakdown()) stores a formatted string:
    "Name: +12.3; Other: -4.0"
  - the indication-centric engine (indication_candidate_discovery.py)
    stores a plain {name: value} dict directly.

Before this module existed, three files each kept an independent copy of
the parser and, in two of them, an independent copy of the "canonical
section names" constant used for completeness checking. When
indication_candidate_discovery.py's compound-support key changed from
"Compound support (non-gating)" to "Compound support (non-gating; max 5)",
only some copies were updated — the others kept classifying every
indication-mode row as incomplete/unmatched without raising any error.
There is now exactly one parser and one set of section-name constants;
every consumer imports them instead of defining its own.
"""
from __future__ import annotations


# Sections botanical_rd_candidate_engine.py's _format_score_breakdown()
# always emits for compound-substitution rows. "Multi-compound match bonus"
# is conditional (merged rows only) and deliberately excluded from this
# "always expected" set.
CANONICAL_SECTIONS = {
    "Chemical/mechanistic link", "Evidence quality", "Product-development fit",
    "Novelty", "Market signal", "Safety/interaction/self-row penalty",
}

# Sections indication_candidate_discovery.py's discover_indication_candidates()
# always emits for indication-centric rows. Kept in sync with that module's
# Score_Breakdown dict keys — if those keys change, update this set in the
# same change (this is the exact drift that made this module necessary).
INDICATION_CANONICAL_SECTIONS = {
    "Direct indication evidence", "Traceability", "Mechanistic plausibility",
    "Preparation applicability", "Compound support (non-gating; max 5)",
    "Baseline development potential",
}

# Maps every known Score_Breakdown component name (both schemas) onto the
# card dimension(s) it contributes to (Scientific / Clinical / Commercial /
# Safety). "Regulatory" is deliberately never a value here: neither engine
# computes an independent regulatory score contribution — see
# NO_REGULATORY_SCORE_CONTRIBUTION_MESSAGE in structured_rationale.py.
COMPONENT_TO_DIMENSIONS = {
    # Compound-substitution schema
    "Chemical/mechanistic link": ["Scientific"],
    "Novelty": ["Scientific"],
    "Multi-compound match bonus": ["Scientific"],
    "Evidence quality": ["Clinical"],
    "Product-development fit": ["Commercial"],
    "Market signal": ["Commercial"],
    "Safety/interaction/self-row penalty": ["Safety"],
    # Indication-centric schema
    "Direct indication evidence": ["Clinical"],
    "Mechanistic plausibility": ["Scientific"],
    "Traceability": ["Clinical"],
    "Preparation applicability": ["Commercial"],
    "Compound support (non-gating; max 5)": ["Scientific"],
    "Baseline development potential": ["Commercial"],
}


def parse_score_breakdown(breakdown) -> dict:
    """Reverses a Score_Breakdown value back into a {name: float} dict.

    Accepts either legitimate shape:
      - a formatted string "Name: +12.3; Other: -4.0" (tolerant of the
        "; Multi-compound match bonus: +N.0" suffix
        _merge_multi_compound_matches appends, and of the literal
        "No breakdown available" placeholder, which returns {})
      - a plain {name: value} dict (indication-centric rows)

    Never raises on a malformed individual entry — an entry that isn't a
    parseable "name: number" pair (string form) or isn't numeric (dict
    form) is skipped, not fatal to the rest of the breakdown.
    """
    if not breakdown or breakdown == "No breakdown available":
        return {}
    if isinstance(breakdown, dict):
        components = {}
        for name, value in breakdown.items():
            try:
                components[str(name).strip()] = float(value)
            except (TypeError, ValueError):
                continue
        return components
    components = {}
    for part in str(breakdown).split("; "):
        if ":" not in part:
            continue
        name, _, value_str = part.rpartition(":")
        try:
            components[name.strip()] = float(value_str.strip())
        except ValueError:
            continue
    return components
