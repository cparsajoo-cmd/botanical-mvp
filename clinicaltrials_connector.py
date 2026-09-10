import requests

from candidate_attribution import combined_record_text, verify_candidate_attribution


def search_clinicaltrials(
    scientific_name,
    indication,
    dosage_form="",
    market="European Union",
    max_results=5,
):
    # ROOT-CAUSE FIX: the previous unquoted, un-ANDed query
    # (f"{scientific_name} {indication}") is a loose free-text relevance
    # search across ClinicalTrials.gov's ENTIRE record (title, sponsor,
    # eligibility criteria, etc.), not scoped to studies that actually test
    # the candidate botanical. It could -- and in production did -- return
    # trials with no real relationship to either the plant or the queried
    # indication (e.g. a congenital-heart-disease education trial for a
    # Melissa officinalis + sleep query). Quoting each term keeps this an
    # AND-style match on the literal phrases, matching the scoping already
    # used by the project's other connectors (see europepmc_connector.py /
    # evidence_collector.py's PubMed query builder). This narrows recall
    # (a documented, accepted trade-off -- see the deliverables report) but
    # every remaining hit is far more likely to genuinely mention both
    # terms. It does NOT by itself guarantee relevance -- see the
    # candidate-attribution verification below, which is what actually
    # gates whether a returned record can count as plant-specific evidence.
    query = f'"{scientific_name}" AND "{indication}"'

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

        # ROOT-CAUSE FIX: verify candidate attribution from the trial's OWN
        # content (title/conditions/interventions -- never the search query
        # context) instead of assuming the returned study is about
        # scientific_name merely because it was returned for that query.
        # This is a general, species-agnostic check (see
        # candidate_attribution.py) that works for arbitrary botanicals,
        # indications, and future datasets. Fail-safe: when the trial's own
        # text does not establish attribution, the record is still saved
        # (so a reviewer can see it and so retrieval-coverage accounting
        # stays honest) but is explicitly marked unverified rather than
        # silently trusted as direct plant-specific evidence.
        attribution = verify_candidate_attribution(
            combined_record_text(title, " ".join(condition_list), " ".join(intervention_names)),
            scientific_name=scientific_name,
        )

        record = {
            "Scientific_Name": scientific_name,
            "Candidate_Attribution_Verified": attribution["verified"],
            "Candidate_Attribution_Basis": attribution["basis"],
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

            # Phase 2 (IMPLEMENTATION_PLAN.md) — the registry API response
            # already provides this identifier (used just above to build
            # Source_URL); persisting it instead of discarding it.
            "NCT_ID": nct_id,

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
