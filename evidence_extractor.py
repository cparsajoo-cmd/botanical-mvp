import re

from safety_interaction_attribution import extract_attributed_safety_interactions


def _text(value):
    return str(value or "").lower()


def _contains(text, keywords):
    return any(k in text for k in keywords)


# Task 14.2 — confirmed defect fix. The generic _contains() substring
# check above was matching "ema" inside unrelated words ("schema",
# "enema", "cinema", "schematic", "hematoma" all contain the letters
# "ema" consecutively). _contains() itself is NOT changed here — it is
# still used, unmodified, for every other keyword list in this file
# (WHO/ESCOP/safety/etc.) — this is a dedicated, narrowly-scoped
# replacement for the EMA/HMPC check only, per the explicit instruction
# not to broadly rewrite the shared helper.
_EMA_HMPC_PATTERN = re.compile(
    r"\bema\b|\bhmpc\b|european medicines agency",
    re.IGNORECASE,
)

# String forms a missing/NaN-like value can stringify to (None -> "None",
# float NaN -> "nan", pandas NA -> "<NA>", pandas NaT -> "NaT") — checked
# case-insensitively so none of them can ever accidentally satisfy
# _EMA_HMPC_PATTERN (they don't contain "ema"/"hmpc"/the full phrase
# anyway, but this makes the "missing values normalize to False"
# guarantee explicit and independently testable, not just incidental).
_MISSING_TEXT_TOKENS = {"nan", "none", "null", "<na>", "nat"}


def contains_ema_hmpc_reference(text):
    """Task 14.2 — narrowly-scoped, word-boundary-aware EMA/HMPC
    authority-mention detector, replacing evidence_extractor.py's
    previous plain substring check for this ONE keyword group only.

    Recognizes: standalone "EMA" (any case, including punctuation-
    delimited forms like "(EMA)" or "EMA,", via \\b word boundaries —
    "(" and ")"/"," are non-word characters, so a boundary exists on
    both sides of "EMA" inside "(EMA)" without needing to enumerate
    every possible surrounding punctuation mark); standalone "HMPC";
    "EMA/HMPC" and "EMA HMPC" (matched via the standalone "EMA"
    pattern, since "/" and " " are both non-word characters); the full
    phrase "European Medicines Agency", including its possessive form
    "European Medicines Agency's" (a plain substring check on the
    phrase already covers the possessive, since "European Medicines
    Agency's" contains "european medicines agency" as a prefix — no
    separate case needed).

    Deliberately rejects: "schema", "enema", "cinema", "schematic",
    "hematoma" — none of these have a word boundary immediately before
    the letters "ema", because in each case "ema" sits in the middle
    of (or attached to) a longer word, not on its own.

    Missing/NaN-like inputs (None, float NaN, pandas NA, empty or
    whitespace-only strings) safely return False — never raise, never
    require a caller to pre-check for missing values first.
    """
    if text is None:
        return False
    try:
        text_str = str(text)
    except Exception:
        return False

    text_str = text_str.strip()
    if not text_str or text_str.lower() in _MISSING_TEXT_TOKENS:
        return False

    return bool(_EMA_HMPC_PATTERN.search(text_str))


def extract_evidence_from_text(text):
    raw = text or ""
    lower = raw.lower()

    record = {
        "Scientific_Name": "",
        "Common_Name": "",
        "Product_Type": "Herbal product",
        "Dosage_Form": "",
        "Target_Indication": "",
        "Target_Market": "European Union",

        "EMA_Status": "",
        "WHO_Status": "",
        "ESCOP_Status": "",

        # Phase 2C (regulatory single-source-of-truth cleanup) — this
        # field is a TEXT-MENTION ANNOTATION only: "this publication's
        # text mentions EMA/HMPC somewhere". It is NOT a regulatory
        # finding and must never be read as one. Whether a plant is
        # actually listed in EMA's HMPC inventory is decided in exactly
        # one place: ema_regulatory_connector.py's live connector,
        # surfaced via botanical_rd_candidate_engine._market_status()/
        # _eu_regulatory_status(). This module has no access to that
        # connector and must not guess a regulatory conclusion from
        # incidental keyword co-occurrence in a PubMed abstract or
        # similar free text.
        "Regulatory_Reference_Detected": False,

        "Clinical_Level": "Not found",
        "Clinical_RCT_Count": 0,
        "Meta_Level": "Not found",
        "Meta_Count": 0,

        "Dosage_Form_Evidence": "Unknown",
        "Infusion_Evidence": "Unknown",

        "Safety_Level": "Unknown",
        "Drug_Interaction_Level": "Unknown",
        "Commercial_Level": "Unknown",

        "Regulatory_Status": "",
        "Novel_Food_Status": "To verify",
        "Reference_Count": 1,
        "Notes": raw,

        # New intelligence fields
        "Publication_Type": "Unknown",
        "Evidence_Type": "Unknown",
        "Evidence_Level": "Unknown",
        "Study_Type": "Unknown",
        "Study_Model": "Unknown",
        "Detected_Dosage_Forms": "",
        "Detected_Indications": "",
        "Dosage_Form_Relevance": "Unknown",
        "Safety_Signal": "",
        "Adverse_Events": None,
        "Interactions_Structured": None,
        "Safety_Reassurance": None,
        "Safety_Data_Status": "not_assessed",
        "Evidence_Score": 0,
    }

    # Scientific name
    match = re.search(r"\b([A-Z][a-z]+)\s+([a-z]+)\b", raw)
    if match:
        record["Scientific_Name"] = match.group(0)

    # Study type / publication type
    if _contains(lower, ["meta-analysis", "meta analysis"]):
        record["Publication_Type"] = "Meta-analysis"
        record["Evidence_Type"] = "Meta-analysis"
        record["Study_Type"] = "Meta-analysis"
        record["Evidence_Level"] = "Very High"
        record["Meta_Level"] = "Strong"
        record["Meta_Count"] = 1

    elif _contains(lower, ["systematic review"]):
        record["Publication_Type"] = "Systematic Review"
        record["Evidence_Type"] = "Systematic Review"
        record["Study_Type"] = "Systematic Review"
        record["Evidence_Level"] = "High"

    elif _contains(lower, ["randomized", "randomised", "placebo-controlled", "placebo controlled", "double-blind", "double blind"]):
        record["Publication_Type"] = "Randomized Controlled Trial"
        record["Evidence_Type"] = "Randomized Controlled Trial"
        record["Study_Type"] = "Randomized Controlled Trial"
        record["Evidence_Level"] = "High"
        record["Clinical_Level"] = "Strong"
        record["Clinical_RCT_Count"] = 1

    elif _contains(lower, ["clinical trial", "patients", "subjects", "volunteers"]):
        record["Publication_Type"] = "Clinical Study"
        record["Evidence_Type"] = "Clinical Study"
        record["Study_Type"] = "Clinical Study"
        record["Evidence_Level"] = "Moderate"
        record["Clinical_Level"] = "Moderate"

    elif _contains(lower, ["cohort", "observational", "case-control", "case control"]):
        record["Publication_Type"] = "Observational Study"
        record["Evidence_Type"] = "Observational Study"
        record["Study_Type"] = "Observational Study"
        record["Evidence_Level"] = "Moderate"

    elif _contains(lower, ["case report", "case series"]):
        record["Publication_Type"] = "Case Report"
        record["Evidence_Type"] = "Case Report"
        record["Study_Type"] = "Case Report"
        record["Evidence_Level"] = "Low"

    elif _contains(lower, ["rat", "rats", "mouse", "mice", "animal model"]):
        record["Publication_Type"] = "Animal Study"
        record["Evidence_Type"] = "Animal Study"
        record["Study_Type"] = "Animal Study"
        record["Evidence_Level"] = "Low"

    elif _contains(lower, ["in vitro", "cell line", "cell culture"]):
        record["Publication_Type"] = "In Vitro"
        record["Evidence_Type"] = "In Vitro"
        record["Study_Type"] = "In Vitro"
        record["Evidence_Level"] = "Very Low"

    elif _contains(lower, ["review"]):
        record["Publication_Type"] = "Review"
        record["Evidence_Type"] = "Review"
        record["Study_Type"] = "Review"
        record["Evidence_Level"] = "Low"

    # Study model
    if _contains(lower, ["patients", "subjects", "volunteers", "clinical trial", "randomized", "randomised"]):
        record["Study_Model"] = "Human"
    elif _contains(lower, ["rat", "rats", "mouse", "mice", "animal model"]):
        record["Study_Model"] = "Animal"
    elif _contains(lower, ["in vitro", "cell line", "cell culture"]):
        record["Study_Model"] = "Cell / In vitro"

    # Dosage form
    detected_forms = []

    dosage_keywords = {
        "Infusion": ["infusion", "tea", "herbal tea", "tisane", "decoction"],
        "Capsule": ["capsule", "capsules"],
        "Tablet": ["tablet", "tablets"],
        "Extract": ["extract", "dry extract", "standardized extract", "standardised extract", "aqueous extract", "ethanolic extract"],
        "Essential oil": ["essential oil", "volatile oil", "aromatherapy"],
        "Syrup": ["syrup"],
        "Cream": ["cream", "ointment", "topical"],
        "Gel": ["gel"],
        "Mouthwash": ["mouthwash", "gargle", "oral rinse"],
        "Spray": ["spray", "nasal spray"],
        "Powder": ["powder"],
    }

    for form, keys in dosage_keywords.items():
        if _contains(lower, keys):
            detected_forms.append(form)

    record["Detected_Dosage_Forms"] = ", ".join(detected_forms)

    if detected_forms:
        record["Dosage_Form"] = detected_forms[0]
        record["Dosage_Form_Evidence"] = "Direct"
        record["Infusion_Evidence"] = "Direct" if "Infusion" in detected_forms else "Indirect"

    # Indication
    detected_indications = []

    indication_keywords = {
        "Sleep and relaxation": ["sleep", "insomnia", "relaxation", "stress", "anxiety", "nervous tension"],
        "Constipation": ["constipation", "laxative", "bowel movement"],
        "Cough": ["cough", "bronchitis", "respiratory", "expectorant"],
        "Digestive comfort": ["digestion", "digestive", "dyspepsia", "bloating", "flatulence"],
        "Skin inflammation": ["skin", "dermatitis", "eczema", "inflammation", "wound"],
        "IBS": ["irritable bowel", "ibs"],
    }

    for indication, keys in indication_keywords.items():
        if _contains(lower, keys):
            detected_indications.append(indication)

    record["Detected_Indications"] = ", ".join(detected_indications)

    if detected_indications:
        record["Target_Indication"] = detected_indications[0]

    # Regulatory
    # Task 14.2 established the word-boundary-aware matcher below.
    # Phase 2C: this NO LONGER writes a regulatory conclusion
    # (EMA_Status). It only records that the text mentions EMA/HMPC —
    # an annotation about the PUBLICATION, not a finding about the
    # PLANT. The one and only place that determines whether a plant is
    # actually listed in EMA's HMPC inventory is the real connector
    # (ema_regulatory_connector.py), consumed via
    # botanical_rd_candidate_engine._market_status()/_eu_regulatory_status().
    if contains_ema_hmpc_reference(raw):
        record["Regulatory_Reference_Detected"] = True

    if _contains(lower, ["who monograph", "world health organization"]):
        record["WHO_Status"] = "Yes"

    if _contains(lower, ["escop"]):
        record["ESCOP_Status"] = "Yes"

    # Safety
    if _contains(lower, ["well tolerated", "safe", "no serious adverse"]):
        record["Safety_Level"] = "Good"
        record["Safety_Signal"] = "Positive safety signal"

    elif _contains(lower, ["adverse event", "adverse reaction", "contraindicated", "warning", "caution"]):
        record["Safety_Level"] = "Caution"
        record["Safety_Signal"] = "Safety caution detected"

    # Conservative plant-attributed extraction. General comparator statements,
    # protective/negated toxicity language, promotional/retracted content, and
    # drug names without an explicit interaction relation are rejected.
    attributed = extract_attributed_safety_interactions(
        raw,
        plant_name=record.get("Scientific_Name", ""),
        structurally_linked=bool(record.get("Scientific_Name")),
    )
    if attributed["adverse_events"]:
        record["Adverse_Events"] = {"source_text": attributed["adverse_events"]}
    if attributed["interactions"]:
        record["Interactions_Structured"] = {"source_text": attributed["interactions"]}
    if attributed["safety_reassurance"]:
        record["Safety_Reassurance"] = {"source_text": attributed["safety_reassurance"]}
    record["Safety_Data_Status"] = attributed["safety_data_status"]

    return record
