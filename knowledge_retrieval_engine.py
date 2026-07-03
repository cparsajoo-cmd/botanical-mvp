import pandas as pd


CANDIDATE_KNOWLEDGE_MAP = {
    "Sleep and relaxation": [
        "Melissa officinalis",
        "Valeriana officinalis",
        "Passiflora incarnata",
        "Matricaria chamomilla",
        "Lavandula angustifolia",
        "Humulus lupulus",
        "Tilia cordata",
    ],
    "Constipation": [
        "Plantago ovata",
        "Linum usitatissimum",
        "Senna alexandrina",
        "Rhamnus frangula",
        "Rheum palmatum",
    ],
    "Cough": [
        "Thymus vulgaris",
        "Althaea officinalis",
        "Plantago lanceolata",
        "Hedera helix",
        "Primula veris",
    ],
    "Digestive comfort": [
        "Mentha piperita",
        "Foeniculum vulgare",
        "Matricaria chamomilla",
        "Carum carvi",
        "Zingiber officinale",
    ],
    "Anxiety": [
        "Passiflora incarnata",
        "Melissa officinalis",
        "Valeriana officinalis",
        "Lavandula angustifolia",
    ],
    "Skin inflammation": [
        "Calendula officinalis",
        "Matricaria chamomilla",
        "Aloe vera",
        "Hamamelis virginiana",
    ],
    "Dry mouth": [
        "Althaea officinalis",
        "Malva sylvestris",
        "Linum usitatissimum",
    ],
    "Allergic rhinitis": [
        "Petasites hybridus",
        "Urtica dioica",
        "Nigella sativa",
    ],
    "IBS": [
        "Mentha piperita",
        "Curcuma longa",
        "Foeniculum vulgare",
        "Matricaria chamomilla",
    ],
    "Wound healing": [
        "Calendula officinalis",
        "Aloe vera",
        "Centella asiatica",
        "Hypericum perforatum",
    ],
}


def _clean(value):
    if pd.isna(value):
        return ""
    return str(value).strip().lower()


def _safe_filter(df, column, value):
    if column not in df.columns:
        return df

    return df[
        df[column].astype(str).str.strip().str.lower()
        == str(value).strip().lower()
    ]


def get_candidate_plants(indication):
    return CANDIDATE_KNOWLEDGE_MAP.get(indication, [])


def retrieve_knowledge(
    df,
    product_type,
    dosage_form,
    indication,
    market,
    evidence_strictness="Dosage-form specific only",
):
    """
    Knowledge Retrieval Engine v1

    Purpose:
    1. Understand the product-development question.
    2. Identify expected candidate plants for the indication.
    3. Retrieve matching evidence records from the database.
    4. Return only records relevant to the selected project.

    Important:
    This engine does not yet search live EMA/WHO/PubMed sources.
    It uses the current structured evidence database plus a candidate plant map.
    """

    result = df.copy()

    # Basic filters
    result = _safe_filter(result, "Product_Type", product_type)
    result = _safe_filter(result, "Target_Indication", indication)
    result = _safe_filter(result, "Target_Market", market)

    # Candidate plant knowledge layer
    candidate_plants = get_candidate_plants(indication)

    if candidate_plants and "Scientific_Name" in result.columns:
        candidate_lower = [p.lower() for p in candidate_plants]

        candidate_records = result[
            result["Scientific_Name"]
            .astype(str)
            .str.lower()
            .isin(candidate_lower)
        ]

        if not candidate_records.empty:
            result = candidate_records

    # Dosage form handling
    if evidence_strictness == "Dosage-form specific only":
        result = _safe_filter(result, "Dosage_Form", dosage_form)

    elif evidence_strictness == "Regulatory-first":
        if "Dosage_Form" in result.columns:
            same_form = _safe_filter(result, "Dosage_Form", dosage_form)
            if not same_form.empty:
                result = same_form

        regulatory_cols = [
            col for col in ["EMA_Status", "WHO_Status", "ESCOP_Status"]
            if col in result.columns
        ]

        if regulatory_cols:
            mask = False
            for col in regulatory_cols:
                mask = mask | result[col].astype(str).str.lower().isin(
                    [
                        "yes",
                        "positive",
                        "supported",
                        "traditional use",
                        "well-established use",
                    ]
                )
            result = result[mask]

    elif evidence_strictness == "Clinical-first":
        if "Clinical_Level" in result.columns:
            clinical_records = result[
                result["Clinical_Level"].astype(str).str.lower().isin(
                    ["strong", "moderate"]
                )
            ]

            if not clinical_records.empty:
                result = clinical_records

    elif evidence_strictness == "Flexible":
        pass

    return result


def explain_retrieval(indication):
    candidates = get_candidate_plants(indication)

    if not candidates:
        return "No candidate plant map is currently defined for this indication."

    return (
        "Expected candidate plants for this indication: "
        + ", ".join(candidates)
    )
