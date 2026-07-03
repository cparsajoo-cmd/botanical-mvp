def _text(record):
    return (
        str(record.get("Source_Title", "")) + " " +
        str(record.get("Notes", "")) + " " +
        str(record.get("Dosage_Form", "")) + " " +
        str(record.get("Target_Indication", ""))
    ).lower()


def classify_evidence(record):
    text = _text(record)

    evidence_type = "Unknown"
    evidence_level = "Unknown"
    study_model = "Unknown"

    if "meta-analysis" in text or "meta analysis" in text:
        evidence_type = "Meta-analysis"
        evidence_level = "Very High"
        study_model = "Human"

    elif "systematic review" in text:
        evidence_type = "Systematic Review"
        evidence_level = "High"
        study_model = "Human"

    elif "randomized" in text or "randomised" in text or "rct" in text:
        evidence_type = "Randomized Controlled Trial"
        evidence_level = "High"
        study_model = "Human"

    elif "clinical trial" in text or "patients" in text or "subjects" in text:
        evidence_type = "Clinical Study"
        evidence_level = "Moderate"
        study_model = "Human"

    elif "animal" in text or "mice" in text or "mouse" in text or "rat" in text:
        evidence_type = "Animal Study"
        evidence_level = "Low"
        study_model = "Animal"

    elif "in vitro" in text or "cell line" in text:
        evidence_type = "In Vitro"
        evidence_level = "Very Low"
        study_model = "In vitro"

    elif "traditional use" in text or "monograph" in text:
        evidence_type = "Traditional / Regulatory"
        evidence_level = "Traditional"
        study_model = "Traditional use"

    dosage_form = str(record.get("Dosage_Form", "")).lower()

    if dosage_form and dosage_form in text:
        dosage_relevance = "Direct"
    elif any(x in text for x in ["extract", "oil", "capsule", "tablet", "infusion", "tea", "cream", "gel", "syrup"]):
        dosage_relevance = "Indirect"
    else:
        dosage_relevance = "Unknown"

    regulatory_sources = []

    if str(record.get("EMA_Status", "")).lower() == "yes":
        regulatory_sources.append("EMA")
    if str(record.get("WHO_Status", "")).lower() == "yes":
        regulatory_sources.append("WHO")
    if str(record.get("ESCOP_Status", "")).lower() == "yes":
        regulatory_sources.append("ESCOP")

    regulatory_evidence = ", ".join(regulatory_sources) if regulatory_sources else "None"

    safety_text = str(record.get("Safety_Level", "")).lower()

    if safety_text in ["good", "acceptable", "high"]:
        safety_confidence = "High"
    elif safety_text in ["caution", "moderate"]:
        safety_confidence = "Moderate"
    elif safety_text in ["high risk", "low"]:
        safety_confidence = "Low"
    else:
        safety_confidence = "Unknown"

    commercial_text = str(record.get("Commercial_Level", "")).lower()

    if commercial_text in ["high", "strong"]:
        commercial_confidence = "High"
    elif commercial_text in ["moderate", "medium"]:
        commercial_confidence = "Moderate"
    elif commercial_text == "low":
        commercial_confidence = "Low"
    else:
        commercial_confidence = "Unknown"

    score = calculate_score(
        evidence_level=evidence_level,
        dosage_relevance=dosage_relevance,
        regulatory_evidence=regulatory_evidence,
        safety_confidence=safety_confidence,
        commercial_confidence=commercial_confidence,
    )

    record["Evidence_Type"] = evidence_type
    record["Evidence_Level"] = evidence_level
    record["Dosage_Form_Relevance"] = dosage_relevance
    record["Study_Model"] = study_model
    record["Regulatory_Evidence"] = regulatory_evidence
    record["Safety_Confidence"] = safety_confidence
    record["Commercial_Confidence"] = commercial_confidence
    record["Extracted_Indication"] = record.get("Target_Indication", "")
    record["Extracted_Dosage_Form"] = record.get("Dosage_Form", "")
    record["Evidence_Score"] = score

    return record


def calculate_score(
    evidence_level,
    dosage_relevance,
    regulatory_evidence,
    safety_confidence,
    commercial_confidence,
):
    score = 0

    score += {
        "Very High": 40,
        "High": 35,
        "Moderate": 25,
        "Low": 15,
        "Very Low": 8,
        "Traditional": 10,
        "Unknown": 0,
    }.get(evidence_level, 0)

    score += {
        "Direct": 25,
        "Indirect": 10,
        "Unknown": 0,
    }.get(dosage_relevance, 0)

    if regulatory_evidence != "None":
        score += 20

    score += {
        "High": 10,
        "Moderate": 6,
        "Low": 2,
        "Unknown": 0,
    }.get(safety_confidence, 0)

    score += {
        "High": 5,
        "Moderate": 3,
        "Low": 1,
        "Unknown": 0,
    }.get(commercial_confidence, 0)

    return min(score, 100)
