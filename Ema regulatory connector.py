"""Real connector to EMA's HMPC "Inventory of herbal substances for
assessment" — a single, official, publicly downloadable PDF that lists
every herbal substance ever proposed to the Committee on Herbal
Medicinal Products for EU monograph assessment.

WHY THIS EXISTS (replacing the old regulatory_connector.py stub):
The previous "EMA/WHO/ESCOP Regulatory" source in Bulk Evidence
Collection was a hardcoded dictionary of exactly 4 plants (the original
sleep-tea set). It was listed in "Sources checked" alongside real API
sources (PubMed, ClinicalTrials.gov, ...), which made it look like every
plant's regulatory status had actually been checked, when in reality
nothing was ever looked up for ~99.8% of the database. This module
fetches EMA's real inventory document instead.

WHAT THIS DOES AND DOES NOT GIVE YOU:
- EMA's HMPC does not offer a bulk API or machine-readable export of
  monograph statuses — the "European Union herbal monographs" browse
  page is a dynamic, JS-rendered list, not something a simple HTTP
  fetch can read reliably. The inventory PDF fetched here is the one
  genuinely bulk-downloadable, structured EMA document that exists.
- The inventory groups columns (Ph. Eur., ESCOP, German Commission E,
  French Avis, WHO, Indian, Chinese) as a table in the PDF's visual
  layout. Extracting raw text from a PDF loses that visual column
  alignment — many rows have several BLANK columns, so a symbol's
  left-to-right text position does not reliably tell you which named
  column it belongs to. Guessing here risks silently mislabeling, e.g.,
  "no ESCOP monograph" as "has an ESCOP monograph" — which is worse
  than not having an answer for a regulatory-safety field.
- Because of that, this connector deliberately reports ONLY the one
  thing that CAN be extracted reliably from linear text: whether the
  substance is present in EMA's official inventory at all (a genuine,
  verifiable "this has been formally proposed to HMPC for EU monograph
  assessment" signal), plus a direct link to the source PDF so a human
  can read off the exact ESCOP/WHO/etc. columns themselves. This is a
  real, honest upgrade over "Not yet verified for everything" — without
  claiming a precision the text extraction can't actually deliver.
- Matching a scientific name (e.g. "Valeriana officinalis") to the
  inventory's pharmacopoeial Latin names (e.g. "Valerianae radix") uses
  a genus/species stem-overlap heuristic — not a hardcoded per-species
  table — so it applies uniformly to any plant, not just ones anyone
  thought to add by hand.
"""

import re
from functools import lru_cache

import requests

EMA_INVENTORY_PDF_URL = (
    "https://www.ema.europa.eu/en/documents/other/"
    "inventory-herbal-substances-assessment_en.pdf"
)

_STOPWORDS = {
    "AESGP", "AYUSH", "IVAA", "EDQM", "PL", "FR", "AT", "DE", "NL", "ES",
    "CZ", "SK", "H", "M", "L", "NIS", "COMPANY",
}

_NAME_START_RE = re.compile(r"^[A-Z][a-zA-Zäöü]+$")


def _fetch_pdf_text(timeout=20):
    try:
        import pypdf
    except ImportError:
        return None, "pypdf not installed (add 'pypdf' to requirements.txt)"

    try:
        response = requests.get(EMA_INVENTORY_PDF_URL, timeout=timeout)
        response.raise_for_status()
    except Exception as exc:
        return None, f"Could not fetch EMA inventory PDF: {exc}"

    try:
        import io
        reader = pypdf.PdfReader(io.BytesIO(response.content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        return None, f"Could not parse EMA inventory PDF: {exc}"

    return text, None


def _parse_substance_names(text):
    """Extract the leading Latin pharmacopoeial name from each entry
    line. Deliberately conservative: only the name is trusted, not the
    downstream ESCOP/WHO/etc. columns (see module docstring)."""
    entries = []
    lines = [l.rstrip() for l in text.split("\n") if l.strip()]

    for i, line in enumerate(lines):
        tokens = line.split()
        if not tokens or not _NAME_START_RE.match(tokens[0]):
            continue

        words = []
        for tok in tokens:
            if _NAME_START_RE.match(tok) and tok.upper() not in _STOPWORDS:
                words.append(tok)
            elif words and re.match(r"^[a-zäöü]+$", tok) and tok.upper() not in _STOPWORDS:
                words.append(tok)
            else:
                break

        if not words:
            continue

        # Handle a name wrapped onto the next line, e.g.
        # "Ginkgo bilobae" \n "folium" — only if the next line starts
        # with a single lowercase Latin word (a plant-part noun).
        if i + 1 < len(lines):
            next_tokens = lines[i + 1].split()
            if (
                len(next_tokens) == 1
                and re.match(r"^[a-zäöü]+$", next_tokens[0])
            ):
                words.append(next_tokens[0])

        entries.append(" ".join(words))

    return entries


def _stem(word, n=4):
    w = word.lower().strip()
    return w[:n] if len(w) >= n else w


def _build_stem_index(entries):
    index = {}
    for entry in entries:
        for word in entry.split():
            index.setdefault(_stem(word), set()).add(entry)
    return index


@lru_cache(maxsize=1)
def _get_inventory():
    """Fetched and parsed once per process (Streamlit keeps this warm
    across reruns within the same server process). Returns
    (stem_index, entries, error) — error is None on success."""
    text, error = _fetch_pdf_text()
    if error:
        return {}, [], error

    entries = _parse_substance_names(text)
    if not entries:
        return {}, [], "Fetched the PDF but could not parse any entries from it."

    return _build_stem_index(entries), entries, None


def search_regulatory_sources_real(
    scientific_name,
    indication="",
    dosage_form="",
    market="European Union",
):
    """Real replacement for the old 4-plant regulatory_connector stub.
    Returns a list of 0 or 1 record, in the same shape the rest of the
    pipeline (multi_source_collector.py / Supabase evidence table)
    already expects.
    """
    stem_index, _entries, error = _get_inventory()

    if error:
        return [{
            "Scientific_Name": scientific_name,
            "Common_Name": "",
            "Product_Type": "Herbal product",
            "Dosage_Form": dosage_form,
            "Target_Indication": indication,
            "Target_Market": market,
            "Source_Type": "Regulatory",
            "Source_Organization": "EMA HMPC (live fetch failed)",
            "Source_Title": "EMA HMPC inventory of herbal substances",
            "Source_URL": EMA_INVENTORY_PDF_URL,
            "Source_Year": "",
            "Notes": f"Could not check EMA's inventory this time: {error}",
            "Evidence_Level": "Not available",
            "EMA_Status": "Not yet verified",
            "WHO_Status": "Not yet verified",
            "ESCOP_Status": "Not yet verified",
            "Regulatory_Status": "Live lookup failed — see Notes.",
        }]

    genus, *rest = scientific_name.split()
    species = rest[0] if rest else ""

    genus_stem = _stem(genus)
    species_stem = _stem(species) if species else None

    # Primary match: the plant's GENUS against the inventory entry's
    # FIRST word only (the pharmacopoeial name's head noun is always
    # genus-derived). This is deliberately strict — matching against
    # ANY word in the entry (including later words) caused false
    # positives: "Valeriana officinalis" was matching "Salviae
    # officinalis folium" purely because "officinalis" is a common
    # Latin species epithet ("medicinal") shared across dozens of
    # unrelated genera (Valeriana, Salvia, Melissa, Foeniculum, ...).
    matched_entries = {
        entry for entry in stem_index.get(genus_stem, set())
        if _stem(entry.split()[0]) == genus_stem
    }

    # Fallback ONLY when genus gives nothing: some pharmacopoeial names
    # use a common/trade name instead of the genus as their head word
    # (e.g. "Ginseng radix" for Panax ginseng) — match the species
    # epithet against the entry's first word in that case, still never
    # against later words, to avoid the same collision risk.
    if not matched_entries and species_stem:
        matched_entries = {
            entry for entry in stem_index.get(species_stem, set())
            if _stem(entry.split()[0]) == species_stem
        }

    if not matched_entries:
        return [{
            "Scientific_Name": scientific_name,
            "Common_Name": "",
            "Product_Type": "Herbal product",
            "Dosage_Form": dosage_form,
            "Target_Indication": indication,
            "Target_Market": market,
            "Source_Type": "Regulatory",
            "Source_Organization": "EMA HMPC — Inventory of herbal substances for assessment",
            "Source_Title": "EMA HMPC inventory of herbal substances",
            "Source_URL": EMA_INVENTORY_PDF_URL,
            "Source_Year": "2021",
            "Notes": (
                f"'{scientific_name}' was not found (by genus/species stem "
                "match) in EMA's official inventory of herbal substances "
                "proposed for HMPC assessment. This means either no "
                "monograph work has been proposed for it, or it appears "
                "under a different pharmacopoeial Latin name than "
                "expected — worth a manual check at the source PDF if "
                "this plant matters for your product."
            ),
            "Evidence_Level": "Checked, not found",
            "EMA_Status": "Not in HMPC inventory (as of 2021 snapshot)",
            "WHO_Status": "Not yet verified",
            "ESCOP_Status": "Not yet verified",
            "Regulatory_Status": "Not found in EMA HMPC's assessment inventory.",
        }]

    matched_names = "; ".join(sorted(matched_entries))
    return [{
        "Scientific_Name": scientific_name,
        "Common_Name": "",
        "Product_Type": "Herbal product",
        "Dosage_Form": dosage_form,
        "Target_Indication": indication,
        "Target_Market": market,
        "Source_Type": "Regulatory",
        "Source_Organization": "EMA HMPC — Inventory of herbal substances for assessment",
        "Source_Title": "EMA HMPC inventory of herbal substances",
        "Source_URL": EMA_INVENTORY_PDF_URL,
        "Source_Year": "2021",
        "Notes": (
            f"Found in EMA's official HMPC inventory as: {matched_names}. "
            "This confirms the substance has been formally proposed/"
            "prioritized for EU herbal monograph assessment. The exact "
            "ESCOP / German Commission E / French / WHO monograph "
            "columns for this row require reading the source PDF table "
            "directly (column alignment isn't reliably recoverable from "
            "plain text extraction) — see Source_URL."
        ),
        "Evidence_Level": "Listed in official EMA HMPC inventory",
        "EMA_Status": f"Listed in HMPC inventory as '{matched_names}' — see source PDF for monograph status",
        "WHO_Status": "See source PDF (column not reliably text-extractable)",
        "ESCOP_Status": "See source PDF (column not reliably text-extractable)",
        "Regulatory_Status": (
            f"Present in EMA HMPC's herbal substance inventory "
            f"('{matched_names}') — proposed/prioritized for assessment."
        ),
    }]
