from pubmed_pipeline import collect_pubmed_evidence
from clinicaltrials_pipeline import collect_clinical_trials_evidence
from regulatory_pipeline import collect_regulatory_evidence


def collect_all_evidence(
    scientific_name,
    indication,
    dosage_form,
    market="European Union",
):
    all_records = []

    print("Collecting PubMed...")
    try:
        all_records.extend(
            collect_pubmed_evidence(
                scientific_name=scientific_name,
                indication=indication,
                dosage_form=dosage_form,
                market=market,
                save=True,
            )
        )
    except Exception as e:
        print("PubMed:", e)

    print("Collecting ClinicalTrials...")
    try:
        all_records.extend(
            collect_clinical_trials_evidence(
                scientific_name=scientific_name,
                indication=indication,
                dosage_form=dosage_form,
                market=market,
                save=True,
            )
        )
    except Exception as e:
        print("ClinicalTrials:", e)

    print("Collecting Regulatory...")
    try:
        all_records.extend(
            collect_regulatory_evidence(
                scientific_name=scientific_name,
                indication=indication,
                dosage_form=dosage_form,
                market=market,
                save=True,
            )
        )
    except Exception as e:
        print("Regulatory:", e)

    return all_records
