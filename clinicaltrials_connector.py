import requests

from candidate_attribution import verify_intervention_attribution


def _intervention_exposure_text(protocol, study_type):
    """Return text scoped ONLY to what was actually administered/assigned.

    REMAINING DEFECT 1 FIX: candidate attribution must be established from
    the intervention/exposure the study actually evaluated, never from
    title/condition/eligibility text where a botanical can appear purely as
    background, prior-treatment history, or a comparator/other-arm
    description. ClinicalTrials.gov already provides structured
    intervention fields -- use them, and nothing else, for this check.

    Interventional studies: armsInterventionsModule.interventions[] (name +
    description) is the actual administered/assigned intervention list.

    Observational studies: many still populate the same interventions
    list (representing the exposure); when they do not, fall back to each
    arm/cohort group's own description (armGroups[].description) as the
    best available structured exposure proxy. If neither is present, this
    returns "" so the caller fails closed rather than guessing from
    unrelated fields.
    """
    interventions_module = protocol.get("armsInterventionsModule", {})
    parts = []
    for intervention in interventions_module.get("interventions", []):
        name = intervention.get("name", "")
        description = intervention.get("description", "")
        if name or description:
            parts.append(f"{name} {description}".strip())

    if not parts and str(study_type or "").strip().upper() == "OBSERVATIONAL":
        for arm in interventions_module.get("armGroups", []):
            description = arm.get("description", "")
            label = arm.get("label", "")
            if description or label:
                parts.append(f"{label} {description}".strip())

    return " ".join(parts).strip()


def search_clinicaltrials(
    scientific_name,
    indication,
    dosage_form="",
    market="European Union",
    max_results=5,
):
    # ROOT-CAUSE FIX (Problem 1, original pass): the previous unquoted,
    # un-ANDed query (f"{scientific_name} {indication}") is a loose
    # free-text relevance search across ClinicalTrials.gov's ENTIRE record
    # (title, sponsor, eligibility criteria, etc.), not scoped to studies
    # that actually test the candidate botanical. It could -- and in
    # production did -- return trials with no real relationship to either
    # the plant or the queried indication (e.g. a congenital-heart-disease
    # education trial for a Melissa officinalis + sleep query). Quoting
    # each term keeps this an AND-style match on the literal phrases,
    # matching the scoping already used by the project's other connectors.
    # This narrows recall (a documented, accepted trade-off) but every
    # remaining hit is far more likely to genuinely mention both terms. It
    # does NOT by itself guarantee relevance -- see the intervention-
    # attribution verification below, which is what actually gates whether
    # a returned record can count as plant-specific evidence.
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

        # REMAINING DEFECT 1 FIX: verify attribution from the intervention/
        # exposure fields ONLY -- never title/condition/eligibility text,
        # where the candidate can appear without being what was actually
        # administered. See _intervention_exposure_text() above and
        # candidate_attribution.py's module docstring. When no
        # intervention/exposure text can be established at all (e.g. an
        # observational study with neither an interventions list nor arm
        # descriptions), this fails closed (verified False) rather than
        # falling back to any other field.
        exposure_text = _intervention_exposure_text(protocol, study_type)
        attribution = verify_intervention_attribution(
            exposure_text,
            scientific_name=scientific_name,
        )

        record = {
            "Scientific_Name": scientific_name,
            "Candidate_Attribution_Verified": attribution["verified"],
            "Candidate_Attribution_Basis": attribution["basis"],
            "Common_Name": "",
            "Product_Type": "Herbal product",
            "Dosage_Form": "",

            # REMAINING DEFECT 3 FIX: the requested/query indication and
            # dosage form must never be written into a field that
            # downstream code (evidence_normalization.py's
            # normalize_indication(), general_indication_relevance.py's
            # explicit-field-overlap match) interprets as a SOURCE-REPORTED
            # fact. Target_Indication/Detected_Indications now carry only
            # what the trial itself reports (its own condition list);
            # Requested_Target_Indication/Requested_Dosage_Form carry the
            # query context separately, mirroring the pattern already
            # established in evidence_collector.py's PubMed path. When the
            # trial reports no condition text, these stay empty rather than
            # being filled in from the query.
            "Requested_Target_Indication": indication,
            "Requested_Dosage_Form": dosage_form,
            "Target_Indication": "; ".join(condition_list),
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

            # Source-reported, not query-stamped (see the indication fix
            # above; the same principle applies here). ClinicalTrials.gov's
            # structured fields do not report a dosage form independently
            # of the intervention description, so this is left honestly
            # empty rather than echoing the requested dosage_form.
            "Detected_Dosage_Forms": "",
            "Detected_Indications": "; ".join(condition_list),
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
