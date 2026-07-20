import requests


def search_chembl(scientific_name, indication, dosage_form="", market="European Union", max_results=5):
    url = "https://www.ebi.ac.uk/chembl/api/data/molecule.json"
    params = {
        "molecule_synonyms__molecule_synonym__icontains": scientific_name,
        "limit": max_results,
    }

    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()

    molecules = r.json().get("molecules", [])
    records = []

    for m in molecules:
        name = m.get("pref_name")
        chembl_id = m.get("molecule_chembl_id", "")

        # ChEMBL sometimes catalogs a crude/whole-plant extract as its
        # own "molecule" entry under a common name (e.g. a record whose
        # pref_name is literally "CHAMOMILE") rather than an isolated
        # chemical constituent. Blindly trusting `pref_name` here meant
        # the plant's own common name could get stored as if it were one
        # of its phytochemical compounds — for any plant whose ChEMBL
        # synonym search happens to surface this kind of record, not
        # just one. A genuine single chemical substance always has
        # structural data (SMILES/InChI) in ChEMBL; a whole-extract or
        # mixture entry does not — that's a reliable, generic way to
        # tell the two apart without hardcoding any plant or compound
        # name.
        has_structure = bool(m.get("molecule_structures"))

        if not name or not has_structure:
            continue

        records.append({
            "Scientific_Name": scientific_name,
            "Common_Name": "",
            "Product_Type": "Herbal product",
            "Dosage_Form": dosage_form,
            "Target_Indication": indication,
            "Target_Market": market,

            "Source_Type": "ChEMBL",
            "Source_Organization": "EMBL-EBI ChEMBL",
            "Source_Title": f"ChEMBL molecule record: {name}",
            "Source_URL": f"https://www.ebi.ac.uk/chembl/compound_report_card/{chembl_id}/" if chembl_id else "",
            "Source_Year": "",

            "Notes": f"ChEMBL chemical/target evidence for {scientific_name}. Molecule: {name}. ChEMBL ID: {chembl_id}",

            "Publication_Type": "Chemical and bioactivity database",
            "Evidence_Type": "Mechanism/Chemistry",
            "Study_Type": "Bioactivity database",
            "Study_Model": "Chemical/Biological target",
            "Evidence_Level": "Supporting",

            "EMA_Status": "",
            "WHO_Status": "",
            "ESCOP_Status": "",

            "Clinical_Level": "Not applicable",
            "Clinical_RCT_Count": 0,
            "Meta_Level": "Not applicable",
            "Meta_Count": 0,

            "Detected_Dosage_Forms": dosage_form,
            "Detected_Indications": indication,
            "Dosage_Form_Relevance": "Indirect",

            "Safety_Level": "To verify",
            "Safety_Signal": "",
            "Drug_Interaction_Level": "To verify",
            "Commercial_Level": "Unknown",
            "Regulatory_Status": "",
            "Novel_Food_Status": "To verify",

            "Population": "",
            "Sample_Size": "",
            "Comparator": "",
            "Primary_Outcome": "Chemical and mechanism support",
            "Result_Direction": "Supporting",
        })

    return records
