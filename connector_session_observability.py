"""
Sprint 6A.1 — Session-scoped Connector Observability.

WHAT THIS IS
A small, pure normalization function: it takes the dict
multi_source_collector.collect_multi_source_evidence() already returns
(sources_checked / errors / saved_records) and reshapes it into one
deterministic, consistent structured object describing THIS ONE
collection session. It performs no I/O of any kind — no network call,
no database read/write, no polling. It is called AFTER Step 2's
collection has already finished, on data that already exists in
memory.

WHAT THIS IS NOT (named explicitly, per the Sprint 6/6A audits'
repeated finding that this repository has no timestamp, version, or
persistence infrastructure to honestly support anything broader)
- NOT persistent monitoring — nothing here is written to Supabase or
  any file; the object exists only for the lifetime of the Streamlit
  session that produced it, exactly like sources_checked/errors/
  saved_records already did before this module existed.
- NOT knowledge freshness — no timestamp is fabricated. "Completed"
  describes THIS collection attempt's outcome, not when data was
  collected relative to now.
- NOT connector health history — there is no history. Only the most
  recent collection result this session holds is ever described.
- NOT a connector redesign — no *_connector.py file is imported,
  modified, or called by this module. It reads a dict that already
  exists; it triggers nothing.

WHY "Connector_Session_Observability", NOT "Connector_Metadata" OR
"Connector_Health"
Both of those names imply capabilities (version tracking, persistent
health, freshness) that were explicitly audited and found not to
exist anywhere in this repository (Sprint 6 and Sprint 6A audits). The
name itself needs to communicate the real scope: session-scoped,
collection-run-specific, non-persistent.

SOURCE-NAME CONSISTENCY (why no fuzzy-matching layer exists here)
sources_checked, saved_records' "source" field, and errors' "source"
field are ALL populated from the exact same source_config["name"]
string inside multi_source_collector._run_one_source() — by
construction, these three never disagree on spelling. No fuzzy-name
mapping is implemented here because the mismatch it would guard
against does not occur in this codebase as written; a defensive
".get('source', 'Unknown')" fallback is used instead, in case a
malformed record is ever produced.
"""

from __future__ import annotations

from source_registry import SOURCE_REGISTRY, get_source_config

# ---------------------------------------------------------------------
# Error classification — only categories reliably detectable from the
# EXISTING error text multi_source_collector.py already produces.
# Never claims "authentication failure" or "parsing failure" unless the
# text explicitly says so; anything else falls back to the honest,
# generic "generic_failure".
# ---------------------------------------------------------------------
_CONFIG_MISSING_PATTERNS = [
    "not configured", "set epo_ops_key", "api key", "environment variable",
    "free registration", "missing credentials", "authentication required",
]
_TIMEOUT_PATTERNS = ["timed out"]
_RATE_LIMIT_PATTERNS = ["rate limit", "429", "too many requests"]
_UNAVAILABLE_PATTERNS = ["not available", "unavailable"]


def _classify_error(error_message) -> str:
    """Returns one of: configuration_missing, timeout, rate_limited,
    unavailable, generic_failure, unknown. Never invents a category the
    text doesn't support."""
    if not error_message:
        return "unknown"
    lowered = str(error_message).lower()
    if any(p in lowered for p in _CONFIG_MISSING_PATTERNS):
        return "configuration_missing"
    if any(p in lowered for p in _TIMEOUT_PATTERNS):
        return "timeout"
    if any(p in lowered for p in _RATE_LIMIT_PATTERNS):
        return "rate_limited"
    if any(p in lowered for p in _UNAVAILABLE_PATTERNS):
        return "unavailable"
    return "generic_failure"


def _connector_type(source_name: str) -> str:
    """Uses source_registry.py as the canonical source for connector
    type — NEVER inferred from the connector's name string. A source
    absent from the registry (shouldn't normally happen, since
    sources_checked is itself built from the registry, but handled
    defensively) gets "Unclassified", never a guess."""
    config = get_source_config(source_name)
    if config and config.get("category"):
        return config["category"]
    return "Unclassified"


# Only ema_regulatory_connector.py implements a real, repository-level
# cache (an in-process lru_cache on the fetched HMPC inventory PDF —
# see that module directly). Every other connector's wording is
# deliberately conservative: it says NOTHING about whether the
# upstream API, an intermediate library, or network infrastructure
# caches responses on their own — only whether THIS repository does.
_EMA_SOURCE_NAME = "EMA/WHO/ESCOP Regulatory"


def _cache_observability(source_name: str) -> str:
    if source_name == _EMA_SOURCE_NAME:
        return (
            "Repository-level cache detected — an in-process lru_cache on the "
            "fetched EMA HMPC inventory PDF text (see ema_regulatory_connector.py). "
            "Unbounded duration (not time-based), cleared only on process/session "
            "restart. Cache hit/miss and cache age are not observable."
        )
    return (
        "No repository-level cache detected. This does not imply the upstream "
        "API, an underlying library, or network infrastructure never caches "
        "responses on their own — only that this repository implements no "
        "cache of its own for this source."
    )


# Connectors this repository has confirmed require no configuration as
# currently implemented (no API key, no auth header used in the actual
# request). NOT the same claim as "credentials were verified" — only
# that none are needed for the code path this repository actually runs.
_NO_CONFIG_REQUIRED_SOURCES = {
    "Europe PMC", "OpenAlex", "CrossRef", "ClinicalTrials.gov", "FDA Labels",
    "LiverTox", "DailyMed", "OpenFDA FAERS", "PubChem", "ChEMBL", "ChEBI",
    "EMA/WHO/ESCOP Regulatory", "Patent Landscape",
}
# Connectors whose configuration state cannot be determined by this
# repository at all — PubMed's real timeout/auth handling lives inside
# Biopython's Entrez internals (opaque to this codebase); Semantic
# Scholar's API key is OPTIONAL and degrades gracefully when absent, so
# its mere presence proves neither that it's set nor that it's valid.
_NOT_OBSERVABLE_CONFIG_SOURCES = {"PubMed", "Semantic Scholar"}


def _configuration_status(source_name: str, error_type) -> str:
    """Conservative only — never "Valid"/"Invalid"/"Authenticated",
    since the mere presence of an API key does not prove it works."""
    if error_type == "configuration_missing":
        return "Not configured"
    if source_name in _NOT_OBSERVABLE_CONFIG_SOURCES:
        return "Not observable"
    if source_name in _NO_CONFIG_REQUIRED_SOURCES:
        return "Not required"
    return "Not observable"


PUBMED_OBSERVABILITY_LIMITATION = (
    "Underlying Biopython Entrez timeout and retry behavior is not observable "
    "from this repository — only the attempted/completed/error outcome "
    "exposed by the current collection flow can be reported."
)


def _connector_limitations(source_name: str) -> list:
    limitations = []
    if source_name == "PubMed":
        limitations.append(PUBMED_OBSERVABILITY_LIMITATION)
    return limitations


SESSION_LIMITATIONS = [
    "Status reflects the current collection session only.",
    "Connector metadata is not persisted across application restarts.",
    "No last-success or last-failure timestamp is available.",
    "Connector version and execution duration are unavailable.",
]


def _derive_overall_status(totals: dict) -> str:
    """Deterministic derivation, documented here (not implicit):
      not_started           — nothing was attempted this session.
      failed                — attempted, but zero sources completed
                               (with or without records).
      completed             — every attempted source completed cleanly
                               (with or without records) — zero
                               failures/timeouts/not-configured.
      completed_with_errors — some sources completed, but at least one
                               failed/timed out/was not configured.
    Never "Overall connector health" or "System health" — this is a
    session-outcome label, not a health claim.
    """
    if totals["sources_attempted"] == 0:
        return "not_started"

    clean_completions = totals["sources_completed"] + totals["sources_completed_no_records"]
    problem_count = totals["sources_failed"] + totals["sources_timed_out"] + totals["sources_not_configured"]

    if clean_completions == 0:
        return "failed"
    if problem_count == 0:
        return "completed"
    return "completed_with_errors"


def _connector_entry(source_name: str, record_count: int, error_message) -> dict:
    """Builds one connector's entry, applying the documented status
    precedence:
      1. configuration_missing (from the recorded error text)
      2. timeout (from the recorded error text)
      3. any other recorded error -> "Failed"
      4. attempted with saved records -> "Completed"
      5. attempted with zero saved records, no error -> "Completed — no records"
    ("Not attempted" and "Unknown" are handled by the caller — a
    connector reaching this function was, by definition, attempted.)
    """
    error_type = None
    if error_message:
        error_type = _classify_error(error_message)
        if error_type == "configuration_missing":
            execution_status = "Not configured"
        elif error_type == "timeout":
            execution_status = "Timed out"
        else:
            execution_status = "Failed"
    elif record_count > 0:
        execution_status = "Completed"
    else:
        execution_status = "Completed — no records"

    return {
        "connector_name": source_name,
        "connector_type": _connector_type(source_name),
        "execution_status": execution_status,
        "configuration_status": _configuration_status(source_name, error_type),
        "records_saved": record_count,
        "cache_observability": _cache_observability(source_name),
        "error_type": error_type,
        "error_message": error_message,
        "limitations": _connector_limitations(source_name),
    }, execution_status


def build_connector_session_observability(collection_result: dict) -> dict:
    """Sprint 6A.1 — the ONE function this module exists to provide.
    Deterministic, pure, no I/O. `collection_result` is exactly what
    multi_source_collector.collect_multi_source_evidence() already
    returns — this function does not call it, does not re-trigger any
    connector, and does not recompute anything already decided by that
    call.
    """
    collection_result = collection_result or {}
    saved_records = collection_result.get("saved_records") or []
    errors = collection_result.get("errors") or []
    sources_checked = collection_result.get("sources_checked") or []

    records_by_source = {}
    for rec in saved_records:
        source = rec.get("source", "Unknown")
        records_by_source[source] = records_by_source.get(source, 0) + 1

    # First recorded error per source wins — deterministic, since
    # sources_checked/errors ordering is itself already deterministic
    # (sorted) by the time this function ever sees it.
    error_by_source = {}
    for err in errors:
        source = err.get("source", "Unknown")
        if source not in error_by_source:
            error_by_source[source] = err.get("error", "")

    connectors = []
    totals = {
        "sources_attempted": len(sources_checked),
        "sources_completed": 0,
        "sources_completed_no_records": 0,
        "sources_failed": 0,
        "sources_timed_out": 0,
        "sources_not_configured": 0,
        "records_saved": len(saved_records),
    }

    for source_name in sources_checked:
        entry, status = _connector_entry(
            source_name, records_by_source.get(source_name, 0), error_by_source.get(source_name),
        )
        connectors.append(entry)
        if status == "Completed":
            totals["sources_completed"] += 1
        elif status == "Completed — no records":
            totals["sources_completed_no_records"] += 1
        elif status == "Timed out":
            totals["sources_timed_out"] += 1
        elif status == "Not configured":
            totals["sources_not_configured"] += 1
        elif status == "Failed":
            totals["sources_failed"] += 1

    # Registered sources that this collection session never attempted
    # at all (e.g. disabled in source_registry.py) — reported as "Not
    # attempted", explicitly separate from the totals above (which only
    # count sources that were actually part of this session).
    all_registered_names = [s["name"] for s in SOURCE_REGISTRY]
    for source_name in all_registered_names:
        if source_name in sources_checked:
            continue
        connectors.append({
            "connector_name": source_name,
            "connector_type": _connector_type(source_name),
            "execution_status": "Not attempted",
            "configuration_status": _configuration_status(source_name, None),
            "records_saved": 0,
            "cache_observability": _cache_observability(source_name),
            "error_type": None,
            "error_message": None,
            "limitations": _connector_limitations(source_name),
        })

    return {
        "scope": "current_collection_session",
        "overall_status": _derive_overall_status(totals),
        "connectors": connectors,
        "session_totals": totals,
        "limitations": list(SESSION_LIMITATIONS),
    }
