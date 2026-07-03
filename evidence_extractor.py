import re


def _find_any(text, keywords):
    t = text.lower()
    return any(k.lower() in t for k in keywords)


def extract_evidence_from_text(source_text):
    text = source_text.strip()
    lower = text.lower()

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
        "Clinical_Level": "",
        "Clinical_RCT_Count": 0,
        "Meta_Level": "",
        "Meta_Count": 0,
        "Infusion_Evidence": "",
        "Safety_Level": "",
        "Drug_Interaction_Level": "",
        "Commercial_Level": "",
        "Regulatory_Status": "",
        "Novel_Food_Status": "",
        "Reference_Count": 1,
        "Notes": text,
    }

    # Scientific name: simple Latin binomial detection
    match = re.search(r"\b([A-Z][a-z]+)\s+([a-z]+)\b", text)
    if match:
        record["Scientific_Name"] = match.group(0)

    # Dosage form
    if _find_any(lower, ["infusion", "herbal tea", "tea", "tisane"]):
        record["Dosage_Form"] = "Infusion"
        record["Infusion_Evidence"] = "Direct"

    elif _find_any(lower, ["capsule", "capsules"]):
        record["Dosage_Form"] = "Capsule"
        record["Infusion_Evidence"] = "Indirect"

    elif _find_any(lower, ["tablet", "tablets"]):
        record["Dosage_Form"] = "Tablet"
        record["Infusion_Evidence"] = "Indirect"

    elif _find_any(lower, ["cream", "ointment"]):
        record["Dosage_Form"] = "Cream"

    elif _find_any(lower, ["syrup"]):
        record["Dosage_Form"] = "Syrup"

    # Indication
    if _find_any(lower, ["sleep", "insomnia", "mental stress", "relaxation", "nervous tension"]):
        record["Target_Indication"] = "Sleep and relaxation"

    elif _find_any(lower, ["constipation", "laxative", "bowel"]):
        record["Target_Indication"] = "Constipation"

    elif _find_any(lower, ["cough", "bronchial", "respiratory"]):
        record["Target_Indication"] = "Cough"

    elif _find_any(lower, ["digestion", "digestive", "gastrointestinal", "stomach"]):
        record["Target_Indication"] = "Digestive comfort"

    elif _find_any(lower, ["anxiety", "anxious"]):
        record["Target_Indication"] = "Anxiety"

    elif _find_any(lower, ["skin", "eczema", "dermatitis", "psoriasis"]):
        record["Target_Indication"] = "Skin inflammation"

    # Source status
    if _find_any(lower, ["ema", "hmpc", "european medicines agency"]):
        record["EMA_Status"] = "Yes"
        record["Regulatory_Status"] = "EMA/HMPC source detected"

    if _find_any(lower, ["who monograph", "world health organization"]):
        record["WHO_Status"] = "Yes"

    if _find_any(lower, ["escop"]):
        record["ESCOP_Status"] = "Yes"

    # Evidence level
    if _find_any(lower, ["randomized", "randomised", "clinical trial", "rct"]):
        record["Clinical_Level"] = "Moderate"
        record["Clinical_RCT_Count"] = 1

    if _find_any(lower, ["systematic review", "meta-analysis", "meta analysis"]):
        record["Meta_Level"] = "Moderate"
        record["Meta_Count"] = 1

    # Safety
    if _find_any(lower, ["well tolerated", "safe", "no serious adverse"]):
        record["Safety_Level"] = "Good"

    elif _find_any(lower, ["contraindicated", "warning", "caution", "adverse"]):
        record["Safety_Level"] = "Caution"

    # Defaults
    if not record["Clinical_Level"]:
        record["Clinical_Level"] = "Not found"

    if not record["Meta_Level"]:
        record["Meta_Level"] = "Not found"

    if not record["Infusion_Evidence"]:
        record["Infusion_Evidence"] = "Not found"

    if not record["Safety_Level"]:
        record["Safety_Level"] = "Unknown"

    return record
