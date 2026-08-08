from pubmed_connector import search_and_fetch_pubmed
from evidence_extractor import extract_evidence_from_text
from evidence_standardizer import standardize_extracted_record
from database import save_evidence_record


def _clean_query_term(value):
    return " ".join(str(value or "").strip().split())


def build_pubmed_query(scientific_name, indication, dosage_form):
    """Backward-compatible broad clinical PubMed query."""
    scientific_name = _clean_query_term(scientific_name)
    indication = _clean_query_term(indication)
    dosage_form = _clean_query_term(dosage_form)
    context_terms = [x for x in (dosage_form, "clinical", "trial", "randomized", "review") if x]
    return f'"{scientific_name}" AND ({indication}) AND ({" OR ".join(context_terms)})'


def build_pubmed_queries(scientific_name, indication, dosage_form):
    """Return a small, polarity-neutral query portfolio for evidence-set coverage.

    A single relevance-ranked PubMed query can be dominated by one study family
    or one evidence type.  These bounded variants deliberately diversify by
    evidence *design*, never by desired result direction, so retrieval can see
    both corroborating and conflicting high-level evidence without using any
    benchmark label.
    """
    scientific_name = _clean_query_term(scientific_name)
    indication = _clean_query_term(indication)
    dosage_form = _clean_query_term(dosage_form)

    base = build_pubmed_query(scientific_name, indication, dosage_form)
    synthesis = (
        f'"{scientific_name}" AND ({indication}) AND '
        '("systematic review" OR "meta-analysis" OR "meta analysis")'
    )
    clinical = (
        f'"{scientific_name}" AND ({indication}) AND '
        '(randomized OR randomised OR trial OR clinical)'
    )

    queries = []
    for query in (base, synthesis, clinical):
        if query and query not in queries:
            queries.append(query)
    return queries


def _article_identity(article):
    pmid = str(article.get("PMID", "") or "").strip()
    if pmid:
        return f"pmid:{pmid}"
    url = str(article.get("Source_URL", "") or "").strip().lower()
    if url:
        return f"url:{url}"
    title = " ".join(str(article.get("Title", "") or "").lower().split())
    return f"title:{title}" if title else ""


def _balanced_unique_articles(query_results, max_results):
    """Round-robin merge query result lists with article-level deduplication."""
    limit = max(0, int(max_results))
    if limit == 0:
        return []

    merged = []
    seen = set()
    depth = 0
    while len(merged) < limit:
        added_at_depth = False
        for articles in query_results:
            if depth >= len(articles):
                continue
            article = articles[depth]
            ident = _article_identity(article)
            if ident and ident in seen:
                continue
            if ident:
                seen.add(ident)
            merged.append(article)
            added_at_depth = True
            if len(merged) >= limit:
                break
        if not added_at_depth and all(depth >= len(items) - 1 for items in query_results):
            break
        depth += 1
    return merged


def collect_pubmed_evidence(
    scientific_name,
    indication,
    dosage_form,
    market="European Union",
    max_results=10,
    save=True
):
    queries = build_pubmed_queries(
        scientific_name=scientific_name,
        indication=indication,
        dosage_form=dosage_form,
    )

    # Keep total returned evidence bounded by max_results, while giving each
    # evidence-design query a chance to contribute.  Each connector call is
    # itself bounded to max_results and the merged set is deduplicated by PMID
    # (falling back to URL/title when PMID is unavailable).
    query_results = [
        search_and_fetch_pubmed(query=query, max_results=max_results)
        for query in queries
    ]
    articles = _balanced_unique_articles(query_results, max_results=max_results)

    saved_records = []

    for article in articles:
        extracted = extract_evidence_from_text(article["Raw_Text"])

        extracted["Scientific_Name"] = scientific_name
        extracted["Target_Indication"] = indication
        extracted["Dosage_Form"] = dosage_form
        extracted["Target_Market"] = market
        extracted["Source_Type"] = "PubMed"
        extracted["Source_Title"] = article["Title"]
        extracted["Source_Organization"] = "NCBI PubMed"
        extracted["Source_URL"] = article["Source_URL"]
        extracted["Notes"] = article["Raw_Text"]
        # Phase 2 (IMPLEMENTATION_PLAN.md) — search_and_fetch_pubmed()
        # already returns the PMID (used to build Source_URL above, and
        # already carried separately in this function's own return value
        # as item["pmid"]); persisting it on the record itself too so it
        # reaches save_evidence_record() instead of only the caller summary.
        extracted["PMID"] = article.get("PMID", "")
        extracted["Source_Year"] = article.get("Year", "")

        standardized = standardize_extracted_record(
            extracted=extracted,
            source_metadata={
                "source_type": "PubMed",
                "source_title": article["Title"],
                "source_url": article["Source_URL"],
                "source_organization": "NCBI PubMed",
                "source_year": article.get("Year", ""),
            }
        )

        row_id = None

        if save:
            row_id = save_evidence_record(standardized)

        saved_records.append({
            "row_id": row_id,
            "pmid": article["PMID"],
            "title": article["Title"],
            "record": standardized,
        })

    return saved_records
