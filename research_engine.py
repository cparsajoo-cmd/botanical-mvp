from evidence_collector import collect_pubmed_evidence


FALLBACK_CANDIDATE_PLANTS = {
    "Sleep and relaxation": [
        "Melissa officinalis",
        "Valeriana officinalis",
        "Passiflora incarnata",
        "Lavandula angustifolia",
        "Humulus lupulus",
        "Matricaria chamomilla",
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


def get_candidate_plants_safe(indication):
    try:
        from knowledge_retrieval_engine import get_candidate_plants
        plants = get_candidate_plants(indication)
        if plants:
            return plants
    except Exception:
        pass

    return FALLBACK_CANDIDATE_PLANTS.get(indication, [])


def run_research_engine(
    product_type,
    dosage_form,
    indication,
    target_market,
    max_results_per_plant=3,
    save=True,
):
    candidate_plants = get_candidate_plants_safe(indication)

    output = {
        "product_type": product_type,
        "dosage_form": dosage_form,
        "indication": indication,
        "target_market": target_market,
        "candidate_plants": candidate_plants,
        "saved_records": [],
        "errors": [],
    }

    for plant in candidate_plants:
        try:
            records = collect_pubmed_evidence(
                scientific_name=plant,
                indication=indication,
                dosage_form=dosage_form,
                market=target_market,
                max_results=max_results_per_plant,
                save=save,
            )

            for r in records:
                output["saved_records"].append(
                    {
                        "plant": plant,
                        "row_id": r.get("row_id"),
                        "source": "PubMed",
                        "pmid": r.get("pmid"),
                        "title": r.get("title"),
                    }
                )

        except Exception as e:
            output["errors"].append(
                {
                    "plant": plant,
                    "error": str(e),
                }
            )

    return output
