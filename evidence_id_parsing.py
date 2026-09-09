"""Canonical evidence-ID collection parsing (Sections 4, 5, 34 of the
2026-09-09 third follow-up: "Fix the current human-evidence count bug").

THE BUG THIS FIXES
A field like Direct_Human_Outcome_Evidence_IDs, once round-tripped through
a DataFrame / CSV / session state, can arrive as the STRING "()" or "[]"
(Python's own repr of an empty tuple/list), not an actual empty
collection. Every ad-hoc "split on ';' and count non-empty pieces"
helper in this codebase (see candidate_shortlisting.py's _split_values(),
whose _MISSING_MARKERS set does not include "()"/"[]"/"{}") then produces
["()"], which is a WRONG count of 1 -- exactly the production
contradiction this pass reported: "Human_Evidence_Status: 1 direct human
outcome record(s)" next to "No confirmed direct human evidence for the
queried indication."

WHY ONE CENTRAL MODULE
The cahier des charges is explicit: "Add robust parsing centrally rather
than fixing each table independently." This module is that single place.
Existing call sites (_split_values() in candidate_shortlisting.py, the
ad-hoc split in post_discovery_investor_view.py's old
_human_evidence_ids_count()) are NOT touched/duplicated here -- only the
evidence-ID-specific call sites this pass is scoped to (human-evidence
IDs; new safety/mechanism ID fields as they're added) are migrated to
call normalize_evidence_ids() instead of re-implementing their own split.
"""

from __future__ import annotations

import ast
import json
import re

# Every one of these, once lowercased and stripped, means "empty" --
# whether it is Python's own str()/repr() of an empty collection, a
# pandas/CSV rendering of a missing value, or a plain empty string.
_EMPTY_STRING_MARKERS = {
    "", "none", "nan", "null", "na", "n/a",
    "[]", "()", "{}", "set()",
}

_SPLIT_PATTERN = re.compile(r"[;,\n]+")


def _clean_token(token: str) -> str:
    return token.strip().strip("'\"").strip()


def _from_string(text: str) -> list[str]:
    stripped = text.strip()
    normalized_lower = stripped.lower()
    if normalized_lower in _EMPTY_STRING_MARKERS:
        return []

    # Try JSON first (e.g. '["E1","E2"]'), then a Python literal (e.g.
    # "('E1', 'E2')" or "{'E1', 'E2'}"), before falling back to a plain
    # delimiter split. Both structured parses give an actual collection,
    # so an empty result from either is *not* the "content is one weird
    # token" case the delimiter-split branch has to handle.
    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(stripped)
        except Exception:
            continue
        if isinstance(parsed, (list, tuple, set, frozenset)):
            return _from_iterable(parsed)
        if isinstance(parsed, (str, int, float)):
            single = str(parsed).strip()
            return [] if not single or single.lower() in _EMPTY_STRING_MARKERS else [single]
        # Any other parsed type (dict, None, bool, ...) is not a usable
        # ID or ID collection -- fall through to the delimiter split
        # below rather than silently returning [] here, in case the raw
        # text was coincidentally valid-but-irrelevant JSON/literal.

    pieces = [_clean_token(p) for p in _SPLIT_PATTERN.split(stripped)]
    return [p for p in pieces if p and p.lower() not in _EMPTY_STRING_MARKERS]


def _from_iterable(values) -> list[str]:
    out: list[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text or text.lower() in _EMPTY_STRING_MARKERS:
            continue
        out.append(text)
    return out


def normalize_evidence_ids(value) -> list[str]:
    """Turns ANY representation of an evidence-ID collection into a
    clean, order-preserving, deduplicated list[str]. Every one of these
    inputs returns []:
        None, "", [], (), set(), {}, "[]", "()", "{}", "None", "nan"
    Every one of these returns ["E1", "E2"]:
        ["E1", "E2"], ("E1", "E2"), "E1;E2", "E1,E2", '["E1","E2"]'
    Never raises -- a value this function cannot make sense of degrades
    to [] rather than propagating an exception into a display layer.
    """
    if value is None:
        return []
    if isinstance(value, float) and value != value:  # NaN, no numpy/math import needed
        return []
    if isinstance(value, (list, tuple, set, frozenset)):
        raw = _from_iterable(value)
    elif isinstance(value, str):
        raw = _from_string(value)
    else:
        raw = _from_string(str(value))

    seen = set()
    deduped = []
    for item in raw:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def count_evidence_ids(value) -> int:
    """Convenience wrapper: len(normalize_evidence_ids(value))."""
    return len(normalize_evidence_ids(value))
