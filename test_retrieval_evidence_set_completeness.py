import evidence_collector as ec


def _article(pmid, title):
    return {
        "PMID": str(pmid),
        "Title": title,
        "Source_URL": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        "Raw_Text": title,
    }


def test_pubmed_query_portfolio_is_design_diverse_and_polarity_neutral():
    queries = ec.build_pubmed_queries("Sambucus nigra", "respiratory symptoms", "")
    assert len(queries) == 3
    joined = " ".join(queries).lower()
    assert "systematic review" in joined
    assert "meta-analysis" in joined
    assert "randomized" in joined
    # Retrieval must not query for the answer it hopes to see.
    for forbidden in ("positive", "negative", "beneficial", "insufficient", "uncertain", "no significant"):
        assert forbidden not in joined


def test_balanced_merge_prevents_first_query_from_monopolizing_slots():
    broad = [_article(1, "Broad 1"), _article(2, "Broad 2"), _article(3, "Broad 3")]
    synth = [_article(10, "Systematic review"), _article(11, "Meta-analysis")]
    clinical = [_article(20, "RCT"), _article(21, "Trial")]
    got = ec._balanced_unique_articles([broad, synth, clinical], max_results=5)
    assert [x["PMID"] for x in got] == ["1", "10", "20", "2", "11"]


def test_balanced_merge_deduplicates_same_publication_across_queries():
    duplicate = _article(99, "Same paper")
    got = ec._balanced_unique_articles(
        [[duplicate, _article(1, "A")], [duplicate, _article(2, "B")], [_article(3, "C")]],
        max_results=5,
    )
    assert [x["PMID"] for x in got].count("99") == 1
    assert len({x["PMID"] for x in got}) == len(got)


def test_collect_pubmed_evidence_uses_portfolio_but_keeps_total_bounded(monkeypatch):
    calls = []
    fixtures = {
        0: [_article(1, "Broad positive"), _article(2, "Broad follow-up")],
        1: [_article(10, "Systematic review"), _article(1, "Broad positive")],
        2: [_article(20, "Randomized trial")],
    }

    def fake_search(query, max_results):
        calls.append((query, max_results))
        return fixtures[len(calls) - 1]

    monkeypatch.setattr(ec, "search_and_fetch_pubmed", fake_search)
    monkeypatch.setattr(ec, "extract_evidence_from_text", lambda text: {})
    monkeypatch.setattr(ec, "standardize_extracted_record", lambda extracted, source_metadata: extracted)

    rows = ec.collect_pubmed_evidence(
        scientific_name="Sambucus nigra",
        indication="respiratory symptoms",
        dosage_form="",
        max_results=3,
        save=False,
    )

    assert len(calls) == 3
    assert len(rows) == 3
    assert [row["pmid"] for row in rows] == ["1", "10", "20"]


def test_empty_dosage_form_does_not_generate_leading_or_clause():
    query = ec.build_pubmed_query("Silybum marianum", "fatty liver", "")
    assert "( OR" not in query
    assert "clinical OR trial" in query
