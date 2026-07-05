import requests

from plant_compound_database import save_plant_compound_record


TIMEOUT = 20


def _safe_get(url, params=None):
    try:
        r = requests.get(url, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def _save_compound(
    scientific_name,
    compound_name,
    source,
    reference_url="",
    compound_class="",
    plant_part="",
    extraction_method="",
    target="",
    mechanism="",
    indication="",
    dosage_form="",
    market="",
    confidence_score=60,
):
    if not compound_name:
        return None

    record = {
        "scientific_name": scientific_name,
        "common_name": "",
        "compound_name": compound_name,
        "compound_class": compound_class,
        "plant_part": plant_part,
        "concentration": "",
        "unit": "",
        "extraction_method": extraction_method,
        "solvent": "",
        "yield_percent": "",
        "target": target,
        "mechanism": mechanism,
        "bioavailability": "",
        "toxicity": "",
        "safety_note": "",
        "indication": indication,
        "dosage_form": dosage_form,
        "market": market,
        "evidence_level": "Database-derived",
        "confidence_score": confidence_score,
        "reference_title": f"{source} compound record for {compound_name}",
        "reference_url": reference_url,
        "source": source,
        "source_year": "",
    }

    try:
        return save_plant_compound_record(record)
    except Exception:
        return None


def search_pubchem_compounds(scientific_name, indication="", dosage_form="", market="", max_results=10):
    records = []

    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{scientific_name}/cids/JSON"
    data = _safe_get(url)

    cids = []
    if data:
        cids = data.get("IdentifierList", {}).get("CID", [])[:max_results]

    for cid in cids:
        summary_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON"
        summary = _safe_get(summary_url)

        compound_name = ""
        if summary:
            compound_name = summary.get("Record", {}).get("RecordTitle", "")

        if compound_name:
            _save_compound(
                scientific_name=scientific_name,
                compound_name=compound_name,
                source="PubChem",
                reference_url=f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}",
                indication=indication,
                dosage_form=dosage_form,
                market=market,
                confidence_score=65,
            )

            records.append(compound_name)

    return records


def search_chebi_compounds(scientific_name, indication="", dosage_form="", market="", max_results=10):
    records = []

    url = "https://www.ebi.ac.uk/ols4/api/search"
    params = {
        "q": scientific_name,
        "ontology": "chebi",
        "rows": max_results,
    }

    data = _safe_get(url, params=params)

    docs = []
    if data:
        docs = data.get("response", {}).get("docs", [])

    for d in docs:
        label = d.get("label", "")
        iri = d.get("iri", "")

        if label:
            _save_compound(
                scientific_name=scientific_name,
                compound_name=label,
                source="ChEBI",
                reference_url=iri,
                compound_class="Chemical ontology record",
                indication=indication,
                dosage_form=dosage_form,
                market=market,
                confidence_score=60,
            )

            records.append(label)

    return records


def search_chembl_compounds(scientific_name, indication="", dosage_form="", market="", max_results=10):
    records = []

    url = "https://www.ebi.ac.uk/chembl/api/data/molecule.json"
    params = {
        "molecule_synonyms__molecule_synonym__icontains": scientific_name,
        "limit": max_results,
    }

    data = _safe_get(url, params=params)

    molecules = []
    if data:
        molecules = data.get("molecules", [])

    for m in molecules:
        compound_name = m.get("pref_name") or ""
        chembl_id = m.get("molecule_chembl_id", "")

        if compound_name:
            _save_compound(
                scientific_name=scientific_name,
                compound_name=compound_name,
                source="ChEMBL",
                reference_url=f"https://www.ebi.ac.uk/chembl/compound_report_card/{chembl_id}/" if chembl_id else "",
                compound_class="Bioactivity database molecule",
                indication=indication,
                dosage_form=dosage_form,
                market=market,
                confidence_score=70,
            )

            records.append(compound_name)

    return records


def collect_compounds_from_all_sources(
    scientific_name,
    indication="",
    dosage_form="",
    market="",
    max_results_per_source=10,
):
    all_compounds = []
    errors = []

    sources = [
        ("PubChem", search_pubchem_compounds),
        ("ChEBI", search_chebi_compounds),
        ("ChEMBL", search_chembl_compounds),
    ]

    for source_name, fn in sources:
        try:
            compounds = fn(
                scientific_name=scientific_name,
                indication=indication,
                dosage_form=dosage_form,
                market=market,
                max_results=max_results_per_source,
            )
            all_compounds.extend(compounds)
        except Exception as e:
            errors.append({
                "source": source_name,
                "plant": scientific_name,
                "error": str(e),
            })

    unique_compounds = sorted(set([c for c in all_compounds if c]))

    return {
        "scientific_name": scientific_name,
        "compound_count": len(unique_compounds),
        "compounds": unique_compounds,
        "errors": errors,
      }
