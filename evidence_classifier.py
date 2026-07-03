import re


DOSAGE_FORMS = {
    "Infusion": ["infusion", "tea", "herbal tea", "tisane", "decoction"],
    "Capsule": ["capsule", "capsules"],
    "Tablet": ["tablet", "tablets"],
    "Extract": ["extract", "standardized extract", "dry extract", "hydroalcoholic extract"],
    "Essential oil": ["essential oil", "aromatherapy", "volatile oil"],
    "Cream": ["cream", "ointment", "topical"],
    "Gel": ["gel"],
    "Syrup": ["syrup"],
    "Powder": ["powder"],
}


INDICATIONS = {
    "Sleep and relaxation": ["sleep", "insomnia", "relaxation", "stress", "anxiety", "nervous tension"],
    "Constipation": ["constipation", "laxative", "bowel movement"],
    "Cough": ["cough", "bronchitis", "respiratory", "expectorant"],
    "Digestive comfort": ["digestion", "digestive", "dyspepsia", "bloating", "flatulence"],
    "Skin inflammation": ["skin", "dermatitis", "eczema", "inflammation", "wound"],
    "IBS": ["irritable bowel", "ibs"],
}


def clean_text(record):
    return (
        str(record.get("Source_Title", "")) + " " +
        str(record.get("Notes", "")) + " " +
        str(record.get("Target_Indication", "")) + " " +
        str(record.get("Dosage_Form", ""))
    ).lower()


def detect_evidence_type(text):
    if "meta-analysis" in text or "meta analysis" in text:
        return "Meta-analysis", "Very High"
    if "systematic review" in text:
        return "Systematic Review", "High"
    if "randomized" in text or "randomised" in text or "rct" in text:
        return "Randomized Controlled Trial", "High"
    if "clinical trial" in text or "patients" in text or "subjects" in text:
        return "Clinical Study", "Moderate"
    if "cohort" in text or "observational" in text:
        return "Observational Study", "Moderate"
    if "case report" in text:
        return "Case Report", "Low"
    if "rat" in text or "mouse" in text or "mice" in text or "animal" in text:
        return "Animal Study", "Low"
    if "in vitro" in text or "cell line" in text:
        return "In Vitro", "Very Low"
    if "traditional use" in text or "monograph" in text:
        return "Traditional / Regulatory", "Traditional"
    return "Unknown", "Unknown"


def detect_study_model(text):
    if any(w in text for w in ["patients", "subjects", "volunteers", "clinical trial", "randomized", "randomised"]):
        return "Human"
    if any(w in text for w in ["rat", "mouse", "mice", "animal"]):
        return "Animal"
    if any(w in text for w in ["in vitro", "cell line"]):
        return "Cell / In vitro"
    return "Unknown"


def detect_dosage_form(text):
    detected = []
    for form, keywords in DOSAGE_FORMS.items():
        if any(k in text for k in keywords):
            detected.append(form)
    return detected


def detect_indication(text):
    detected = []
    for indication, keywords in INDICATIONS.items():
        if any(k in text for k in keywords):
            detected.append(indication)
    return detected


def classify_dosage_relevance(record, text):
    selected_form = str(record.get("Dosage_Form", "")).strip()
    detected_forms = detect_dosage_form(text)

    if selected_form and selected_form in detected_forms:
        return "Direct"

    if detected_forms:
        return "Indirect"

    return "Unknown"


def classify_regulatory(record):
    agencies = []

    if str(record.get("EMA_Status", "")).lower() == "yes":
        agencies.append("EMA")
    if str(record.get("WHO_Status", "")).lower() == "yes":
        agencies.append("WHO")
    if str(record.get("ESCOP_Status", "")).lower() == "yes":
        agencies.append("ESCOP")

    return ", ".join(agencies) if agencies else "None"


def calculate_score(evidence_level, dosage_relevance, regulatory, study_model):
    score = 0

    score += {
        "Very High": 40,
        "High": 35,
        "Moderate": 25,
        "Low": 12,
        "Very Low": 6,
        "Traditional": 10,
        "Unknown": 0,
    }.get(evidence_level, 0)

    score += {
        "Direct": 30,
        "Indirect": 10,
        "Unknown": 0,
    }.get(dosage_relevance, 0)

    if regulatory != "None":
        score += 20

    if study_model == "Human":
        score += 10
    elif study_model == "Animal":
        score += 4
    elif study_model == "Cell / In vitro":
        score += 2

    return min(score, 100)


def classify_evidence(record):
    text = clean_text(record)

    evidence_type, evidence_level = detect_evidence_type(text)
    study_model = detect_study_model(text)
    detected_forms = detect_dosage_form(text)
    detected_indications = detect_indication(text)
    dosage_relevance = classify_dosage_relevance(record, text)
    regulatory = classify_regulatory(record)

    score = calculate_score(
        evidence_level=evidence_level,
        dosage_relevance=dosage_relevance,
        regulatory=regulatory,
        study_model=study_model,
    )

    record["Evidence_Type"] = evidence_type
    record["Evidence_Level"] = evidence_level
    record["Study_Model"] = study_model
    record["Detected_Dosage_Forms"] = ", ".join(detected_forms)
    record["Detected_Indications"] = ", ".join(detected_indications)
    record["Dosage_Form_Relevance"] = dosage_relevance
    record["Regulatory_Evidence"] = regulatory
    record["Evidence_Score"] = score

    return record
