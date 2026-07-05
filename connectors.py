import requests

PUBCHEM_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
CHEMBL_BASE = "https://www.ebi.ac.uk/chembl/api/data"
EUROPEPMC_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
CTGOV_BASE = "https://clinicaltrials.gov/api/v2/studies"


# ---------------------------------------------------------------
# PubChem
# ---------------------------------------------------------------
def get_pubchem_data(compound_name, timeout=8):
    try:
        cid_url = f"{PUBCHEM_BASE}/compound/name/{compound_name}/cids/JSON"
        r = requests.get(cid_url, timeout=timeout)
        r.raise_for_status()
        cids = r.json()["IdentifierList"]["CID"]
        if not cids:
            return {"error": "No PubChem CID found for this compound name"}
        cid = cids[0]

        prop_url = (
            f"{PUBCHEM_BASE}/compound/cid/{cid}/property/"
            "MolecularFormula,MolecularWeight,CanonicalSMILES,IUPACName/JSON"
        )
        r2 = requests.get(prop_url, timeout=timeout)
        r2.raise_for_status()
        props = r2.json()["PropertyTable"]["Properties"][0]

        return {
            "cid": cid,
            "molecular_formula": props.get("MolecularFormula"),
            "molecular_weight": props.get("MolecularWeight"),
            "canonical_smiles": props.get("CanonicalSMILES"),
            "iupac_name": props.get("IUPACName"),
            "source_url": f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}",
        }
    except requests.exceptions.RequestException as e:
        return {"error": f"Network/API error: {e}"}
    except (KeyError, IndexError, ValueError):
        return {"error": "Unexpected PubChem response format"}


# ---------------------------------------------------------------
# ChEMBL
# ---------------------------------------------------------------
def get_chembl_targets(compound_name, timeout=8):
    try:
        search_url = f"{CHEMBL_BASE}/molecule/search?q={compound_name}&format=json"
        r = requests.get(search_url, timeout=timeout)
        r.raise_for_status()
        molecules = r.json().get("molecules", [])
        if not molecules:
            return {"error": "No ChEMBL molecule match found"}
        chembl_id = molecules[0]["molecule_chembl_id"]

        mech_url = f"{CHEMBL_BASE}/mechanism.json?molecule_chembl_id={chembl_id}"
        r2 = requests.get(mech_url, timeout=timeout)
        r2.raise_for_status()
        mechanisms = r2.json().get("mechanisms", [])

        targets = [
            {
                "target_chembl_id": m.get("target_chembl_id"),
                "mechanism_of_action": m.get("mechanism_of_action"),
                "action_type": m.get("action_type"),
            }
            for m in mechanisms
        ]

        return {
            "chembl_id": chembl_id,
            "mechanisms": targets,
            "source_url": f"https://www.ebi.ac.uk/chembl/compound_report_card/{chembl_id}/",
        }
    except requests.exceptions.RequestException as e:
        return {"error": f"Network/API error: {e}"}
    except (KeyError, IndexError, ValueError):
        return {"error": "Unexpected ChEMBL response format"}


# ---------------------------------------------------------------
# Europe PMC (scientific articles)
# ---------------------------------------------------------------
def search_articles(plant_name, indication="", max_results=5, timeout=10):
    query = f'"{plant_name}"'
    if indication:
        query += f' AND "{indication}"'

    params = {
        "query": query,
        "format": "json",
        "pageSize": max_results,
        "resultType": "core",
    }

    try:
        r = requests.get(EUROPEPMC_BASE, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        results = data.get("resultList", {}).get("result", [])

        articles = []
        for item in results:
            articles.append({
                "title": item.get("title"),
                "authors": item.get("authorString"),
                "journal": item.get("journalTitle"),
                "year": item.get("pubYear"),
                "doi": item.get("doi"),
                "pmid": item.get("pmid"),
                "abstract": item.get("abstractText", "")[:500],
                "source_url": f"https://europepmc.org/article/MED/{item.get('pmid')}" if item.get("pmid") else None,
            })
        return {"count": data.get("hitCount", 0), "articles": articles}

    except requests.exceptions.RequestException as e:
        return {"error": f"Network/API error: {e}"}
    except (KeyError, ValueError):
        return {"error": "Unexpected Europe PMC response format"}


# ---------------------------------------------------------------
# ClinicalTrials.gov
# ---------------------------------------------------------------
def search_trials(plant_name, indication="", max_results=5, timeout=10):
    query = plant_name
    if indication:
        query += f" {indication}"

    params = {
        "query.term": query,
        "pageSize": max_results,
        "format": "json",
    }

    try:
        r = requests.get(CTGOV_BASE, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        studies = data.get("studies", [])

        trials = []
        for s in studies:
            protocol = s.get("protocolSection", {})
            identification = protocol.get("identificationModule", {})
            status_module = protocol.get("statusModule", {})
            design_module = protocol.get("designModule", {})
            conditions_module = protocol.get("conditionsModule", {})

            nct_id = identification.get("nctId")
            trials.append({
                "nct_id": nct_id,
                "title": identification.get("briefTitle"),
                "status": status_module.get("overallStatus"),
                "phase": design_module.get("phases", []),
                "conditions": conditions_module.get("conditions", []),
                "source_url": f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else None,
            })
        return {"count": len(trials), "trials": trials}

    except requests.exceptions.RequestException as e:
        return {"error": f"Network/API error: {e}"}
    except (KeyError, ValueError):
        return {"error": "Unexpected ClinicalTrials.gov response format"}
