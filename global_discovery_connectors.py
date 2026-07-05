import requests
import time

REQUEST_TIMEOUT = 25
HEADERS = {"User-Agent": "Botanical-AI-Discovery/1.0"}


def _get(url, params=None):
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def make_record(
    record_type,
    scientific_name="",
    common_name="",
    family="",
    region="",
    compound="",
    target="",
    mechanism="",
    title="",
    url="",
    source="",
    evidence_type="",
):
    return {
        "record_type": record_type,
        "scientific_name": scientific_name or "",
        "common_name": common_name or "",
        "family": family or "",
        "region": region or "",
        "compound": compound or "",
        "target": target or "",
        "mechanism": mechanism or "",
        "title": title or "",
        "url": url or "",
        "source": source or "",
        "evidence_type": evidence_type or "",
    }


def search_kew(keyword, limit=30):
    data = _get(
        "https://powo.science.kew.org/api/2/search",
        {"q": keyword, "perPage": limit},
    )
    if not data:
        return []

    records = []
    for item in data.get("results", []):
        records.append(
            make_record(
                record_type="plant",
                scientific_name=item.get("name", ""),
                family=item.get("family", ""),
                region=item.get("distribution", ""),
                source="Kew POWO",
                title=item.get("name", ""),
                url="https://powo.science.kew.org/",
            )
        )
    return records


def search_gbif(keyword, limit=30):
    data = _get(
        "https://api.gbif.org/v1/species/search",
        {"q": keyword, "rank": "SPECIES", "limit": limit},
    )
    if not data:
        return []

    records = []
    for item in data.get("results", []):
        if item.get("kingdom") != "Plantae":
            continue

        records.append(
            make_record(
                record_type="plant",
                scientific_name=item.get("scientificName", ""),
                family=item.get("family", ""),
                source="GBIF",
                title=item.get("scientificName", ""),
                url=f"https://www.gbif.org/species/{item.get('key')}" if item.get("key") else "",
            )
        )
    return records


def search_pubchem(keyword, limit=10):
    data = _get(
        f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{keyword}/cids/JSON"
    )
    if not data:
        return []

    cids = data.get("IdentifierList", {}).get("CID", [])[:limit]
    records = []

    for cid in cids:
        records.append(
            make_record(
                record_type="compound",
                compound=keyword,
                source="PubChem",
                title=f"PubChem CID {cid}: {keyword}",
                url=f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}",
                evidence_type="chemical database",
            )
        )

    return records


def search_chembl(keyword, limit=10):
    data = _get(
        "https://www.ebi.ac.uk/chembl/api/data/molecule/search.json",
        {"q": keyword, "limit": limit},
    )
    if not data:
        return []

    records = []
    for item in data.get("molecules", []):
        chembl_id = item.get("molecule_chembl_id", "")
        name = item.get("pref_name") or keyword

        records.append(
            make_record(
                record_type="compound",
                compound=name,
                source="ChEMBL",
                title=f"ChEMBL molecule: {name}",
                url=f"https://www.ebi.ac.uk/chembl/compound_report_card/{chembl_id}/" if chembl_id else "",
                evidence_type="bioactivity database",
            )
        )
    return records


def search_europepmc(keyword, limit=20):
    data = _get(
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
        {"query": keyword, "format": "json", "pageSize": limit},
    )
    if not data:
        return []

    records = []
    for paper in data.get("resultList", {}).get("result", []):
        records.append(
            make_record(
                record_type="paper",
                title=paper.get("title", ""),
                source="Europe PMC",
                url=paper.get("doi", ""),
                evidence_type=paper.get("pubType", ""),
            )
        )
    return records


def search_openalex(keyword, limit=20):
    data = _get(
        "https://api.openalex.org/works",
        {"search": keyword, "per-page": limit},
    )
    if not data:
        return []

    records = []
    for item in data.get("results", []):
        records.append(
            make_record(
                record_type="paper",
                title=item.get("display_name", ""),
                source="OpenAlex",
                url=item.get("id", ""),
                evidence_type="scientific literature",
            )
        )
    return records


def search_crossref(keyword, limit=20):
    data = _get(
        "https://api.crossref.org/works",
        {"query": keyword, "rows": limit},
    )
    if not data:
        return []

    records = []
    for item in data.get("message", {}).get("items", []):
        title = ""
        if item.get("title"):
            title = item.get("title", [""])[0]

        records.append(
            make_record(
                record_type="paper",
                title=title,
                source="CrossRef",
                url=item.get("URL", ""),
                evidence_type=item.get("type", ""),
            )
        )
    return records


def search_clinicaltrials(keyword, limit=20):
    data = _get(
        "https://clinicaltrials.gov/api/v2/studies",
        {"query.term": keyword, "pageSize": limit},
    )
    if not data:
        return []

    records = []
    for study in data.get("studies", []):
        protocol = study.get("protocolSection", {})
        identification = protocol.get("identificationModule", {})
        status = protocol.get("statusModule", {})

        nct_id = identification.get("nctId", "")
        title = identification.get("briefTitle", "")

        records.append(
            make_record(
                record_type="clinical_trial",
                title=title,
                source="ClinicalTrials.gov",
                url=f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else "",
                evidence_type=status.get("overallStatus", ""),
            )
        )
    return records


DISCOVERY_SOURCES = [
    search_kew,
    search_gbif,
    search_pubchem,
    search_chembl,
    search_europepmc,
    search_openalex,
    search_crossref,
    search_clinicaltrials,
]


def discover_records(keyword):
    all_records = []

    for source in DISCOVERY_SOURCES:
        try:
            records = source(keyword)
            all_records.extend(records)
            time.sleep(0.2)
        except Exception:
            continue

    return deduplicate_records(all_records)


def deduplicate_records(records):
    unique = {}

    for r in records:
        key = "|".join([
            r.get("record_type", ""),
            r.get("scientific_name", "").lower(),
            r.get("compound", "").lower(),
            r.get("title", "").lower(),
            r.get("source", ""),
        ])

        if key not in unique:
            unique[key] = r

    return list(unique.values())
