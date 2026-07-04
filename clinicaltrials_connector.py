import requests


def search_clinicaltrials(
    scientific_name,
    indication,
    dosage_form="",
    market="European Union",
    max_results=5,
):
    query = f"{scientific_name} {indication}"

    url = "https://clinicaltrials.gov/api/v2/studies"

    params = {
        "query.term": query,
        "pageSize": max_results,
        "format": "json",
    }

    response = requests.get(url, params=params, timeout=20)
    response.raise_for_status()

    data = response.json()
    studies = data.get("studies", [])

    records = []

    for study in studies:
        protocol = study.get("protocolSection", {})
        identification = protocol.get("identificationModule", {})
        status = protocol.get("statusModule", {})
        design = protocol.get("designModule", {})
        conditions = protocol.get("conditionsModule", {})
        interventions = protocol.get("armsInterventionsModule", {})
        outcomes = protocol.get("outcomesModule", {})

        nct_id = identification.get("nctId", "")
        title = identification.get("briefTitle", "")
        phase_list = design.get("phases", [])
        study_type = design.get("studyType", "")
        enrollment = design.get("enrollmentInfo", {}).get("count", "")

        condition_list = conditions.get("conditions", [])

        intervention_names = []
        for intervention in interventions.get("interventions", []):
            name = intervention.get("name", "")
            if name:
                intervention_names.append(name)

        primary_outcomes = []
        for outcome in outcomes.get("primaryOutcomes", []):
            measure = outcome.get("measure", "")
            if measure:
                primary_outcomes.append(measure)

        raw_text = " ".join([
            title,
            " ".join(condition_list),
            " ".join(intervention_names),
            " ".join(primary_outcomes),
            study_type,
            " ".join(phase_list),
        ])

        record = {
            "Scientific_Name": scientific_name,
            "Common_Name": "",
            "Product_Type": "Herbal product",
            "Dosage_Form": dosage_form,
            "Target_Indication": indication,
            "Target_Market": market,

            "Source_Type": "ClinicalTrials.gov",
            "Source_Organization": "ClinicalTrials.gov",
            "Source_Title": title,
            "Source_URL": f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else "",
            "Source_Year": "",

            "Notes": raw_text,

            "Publication_Type": "Clinical Trial Registry",
            "Evidence_Type": "Clinical Trial Registry",
            "Study_Type": "Clinical Trial",
            "Study_Model": "Human",
            "Evidence_Level": "Moderate",

            "Clinical_Level": "Moderate",
            "Clinical_RCT_Count": 1 if "randomized" in raw_text.lower() else 0,
            "Meta_Level": "Not found",
            "Meta_Count": 0,

            "Detected_Dosage_Forms": dosage_form,
            "Detected_Indications": indication,
            "Dosage_Form_Relevance": "Unknown",

            "EMA_Status": "",
            "WHO_Status": "",
            "ESCOP_Status": "",

            "Safety_Level": "Unknown",
            "Safety_Signal": "",
            "Drug_Interaction_Level": "Unknown",
            "Commercial_Level": "Unknown",
            "Regulatory_Status": "",
            "Novel_Food_Status": "To verify",

            "Population": "",
            "Sample_Size": str(enrollment),
            "Comparator": "",
            "Primary_Outcome": "; ".join(primary_outcomes),
            "Result_Direction": "Unknown",
        }

        records.append(record)

    return records
