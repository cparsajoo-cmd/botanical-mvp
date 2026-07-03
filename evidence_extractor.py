import re


def _contains(text, words):
    text = text.lower()
    return any(w.lower() in text for w in words)


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
        "Clinical_Level": "Not found",
        "Clinical_RCT_Count": 0,
        "Meta_Level": "Not found",
        "Meta_Count": 0,
        "Infusion_Evidence": "Not found",
        "Safety_Level": "Unknown",
        "Drug_Interaction_Level": "Unknown",
        "Commercial_Level": "Unknown",
        "Regulatory_Status": "",
        "Novel_Food_Status": "To verify",
        "Reference_Count": 1,
        "Notes": raw,
    }

    # Scientific name
    match = re.search(r"\b([A-Z][a-z]+)\s+([a-z]+)\b", raw)
    if match:
        record["Scientific_Name"] = match.group(0)

    # Dosage form
    if _contains(lower, ["infusion", "herbal tea", "tea", "tisane"]):
        record["Dosage_Form"] = "Infusion"
        record["Infusion_Evidence"] = "Direct"
    elif _contains(lower, ["capsule", "capsules"]):
        record["Dosage_Form"] = "Capsule"
        record["Infusion_Evidence"] = "Indirect"
    elif _contains(lower, ["tablet", "tablets"]):
        record["Dosage_Form"] = "Tablet"
        record["Infusion_Evidence"] = "Indirect"
    elif _contains(lower, ["syrup"]):
        record["Dosage_Form"] = "Syrup"
    elif _contains(lower, ["cream", "ointment", "topical"]):
        record["Dosage_Form"] = "Cream"
    elif _contains(lower, ["extract"]):
        record["Dosage_Form"] = "Extract"

    # Indication
    if _contains(lower, ["sleep", "insomnia", "relaxation", "stress", "nervous tension"]):
        record["Target_Indication"] = "Sleep and relaxation"
    elif _contains(lower, ["constipation", "laxative", "bowel"]):
        record["Target_Indication"] = "Constipation"
    elif _contains(lower, ["cough", "bronchial", "respiratory"]):
        record["Target_Indication"] = "Cough"
    elif _contains(lower, ["digestive", "digestion", "gastrointestinal", "bloating", "flatulence"]):
        record["Target_Indication"] = "Digestive comfort"
    elif _contains(lower, ["anxiety", "anxious"]):
        record["Target_Indication"] = "Anxiety"
    elif _contains(lower, ["skin", "eczema", "dermatitis", "psoriasis", "inflammation"]):
        record["Target_Indication"] = "Skin inflammation"

    # Source / regulatory signals
    if _contains(lower, ["ema", "hmpc", "european medicines agency"]):
        record["EMA_Status"] = "Yes"
        record["Regulatory_Status"] = "EMA/HMPC evidence detected"

    if _contains(lower, ["who monograph", "world health organization"]):
        record["WHO_Status"] = "Yes"

    if _contains(lower, ["escop"]):
        record["ESCOP_Status"] = "Yes"

    # Clinical evidence
    if _contains(lower, ["randomized", "randomised", "clinical trial", "rct"]):
        record["Clinical_Level"] = "Moderate"
        record["Clinical_RCT_Count"] = 1

    if _contains(lower, ["systematic review", "meta-analysis", "meta analysis"]):
        record["Meta_Level"] = "Moderate"
        record["Meta_Count"] = 1

    # Safety
    if _contains(lower, ["well tolerated", "safe", "no serious adverse"]):
        record["Safety_Level"] = "Good"
    elif _contains(lower, ["contraindicated", "warning", "caution", "adverse event", "adverse reaction"]):
        record["Safety_Level"] = "Caution"

    return record
