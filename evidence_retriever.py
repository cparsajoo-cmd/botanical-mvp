import pandas as pd


def normalize_text(value):
    if pd.isna(value):
        return ""
    return str(value).strip().lower()


def text_contains_any(text, keywords):
    text = normalize_text(text)
    return any(keyword in text for keyword in keywords)


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

    # Exact indication match first
    if indication and "Target_Indication" in result.columns:
        exact = result[
            result["Target_Indication"].astype(str).str.lower()
            == str(indication).lower()
        ]

        if not exact.empty:
            result = exact

    # If no exact indication match, try semantic keyword retrieval
    if free_question and "Target_Indication" in result.columns:
        q = normalize_text(free_question)

        indication_keywords = {
            "
