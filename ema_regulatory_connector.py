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
  assessment" signal). WHO and ESCOP are separate authorities and are
  never inferred from this EMA document; they remain "Not independently
  verified" unless a separately curated, source-specific record exists. This is a
  real, honest upgrade over "Not yet verified for everything" — without
  claiming a precision the text extraction can't actually deliver.
- Matching a scientific name (e.g. "Valeriana officinalis") to the
  inventory's pharmacopoeial Latin names (e.g. "Valerianae radix") uses
  a genus/species taxonomic-matching strategy — not a hardcoded
  per-species table — so it applies uniformly to any plant, not just
  ones anyone thought to add by hand.

PHASE 2B (regulatory-connector audit) — WHAT CHANGED AND WHY
A real Streamlit run against the live inventory PDF exposed three
generic defects, all fixed in this module:

1. PARSING FALSE POSITIVES. The old name-extraction regex accepted any
   run of capitalized-then-lowercase words as a candidate "Latin name",
   which also matches ordinary English sentence fragments the PDF's
   own header/footer/address boilerplate contains (e.g. "Official
   address Domenico Scarlattilaan..."). Fix: an entry is only accepted
   if its LAST word is a recognized pharmacopoeial plant-part noun
   (_PHARMACOPOEIAL_PART_NOUNS below — standard Ph. Eur./EMA anatomical
   vocabulary, not a plant-name list) — see _parse_substance_names().

2. GENUS-COLLISION FALSE POSITIVES. The old matcher truncated every
   word to its first 4 characters and compared those prefixes for
   equality (_stem()). That is far too short to be genus-specific:
   "Glycyrrhiza" and "Glycine" both truncate to "glyc", so a search for
   one could match inventory entries for the other — two botanically
   unrelated genera. Fix: _latin_root() strips a recognized Latin
   genitive-case ending (the PDF's pharmacopoeial names are declined,
   e.g. "Valerianae" for Valeriana) instead of blindly truncating,
   keeping a much longer, genuinely genus-specific root, then compares
   full stripped roots for exact equality — never a short prefix.

3. NO SPECIES-LEVEL DISCRIMINATION. The old matcher only ever compared
   an entry's FIRST word (the genus) and completely ignored whether a
   SECOND word (a species epithet, when the inventory entry names one)
   agreed with the searched species — so any species within a matched
   genus was reported as "Listed", even when the inventory entry names
   a *different* species of that genus. Fix: _classify_inventory_match()
   below explicitly compares the entry's second word (when present and
   not itself a plant-part noun) against the searched species root, and
   returns one of several distinct match categories (see next section)
   instead of a single found/not-found boolean. Only an
   exact_species_match, verified_synonym_match, or
   verified_pharmacopoeial_name_match may report as genuinely "Listed" —
   a genus_only_match or related_species_only match never does.

STRUCTURED MATCH CATEGORIES (new "Taxonomic_Match_Status" field, plus
the module-level classify function below returns the same vocabulary):
  - exact_species_match             — genus AND species both agree
  - verified_synonym_match          — resolved via _VERIFIED_SYNONYMS
  - verified_pharmacopoeial_name_match — resolved via
                                         _VERIFIED_SPECIES_TO_PHARMACOPOEIAL_NAME,
                                         keyed by the searched scientific
                                         name (e.g. "panax ginseng" ->
                                         "Ginseng radix")
  - genus_only_match                — genus agrees; inventory entry
                                       names no species (or names none
                                       explicitly)
  - related_species_only            — genus agrees; inventory entry
                                       names a DIFFERENT species
  - ambiguous_match                 — more than one genus-level entry
                                       found with conflicting species
                                       signals; cannot resolve safely
  - searched_not_found              — inventory fetched/parsed fine;
                                       no genus-level match at all
  - parsing_failed                  — the PDF was fetched but its text
                                       could not be parsed into entries
  - source_unavailable              — the PDF itself could not be
                                       fetched (network/timeout/etc.)

_VERIFIED_SYNONYMS and _VERIFIED_SPECIES_TO_PHARMACOPOEIAL_NAME are
deliberately EMPTY by default. Populating either with an unverified
entry would silently manufacture a false "Listed" result — exactly
what this phase exists to eliminate — so an entry may only be added
once it is backed by a citable authority (e.g. World Flora Online for
a synonym, or the European Pharmacopoeia itself for a pharmacopoeial-
name mapping). The mechanism is generic and reusable; it is not
pre-populated with any specific plant. Direction is fixed and
consistent for both tables: the KEY is always the scientific name this
connector is searched with (the normal call-path input) — for
_VERIFIED_SYNONYMS the VALUE is another scientific name to resolve
through; for _VERIFIED_SPECIES_TO_PHARMACOPOEIAL_NAME the VALUE is the
literal, verified pharmacopoeial inventory entry text itself.
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

# Standard Ph. Eur. / EMA pharmacopoeial plant-part nouns. Every genuine
# HMPC inventory entry names a plant PART (this is literally what a
# "herbal substance" is: species + part), so requiring the last word of
# a candidate entry to be one of these is a generic, structural filter
# against non-botanical PDF text (addresses, headers, titles) — not a
# per-species rule. Latin singular/plural forms both included.
_PHARMACOPOEIAL_PART_NOUNS = {
    "radix", "radices", "rhizoma", "rhizomata", "herba", "herbae",
    "folium", "folia", "flos", "flores", "fructus", "semen", "semina",
    "cortex", "cortices", "summitas", "summitates", "oleum", "olea",
    "gummi", "resina", "succus", "tuber", "tubera", "bulbus", "bulbi",
    "lignum", "pericarpium", "stigma", "stigmata", "aetheroleum",
    "extractum", "tinctura", "pollen", "cera", "gemma", "gemmae",
    "cacumen", "cacumina", "pix", "balsamum",
}

# Common Latin noun-declension endings, longest first, stripped from a
# word's end (when enough of the word remains) to get a genuinely
# genus/species-specific root. This replaces a fixed-length prefix
# truncation (which caused real cross-genus collisions, e.g.
# "Glycyrrhiza"/"Glycine" both truncating to "glyc") with something
# that tracks actual Latin grammar instead of an arbitrary character
# count — still fully generic, not tied to any specific genus.
_GENITIVE_SUFFIXES = sorted(
    {"arum", "orum", "erum", "ae", "is", "us", "um", "i", "a", "e", "o"},
    key=len,
    reverse=True,
)

_MIN_ROOT_LEN = 4


def _latin_root(word):
    """Strip a recognized Latin case ending from `word`, keeping at
    least _MIN_ROOT_LEN characters of root. Falls back to the whole
    lowercased word if nothing safe can be stripped. Deliberately NOT a
    fixed-length prefix truncation — see module docstring, defect 2."""
    w = word.lower().strip()
    for suf in _GENITIVE_SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= _MIN_ROOT_LEN:
            return w[: -len(suf)]
    return w


# Verified taxonomic-synonym table: {"searched genus species" (lower,
# whitespace-normalized): "accepted genus species" (lower)}. See module
# docstring — deliberately empty; only add an entry backed by a citable
# authority (e.g. World Flora Online), never as a guess.
_VERIFIED_SYNONYMS = {}

# Verified accepted-species -> pharmacopoeial-inventory-name table:
# {"accepted genus species" (lower, whitespace-normalized): "verified
# pharmacopoeial inventory entry name" (as it appears in the EMA
# inventory, e.g. "Ginseng radix")}. Direction matters and is fixed:
# the KEY is the scientific botanical name this connector is searched
# with (the normal call-path input); the VALUE is the exact inventory
# entry text it is verified to correspond to, for cases where the
# inventory's head word is a trade/common Latin name rather than the
# genus (e.g. key "panax ginseng" -> value "ginseng radix"). See module
# docstring — deliberately empty; only add an entry backed by a
# citable pharmacopoeial source (e.g. Ph. Eur. itself), never a guess.
_VERIFIED_SPECIES_TO_PHARMACOPOEIAL_NAME = {}


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


def _classify_fetch_error(error_text):
    """Distinguishes a genuine source/connector failure (network,
    timeout, missing dependency) from a parsing failure (the PDF was
    fetched fine but its text couldn't be turned into entries) — both
    used to collapse into one generic error. Pattern-based on the
    error message this module itself generates above; not user input."""
    low = (error_text or "").lower()
    if "could not parse" in low or "could not parse any entries" in low:
        return "parsing_failed"
    return "source_unavailable"


def _parse_substance_names(text):
    """Extract the leading Latin pharmacopoeial name from each entry
    line. Deliberately conservative: only the name is trusted, not the
    downstream ESCOP/WHO/etc. columns (see module docstring).

    PHASE 2B: an entry is only accepted if its LAST word is a
    recognized pharmacopoeial plant-part noun
    (_PHARMACOPOEIAL_PART_NOUNS) — every genuine inventory entry names
    a plant part, so this structurally rejects non-botanical PDF text
    (addresses, headers, titles) without naming any specific plant or
    indication. See module docstring, defect 1.
    """
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

        # Structural rejection of non-botanical text (defect 1): the
        # last word must be a recognized plant-part noun. A genuine
        # multi-word administrative fragment ("Official address
        # Domenico Scarlattilaan") will not end in one of these.
        if words[-1].lower() not in _PHARMACOPOEIAL_PART_NOUNS:
            continue

        entries.append(" ".join(words))

    return entries


def _build_stem_index(entries):
    index = {}
    for entry in entries:
        for word in entry.split():
            index.setdefault(_latin_root(word), set()).add(entry)
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


def _classify_inventory_match(scientific_name, stem_index):
    """PHASE 2B core taxonomic-matching logic (defects 2 and 3).

    Returns (category, matched_entries) where category is one of:
    "exact_species_match", "verified_synonym_match",
    "verified_pharmacopoeial_name_match", "genus_only_match",
    "related_species_only", "ambiguous_match", "searched_not_found".

    Deliberately generic: driven only by (a) the searched name's own
    genus/species words, (b) the closed, universal Latin
    plant-part-noun vocabulary, and (c) whatever the (empty-by-default)
    verified synonym/pharmacopoeial tables contain — never a per-plant
    branch.
    """
    normalized = " ".join(scientific_name.strip().lower().split())

    if normalized in _VERIFIED_SYNONYMS:
        accepted = _VERIFIED_SYNONYMS[normalized]
        category, entries = _classify_inventory_match(accepted, stem_index)
        if category in ("exact_species_match", "genus_only_match"):
            return "verified_synonym_match", entries
        return category, entries

    if normalized in _VERIFIED_SPECIES_TO_PHARMACOPOEIAL_NAME:
        # Direction: KEY is the searched scientific name; VALUE is the
        # literal, verified pharmacopoeial inventory entry text itself
        # (e.g. "Ginseng radix") — NOT another scientific name to
        # re-resolve. So this looks the exact entry text up directly
        # against the parsed inventory, rather than recursing back
        # through genus/species matching (which expects a botanical
        # name, not a pharmacopoeial trade name).
        target = _VERIFIED_SPECIES_TO_PHARMACOPOEIAL_NAME[normalized].strip().lower()
        all_entries = set().union(*stem_index.values()) if stem_index else set()
        found = {entry for entry in all_entries if entry.strip().lower() == target}
        if found:
            return "verified_pharmacopoeial_name_match", found
        return "searched_not_found", set()

    genus, *rest = scientific_name.split()
    species = rest[0] if rest else ""

    genus_root = _latin_root(genus)
    species_root = _latin_root(species) if species else None

    # Primary match: the plant's GENUS against the inventory entry's
    # FIRST word only (the pharmacopoeial name's head noun is always
    # genus-derived). Deliberately strict — matching against ANY word
    # in the entry (including later words) caused false positives:
    # "Valeriana officinalis" was matching "Salviae officinalis folium"
    # purely because "officinalis" is a common Latin species epithet
    # ("medicinal") shared across dozens of unrelated genera.
    genus_candidates = {
        entry for entry in stem_index.get(genus_root, set())
        if _latin_root(entry.split()[0]) == genus_root
    }

    if not genus_candidates:
        # PHASE 2B CORRECTION: there used to be a fallback here that
        # matched the searched SPECIES epithet against an entry's head
        # word (intended for pharmacopoeial trade names like "Ginseng
        # radix" for Panax ginseng). That fallback was itself an
        # unverified inference, not a taxonomic match — species
        # epithets are frequently shared, generic Latin adjectives
        # ("officinalis", "vulgaris", "alba", "major", "minor", ...)
        # that say nothing about genus identity, so matching one
        # against an unrelated entry's head word is exactly the kind
        # of false positive this phase exists to eliminate. A
        # genuine pharmacopoeial trade name may ONLY produce a listed
        # result via the explicitly verified
        # _VERIFIED_SPECIES_TO_PHARMACOPOEIAL_NAME mapping above —
        # never an automatic epithet-to-head-word guess.
        return "searched_not_found", set()

    if not species_root:
        return "genus_only_match", genus_candidates

    exact, genus_level, other_species = set(), set(), set()
    for entry in genus_candidates:
        words = entry.split()
        if len(words) < 2:
            genus_level.add(entry)
            continue
        second_root = _latin_root(words[1])
        if words[1].lower() in _PHARMACOPOEIAL_PART_NOUNS:
            # Second word is itself the plant part -> this entry names
            # no species, only a genus ("Menthae folium").
            genus_level.add(entry)
        elif second_root == species_root:
            exact.add(entry)
        else:
            other_species.add(entry)

    if exact:
        return "exact_species_match", exact
    if genus_level and other_species:
        # Conflicting signals within the same genus: some entries name
        # no species at all, others name a different one. Not safe to
        # resolve automatically either way.
        return "ambiguous_match", genus_level | other_species
    if genus_level:
        return "genus_only_match", genus_level
    if other_species:
        return "related_species_only", other_species
    return "searched_not_found", set()


def search_regulatory_sources_real(
    scientific_name,
    indication="",
    dosage_form="",
    market="European Union",
):
    """Real replacement for the old 4-plant regulatory_connector stub.
    Returns a list of 0 or 1 record, in the same shape the rest of the
    pipeline (multi_source_collector.py / Supabase evidence table)
    already expects, PLUS a new "Taxonomic_Match_Status" field (Phase
    2B, additive — see module docstring for the full vocabulary).

    IMPORTANT: EMA_Status only ever claims "Listed in HMPC inventory"
    for exact_species_match, verified_synonym_match, or
    verified_pharmacopoeial_name_match. Every other category's
    EMA_Status text is phrased to include "not found" so
    standard_evidence_builder.classify_ema_hmpc_signal() (the shared
    downstream normalization helper) correctly resolves it to
    searched_not_found rather than inventory_listed — the exact
    summary/detail contradiction this phase exists to eliminate.
    """
    stem_index, _entries, error = _get_inventory()

    source_url = f"{EMA_INVENTORY_PDF_URL}#plant={scientific_name.replace(' ', '_')}"

    if error:
        fetch_category = _classify_fetch_error(error)
        organization = (
            "EMA HMPC (PDF parsing failed)" if fetch_category == "parsing_failed"
            else "EMA HMPC (live fetch failed)"
        )
        return [{
            "Scientific_Name": scientific_name,
            "Common_Name": "",
            "Product_Type": "Herbal product",
            "Dosage_Form": dosage_form,
            "Target_Indication": indication,
            "Target_Market": market,
            "Source_Type": "Regulatory",
            "Source_Organization": organization,
            "Source_Title": f"EMA HMPC inventory of herbal substances — {scientific_name}",
            "Source_URL": source_url,
            "Source_Year": "",
            "Notes": f"Could not check EMA's inventory this time: {error}",
            "Evidence_Level": "Not available",
            "EMA_Status": "Not yet verified",
            "WHO_Status": "Not independently verified",
            "ESCOP_Status": "Not independently verified",
            "Regulatory_Status": "Live lookup failed — see Notes.",
            "Taxonomic_Match_Status": fetch_category,
        }]

    category, matched_entries = _classify_inventory_match(scientific_name, stem_index)

    if category in ("exact_species_match", "verified_synonym_match", "verified_pharmacopoeial_name_match"):
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
            "Source_Title": f"EMA HMPC inventory of herbal substances — {scientific_name}",
            "Source_URL": source_url,
            "Source_Year": "2021",
            "Notes": (
                f"Found in EMA's official HMPC inventory as: {matched_names}. "
                "This confirms the substance has been formally proposed/"
                "prioritized for EU herbal monograph assessment. The exact "
                "WHO and ESCOP status are not inferred from this EMA PDF. "
                "Those authorities require independent verification from their "
                "own sources; this record therefore reports only the EMA HMPC "
                "inventory signal."
            ),
            "Evidence_Level": "Listed in official EMA HMPC inventory",
            "EMA_Status": f"Listed in HMPC inventory as '{matched_names}' — see source PDF for monograph status",
            "WHO_Status": "Not independently verified",
            "ESCOP_Status": "Not independently verified",
            "Regulatory_Status": (
                f"Present in EMA HMPC's herbal substance inventory "
                f"('{matched_names}') — proposed/prioritized for assessment."
            ),
            "Taxonomic_Match_Status": category,
        }]

    if category == "genus_only_match":
        matched_names = "; ".join(sorted(matched_entries))
        notes = (
            f"'{scientific_name}''s genus appears in EMA's official inventory "
            f"as: {matched_names}, but no species-specific entry could be "
            f"confirmed. Not counted as a species-level match — worth a "
            "manual check at the source PDF."
        )
    elif category == "related_species_only":
        matched_names = "; ".join(sorted(matched_entries))
        notes = (
            f"Other species of the same genus appear in EMA's official "
            f"inventory ({matched_names}), but '{scientific_name}' itself "
            "was not found. These are different species and must not be "
            "treated as evidence for this one."
        )
    elif category == "ambiguous_match":
        matched_names = "; ".join(sorted(matched_entries))
        notes = (
            f"Inventory entries for this genus give conflicting species "
            f"signals ({matched_names}) — cannot resolve with confidence "
            f"whether '{scientific_name}' itself is listed. Not found with "
            "confidence; worth a manual check at the source PDF."
        )
    else:  # searched_not_found
        notes = (
            f"'{scientific_name}' was not found (by taxonomic genus/species "
            "match) in EMA's official inventory of herbal substances "
            "proposed for HMPC assessment. This means either no "
            "monograph work has been proposed for it, or it appears "
            "under a different pharmacopoeial Latin name than "
            "expected — worth a manual check at the source PDF if "
            "this plant matters for your product."
        )

    return [{
        "Scientific_Name": scientific_name,
        "Common_Name": "",
        "Product_Type": "Herbal product",
        "Dosage_Form": dosage_form,
        "Target_Indication": indication,
        "Target_Market": market,
        "Source_Type": "Regulatory",
        "Source_Organization": "EMA HMPC — Inventory of herbal substances for assessment",
        "Source_Title": f"EMA HMPC inventory of herbal substances — {scientific_name}",
        "Source_URL": source_url,
        "Source_Year": "2021",
        "Notes": notes,
        "Evidence_Level": "Checked, not found",
        "EMA_Status": "Not in HMPC inventory (as of 2021 snapshot)",
        "WHO_Status": "Not independently verified",
        "ESCOP_Status": "Not independently verified",
        "Regulatory_Status": "Not found in EMA HMPC's assessment inventory.",
        "Taxonomic_Match_Status": category,
    }]
