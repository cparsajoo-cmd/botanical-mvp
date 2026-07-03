from Bio import Entrez


Entrez.email = "hamidbabaeiulg@gmail.com"


def search_pubmed(query, max_results=20):
    handle = Entrez.esearch(
        db="pubmed",
        term=query,
        retmax=max_results,
        sort="relevance"
    )
    record = Entrez.read(handle)
    return record.get("IdList", [])


def fetch_pubmed_article(pmid):
    handle = Entrez.efetch(
        db="pubmed",
        id=pmid,
        rettype="abstract",
        retmode="xml"
    )
    record = Entrez.read(handle)

    article = record["PubmedArticle"][0]
    citation = article["MedlineCitation"]
    article_data = citation["Article"]

    title = str(article_data.get("ArticleTitle", ""))

    abstract_parts = article_data.get("Abstract", {}).get("AbstractText", [])
    abstract = " ".join([str(x) for x in abstract_parts])

    journal = str(article_data.get("Journal", {}).get("Title", ""))

    return {
        "PMID": pmid,
        "Title": title,
        "Abstract": abstract,
        "Journal": journal,
        "Source_Type": "PubMed",
        "Source_Organization": "NCBI PubMed",
        "Source_URL": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        "Raw_Text": title + "\n\n" + abstract,
    }


def search_and_fetch_pubmed(query, max_results=10):
    pmids = search_pubmed(query, max_results=max_results)
    articles = []

    for pmid in pmids:
        try:
            articles.append(fetch_pubmed_article(pmid))
        except Exception:
            continue

    return articles
