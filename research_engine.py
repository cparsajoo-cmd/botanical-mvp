from knowledge_retrieval_engine import get_candidate_plants
from evidence_collector import collect_pubmed_evidence
from evidence_database import load_evidence_database
from knowledge_retrieval_engine import retrieve_knowledge
from evidence_filtering_engine import apply_evidence_filters
from decision_engine import analyze_evidence


def run_research(
    product_type,
    dosage_form,
    indication,
    target_market,
    evidence_strictness="Dosage-form specific only",
    max_pubmed_results_per_plant=3,
    collect_online=True,
):
    """
    General botanical product research engine.
    Not limited to infusion or sleep.
    """

    candidate_plants = get_candidate_plants(indication)

    collected = []

    if collect_online:
        for plant in candidate_plants:
            try:
                records = collect_pubmed_evidence(
                    scientific_name=plant,
                    indication=indication,
                    dosage_form=dosage_form,
                    market=target_market,
                    max_results=max_pubmed_results_per_plant,
                    save=True,
                )
                collected.extend(records)
            except Exception as e:
                collected.append({
                    "plant": plant,
                    "error": str(e),
                })

    df = load_evidence_database()

    retrieved = retrieve_knowledge(
        df=df,
        product_type=product_type,
        dosage_form=dosage_form,
        indication=indication,
        market=target_market,
        evidence_strictness=evidence_strictness,
    )

    filtered = apply_evidence_filters(
        df=retrieved,
        dosage_form=dosage_form,
        evidence_strictness=evidence_strictness,
    )

    decision = analyze_evidence(
        df=filtered,
        product_type=product_type,
        dosage_form=dosage_form,
        indication=indication,
        market=target_market,
        min_score=0,
    )

    return {
        "candidate_plants": candidate_plants,
        "collected_records": collected,
        "decision": decision,
    }
