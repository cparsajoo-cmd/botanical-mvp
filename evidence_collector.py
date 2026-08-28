from pubmed_connector import search_and_fetch_pubmed
from evidence_extractor import extract_evidence_from_text
from evidence_standardizer import standardize_extracted_record
from database import save_evidence_record

import time


def _clean_query_term(value):
    return " ".join(str(value or "").strip().split())


def build_pubmed_query(scientific_name, indication, dosage_form):
    """Backward-compatible broad clinical PubMed query."""
    scientific_name = _clean_query_term(scientific_name)
    indication = _clean_query_term(indication)
    dosage_form = _clean_query_term(dosage_form)
    context_terms = [x for x in (dosage_form, "clinical", "trial", "randomized", "review") if x]
    return f'"{scientific_name}" AND ({indication}) AND ({" OR ".join(context_terms)})'


def _indication_core(indication):
    """Relax indication wording without encoding an expected result.

    Validation questions often contain decision-context words (for example
    "adjunctive support", "prevention", or "symptom management") that are not
    consistently present in PubMed titles/abstract indexing.  Removing only a
    small set of generic context modifiers preserves the clinical condition
    while improving recall.
    """
    import re

    text = _clean_query_term(indication)
    if not text:
        return ""
    generic = {
        "adjunctive", "adjunct", "support", "supportive", "management",
        "treatment", "therapy", "therapeutic", "prevention", "preventive",
        "symptoms", "symptom", "control", "clinical",
    }
    tokens = re.findall(r"[A-Za-z0-9-]+", text)
    kept = [token for token in tokens if token.lower() not in generic]
    return " ".join(kept) or text


def _genus_name(scientific_name):
    parts = _clean_query_term(scientific_name).split()
    return parts[0] if parts else ""


def build_pubmed_queries(scientific_name, indication, dosage_form):
    """Return a polarity-neutral query portfolio with recall and freshness lanes.

    The portfolio deliberately varies evidence design, taxonomic specificity,
    indication strictness, and sort order.  It never varies by desired outcome.
    This prevents an exact botanical/wording match or a highly cited older
    review from monopolizing the evidence set.
    """
    scientific_name = _clean_query_term(scientific_name)
    indication = _clean_query_term(indication)
    dosage_form = _clean_query_term(dosage_form)
    core_indication = _indication_core(indication)
    genus = _genus_name(scientific_name)

    base = build_pubmed_query(scientific_name, indication, dosage_form)
    synthesis = (
        f'"{scientific_name}" AND ({indication}) AND '
        '("systematic review" OR "meta-analysis" OR "meta analysis")'
    )
    clinical = (
        f'"{scientific_name}" AND ({indication}) AND '
        '(randomized OR randomised OR trial OR clinical)'
    )

    # Recall lane: relax only generic decision-context wording and, where
    # possible, botanical species specificity to genus level.  This is useful
    # for literature indexed under Crataegus spp. rather than one species.
    relaxed_name = genus or scientific_name
    relaxed = (
        f'({scientific_name!r} OR {relaxed_name!r}) AND ({core_indication or indication}) AND '
        '(review OR trial OR randomized OR randomised OR meta-analysis)'
    ).replace("'", '"')

    queries = []
    for query in (base, synthesis, clinical, relaxed):
        if query and query not in queries:
            queries.append(query)
    return queries


def build_pubmed_query_plan(scientific_name, indication, dosage_form):
    """Pair query variants with ranking modes, including one recency lane."""
    queries = build_pubmed_queries(scientific_name, indication, dosage_form)
    plan = [(query, "relevance") for query in queries]
    if queries:
        # Re-run the relaxed query by publication date so newer direct evidence
        # gets one bounded opportunity to enter the set.
        plan.append((queries[-1], "pub date"))
    return plan


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
    save=True,
    allow_llm=True,
):
    query_plan = build_pubmed_query_plan(
        scientific_name=scientific_name,
        indication=indication,
        dosage_form=dosage_form,
    )

    # Stage-2 runtime hotfix: preserve the full polarity-neutral query portfolio,
    # but do NOT make the whole PubMed source all-or-nothing.  Previously all
    # lanes were executed serially in one list-comprehension.  One slow/429 lane
    # could therefore make the entire PubMed future miss the outer Stage-2
    # deadline and discard evidence that earlier lanes had already found.
    #
    # Keep PubMed itself bounded to 30 s, leaving headroom inside the collector's
    # 45 s per-plant budget for extraction/standardization/persistence and the
    # other sources.  Successful lanes are retained incrementally; a failure in
    # one lane no longer erases successful results from the others.
    pubmed_deadline = time.monotonic() + 30.0
    query_results = []
    last_error = None
    successful_lane_count = 0

    for query, sort in query_plan:
        remaining = pubmed_deadline - time.monotonic()
        if remaining <= 1.0:
            break

        # search_and_fetch_pubmed performs two HTTP calls (esearch + efetch),
        # both using this timeout. Split the remaining lane budget between them
        # and never exceed the connector's historical 10 s request timeout.
        request_timeout = max(1.0, min(10.0, remaining / 2.0))
        try:
            try:
                lane_articles = search_and_fetch_pubmed(
                    query=query,
                    max_results=max_results,
                    sort=sort,
                    timeout=request_timeout,
                )
            except TypeError as exc:
                # Test doubles and older compatible connector shims may not
                # accept the timeout keyword.  Preserve compatibility without
                # weakening production behavior, where the real connector does.
                if "timeout" not in str(exc):
                    raise
                lane_articles = search_and_fetch_pubmed(
                    query=query,
                    max_results=max_results,
                    sort=sort,
                )
            query_results.append(lane_articles or [])
            successful_lane_count += 1
        except Exception as exc:
            # Lane-level isolation is intentional: broad/review/clinical/recency
            # searches are independent retrieval opportunities.  A rate limit or
            # timeout in one must not destroy evidence already returned by another.
            last_error = exc
            query_results.append([])

    # If every lane failed, preserve the previous failure semantics so the
    # multi-source collector records PubMed as an error instead of silently
    # reporting a successful zero-result search.
    if successful_lane_count == 0 and last_error is not None:
        raise last_error

    # Keep total returned evidence bounded by max_results, while giving every
    # completed evidence-design/recency lane a chance to contribute.  The merged
    # set is deduplicated by PMID (falling back to URL/title when PMID is absent).
    articles = _balanced_unique_articles(query_results, max_results=max_results)

    saved_records = []

    for article in articles:
        extracted = extract_evidence_from_text(article["Raw_Text"])

        extracted["Scientific_Name"] = scientific_name
        # Search/product context must never overwrite facts extracted from the
        # study itself.  Keep the requested indication/form under dedicated
        # transient keys; build_standard_evidence() can use them for contextual
        # directness, while Target_Indication/Dosage_Form remain evidence facts.
        extracted["Requested_Target_Indication"] = indication
        extracted["Requested_Dosage_Form"] = dosage_form
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
            },
            allow_llm=allow_llm,
        )

        row_id = None

        if save:
            row_id = save_evidence_record(standardized)

        saved_records.append({
            "row_id": row_id,
            "pmid": article["PMID"],
            "title": article["Title"],
            # Keep the collector summary source-explicit, matching every
            # non-PubMed connector's saved-record shape.  Session observability
            # and retrieval-coverage logic must never have to infer PubMed from
            # the nested standardized row.
            "source": "PubMed",
            "record": standardized,
        })

    return saved_records
