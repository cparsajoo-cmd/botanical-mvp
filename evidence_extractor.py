import re


def _text(value):
    return str(value or "").lower()


def _contains(text, keywords):
    return any(k in text for k in keywords)


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
    if _contains(lower, ["ema", "hmpc", "european medicines agency"]):
        record["EMA_Status"] = "Yes"
        record["Regulatory_Status"] = "EMA/HMPC evidence detected"

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

    return record
