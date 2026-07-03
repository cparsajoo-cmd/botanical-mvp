from knowledge_retrieval_engine import get_candidate_plants, retrieve_knowledge
from evidence_collector import collect_pubmed_evidence
from evidence_database import load_evidence_database
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
    Works for any botanical product, indication and dosage form.
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

                if records:
                    collected.extend(records)

            except Exception as e:
                collected.append(
                    {
                        "plant": plant,
                        "error": str(e),
                    }
                )

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


# ------------------------------------------------------------------
# Compatibility wrapper for app.py
# ------------------------------------------------------------------

def run_research_engine(
    product_type,
    dosage_form,
    indication,
    target_market,
    evidence_strictness="Dosage-form specific only",
    max_results_per_plant=3,
    save=True,
):
    """
    Wrapper used by app.py.
    """

    result = run_research(
        product_type=product_type,
        dosage_form=dosage_form,
        indication=indication,
        target_market=target_market,
        evidence_strictness=evidence_strictness,
        max_pubmed_results_per_plant=max_results_per_plant,
        collect_online=save,
    )

    return {
        "candidate_plants": result.get("candidate_plants", []),
        "saved_records": result.get("collected_records", []),
        "errors": [
            r for r in result.get("collected_records", [])
            if isinstance(r, dict) and "error" in r
        ],
        "decision": result.get("decision"),
    }
