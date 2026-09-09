import pandas as pd

from commercial_evidence_import import normalize_commercial_evidence_import


def test_empty_and_none_input_returns_empty_with_no_rejections():
    df, rejected = normalize_commercial_evidence_import(None)
    assert df.empty
    assert rejected == []
    df, rejected = normalize_commercial_evidence_import(pd.DataFrame())
    assert df.empty
    assert rejected == []


def test_row_with_product_and_brand_is_accepted():
    raw = pd.DataFrame([{
        "Scientific_Name": "Withania somnifera",
        "Product_Name": "SleepWell Capsules",
        "Brand": "BrandCo",
    }])
    normalized, rejected = normalize_commercial_evidence_import(raw)
    assert len(normalized) == 1
    assert rejected == []
    assert normalized.loc[0, "Scientific_Name"] == "Withania somnifera"


def test_row_with_product_and_retailer_or_seller_is_accepted_and_renamed():
    raw = pd.DataFrame([{
        "Scientific_Name": "Withania somnifera",
        "Product_Name": "SleepWell Capsules",
        "Retailer_or_Seller": "Herbal Marketplace",
    }])
    normalized, rejected = normalize_commercial_evidence_import(raw)
    assert len(normalized) == 1
    assert rejected == []
    # Renamed to the column market_intelligence_engine.py actually reads.
    assert normalized.loc[0, "Retailer"] == "Herbal Marketplace"
    assert "Retailer_or_Seller" not in normalized.columns


def test_plant_column_alias_is_renamed_to_scientific_name():
    raw = pd.DataFrame([{
        "Plant": "Withania somnifera",
        "Product_Name": "SleepWell Capsules",
        "Brand": "BrandCo",
    }])
    normalized, rejected = normalize_commercial_evidence_import(raw)
    assert len(normalized) == 1
    assert normalized.loc[0, "Scientific_Name"] == "Withania somnifera"


def test_row_with_recognized_market_source_type_and_no_product_name_is_accepted():
    raw = pd.DataFrame([{
        "Scientific_Name": "Withania somnifera",
        "Market_Source_Type": "Marketplace",
    }])
    normalized, rejected = normalize_commercial_evidence_import(raw)
    assert len(normalized) == 1
    assert rejected == []


def test_row_missing_plant_name_is_rejected_with_reason():
    raw = pd.DataFrame([{
        "Product_Name": "SleepWell Capsules",
        "Brand": "BrandCo",
    }])
    normalized, rejected = normalize_commercial_evidence_import(raw)
    assert normalized.empty
    assert len(rejected) == 1
    assert "plant name" in rejected[0]["reason"].lower()


def test_row_with_product_name_but_no_brand_or_retailer_is_rejected():
    raw = pd.DataFrame([{
        "Scientific_Name": "Withania somnifera",
        "Product_Name": "SleepWell Capsules",
    }])
    normalized, rejected = normalize_commercial_evidence_import(raw)
    assert normalized.empty
    assert len(rejected) == 1
    assert "product identity" in rejected[0]["reason"].lower()


def test_row_with_unrecognized_market_source_type_and_no_product_identity_is_rejected():
    raw = pd.DataFrame([{
        "Scientific_Name": "Withania somnifera",
        "Market_Source_Type": "Some random text",
    }])
    normalized, rejected = normalize_commercial_evidence_import(raw)
    assert normalized.empty
    assert len(rejected) == 1


def test_mixed_valid_and_invalid_rows_are_partitioned_correctly():
    raw = pd.DataFrame([
        {"Scientific_Name": "Withania somnifera", "Product_Name": "A", "Brand": "X"},
        {"Product_Name": "B", "Brand": "Y"},  # missing plant name
        {"Scientific_Name": "Matricaria chamomilla", "Product_Name": "C"},  # no brand/retailer
        {"Scientific_Name": "Panax ginseng", "Market_Source_Type": "Official manufacturer"},
    ])
    normalized, rejected = normalize_commercial_evidence_import(raw)
    assert len(normalized) == 2
    assert len(rejected) == 2
    assert set(normalized["Scientific_Name"]) == {"Withania somnifera", "Panax ginseng"}


def test_source_url_or_id_is_renamed_to_source_url():
    raw = pd.DataFrame([{
        "Scientific_Name": "Withania somnifera",
        "Product_Name": "SleepWell Capsules",
        "Brand": "BrandCo",
        "Source_URL_or_ID": "https://example.test/product/123",
    }])
    normalized, rejected = normalize_commercial_evidence_import(raw)
    assert normalized.loc[0, "Source_URL"] == "https://example.test/product/123"


def test_optional_fields_are_not_required():
    """Section 11: 'Do NOT require every optional field.' -- Dosage_Form,
    Preparation, Country_Market, Indication, Retrieval_Timestamp are all
    absent here and the row must still be accepted.
    """
    raw = pd.DataFrame([{
        "Scientific_Name": "Withania somnifera",
        "Product_Name": "SleepWell Capsules",
        "Brand": "BrandCo",
    }])
    normalized, rejected = normalize_commercial_evidence_import(raw)
    assert len(normalized) == 1
    assert rejected == []
