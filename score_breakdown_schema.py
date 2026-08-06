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

# Sections candidate_shortlisting.py's authoritative Overall_Score (Phase 3,
# IMPLEMENTATION_PLAN.md) always emits. This is now the ONE score that
# drives shortlist status, report ranking, and the final recommendation —
# see candidate_shortlisting.py's merge_authoritative_scores(). The legacy
# CANONICAL_SECTIONS (compound-substitution) and INDICATION_CANONICAL_SECTIONS
# (indication-centric) schemas above may still appear on raw, pre-merge rows
# used for internal/diagnostic purposes, but never on the final,
# user-facing R&D_Opportunity_Score/Score_Breakdown after Phase 3.
AUTHORITATIVE_CANONICAL_SECTIONS = {
    "Indication Relevance", "Scientific Evidence", "Compound Support",
    "Mechanism Support", "Safety & Regulatory", "Novelty & Market",
}

# Maps every known Score_Breakdown component name (all three schemas) onto the
# card dimension(s) it contributes to (Scientific / Clinical / Commercial /
# Safety). "Regulatory" is deliberately never a value here: no engine
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
    # Authoritative plant-level schema (Phase 3, renamed Phase 5:
    # "Evidence Quality" -> "Scientific Evidence", now backed by
    # Scientific_Evidence_Score rather than raw Evidence_Quality_Score —
    # see candidate_shortlisting.py's _scientific_evidence_components()).
    "Indication Relevance": ["Clinical"],
    "Scientific Evidence": ["Clinical"],
    "Compound Support": ["Scientific"],
    "Mechanism Support": ["Scientific"],
    "Safety & Regulatory": ["Safety"],
    "Novelty & Market": ["Commercial"],
}


# ======================================================================
# PHASE 2 — score-contribution duplicate guard.
#
# See PHASE2_EVIDENCE_ARCHITECTURE_AUDIT.md section 3e: no existing
# structure tracks score contributions per individual evidence item (only
# pre-aggregated {component_name: value} totals, parsed above). Wiring
# this into botanical_rd_candidate_engine.py's frozen scoring internals
# is out of scope for this phase (no modification to the core scoring
# function is permitted). This is therefore minimal, additive,
# backward-compatible infrastructure only: a small utility any caller
# that DOES build a per-evidence contribution list (present or future)
# can use to guarantee the same evidence is never counted twice for the
# same score component, without changing any weight or formula.
#
# score_identity (see standard_evidence_schema.py's module docstring)
# is deliberately a (evidence_identity, component) PAIR, not a property
# of EvidenceRecord alone — the same evidence CAN legitimately count
# toward two different, genuinely different components.
# ======================================================================


def score_contribution_key(evidence_identity: str, component_name: str) -> str:
    """Stable, JSON-serializable key identifying "this evidence already
    contributed to this score component". Built from a
    deduplication_engine.compute_evidence_identity() string plus the
    component name (e.g. one of CANONICAL_SECTIONS /
    INDICATION_CANONICAL_SECTIONS / AUTHORITATIVE_CANONICAL_SECTIONS
    above), hashed with the same deterministic SHA-256 helper used for
    evidence identity itself — never Python's randomized hash().
    """
    from deduplication_engine import stable_identity_hash

    return stable_identity_hash(f"{evidence_identity}||{component_name}")


def dedupe_score_contributions(contributions) -> list:
    """Given an iterable of contribution dicts, each with at least
    "evidence_identity" and "component" keys, returns a new list with
    duplicate (evidence_identity, component) pairs removed — first
    occurrence wins. Ranking/weights/values are never modified; this
    only removes exact repeats of the same evidence counting toward the
    same component (e.g. the same article surfacing once via PubMed and
    once via Europe PMC, both attempting to contribute to "Evidence
    quality"). A contribution missing either key is left in the output
    unchanged (nothing to dedupe it against) rather than dropped
    silently.
    """
    seen = set()
    result = []
    for contribution in contributions or []:
        evidence_identity = contribution.get("evidence_identity") if isinstance(contribution, dict) else None
        component = contribution.get("component") if isinstance(contribution, dict) else None
        if evidence_identity is None or component is None:
            result.append(contribution)
            continue
        key = score_contribution_key(evidence_identity, component)
        if key in seen:
            continue
        seen.add(key)
        result.append(contribution)
    return result


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
