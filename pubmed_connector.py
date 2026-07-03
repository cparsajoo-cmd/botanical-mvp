from Bio import Entrez

Entrez.email = "your_email@example.com"


def search_pubmed(query, max_results=20):

    handle = Entrez.esearch(
        db="pubmed",
        term=query,
        retmax=max_results
    )

    record = Entrez.read(handle)

    return record["IdList"]


def fetch_article(pmid):

    handle = Entrez.efetch(
        db="pubmed",
        id=pmid,
        rettype="abstract",
        retmode="xml"
    )

    return Entrez.read(handle)
