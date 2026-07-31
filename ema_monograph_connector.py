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
  Melissa officinalis has no well-established-use content in ANY of
  its clinical sections — it's a pure traditional-use monograph).
  IMPORTANT, confirmed by live testing: this connector can only detect
  a section as "confirmed empty" when BOTH columns are empty. For a
  traditional-use-only plant like Melissa, every section still has
  Traditional-use content, so `{field}_section_status` will report
  "has_content_see_raw_text" for essentially every section — it is
  NOT a per-column signal, only a whole-section one. Do not read
  "has_content_see_raw_text" as "WEU has content"; it may equally mean
  only TU has content, which is the common case. This was the exact
  mistake an earlier version of this connector's own diagnostic check
  made, caught only by live-testing against the real deployed fetch.
- DECISION, confirmed after that same live testing: when a section has
  any content, this connector does NOT attempt to split WEU text from
  TU text. An earlier version tried; PDF text extraction collapses the
  two-column table with no reliable delimiter, and every populated
  section tested came back unsplittable — the split machinery fired
  100% of the time it mattered and told the caller nothing beyond
  "read the raw text yourself," which is exactly what the raw text
  field is for. Per-section `{field}_raw_text` is therefore the
  SOURCE OF TRUTH for content; a human reads WEU vs. TU off that text
  directly, the same way ema_regulatory_connector.py already asks a
  human to read the inventory PDF's columns directly rather than trust
  a guess.
  which is exactly what the raw text field is for. Per-section
  `{field}_raw_text` is therefore the SOURCE OF TRUTH for content; a
  human reads WEU vs. TU off that text directly, the same way
  ema_regulatory_connector.py already asks a human to read the
  inventory PDF's columns directly rather than trust a guess.
- Some monographs (e.g. Valeriana officinalis, radix) have a THIRD
  usage context within Traditional Use itself — e.g. "oral use" vs.
  "use as bath additive" — each with its own posology and
  contraindications. Since sections are returned as raw text, this
  sub-context is preserved automatically (nothing is stripped or
  merged away) — it's just up to the reader to notice it in the text.
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

WEU_NOT_APPLICABLE = "WEU_NOT_APPLICABLE"  # kept for backward compat; unused as of the raw-text-primary redesign
NOT_RELIABLY_EXTRACTED = "NOT_RELIABLY_EXTRACTED"  # kept for backward compat; unused as of the raw-text-primary redesign

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


def _detect_section_emptiness(section_text):
    """Detect whether a clinical section is CONFIRMED ENTIRELY EMPTY
    (no content in either the Well-established-use or Traditional-use
    column) — the one binary fact reliably extractable from linear PDF
    text for a two-column table.

    NAMING CORRECTION (confirmed with Hamid after live-testing against
    the real Melissa officinalis monograph): an earlier version of this
    function was named _detect_weu_status and implied it could tell you
    whether the WEU column specifically was empty. It could not. Live
    testing showed why: Melissa's monograph has an empty WEU column in
    every single clinical section, yet this function returned
    "present_see_raw_text" for nearly all of them — because TU content
    was present, and this function has no way to know WHICH column
    contributed that content once the two-column table has collapsed
    into linear text. It can only tell you "this section has zero
    content in it" vs. "this section has content in it (from WEU, TU,
    or both — read raw_text to find out which)". Renamed and
    redocumented to say exactly that and nothing more.

    Returns one of:
      - "section_entirely_empty"    — confirmed no WEU or TU content at all
      - "has_content_see_raw_text"  — some content present; which
                                       column(s) it belongs to is NOT
                                       determined by this function
    """
    stripped = section_text.strip()
    if not stripped:
        return "section_entirely_empty"

    header_only_re = re.compile(
        r"^(well[\s-]*established\s+use)\s*(traditional\s+use)\s*$",
        re.IGNORECASE,
    )
    if header_only_re.match(stripped):
        return "section_entirely_empty"

    return "has_content_see_raw_text"


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
            base_record[f"{field_name}_raw_text"] = None
            base_record[f"{field_name}_section_status"] = None
            base_record[f"{field_name}_extraction_note"] = (
                "Section not found in extracted text."
            )
            continue

        # raw_text is the SOURCE OF TRUTH — read it directly for the
        # real content (WEU and TU together, exactly as the monograph
        # states it). section_status only tells you whether the WHOLE
        # section is confirmed empty (no WEU, no TU); it does NOT tell
        # you whether WEU specifically is empty when the section has
        # any content at all — see _detect_section_emptiness()'s
        # docstring for why that distinction matters and why it
        # doesn't (and can't reliably) go further than this.
        base_record[f"{field_name}_raw_text"] = section_text
        base_record[f"{field_name}_section_status"] = _detect_section_emptiness(section_text)

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
