import pandas as pd


def normalize_text(value):
    if pd.isna(value):
        return ""
    return str(value).strip().lower()


def retrieve_evidence(
    df,
    product_type=None,
    dosage_form=None,
    indication=None,
    market=None,
    free_question=None,
):
    result = df.copy()

    if product_type and "Product_Type" in result.columns:
        result = result[
            result["Product_Type"].astype(str).str.lower()
            == str(product_type).lower()
        ]

    if dosage_form and "Dosage_Form" in result.columns:
        result = result[
            result["Dosage_Form"].astype(str).str.lower()
            == str(dosage_form).lower()
        ]

    if market and "Target_Market" in result.columns:
        result = result[
            result["Target_Market"].astype(str).str.lower()
            == str(market).lower()
        ]

    if indication and "Target_Indication" in result.columns:
        exact = result[
            result["Target_Indication"].astype(str).str.lower()
            == str(indication).lower()
        ]
        if not exact.empty:
            result = exact

    if free_question and "Target_Indication" in result.columns:
        q = normalize_text(free_question)

        indication_keywords = {
            "Sleep and relaxation": [
                "sleep", "bedtime", "insomnia", "relaxation", "stress", "calm"
            ],
            "Constipation": [
                "constipation", "laxative", "bowel", "intestinal transit"
            ],
            "Cough": [
                "cough", "throat", "bronchial", "respiratory"
            ],
            "Digestive comfort": [
                "digestive", "digestion", "stomach", "bloating", "gas"
            ],
            "Anxiety": [
                "anxiety", "anxious", "nervous", "tension"
            ],
            "Skin": [
                "skin", "dermatitis", "eczema", "psoriasis", "topical"
            ],
        }

        matched_indications = []

        for ind, keywords in indication_keywords.items():
            if any(keyword in q for keyword in keywords):
                matched_indications.append(ind)

        if matched_indications:
            semantic = result[
                result["Target_Indication"].astype(str).isin(matched_indications)
            ]
            if not semantic.empty:
                result = semantic

    return result
