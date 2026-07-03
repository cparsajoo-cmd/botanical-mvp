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
    ],
    "Cough": [
        "Thymus vulgaris",
        "Althaea officinalis",
        "Plantago lanceolata",
        "Hedera helix",
    ],
    "Digestive comfort": [
        "Mentha piperita",
        "Foeniculum vulgare",
        "Zingiber officinale",
        "Matricaria chamomilla",
    ],
    "Skin inflammation": [
        "Calendula officinalis",
        "Aloe vera",
        "Matricaria chamomilla",
        "Hamamelis virginiana",
    ],
    "IBS": [
        "Mentha piperita",
        "Curcuma longa",
        "Foeniculum vulgare",
        "Matricaria chamomilla",
    ],
}


def get_candidate_plants(indication):
    return CANDIDATE_KNOWLEDGE_MAP.get(indication, [])


def _safe_col(df, col):
    if col not in df.columns:
        df[col] = ""
    return df


def _contains_value(series, value):
    return series.astype(str).str.strip().str.lower() == str(value).strip().lower()


def retrieve_knowledge(
    df,
    product_type,
    dosage_form,
    indication,
    market,
    evidence_strictness="Dosage-form specific only",
):
    """
    Retrieval should be tolerant.
    Online records are imperfectly extracted, so do not over-filter too early.
    """

    if df is None or df.empty:
        return pd.DataFrame()

    result = df.copy()

    needed_cols = [
        "Product_Type",
        "Dosage_Form",
        "Target_Indication",
        "Target_Market",
        "Scientific_Name",
    ]

    for col in needed_cols:
        result = _safe_col(result, col)

    # Product type filter: keep matching records, but do not discard empty product_type
    product_mask = (
        _contains_value(result["Product_Type"], product_type)
        | (result["Product_Type"].astype(str).str.strip() == "")
    )
    result = result[product_mask]

    # Indication filter: keep matching records, but do not discard empty indication
    indication_mask = (
        _contains_value(result["Target_Indication"], indication)
        | (result["Target_Indication"].astype(str).str.strip() == "")
    )
    result = result[indication_mask]

    # Market filter: keep matching records, EU records, or empty market
    market_mask = (
        _contains_value(result["Target_Market"], market)
        | _contains_value(result["Target_Market"], "European Union")
        | (result["Target_Market"].astype(str).str.strip() == "")
    )
    result = result[market_mask]

    # Candidate plant layer
    candidate_plants = get_candidate_plants(indication)

    if candidate_plants:
        candidate_lower = [p.lower() for p in candidate_plants]
        result = result[
            result["Scientific_Name"]
            .astype(str)
            .str.lower()
            .isin(candidate_lower)
        ]

    # Dosage form
    if evidence_strictness == "Dosage-form specific only":
        dosage_mask = (
            _contains_value(result["Dosage_Form"], dosage_form)
            | (result["Dosage_Form"].astype(str).str.strip() == "")
        )
        result = result[dosage_mask]

    elif evidence_strictness == "Clinical-first":
        if "Clinical_Level" in result.columns:
            clinical = result[
                result["Clinical_Level"]
                .astype(str)
                .str.lower()
                .isin(["strong", "moderate"])
            ]
            if not clinical.empty:
                result = clinical

    elif evidence_strictness == "Regulatory-first":
        # PubMed records may not have EMA/WHO/ESCOP.
        # Do not remove them if no regulatory records exist yet.
        regulatory_cols = [
            c for c in ["EMA_Status", "WHO_Status", "ESCOP_Status"]
            if c in result.columns
        ]

        if regulatory_cols:
            mask = False
            for col in regulatory_cols:
                mask = mask | result[col].astype(str).str.lower().isin(["yes", "supported"])

            regulatory_result = result[mask]
            if not regulatory_result.empty:
                result = regulatory_result

    return result.reset_index(drop=True)
