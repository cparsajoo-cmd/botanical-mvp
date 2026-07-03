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
        return pd.Data
