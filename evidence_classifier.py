"""
Evidence Classification Engine
Botanical Product Intelligence Platform

This module classifies the strength of scientific evidence
independently from the data source (PubMed, EMA, WHO, ESCOP,
ClinicalTrials, PDF, etc.).
"""


def classify_evidence(record):

    evidence_type = classify_evidence_type(record)

    evidence_level = classify_evidence_level(evidence_type)

    dosage_relevance = classify_dosage_form_relevance(record)

    regulatory = classify_regulatory_support(record)

    safety = classify_safety(record)

    commercial = classify_commercial(record)

    score = calculate_evidence_score(
        evidence_level=evidence_level,
        dosage_relevance=dosage_relevance,
        regulatory=regulatory,
        safety=safety,
        commercial=commercial,
    )

    record["Evidence_Type"] = evidence_type
    record["Evidence_Level"] = evidence_level
    record["Dosage_Form_Relevance"] = dosage_relevance
    record["Regulatory_Evidence"] = regulatory
    record["Safety_Confidence"] = safety
    record["Commercial_Confidence"] = commercial
    record["Evidence_Score"] = score

    return record


# -------------------------------------------------------
# Evidence Type
# -------------------------------------------------------

def classify_evidence_type(record):

    text = (
        str(record.get("Notes", "")) + " " +
        str(record.get("Source_Title", ""))
    ).lower()

    if "meta-analysis" in text or "meta analysis" in text:
        return "Meta-analysis"

    if "systematic review" in text:
        return "Systematic Review"

    if "randomized" in text or "randomised" in text:
        return "Randomized Controlled Trial"

    if "clinical trial" in text:
        return "Clinical Trial"

    if "cohort" in text:
        return "Cohort Study"

    if "case report" in text:
        return "Case Report"

    if "animal" in text or "rat" in text or "mouse" in text:
        return "Animal Study"

    if "in vitro" in text:
        return "In Vitro"

    if "traditional use" in text:
        return "Traditional Use"

    return "Unknown"


# -------------------------------------------------------
# Evidence Level
# -------------------------------------------------------

def classify_evidence_level(evidence_type):

    table = {

        "Meta-analysis": "Very High",

        "Systematic Review": "High",

        "Randomized Controlled Trial": "High",

        "Clinical Trial": "Moderate",

        "Cohort Study": "Moderate",

        "Case Report": "Low",

        "Animal Study": "Very Low",

        "In Vitro": "Very Low",

        "Traditional Use": "Traditional",

        "Unknown": "Unknown"

    }

    return table.get(evidence_type, "Unknown")


# -------------------------------------------------------
# Dosage Form Relevance
# -------------------------------------------------------

def classify_dosage_form_relevance(record):

    evidence = str(
        record.get(
            "Dosage_Form_Evidence",
            record.get("Infusion_Evidence", "")
        )
    ).lower()

    if evidence == "direct":
        return "Direct"

    if evidence == "indirect":
        return "Indirect"

    return "Unknown"


# -------------------------------------------------------
# Regulatory
# -------------------------------------------------------

def classify_regulatory_support(record):

    agencies = []

    if str(record.get("EMA_Status", "")).lower() == "yes":
        agencies.append("EMA")

    if str(record.get("WHO_Status", "")).lower() == "yes":
        agencies.append("WHO")

    if str(record.get("ESCOP_Status", "")).lower() == "yes":
        agencies.append("ESCOP")

    if len(agencies) == 0:
        return "None"

    return ", ".join(agencies)


# -------------------------------------------------------
# Safety
# -------------------------------------------------------

def classify_safety(record):

    safety = str(record.get("Safety_Level", "")).lower()

    if safety in ["good", "high"]:
        return "High"

    if safety in ["acceptable", "moderate"]:
        return "Moderate"

    if safety in ["caution", "low"]:
        return "Low"

    return "Unknown"


# -------------------------------------------------------
# Commercial
# -------------------------------------------------------

def classify_commercial(record):

    commercial = str(record.get("Commercial_Level", "")).lower()

    if commercial in ["high", "strong"]:
        return "High"

    if commercial in ["medium", "moderate"]:
        return "Moderate"

    if commercial in ["low"]:
        return "Low"

    return "Unknown"


# -------------------------------------------------------
# Evidence Score
# -------------------------------------------------------

def calculate_evidence_score(
        evidence_level,
        dosage_relevance,
        regulatory,
        safety,
        commercial):

    score = 0

    evidence_points = {

        "Very High": 40,

        "High": 35,

        "Moderate": 25,

        "Low": 15,

        "Very Low": 8,

        "Traditional": 5,

        "Unknown": 0

    }

    score += evidence_points.get(evidence_level, 0)

    if dosage_relevance == "Direct":
        score += 20

    elif dosage_relevance == "Indirect":
        score += 10

    if regulatory != "None":
        score += 20

    safety_points = {

        "High": 10,

        "Moderate": 7,

        "Low": 3,

        "Unknown": 0

    }

    score += safety_points.get(safety, 0)

    commercial_points = {

        "High": 10,

        "Moderate": 6,

        "Low": 2,

        "Unknown": 0

    }

    score += commercial_points.get(commercial, 0)

    return min(score, 100)
