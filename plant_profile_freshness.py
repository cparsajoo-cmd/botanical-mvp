"""
plant_profile_freshness.py — Task 17.

Pure, Streamlit-independent, database-independent helper for
pages/Plant_Profile.py's Evidence Freshness section — same reasoning
as Task 16's own regulatory-evidence helper module:
pages/Plant_Profile.py executes real Streamlit calls and a real
database load at import time, so a pure function with neither
dependency is what makes this testable at all.

DATE SCHEMA AUDIT (performed before writing any code here)
Searched the active evidence_records schema (database.py's
save_evidence_record()/load_evidence_records(), and every production-
active connector that populates a row before it reaches that schema)
for every date-like field name suggested by this task
(Publication_Date, Evidence_Date, Publication_Year, Year) plus
ingestion/system-timestamp names explicitly to be treated with
suspicion (Created_At, Updated_At, Ingested_At) and
data_contracts.RegulatoryRecord.last_verified_date.

FOUND: exactly one structured, source-derived date-like field exists
anywhere in the active schema — "Source_Year" (database.py:135,
sources.year on write; database.py:328 / "Source_Year" on read).
Every production-active connector that ever sets it writes a bare
4-digit year string (confirmed by direct inspection:
ema_regulatory_connector.py, europepmc_connector.py,
crossref_connector.py all write e.g. "2021" — never a fuller date).
pubmed_connector.py does not set it at all — PubMed-sourced records in
this repository currently carry NO date information, a genuine,
disclosed limitation, not a bug in this module.

EXCLUDED, WITH REASONS:
  - Created_At / Updated_At / Ingested_At: do not exist anywhere in
    the active evidence_records schema. The only "created_at"-shaped
    field found anywhere in this repository belongs to
    scientific_evidence_collector.py, confirmed `legacy_candidates` by
    repo_dependency_audit.py — it writes to a Supabase table
    (`scientific_evidence`) this active pipeline never reads from (see
    the Task 11 audit's own finding on this table's dead write path).
    Even if it were active, it would be a cache/ingestion timestamp
    ("when did OUR system see this"), not evidence.publication.date —
    exactly the kind of field this task says not to use.
  - data_contracts.RegulatoryRecord.last_verified_date: a dataclass
    field on a different, still-unpersisted contract (Task 14.1) — its
    own module docstring documents it is deliberately always left None
    (Source_Year is a document/PDF snapshot year, not a verification
    date — converting it to a fabricated "verified" date was
    explicitly rejected during that task). Not a column on
    evidence_records at all, and not evidence-date semantics even if
    it were populated.

CONCLUSION: DATE_FIELD_PRECEDENCE below has exactly one entry today.
It is written as an ordered tuple, not a single hardcoded field name,
specifically so a future second genuine date field could be added, in
priority order, without restructuring this module's own logic — not
because more than one field currently exists.
"""

import re
from datetime import date, datetime

import pandas as pd

from standard_evidence_builder import normalize_missing_value

# The active evidence_records schema's ONLY structured, source-derived
# date-like field today — see this module's own docstring above for
# the full audit and every excluded alternative, with reasons.
DATE_FIELD_PRECEDENCE = ("Source_Year",)

_YEAR_PATTERN = re.compile(r"^\d{4}$")

# A basic plausibility bound, wide enough to accept a genuinely old
# historical citation without accepting obvious garbage (e.g. "0000",
# "9999", or a typo). Not a scientific claim about publication history
# — purely a crash/nonsense guard, per this task's "invalid or
# impossible dates... must not crash" requirement.
_MIN_PLAUSIBLE_YEAR = 1000
_MAX_PLAUSIBLE_YEAR = 2100


def _plausible_year(year):
    return _MIN_PLAUSIBLE_YEAR <= year <= _MAX_PLAUSIBLE_YEAR


def _parse_evidence_date(value):
    """Returns (display_string, sort_key) for a genuinely valid,
    plausible date-like value, or None for anything missing, invalid,
    or implausible.

    NEVER invents precision: display_string is always exactly the
    value the source actually gave (a bare year stays a bare year,
    e.g. "2021" — never reformatted into "2021-01-01"). sort_key is an
    internal-only (year, month, day) tuple used purely to determine
    oldest/newest correctly across mixed precision — a year-only value
    sorts as if it were January 1st of that year, but that assumption
    is NEVER shown to a caller or user.
    """
    normalized = normalize_missing_value(value)
    if normalized is None:
        return None

    # Guard against True/False (a bool IS an int in Python) being
    # silently misread as year 1 or year 0.
    if isinstance(normalized, bool):
        return None

    # A real datetime-like object (pandas Timestamp / date / datetime) —
    # defensive handling per this task's "datetime and pandas Timestamp
    # values" requirement, even though no active connector currently
    # produces one for Source_Year (always a plain string today).
    if isinstance(normalized, (pd.Timestamp, datetime, date)):
        try:
            year = normalized.year
        except Exception:
            return None
        if not _plausible_year(year):
            return None
        if isinstance(normalized, (pd.Timestamp, datetime)):
            display = normalized.date().isoformat()
            sort_key = (normalized.year, normalized.month, normalized.day)
        else:
            display = normalized.isoformat()
            sort_key = (normalized.year, normalized.month, normalized.day)
        return display, sort_key

    # A numeric year (int, or a whole-number float) — defensive
    # handling for "mixed data types"; a non-whole-number float (e.g.
    # 2021.5) is not a genuine year and is correctly treated as
    # invalid, not rounded or guessed.
    if isinstance(normalized, (int, float)):
        try:
            year = int(normalized)
        except Exception:
            return None
        if float(year) != float(normalized):
            return None
        if not _plausible_year(year):
            return None
        return str(year), (year, 1, 1)

    text = str(normalized).strip()
    if not text:
        return None

    # Year-only (exactly 4 digits) — the shape every active connector
    # actually writes today (see this module's own docstring).
    if _YEAR_PATTERN.match(text):
        year = int(text)
        if not _plausible_year(year):
            return None
        return text, (year, 1, 1)

    # Defensive: a fuller date string, in case a future field or
    # connector ever carries one. Parsed ONLY to derive a sort key —
    # the ORIGINAL string is still what gets returned/displayed, never
    # a reformatted or invented value.
    try:
        parsed = pd.to_datetime(text, errors="raise")
    except Exception:
        return None

    if not _plausible_year(parsed.year):
        return None
    return text, (parsed.year, parsed.month, parsed.day)


def summarize_evidence_freshness(dataframe, scientific_name):
    """Task 17 — summarizes evidence-date coverage for one plant across
    ALL of its evidence rows (never plant_data.iloc[0] or any other
    single-row shortcut).

    Parameters
    ----------
    dataframe : the already-loaded evidence DataFrame (e.g.
        evidence_database.load_evidence_database()'s return value —
        this function never loads or queries anything itself).
    scientific_name : the selected plant's Scientific_Name, matched
        exactly — the same equality check Task 16's
        get_regulatory_source_rows() already uses.

    Returns
    -------
    A dict with exactly these keys:
      total_records    — int, every evidence row for this plant,
                          dated or not.
      dated_records     — int, rows that contributed a valid,
                           plausible date (at most one date per row —
                           see DATE_FIELD_PRECEDENCE).
      undated_records   — int, total_records - dated_records.
      oldest_date        — str, the ORIGINAL value (year-only or fuller,
                           exactly as the source gave it) of the
                           earliest dated record, or None if no row is
                           dated.
      newest_date        — str, same, for the latest dated record, or
                           None.
      date_range         — str, "{oldest} – {newest}" when they differ,
                           just the single value when every dated
                           record shares the same date, or None if no
                           row is dated.

    Never mutates `dataframe`. Never raises — degrades to the
    all-zero/all-None result above for any missing/malformed input.
    Duplicate dates across different rows are NOT deduplicated —
    dated_records counts every row that has a valid date, even if
    several rows share the exact same value; this function never
    reduces a genuine evidence-record count.
    """
    result = {
        "total_records": 0,
        "dated_records": 0,
        "undated_records": 0,
        "oldest_date": None,
        "newest_date": None,
        "date_range": None,
    }

    if dataframe is None or not hasattr(dataframe, "empty") or dataframe.empty:
        return result

    if "Scientific_Name" not in dataframe.columns:
        return result

    normalized_name = normalize_missing_value(scientific_name)
    if normalized_name is None:
        return result

    try:
        plant_rows = dataframe[dataframe["Scientific_Name"] == normalized_name]
    except Exception:
        return result

    total_records = len(plant_rows)
    if total_records == 0:
        return result

    result["total_records"] = total_records

    parsed_dates = []  # (display, sort_key) — at most one entry per row
    for _, row in plant_rows.iterrows():
        row_date = None
        for field_name in DATE_FIELD_PRECEDENCE:
            if field_name not in plant_rows.columns:
                continue
            try:
                candidate = _parse_evidence_date(row.get(field_name))
            except Exception:
                candidate = None
            if candidate is not None:
                row_date = candidate
                break  # deterministic precedence: first matching field wins
        if row_date is not None:
            parsed_dates.append(row_date)

    dated_records = len(parsed_dates)
    result["dated_records"] = dated_records
    result["undated_records"] = total_records - dated_records

    if dated_records == 0:
        return result

    oldest_display, _ = min(parsed_dates, key=lambda pair: pair[1])
    newest_display, _ = max(parsed_dates, key=lambda pair: pair[1])

    result["oldest_date"] = oldest_display
    result["newest_date"] = newest_display
    result["date_range"] = (
        oldest_display if oldest_display == newest_display
        else f"{oldest_display} \u2013 {newest_display}"
    )

    return result
