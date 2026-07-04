from knowledge_retrieval_engine import get_candidate_plants
from multi_source_collector import collect_multi_source_evidence
from evidence_database import load_evidence_database
from knowledge_retrieval_engine import retrieve_knowledge
from evidence_filtering_engine import apply_evidence_filters
from decision_engine import analyze_evidence


def run_research_engine(
    product_type,
    dosage_form,
    indication,
    target_market,
    evidence_strictness="Dosage-form specific only",
    max_results_per_plant=3,
    save=True,
):
    candidate_plants = get_candidate_plants(indication)

    all_saved_records = []
    all_errors = []

    for plant in candidate_plants:
        result = collect_multi_source_evidence(
            scientific_name=plant,
            indication=indication,
            dosage_form=dosage_form,
            market=target_market,
            max_pubmed_results=max_results_per_plant,
            max_clinicaltrials_results=3,
            save=save,
        )

        all_saved_records.extend(result.get("saved_records", []))
        all_errors.extend(result.get("errors", []))

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
        "saved_records": all_saved_records,
        "errors": all_errors,
        "decision": decision,
    }
