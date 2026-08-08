import evidence_collector as ec
import pubmed_connector as pc


def _article(pmid, title, year=""):
    return {
        "PMID": str(pmid),
        "Title": title,
        "Source_URL": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        "Raw_Text": title,
        "Year": year,
    }


def test_indication_relaxation_removes_generic_context_but_keeps_condition():
    assert ec._indication_core("Chronic heart failure adjunctive support") == "Chronic heart failure"


def test_query_plan_contains_relaxed_genus_lane_and_recency_lane():
    plan = ec.build_pubmed_query_plan(
        "Crataegus monogyna",
        "Chronic heart failure adjunctive support",
        "oral extract",
    )
    assert len(plan) == 5
    relaxed_query, relaxed_sort = plan[-2]
    fresh_query, fresh_sort = plan[-1]
    assert "Crataegus" in relaxed_query
    assert "Chronic heart failure" in relaxed_query
    assert "adjunctive support" not in relaxed_query
    assert relaxed_sort == "relevance"
    assert fresh_query == relaxed_query
    assert fresh_sort == "pub date"


def test_collect_gives_fresh_lane_a_bounded_slot(monkeypatch):
    calls = []
    fixtures = [
        [_article(1, "Old highly relevant review", "2008")],
        [_article(1, "Old highly relevant review", "2008")],
        [_article(2, "Older trial", "2002")],
        [_article(3, "Relaxed genus review", "2012")],
        [_article(4, "Newer direct conflicting trial", "2025")],
    ]

    def fake_search(query, max_results, sort="relevance"):
        calls.append((query, max_results, sort))
        return fixtures[len(calls) - 1]

    monkeypatch.setattr(ec, "search_and_fetch_pubmed", fake_search)
    monkeypatch.setattr(ec, "extract_evidence_from_text", lambda text: {})
    monkeypatch.setattr(ec, "standardize_extracted_record", lambda extracted, source_metadata: extracted)

    rows = ec.collect_pubmed_evidence(
        "Crataegus monogyna",
        "Chronic heart failure adjunctive support",
        "oral extract",
        max_results=5,
        save=False,
    )
    assert calls[-1][2] == "pub date"
    assert "4" in [row["pmid"] for row in rows]


def test_pubmed_search_passes_requested_sort(monkeypatch):
    captured = {}

    class Resp:
        def raise_for_status(self):
            return None
        def json(self):
            return {"esearchresult": {"idlist": ["123"]}}

    def fake_get(url, params, timeout):
        captured.update(params)
        return Resp()

    monkeypatch.setattr(pc.requests, "get", fake_get)
    assert pc.search_pubmed("hawthorn", max_results=1, sort="pub date") == ["123"]
    assert captured["sort"] == "pub date"
