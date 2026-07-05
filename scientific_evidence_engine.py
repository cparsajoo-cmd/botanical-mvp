import requests
import re
from urllib.parse import quote_plus


TIMEOUT = 25


TRUST_WEIGHTS = {
    "ClinicalTrials.gov": 95,
    "PubMed": 95,
    "Europe PMC": 90,
    "ChEMBL": 85,
    "PubChem": 85,
    "ChEBI": 80,
    "OpenAlex": 75,
    "CrossRef": 70,
    "Regulatory Search": 80,
}


def safe_get_json(url, params=None):
    try:
        r = requests.get(url, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e), "url": url, "params": params}


def clean_text(x):
    if x is None:
        return ""
    return str(x).replace("\n", " ").strip()


def score_text_evidence(text):
    text = clean_text(text).lower()
    score = 0
    flags = []

    if "meta-analysis" in text or "meta analysis" in text:
        score += 35
        flags.append("Meta-analysis")

    if "systematic review" in text:
        score += 30
        flags.append("Systematic review")

    if "randomized" in text or "randomised" in text or "rct" in text:
        score += 30
        flags.append("Randomized clinical trial")

    if "clinical trial" in text or "human" in text or "patients" in text:
        score += 25
        flags.append("Human evidence")

    if "animal" in text or "rat" in text or "mouse" in text or "mice" in text:
        score += 10
        flags.append("Animal evidence")

    if "in vitro" in text or "cell" in text:
        score += 5
        flags.append("In vitro evidence")

    if "safety" in text or "adverse" in text or "tolerability" in text:
        score += 10
        flags.append("Safety data")

    return min(score, 100), flags


def source_record(source, title, url, abstract="", year="", extra=None):
    text = f"{title} {abstract}"
    evidence_score, flags = score_text_evidence(text)

    trust = TRUST_WEIGHTS.get(source, 60)

    final_score = round((evidence_score * 0.7) + (trust * 0.3), 1)

    return {
        "source": source,
        "title": clean_text(title),
        "url": clean_text(url),
        "abstract": clean_text(abstract),
        "year": clean_text(year),
        "trust_score": trust,
        "evidence_score": evidence_score,
        "final_source_score": final_score,
        "evidence_flags": ", ".join(flags),
        "extra": extra or {},
    }


def search_europe_pmc(plant, indication, max_results=8):
    query = f'"{plant}" AND "{indication}"'
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {
        "query": query,
        "format": "json",
        "pageSize": max_results,
    }

    data = safe_get_json(url, params=params)
    results = []

    for item in data.get("resultList", {}).get("result", []):
        pmid = item.get("pmid", "")
        doi = item.get("doi", "")
        link = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else f"https://doi.org/{doi}" if doi else ""
        results.append(
            source_record(
                "Europe PMC",
                item.get("title", ""),
                link,
                item.get("abstractText", ""),
                item.get("pubYear", ""),
                {"pmid": pmid, "doi": doi, "journal": item.get("journalTitle", "")},
            )
        )

    return results


def search_pubmed(plant, indication, max_results=8):
    query = f'{plant} {indication}'
    esearch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"

    search_data = safe_get_json(
        esearch_url,
        params={
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": max_results,
        },
    )

    ids = search_data.get("esearchresult", {}).get("idlist", [])
    if not ids:
        return []

    summary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    summary_data = safe_get_json(
        summary_url,
        params={
            "db": "pubmed",
            "id": ",".join(ids),
            "retmode": "json",
        },
    )

    results = []
    for pmid in ids:
        item = summary_data.get("result", {}).get(pmid, {})
        title = item.get("title", "")
        year = str(item.get("pubdate", ""))[:4]
        results.append(
            source_record(
                "PubMed",
                title,
                f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "",
                year,
                {"pmid": pmid, "journal": item.get("fulljournalname", "")},
            )
        )

    return results


def search_clinical_trials(plant, indication, max_results=8):
    query = f"{plant} {indication}"
    url = "https://clinicaltrials.gov/api/v2/studies"
    params = {
        "query.term": query,
        "pageSize": max_results,
        "format": "json",
    }

    data = safe_get_json(url, params=params)
    results = []

    for study in data.get("studies", []):
        protocol = study.get("protocolSection", {})
        ident = protocol.get("identificationModule", {})
        design = protocol.get("designModule", {})
        status = protocol.get("statusModule", {})
        cond = protocol.get("conditionsModule", {})
        out = protocol.get("outcomesModule", {})

        nct = ident.get("nctId", "")
        title = ident.get("briefTitle", "")
        conditions = " ".join(cond.get("conditions", []))
        outcomes = " ".join([x.get("measure", "") for x in out.get("primaryOutcomes", [])])
        abstract = f"{conditions} {outcomes} {design.get('studyType', '')} {' '.join(design.get('phases', []))}"

        results.append(
            source_record(
                "ClinicalTrials.gov",
                title,
                f"https://clinicaltrials.gov/study/{nct}" if nct else "",
                abstract,
                status.get("startDateStruct", {}).get("date", "")[:4],
                {
                    "nct_id": nct,
                    "study_type": design.get("studyType", ""),
                    "enrollment": design.get("enrollmentInfo", {}).get("count", ""),
                    "status": status.get("overallStatus", ""),
                },
            )
        )

    return results


def search_pubchem_compounds(compound, max_results=1):
    cid_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{quote_plus(compound)}/cids/JSON"
    cid_data = safe_get_json(cid_url)

    cids = cid_data.get("IdentifierList", {}).get("CID", [])[:max_results]
    results = []

    for cid in cids:
        url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON"
        data = safe_get_json(url)
        title = data.get("Record", {}).get("RecordTitle", compound)

        results.append(
            source_record(
                "PubChem",
                title,
                f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}",
                f"PubChem compound record for {compound}",
                "",
                {"cid": cid},
            )
        )

    return results


def search_chembl(compound, max_results=5):
    url = "https://www.ebi.ac.uk/chembl/api/data/molecule.json"
    params = {
        "molecule_synonyms__molecule_synonym__icontains": compound,
        "limit": max_results,
    }

    data = safe_get_json(url, params=params)
    results = []

    for mol in data.get("molecules", []):
        name = mol.get("pref_name") or compound
        chembl_id = mol.get("molecule_chembl_id", "")

        results.append(
            source_record(
                "ChEMBL",
                f"ChEMBL molecule record: {name}",
                f"https://www.ebi.ac.uk/chembl/compound_report_card/{chembl_id}/" if chembl_id else "",
                f"Bioactivity and target database record for {name}",
                "",
                {"chembl_id": chembl_id},
            )
        )

    return results


def search_chebi(term, max_results=5):
    url = "https://www.ebi.ac.uk/ols4/api/search"
    params = {
        "q": term,
        "ontology": "chebi",
        "rows": max_results,
    }

    data = safe_get_json(url, params=params)
    results = []

    for doc in data.get("response", {}).get("docs", []):
        label = doc.get("label", term)
        iri = doc.get("iri", "")

        results.append(
            source_record(
                "ChEBI",
                f"ChEBI chemical ontology record: {label}",
                iri,
                f"Chemical ontology record related to {term}",
                "",
                {"iri": iri},
            )
        )

    return results


def search_openalex(plant, indication, max_results=8):
    query = f"{plant} {indication}"
    url = "https://api.openalex.org/works"
    params = {
        "search": query,
        "per-page": max_results,
    }

    data = safe_get_json(url, params=params)
    results = []

    for item in data.get("results", []):
        title = item.get("title", "")
        year = item.get("publication_year", "")
        open_url = item.get("id", "")

        results.append(
            source_record(
                "OpenAlex",
                title,
                open_url,
                "",
                year,
                {
                    "doi": item.get("doi", ""),
                    "cited_by_count": item.get("cited_by_count", 0),
                },
            )
        )

    return results


def search_crossref(plant, indication, max_results=8):
    query = f"{plant} {indication}"
    url = "https://api.crossref.org/works"
    params = {
        "query": query,
        "rows": max_results,
    }

    data = safe_get_json(url, params=params)
    results = []

    for item in data.get("message", {}).get("items", []):
        title = " ".join(item.get("title", []))
        doi = item.get("DOI", "")
        year = ""

        try:
            year = item.get("published-print", item.get("published-online", {})).get("date-parts", [[None]])[0][0]
        except Exception:
            year = ""

        results.append(
            source_record(
                "CrossRef",
                title,
                f"https://doi.org/{doi}" if doi else item.get("URL", ""),
                "",
                year,
                {"doi": doi, "publisher": item.get("publisher", "")},
            )
        )

    return results


def regulatory_search_urls(plant, indication, market="European Union"):
    queries = [
        f"{plant} EMA HMPC monograph",
        f"{plant} WHO monograph medicinal plant",
        f"{plant} ESCOP monograph",
        f"{plant} EFSA botanical safety",
        f"{plant} FDA label safety",
        f"{plant} Health Canada natural health product",
        f"{plant} TGA herbal medicine",
    ]

    records = []

    for q in queries:
        records.append(
            source_record(
                "Regulatory Search",
                q,
                f"https://www.google.com/search?q={quote_plus(q)}",
                f"Regulatory search query for {plant} and {market}",
                "",
                {"query": q, "market": market},
            )
        )

    return records


def aggregate_decision(records):
    if not records:
        return {
            "overall_evidence_score": 0,
            "clinical_score": 0,
            "chemistry_score": 0,
            "regulatory_score": 0,
            "decision_class": "No reliable evidence found",
            "decision_reason": "No records retrieved.",
        }

    df_scores = [r["final_source_score"] for r in records]
    overall = round(sum(df_scores) / len(df_scores), 1)

    clinical_sources = [r for r in records if r["source"] in ["PubMed", "Europe PMC", "ClinicalTrials.gov"]]
    chemistry_sources = [r for r in records if r["source"] in ["PubChem", "ChEMBL", "ChEBI"]]
    regulatory_sources = [r for r in records if r["source"] == "Regulatory Search"]

    clinical_score = round(sum(r["final_source_score"] for r in clinical_sources) / len(clinical_sources), 1) if clinical_sources else 0
    chemistry_score = round(sum(r["final_source_score"] for r in chemistry_sources) / len(chemistry_sources), 1) if chemistry_sources else 0
    regulatory_score = round(sum(r["final_source_score"] for r in regulatory_sources) / len(regulatory_sources), 1) if regulatory_sources else 0

    final = round(
        clinical_score * 0.45 +
        chemistry_score * 0.30 +
        regulatory_score * 0.25,
        1,
    )

    if final >= 80:
        decision_class = "High-priority development candidate"
    elif final >= 65:
        decision_class = "Promising R&D candidate"
    elif final >= 45:
        decision_class = "Early research candidate"
    else:
        decision_class = "Insufficient evidence / low priority"

    return {
        "overall_evidence_score": overall,
        "clinical_score": clinical_score,
        "chemistry_score": chemistry_score,
        "regulatory_score": regulatory_score,
        "final_scientific_score": final,
        "decision_class": decision_class,
        "decision_reason": (
            f"Clinical {clinical_score}/100, chemistry {chemistry_score}/100, "
            f"regulatory {regulatory_score}/100."
        ),
    }


def collect_scientific_evidence(
    plant,
    indication,
    compounds=None,
    market="European Union",
    max_results=8,
):
    compounds = compounds or []

    all_records = []

    all_records.extend(search_pubmed(plant, indication, max_results=max_results))
    all_records.extend(search_europe_pmc(plant, indication, max_results=max_results))
    all_records.extend(search_clinical_trials(plant, indication, max_results=max_results))
    all_records.extend(search_openalex(plant, indication, max_results=max_results))
    all_records.extend(search_crossref(plant, indication, max_results=max_results))

    for compound in compounds:
        all_records.extend(search_pubchem_compounds(compound))
        all_records.extend(search_chembl(compound))
        all_records.extend(search_chebi(compound))

    all_records.extend(regulatory_search_urls(plant, indication, market=market))

    decision = aggregate_decision(all_records)

    return {
        "plant": plant,
        "indication": indication,
        "market": market,
        "record_count": len(all_records),
        "records": all_records,
        "decision": decision,
  }
