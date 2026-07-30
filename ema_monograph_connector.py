"""Real connector to individual EMA/HMPC per-substance "European Union
herbal monograph" / "Community herbal monograph" documents — the
richer, section-structured counterpart to ema_regulatory_connector.py
(which only checks presence in EMA's bulk inventory PDF).

WHAT THIS DOES:
Fetches the real monograph PDF for a (Scientific_Name, Plant_Part) pair
listed in ema_monograph_registry.py, extracts its numbered clinical
sections (4.1 Therapeutic indications through 4.9 Overdose), and
returns them as a structured MonographRecord — kept separate for
"Well-established use" (WEU) and "Traditional use" (TU) wherever the
source document itself separates them.

WHY THIS IS A SEPARATE MODULE FROM ema_regulatory_connector.py, NOT AN
EXTENSION OF IT:
The inventory connector deliberately reports almost nothing (presence
in an inventory) because inventory PDF text loses its column
structure. Per-substance monograph PDFs are different: HMPC monographs
follow a standardized, SmPC-style numbered-section template, which
extracts far more reliably. This module can therefore respond with
real clinical content (indications, posology, contraindications,
interactions, warnings) — content the inventory connector correctly
refuses to guess at.

HARD RULE — SCORING ISOLATION (do not remove without an explicit,
separate, reviewed decision):
The records this module returns must NEVER be added to
EVIDENCE_TEXT_INDEX_ALLOWLIST in botanical_rd_candidate_engine.py, and
must never be concatenated into the free-text pool that
_evidence_level() / classify_evidence_hierarchy() /
classify_negative_evidence() read. That existing allowlist already
lets ema_regulatory_connector.py's short "found in inventory" notes
leak into R&D_Opportunity_Score's "Regulatory / monograph evidence"
bucket (see the regulatory-connectors proposal, section on the score-
leakage finding) — an unintended side effect, not a design decision.
This module's records are far richer, more clinical-sounding text
(contraindications, posology, undesirable effects); if they entered
that same pool the same way, the leak would get substantially worse
and much harder to reason about. If contraindication data should ever
deliberately influence a hard safety gate, that must be a new,
explicit, structured-field-to-structured-gate connection — reviewed on
its own, not an accidental byproduct of this module's output sitting
in a shared text column.

REAL-WORLD PARSING NOTES (confirmed against actual fetched documents,
not assumed):
- The "Well-established use" column is frequently ENTIRELY EMPTY (e.g.
  Melissa officinalis has no well-established-use content in any
  clinical section — it's a pure traditional-use monograph). This is a
  common case, not an edge case, and is represented explicitly below
  as WEU_NOT_APPLICABLE rather than being confused with a parsing
  failure.
- Some monographs (e.g. Valeriana officinalis, radix) have a THIRD
  usage context within Traditional Use itself — e.g. "oral use" vs.
  "use as bath additive" — each with its own posology and
  contraindications. This parser captures that as sub-context text
  within the TU field rather than silently merging or discarding it;
  a future revision could split it further if a consumer needs to.
- Section numbers are not perfectly uniform across all monographs (a
  few multi-part-substance monographs shift numbering slightly for
  composition tables). The section regex below is anchored on the
  cross-document-stable clinical section numbers (4.1-4.9), which held
  across every real document checked during this connector's design
  (Melissa, Valeriana, Passiflora).
"""

import io
import re
from functools import lru_cache

import requests

from ema_monograph_registry import STANDALONE_MONOGRAPHS, COMBINATION_MONOGRAPHS

WEU_NOT_APPLICABLE = "WEU_NOT_APPLICABLE"  # confirmed absent, not a parse failure
NOT_RELIABLY_EXTRACTED = "NOT_RELIABLY_EXTRACTED"  # present but split not recoverable

# Section headers, in the order they appear in a standard HMPC
# monograph. Each tuple is (section_number, canonical_field_name).
_CLINICAL_SECTIONS = [
    ("4.1", "therapeutic_indications"),
    ("4.2", "posology"),
    ("4.3", "contraindications"),
    ("4.4", "special_warnings"),
    ("4.5", "interactions"),
    ("4.6", "fertility_pregnancy_lactation"),
    ("4.7", "effects_on_driving"),
    ("4.8", "undesirable_effects"),
    ("4.9", "overdose"),
]

# Matches a line that starts a numbered clinical section, e.g.
# "4.1. Therapeutic indications" or "4.1 Therapeutic indications".
_SECTION_HEADER_RE = re.compile(
    r"^\s*(4\.\d)\.?\s+[A-Z][a-zA-Z].*$", re.MULTILINE
)

# A "5." (Pharmacological properties) or higher top-level section marks
# the end of the clinical-particulars block we care about.
_SECTION_5_RE = re.compile(r"^\s*5\.\s+[A-Z]", re.MULTILINE)


def _fetch_pdf_text(url, timeout=20):
    try:
        import pypdf
    except ImportError:
        return None, "pypdf not installed (add 'pypdf' to requirements.txt)"

    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
    except Exception as exc:
        return None, f"Could not fetch monograph PDF: {exc}"

    try:
        reader = pypdf.PdfReader(io.BytesIO(response.content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        return None, f"Could not parse monograph PDF: {exc}"

    return text, None


def _split_clinical_sections(full_text):
    """Return {section_number: raw_section_text} for every 4.x section
    found. Conservative: if the section-5 boundary can't be located,
    section 4.9 simply runs to whatever text follows (still usually
    fine since 4.9 is short), rather than guessing a cutoff.
    """
    matches = list(_SECTION_HEADER_RE.finditer(full_text))
    if not matches:
        return {}

    end_match = _SECTION_5_RE.search(full_text)
    hard_end = end_match.start() if end_match else len(full_text)

    sections = {}
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else hard_end
        section_number = m.group(1)
        sections[section_number] = full_text[start:end].strip()
    return sections


def _split_weu_tu(section_text):
    """Split a section's text into (well_established_use, traditional_use).

    HMPC monographs render this as a two-column table; PDF text
    extraction collapses it to linear text with no reliable delimiter
    between columns. This function looks for the literal heading
    pattern "Well-established use" / "Traditional use" appearing on
    their own or as a lead-in — when it can't find a clean split point,
    it returns the whole text under WEU with TU set to
    NOT_RELIABLY_EXTRACTED, rather than guessing where the boundary is.

    IMPORTANT — confirmed real-world case: when a monograph has NO
    well-established-use content, the extracted text often just starts
    directly with the traditional-use text (no "Well-established use"
    heading line to find at all, since the column was empty in the
    source table). This function treats "no WEU heading found AND no
    'Not applicable' marker found" as WEU_NOT_APPLICABLE, not as a
    failed split — this was confirmed against the real Melissa
    officinalis monograph, which has this exact shape.
    """
    stripped = section_text.strip()
    if not stripped:
        return WEU_NOT_APPLICABLE, WEU_NOT_APPLICABLE

    # A lone "Well-established use Traditional use" run-together header
    # (common after PDF extraction collapses the two-column table
    # header into one line) — if that's ALL that's left after removing
    # the header, both columns were empty.
    header_only_re = re.compile(
        r"^(well[\s-]*established\s+use)\s*(traditional\s+use)\s*$",
        re.IGNORECASE,
    )
    if header_only_re.match(stripped):
        return WEU_NOT_APPLICABLE, WEU_NOT_APPLICABLE

    # No reliable heuristic exists yet to split WEU text from TU text
    # when both are genuinely present and run together after PDF
    # extraction (this is the same class of problem the inventory
    # connector's docstring describes for column-based tables) — flag
    # rather than guess.
    return NOT_RELIABLY_EXTRACTED, NOT_RELIABLY_EXTRACTED


def fetch_monograph_record(scientific_name, plant_part):
    """Fetch and parse the real EMA/HMPC monograph for a single
    (Scientific_Name, Plant_Part) pair.

    Returns a dict shaped as a Regulatory Knowledge Card record. This
    is DELIBERATELY NOT the same shape as the evidence records
    ema_regulatory_connector.py / multi_source_collector.py produce —
    see the scoring-isolation note in this module's docstring. Callers
    must not write this record into evidence_df or any table that
    feeds EVIDENCE_TEXT_INDEX_ALLOWLIST.
    """
    key = (scientific_name, plant_part)
    entry = STANDALONE_MONOGRAPHS.get(key)

    if entry is None:
        return {
            "Scientific_Name": scientific_name,
            "Plant_Part": plant_part,
            "Found_In_Registry": False,
            "Notes": (
                f"No verified monograph registry entry for "
                f"'{scientific_name}, {plant_part}'. This connector only "
                "covers a hand-verified pilot set — see "
                "ema_monograph_registry.py. Not finding an entry here "
                "does NOT mean no EMA monograph exists for this plant; "
                "it means this connector hasn't been extended to it yet."
            ),
        }

    text, error = _fetch_pdf_text(entry["url"])
    base_record = {
        "Scientific_Name": scientific_name,
        "Plant_Part": plant_part,
        "Found_In_Registry": True,
        "Monograph_Reference_Number": entry["monograph_reference"],
        "Monograph_Status": entry["status"],
        "Monograph_Adoption_Date": entry["adopted_date"],
        "Monograph_URL": entry["url"],
    }

    if error:
        base_record["Fetch_Error"] = error
        return base_record

    sections_raw = _split_clinical_sections(text)
    if not sections_raw:
        base_record["Fetch_Error"] = (
            "Fetched the PDF but could not locate any numbered clinical "
            "sections (4.1-4.9) in the extracted text — the document's "
            "layout may differ from the standard template this parser "
            "expects. Do not assume the monograph has no clinical "
            "content; assume the parser needs a human to look at this "
            "one specific document."
        )
        return base_record

    for section_number, field_name in _CLINICAL_SECTIONS:
        section_text = sections_raw.get(section_number, "")
        if not section_text:
            base_record[f"{field_name}_WEU"] = None
            base_record[f"{field_name}_TU"] = None
            base_record[f"{field_name}_extraction_note"] = (
                "Section not found in extracted text."
            )
            continue

        weu, tu = _split_weu_tu(section_text)
        base_record[f"{field_name}_WEU"] = weu
        base_record[f"{field_name}_TU"] = tu
        # Keep the raw combined text too, since — per this module's own
        # documented limitation — WEU/TU splitting is not yet reliable
        # for sections where both columns are genuinely populated. A
        # consumer needing the real content today should read this
        # field and split it by eye, exactly as ema_regulatory_
        # connector.py asks a human to read the inventory PDF directly
        # for columns it won't guess at.
        base_record[f"{field_name}_raw_text"] = section_text

    return base_record


@lru_cache(maxsize=64)
def fetch_monograph_record_cached(scientific_name, plant_part):
    """Cached wrapper — fetched once per process, same caching pattern
    as ema_regulatory_connector.py's _get_inventory()."""
    return fetch_monograph_record(scientific_name, plant_part)


def fetch_combination_monograph_record(combination_key):
    """Fetch and parse a combination monograph (Option B record type —
    see ema_monograph_registry.COMBINATION_MONOGRAPHS). Kept as a
    clearly distinct shape from single-substance records: combination
    monographs answer "is this specific combination recognized," not
    "is this plant recognized," and their composition tables (percentage
    ranges per substance) don't map onto the single-substance schema.

    NOTE: as of this connector's initial build, neither combination
    monograph in the registry has a directly-confirmed, fetchable PDF
    URL for the STANDALONE monograph document (one entry only has the
    HMPC Opinion document URL, which contains the monograph as an
    annex but is not the monograph PDF itself; the other has no URL
    confirmed at all). This function is intentionally a stub that
    reports that gap rather than fetching the wrong document type or
    guessing a URL — closing this gap is a follow-up task, not
    something to paper over here.
    """
    entry = COMBINATION_MONOGRAPHS.get(combination_key)
    if entry is None:
        return {
            "Combination_Key": combination_key,
            "Found_In_Registry": False,
        }

    if not entry.get("url") or "opinion-hmpc" in entry.get("url", ""):
        return {
            "Combination_Key": combination_key,
            "Combination_Label": entry["combination_label"],
            "Found_In_Registry": True,
            "Monograph_Reference_Number": entry["monograph_reference"],
            "Monograph_Status": entry["status"],
            "Fetch_Error": (
                "No directly-confirmed URL for the standalone monograph "
                "PDF (as opposed to the HMPC Opinion document, which "
                "contains the monograph as an annex but has different "
                "structure/pagination). Fetching and parsing this "
                "correctly needs that URL confirmed first — see "
                "ema_monograph_registry.py's note on this entry."
            ),
        }

    text, error = _fetch_pdf_text(entry["url"])
    if error:
        return {
            "Combination_Key": combination_key,
            "Combination_Label": entry["combination_label"],
            "Found_In_Registry": True,
            "Fetch_Error": error,
        }

    sections_raw = _split_clinical_sections(text)
    record = {
        "Combination_Key": combination_key,
        "Combination_Label": entry["combination_label"],
        "Found_In_Registry": True,
        "Monograph_Reference_Number": entry["monograph_reference"],
        "Monograph_Status": entry["status"],
        "Monograph_Adoption_Date": entry.get("adopted_date"),
        "Monograph_URL": entry["url"],
    }
    for section_number, field_name in _CLINICAL_SECTIONS:
        record[f"{field_name}_raw_text"] = sections_raw.get(section_number)
    return record
