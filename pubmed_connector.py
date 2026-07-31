import os
import xml.etree.ElementTree as ET
from typing import Dict, List

import requests


NCBI_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
DEFAULT_TIMEOUT = float(os.getenv("PUBMED_TIMEOUT_SECONDS", "10"))
DEFAULT_EMAIL = os.getenv("NCBI_EMAIL", "hamidbabaeiulg@gmail.com")
API_KEY = os.getenv("NCBI_API_KEY", "").strip()


def _params(**kwargs):
    params = {"email": DEFAULT_EMAIL, **kwargs}
    if API_KEY:
        params["api_key"] = API_KEY
    return params


def search_pubmed(query: str, max_results: int = 20, timeout: float = DEFAULT_TIMEOUT) -> List[str]:
    response = requests.get(
        f"{NCBI_BASE}/esearch.fcgi",
        params=_params(
            db="pubmed",
            term=query,
            retmax=max(0, int(max_results)),
            sort="relevance",
            retmode="json",
        ),
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json().get("esearchresult", {}).get("idlist", [])


def _node_text(node) -> str:
    if node is None:
        return ""
    return "".join(node.itertext()).strip()


def _parse_pubmed_xml(xml_text: str) -> List[Dict]:
    root = ET.fromstring(xml_text)
    articles: List[Dict] = []

    for pubmed_article in root.findall(".//PubmedArticle"):
        citation = pubmed_article.find("MedlineCitation")
        if citation is None:
            continue
        pmid = _node_text(citation.find("PMID"))
        article = citation.find("Article")
        if article is None:
            continue

        title = _node_text(article.find("ArticleTitle"))
        abstract_parts = [
            _node_text(node)
            for node in article.findall("./Abstract/AbstractText")
            if _node_text(node)
        ]
        abstract = " ".join(abstract_parts)
        journal = _node_text(article.find("./Journal/Title"))

        articles.append({
            "PMID": pmid,
            "Title": title,
            "Abstract": abstract,
            "Journal": journal,
            "Source_Type": "PubMed",
            "Source_Organization": "NCBI PubMed",
            "Source_URL": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
            "Raw_Text": f"{title}\n\n{abstract}".strip(),
        })

    return articles


def fetch_pubmed_articles(pmids: List[str], timeout: float = DEFAULT_TIMEOUT) -> List[Dict]:
    ids = [str(pmid).strip() for pmid in pmids if str(pmid).strip()]
    if not ids:
        return []

    response = requests.get(
        f"{NCBI_BASE}/efetch.fcgi",
        params=_params(
            db="pubmed",
            id=",".join(ids),
            rettype="abstract",
            retmode="xml",
        ),
        timeout=timeout,
    )
    response.raise_for_status()
    return _parse_pubmed_xml(response.text)


def fetch_pubmed_article(pmid: str, timeout: float = DEFAULT_TIMEOUT) -> Dict:
    articles = fetch_pubmed_articles([pmid], timeout=timeout)
    if not articles:
        raise ValueError(f"No PubMed article returned for PMID {pmid}")
    return articles[0]


def search_and_fetch_pubmed(
    query: str,
    max_results: int = 10,
    timeout: float = DEFAULT_TIMEOUT,
) -> List[Dict]:
    """Search PubMed and fetch matching abstracts in one bounded batch.

    The previous Biopython implementation performed one unbounded network call
    per PMID. A discovery pass could therefore block Streamlit for many
    minutes. This implementation uses two HTTP calls total and applies an
    explicit timeout to both.
    """
    pmids = search_pubmed(query, max_results=max_results, timeout=timeout)
    return fetch_pubmed_articles(pmids, timeout=timeout)
