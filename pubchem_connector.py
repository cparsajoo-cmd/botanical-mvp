import requests

# --- ADMET/developability additions (2026-09-11) -----------------------
# The functions below are ADDITIVE only. They do not change search_pubchem()
# or any of its existing behavior/callers in any way. They exist to support
# admet_developability.py's molecular-descriptor-based absorption
# interpretation -- see that module's docstring for exactly how these
# descriptors are (and are not) used. Nothing here fetches ADMET
# predictions from PubChem; PubChem does not provide those. It provides
# raw computed physicochemical descriptors only.

_ADMET_PROPERTY_FIELDS = (
    "MolecularWeight",
    "XLogP",
    "TPSA",
    "HBondDonorCount",
    "HBondAcceptorCount",
    "RotatableBondCount",
)


def resolve_pubchem_cid(compound_name, timeout=20):
    """Resolve a compound name to its first PubChem CID.

    Returns None on any failure, timeout, or no match -- never raises.
    Uses the same name-lookup endpoint as search_pubchem(), but this is a
    separate function/request: search_pubchem()'s own behavior is
    unchanged.
    """
    query = str(compound_name or "").strip()
    if not query:
        return None

    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{query}/cids/JSON"
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        cids = r.json().get("IdentifierList", {}).get("CID", [])
        return cids[0] if cids else None
    except Exception:
        return None


def fetch_pubchem_properties_by_cid(cids, timeout=20):
    """Batch-fetch computed physicochemical descriptors for a list of
    PubChem CIDs in a SINGLE request (comma-separated CIDs) -- never one
    request per compound, per the platform's performance conventions.

    Returns {cid(int): {property_name: value, ...}}. A CID with no
    returned properties is simply absent from the result (never
    fabricated) -- callers must treat an absent CID the same as "no data".

    These are raw computed molecular descriptors (Lipinski/Veber-style
    physicochemical properties), NOT ADMET predictions. Any interpretation
    built on top of them must be clearly labeled as property-derived /
    computational -- see admet_developability.py.
    """
    clean_cids = sorted({int(c) for c in cids if c is not None and str(c).strip().isdigit()})
    if not clean_cids:
        return {}

    cid_list = ",".join(str(c) for c in clean_cids)
    props = ",".join(_ADMET_PROPERTY_FIELDS)
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid_list}/property/{props}/JSON"

    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        rows = r.json().get("PropertyTable", {}).get("Properties", [])
    except Exception:
        return {}

    result = {}
    for row in rows:
        cid = row.get("CID")
        if cid is None:
            continue
        try:
            cid = int(cid)
        except (TypeError, ValueError):
            continue
        result[cid] = {k: row.get(k) for k in _ADMET_PROPERTY_FIELDS if k in row}
    return result


def resolve_compound_properties(compound_names, cid_cache=None, timeout=20):
    """Resolve a list of compound names to physicochemical descriptors.

    Intended to be called ONCE per run/page render with the full
    de-duplicated compound set across every candidate plant (see
    admet_developability.attach_admet_developability()'s caller), never
    once per row/candidate:

      1. Each UNIQUE compound name is resolved to a CID (PubChem's name
         endpoint has no batch form, so this is one request per unique
         name -- memoized via ``cid_cache`` across calls in the same
         session/run if the caller supplies one, e.g. a dict backed by
         st.cache_data).
      2. ALL resulting CIDs' properties are then fetched in a single
         batched request via fetch_pubchem_properties_by_cid().

    Returns {normalized_compound_name (lowercase): {property_name: value}}.
    A compound with no resolvable CID or no returned properties is simply
    absent from the result -- callers must treat that as "no data", never
    infer favorable values.
    """
    cache = cid_cache if cid_cache is not None else {}
    name_to_cid = {}
    for raw_name in dict.fromkeys(str(n).strip() for n in (compound_names or []) if str(n).strip()):
        key = raw_name.lower()
        if key in cache:
            cid = cache[key]
        else:
            cid = resolve_pubchem_cid(raw_name, timeout=timeout)
            cache[key] = cid
        if cid:
            name_to_cid[raw_name] = cid

    if not name_to_cid:
        return {}

    props_by_cid = fetch_pubchem_properties_by_cid(name_to_cid.values(), timeout=timeout)

    result = {}
    for name, cid in name_to_cid.items():
        if cid in props_by_cid:
            result[name.lower()] = props_by_cid[cid]
    return result


def search_pubchem(scientific_name, indication, dosage_form="", market="European Union", max_results=5):
    query = scientific_name

    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{query}/cids/JSON"

    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        cids = r.json().get("IdentifierList", {}).get("CID", [])[:max_results]
    except Exception:
        cids = []

    records = []

    for cid in cids:
        summary_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON"

        try:
            s = requests.get(summary_url, timeout=20)
            s.raise_for_status()
            data = s.json().get("Record", {})
        except Exception:
            data = {}

        title = data.get("RecordTitle", f"PubChem compound {cid}")
        raw_text = f"PubChem compound related to {scientific_name}. CID: {cid}. Title: {title}"

        records.append({
            "Scientific_Name": scientific_name,
            "Common_Name": "",
            "Product_Type": "Herbal product",
            "Dosage_Form": dosage_form,
            "Target_Indication": indication,
            "Target_Market": market,

            "Source_Type": "PubChem",
            "Source_Organization": "NCBI PubChem",
            "Source_Title": title,
            "Source_URL": f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}",
            "Source_Year": "",

            "Notes": raw_text,

            "Publication_Type": "Chemical database",
            "Evidence_Type": "Chemical composition",
            "Study_Type": "Chemical database",
            "Study_Model": "Chemical",
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
            "Primary_Outcome": "Chemical identity support",
            "Result_Direction": "Supporting",
        })

    return records
