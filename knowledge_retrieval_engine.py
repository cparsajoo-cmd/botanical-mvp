import pandas as pd

from global_plant_candidate_database import GLOBAL_PLANT_CANDIDATES
from therapeutic_area_registry import (
    get_candidate_hypotheses,
    get_related_concepts,
    lookup_therapeutic_area,
)


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


def _norm_indication(value):
    return " ".join(str(value or "").strip().lower().split())


def get_candidate_plants(indication):
    """Return discovery hypotheses for an indication without exact-string gating.

    The legacy map remains a backward-compatible seed, but unknown/free-text
    indications are resolved through the existing therapeutic-area registry and
    global plant candidate database. Related areas are used only as *search
    hypotheses* (never as evidence), which is already the contract of
    therapeutic_area_registry.py. This removes the previous six-indication
    exact-match blocker without adding per-holdout rules.
    """
    query = str(indication or "").strip()
    if not query:
        return []

    out = []
    seen = set()

    def add(name):
        key = _norm_indication(name)
        if name and key and key not in seen:
            seen.add(key)
            out.append(str(name).strip())

    # Preserve historical ordering for existing exact production inputs.
    for plant in CANDIDATE_KNOWLEDGE_MAP.get(query, []):
        add(plant)

    area = lookup_therapeutic_area(query)
    if area is None:
        return out

    allowed_concepts = {area.canonical_name}
    # One hop is deliberately bounded: broad enough for closely related search
    # hypotheses (e.g. stress/anxiety) but not an uncontrolled graph expansion.
    allowed_concepts.update(get_related_concepts(area.canonical_name, max_hops=1))

    for plant in get_candidate_hypotheses(area.canonical_name):
        add(plant)

    for record in GLOBAL_PLANT_CANDIDATES:
        indications = record.get("Indications", ()) or ()
        for candidate_indication in indications:
            candidate_area = lookup_therapeutic_area(candidate_indication)
            if candidate_area is not None and candidate_area.canonical_name in allowed_concepts:
                add(record.get("Scientific_Name", ""))
                break

    # Related concepts may themselves carry explicit hypothesis pools even when
    # the global plant table is sparse. They remain candidate hypotheses only.
    for concept in sorted(allowed_concepts - {area.canonical_name}):
        for plant in get_candidate_hypotheses(concept):
            add(plant)

    return out


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
