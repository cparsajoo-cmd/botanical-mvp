"""Commercial evidence provider boundary (Sections 8 & 12 of the 2026-09-09
investor-view cahier des charges).

WHAT THIS IS
A single place that defines the canonical status vocabulary for ANY
external commercial-evidence lookup (today: retail/brand product search),
and a provider DISPATCHER that routes to a concrete implementation by
name via SEARCH_API_PROVIDER, without hardwiring one vendor into the
call sites. It does not implement a paid provider -- see "WHY NO REAL
PROVIDER IS WIRED IN" below -- it implements the boundary so one can be
added later by writing exactly one function.

WHY A SEPARATE MODULE, NOT A REWRITE OF _search_retail_products()
botanical_rd_candidate_engine.py::_search_retail_products() already has a
tested, working "honest stub" (Search not performed / not configured / not
implemented). This module does not replace its behavior for existing
callers -- it factors the SAME decision logic out into a reusable,
independently-testable dispatcher, and _search_retail_products() is
refactored to delegate to it (Section 39: "do not duplicate existing
scoring/business logic into another parallel implementation").

CANONICAL STATUS VOCABULARY (Section 8)
    SEARCH_NOT_PERFORMED        -- live search is disabled for this run.
    PROVIDER_UNAVAILABLE        -- live search is enabled, but no provider
                                    is configured/reachable (no API key, or
                                    the configured provider name isn't a
                                    known one).
    CONNECTOR_NOT_IMPLEMENTED   -- a provider IS configured (key + name),
                                    but this codebase has no real call
                                    implemented for it yet.
    SEARCH_FAILED                -- a real provider call was attempted and
                                    raised/errored.
    SEARCH_COMPLETED_NO_RESULTS  -- a real provider call completed and
                                    returned zero results.
    SEARCH_COMPLETED_RESULTS_FOUND -- a real provider call completed and
                                    returned at least one result.
These six states are never collapsed into each other. In particular,
SEARCH_COMPLETED_NO_RESULTS is NEVER produced by the absence of a
configured provider -- that is PROVIDER_UNAVAILABLE or
CONNECTOR_NOT_IMPLEMENTED, not "zero competitors" (Section 5/33).

WHY NO REAL PROVIDER IS WIRED IN
Retail/brand product presence needs a paid, ToS-compliant web-search API
(Bing Web Search API, SerpAPI, etc.) -- there is no free structured source
for "which brands sell X". Section 12 of the cahier des charges is explicit
that choosing/purchasing one is not this pass's job, and that fabricating
results is never acceptable ("If implementing a real provider cannot be
done responsibly in the current repository without choosing/purchasing a
provider, build the provider boundary and honest unavailable state, and
DO NOT fabricate product data."). _PROVIDER_IMPLEMENTATIONS below is where
a real call gets added later -- one entry, one function, nothing else in
the codebase changes.
"""

from __future__ import annotations

import os
from typing import Callable, Optional

SEARCH_NOT_PERFORMED = "SEARCH_NOT_PERFORMED"
PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
CONNECTOR_NOT_IMPLEMENTED = "CONNECTOR_NOT_IMPLEMENTED"
SEARCH_FAILED = "SEARCH_FAILED"
SEARCH_COMPLETED_NO_RESULTS = "SEARCH_COMPLETED_NO_RESULTS"
SEARCH_COMPLETED_RESULTS_FOUND = "SEARCH_COMPLETED_RESULTS_FOUND"

ALL_RETAIL_SEARCH_STATUSES = (
    SEARCH_NOT_PERFORMED,
    PROVIDER_UNAVAILABLE,
    CONNECTOR_NOT_IMPLEMENTED,
    SEARCH_FAILED,
    SEARCH_COMPLETED_NO_RESULTS,
    SEARCH_COMPLETED_RESULTS_FOUND,
)

# Statuses that mean "we do not have a usable read on this dimension" --
# i.e. everything except the two SEARCH_COMPLETED_* outcomes. Reused by
# completeness/classification logic so "no signal" is defined in one place.
UNUSABLE_RETAIL_SEARCH_STATUSES = {
    SEARCH_NOT_PERFORMED, PROVIDER_UNAVAILABLE, CONNECTOR_NOT_IMPLEMENTED,
    SEARCH_FAILED,
}

# Registry of real provider implementations. Empty today (Section 12: no
# provider is chosen/purchased in this pass). Each entry is a callable
# ``fn(query: str, api_key: str) -> dict`` returning at minimum
# {"results": [...]} on success; raise on failure (caught by the
# dispatcher and reported as SEARCH_FAILED). Adding SerpAPI/Bing later is
# exactly: define the function, add one line here -- no call site changes.
_PROVIDER_IMPLEMENTATIONS: dict[str, Callable[[str, str], dict]] = {}


def dispatch_retail_provider_search(
    query: str,
    *,
    use_live_search: bool,
    provider_env_var: str = "SEARCH_API_PROVIDER",
    api_key_env_var: str = "SEARCH_API_KEY",
) -> dict:
    """Single decision point for retail/brand product search status.

    Returns a dict always containing at least ``status`` (one of
    ALL_RETAIL_SEARCH_STATUSES), ``canonical_status`` (kept identical to
    ``status`` -- this module IS the canonical vocabulary, unlike the
    legacy SOURCE_UNAVAILABLE/COMPLETED strings elsewhere in the codebase
    which predate it and are left alone per Section 39), ``source_type``,
    ``query``, ``detail``, and ``results`` (a list, empty unless a real
    provider call actually returned results).
    """
    base = {"source_type": "Retail/brand product search", "query": query, "results": []}

    if not use_live_search:
        return {
            **base,
            "status": SEARCH_NOT_PERFORMED,
            "canonical_status": SEARCH_NOT_PERFORMED,
            "detail": "Live search disabled for this run.",
        }

    api_key = os.environ.get(api_key_env_var)
    if not api_key:
        return {
            **base,
            "status": PROVIDER_UNAVAILABLE,
            "canonical_status": PROVIDER_UNAVAILABLE,
            "detail": (
                f"Set {api_key_env_var} to a configured retail/brand search "
                "provider's key to enable this search. No free source exists "
                "for this data."
            ),
        }

    provider_name = (os.environ.get(provider_env_var) or "").strip().lower()
    if not provider_name:
        return {
            **base,
            "status": PROVIDER_UNAVAILABLE,
            "canonical_status": PROVIDER_UNAVAILABLE,
            "detail": (
                f"{api_key_env_var} is set, but {provider_env_var} is not -- "
                "no provider selected."
            ),
        }

    implementation = _PROVIDER_IMPLEMENTATIONS.get(provider_name)
    if implementation is None:
        return {
            **base,
            "status": CONNECTOR_NOT_IMPLEMENTED,
            "canonical_status": CONNECTOR_NOT_IMPLEMENTED,
            "detail": (
                f"{provider_env_var}={provider_name!r} is not a wired-in "
                "provider. No real call is implemented for it yet; see "
                "_PROVIDER_IMPLEMENTATIONS in this module."
            ),
        }

    try:
        outcome = implementation(query, api_key)
        results = outcome.get("results", []) if isinstance(outcome, dict) else []
        status = SEARCH_COMPLETED_RESULTS_FOUND if results else SEARCH_COMPLETED_NO_RESULTS
        return {
            **base,
            "status": status,
            "canonical_status": status,
            "detail": f"{provider_name} search completed.",
            "results": results,
        }
    except Exception as exc:  # pragma: no cover - defensive, no real provider today
        return {
            **base,
            "status": SEARCH_FAILED,
            "canonical_status": SEARCH_FAILED,
            "detail": f"{provider_name} search raised: {exc}",
        }
