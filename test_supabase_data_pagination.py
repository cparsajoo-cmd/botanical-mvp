"""Regression tests for supabase_data._fetch_table_df's pagination.

Production bug: load_evidence_records_df() (backed by _fetch_table_df) was
silently returning only ~half of a 21,806-row table (11,195 rows), with no
error anywhere -- the backfill itself reported failed=0. Root cause:
_fetch_table_df paginated with `.range(start, end)` but with no `.order(...)`
applied first. PostgREST/Supabase does not guarantee a stable row order
across separate requests without an explicit order, so consecutive
`.range()` calls were not guaranteed to see the same underlying ordering --
especially once the query involves an embedded-resource join, as
evidence_records' `plants(...)`/`sources(...)` select does. That let a page
appear shorter than page_size (ending the pagination loop) long before every
row had actually been returned.

These tests use a fake Supabase client that mimics the real
`.table(...).select(...).order(...).range(...).execute()` chain -- including
rejecting any `.range()` call that wasn't preceded by `.order()`, so a
regression back to unordered pagination would fail these tests immediately,
not just silently under-fetch as it did in production.
"""
from types import SimpleNamespace

import pandas as pd
import pytest

import supabase_data
import backfill_evidence_embeddings as backfill_mod


class _FakePaginatedSupabaseClient:
    """Mimics supabase-py's `.table(...).select(...).order(...).range(...)
    .execute()` chain against an in-memory list of rows, tracking every
    `.range()`/`.order()` call made so tests can assert on pagination
    shape (call count, boundaries, ordering) as well as on the final
    merged result."""

    def __init__(self, rows: list[dict]):
        self._rows = rows
        self.range_calls: list[tuple[int, int]] = []
        self.order_calls: list[str] = []
        self.select_calls: list[str] = []
        self.table_calls: list[str] = []

    def table(self, name: str):
        self.table_calls.append(name)
        return _FakePaginatedQuery(self, name)


class _FakePaginatedQuery:
    def __init__(self, client: _FakePaginatedSupabaseClient, name: str):
        self._client = client
        self._name = name
        self._order_col = None
        self._range = None

    def select(self, expr):
        self._client.select_calls.append(expr)
        return self

    def order(self, col):
        self._order_col = col
        self._client.order_calls.append(col)
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def execute(self):
        if self._order_col is None:
            # This is exactly the production bug: pagination without a
            # preceding .order() is not deterministic. Fail loudly here
            # instead of silently returning an arbitrary/inconsistent slice.
            raise AssertionError(
                ".range() was called without a preceding .order() -- "
                "pagination is not guaranteed deterministic without it."
            )
        start, end = self._range
        self._client.range_calls.append((start, end))
        page = self._client._rows[start:end + 1]
        return SimpleNamespace(data=page)


def _make_rows(n: int) -> list[dict]:
    return [{"id": i, "name": f"row-{i}"} for i in range(1, n + 1)]


def test_fetch_table_df_returns_all_rows_across_many_pages(monkeypatch):
    """The exact reported scenario: 21806 rows must come back in full, not
    the ~half (11195) the unordered-pagination bug produced."""
    rows = _make_rows(21806)
    fake_client = _FakePaginatedSupabaseClient(rows)
    monkeypatch.setattr(supabase_data, "get_supabase_client", lambda: fake_client)

    df = supabase_data._fetch_table_df("evidence_records", page_size=1000)

    assert len(df) == 21806
    assert set(df["id"]) == set(range(1, 21807))  # no omissions, no duplicates


def test_fetch_table_df_orders_before_every_range_call(monkeypatch):
    """Every page must be requested with an explicit .order() -- proven
    here by the fake raising if .range() is ever called without one first."""
    rows = _make_rows(2500)
    fake_client = _FakePaginatedSupabaseClient(rows)
    monkeypatch.setattr(supabase_data, "get_supabase_client", lambda: fake_client)

    supabase_data._fetch_table_df("evidence_records", page_size=1000, order_by="id")

    assert fake_client.order_calls == ["id"] * len(fake_client.range_calls)


def test_fetch_table_df_makes_expected_number_of_sequential_range_calls(monkeypatch):
    """21806 rows at page_size=1000 -> 22 sequential, non-overlapping,
    gapless page requests (21 full pages + 1 partial 806-row page), and
    pagination must stop exactly there -- no extra trailing request."""
    rows = _make_rows(21806)
    fake_client = _FakePaginatedSupabaseClient(rows)
    monkeypatch.setattr(supabase_data, "get_supabase_client", lambda: fake_client)

    supabase_data._fetch_table_df("evidence_records", page_size=1000)

    assert len(fake_client.range_calls) == 22
    for i, (start, end) in enumerate(fake_client.range_calls):
        assert start == i * 1000
        assert end == start + 999
    # The final page's request range extends past the last real row (21805,
    # 0-indexed) -- the short page it returns (806 rows) is what ends the
    # loop; pagination does not need to know the total count in advance.
    assert fake_client.range_calls[-1] == (21000, 21999)


def test_fetch_table_df_final_short_page_ends_pagination(monkeypatch):
    """A page that returns fewer than page_size rows must stop pagination
    immediately, without an extra (empty) request afterward."""
    rows = _make_rows(1500)  # 1 full page + 1 short (500-row) page
    fake_client = _FakePaginatedSupabaseClient(rows)
    monkeypatch.setattr(supabase_data, "get_supabase_client", lambda: fake_client)

    df = supabase_data._fetch_table_df("evidence_records", page_size=1000)

    assert len(df) == 1500
    assert len(fake_client.range_calls) == 2  # not 3


def test_fetch_table_df_exact_multiple_of_page_size_does_not_over_fetch(monkeypatch):
    """When the table size is an exact multiple of page_size, the last full
    page (page_size rows) still correctly ends pagination on the next
    request, which must come back empty and stop the loop -- not loop
    forever."""
    rows = _make_rows(2000)  # exactly 2 full pages of 1000
    fake_client = _FakePaginatedSupabaseClient(rows)
    monkeypatch.setattr(supabase_data, "get_supabase_client", lambda: fake_client)

    df = supabase_data._fetch_table_df("evidence_records", page_size=1000)

    assert len(df) == 2000
    assert len(fake_client.range_calls) == 3  # two full pages + one empty page that stops the loop


def test_fetch_table_df_empty_table_returns_empty_dataframe(monkeypatch):
    fake_client = _FakePaginatedSupabaseClient([])
    monkeypatch.setattr(supabase_data, "get_supabase_client", lambda: fake_client)

    df = supabase_data._fetch_table_df("evidence_records", page_size=1000)

    assert isinstance(df, pd.DataFrame)
    assert df.empty
    assert len(fake_client.range_calls) == 1  # one request, confirms emptiness, then stops


def test_fetch_table_df_preserves_select_expr_across_every_page(monkeypatch):
    """The existing embedded-resource select (plants/sources join) must be
    sent unchanged on every page, not just the first."""
    rows = _make_rows(1500)
    fake_client = _FakePaginatedSupabaseClient(rows)
    monkeypatch.setattr(supabase_data, "get_supabase_client", lambda: fake_client)

    expr = "*, plants(scientific_name, common_name), sources(*)"
    supabase_data._fetch_table_df("evidence_records", page_size=1000, select_expr=expr)

    assert fake_client.select_calls == [expr, expr]  # once per page, unchanged


def test_load_evidence_records_df_returns_all_21806_mocked_rows(monkeypatch):
    """Integration-level proof, through the real public loader used by
    backfill_evidence_embeddings.py: all 21806 canonical evidence_records
    must come back, matching Supabase SQL's eligible_records count, not the
    11195 the bug produced."""
    rows = [
        {
            "id": i,
            "plant_id": (i % 50) + 1,
            "plants": {"scientific_name": f"Plant {i % 50}", "common_name": ""},
            "sources": {"url": "", "title": "", "source_type": "journal"},
            "target_indication": "cognitive decline",
        }
        for i in range(1, 21807)
    ]
    fake_client = _FakePaginatedSupabaseClient(rows)
    monkeypatch.setattr(supabase_data, "get_supabase_client", lambda: fake_client)

    df = supabase_data.load_evidence_records_df()

    assert len(df) == 21806
    assert set(df["Evidence_Record_ID"]) == set(range(1, 21807))
    assert df["Plant_ID"].notna().all()


# ---------------------------------------------------------------------------
# strict mode: a permanently-failed page must not silently look successful
#
# The pagination-ordering fix above prevents one class of silent partial
# load. This section covers a second, distinct one: even with correct
# ordering, a page can genuinely fail every retry (network outage, a
# persistent 5xx). Non-strict behavior (the app's existing default) still
# returns whatever was collected so far -- appropriate for interactive use.
# The embedding backfill needs the opposite: a loud, unambiguous failure
# (IncompletePaginationError) so a broken CI run cannot report success
# while only part of evidence_records was actually loaded.
# ---------------------------------------------------------------------------

class _FailingPageQuery:
    """A single query-builder chain where one specific page start offset
    always raises on .execute() -- even across every retry attempt --
    simulating a page that is permanently unreachable partway through a
    large fetch (e.g. a persistent network/server error), rather than a
    transient one a retry would recover from."""

    def __init__(self, client: "_PermanentlyFailingMiddlePageClient", fail_start: int):
        self._client = client
        self._fail_start = fail_start
        self._order_col = None
        self._range = None

    def select(self, expr):
        return self

    def order(self, col):
        self._order_col = col
        self._client.order_calls.append(col)
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def execute(self):
        if self._order_col is None:
            raise AssertionError(
                ".range() was called without a preceding .order() -- "
                "pagination is not guaranteed deterministic without it."
            )
        start, end = self._range
        self._client.range_calls.append((start, end))
        if start == self._fail_start:
            raise ConnectionError(f"simulated permanent failure fetching offset {start}")
        page = self._client._rows[start:end + 1]
        return SimpleNamespace(data=page)


class _PermanentlyFailingMiddlePageClient:
    """A fake Supabase client where every page succeeds except one specific
    offset, which always raises regardless of how many times it's retried."""

    def __init__(self, rows: list[dict], fail_start: int):
        self._rows = rows
        self._fail_start = fail_start
        self.range_calls: list[tuple[int, int]] = []
        self.order_calls: list[str] = []
        self.table_calls: list[str] = []

    def table(self, name):
        self.table_calls.append(name)
        return _FailingPageQuery(self, self._fail_start)


def test_fetch_table_df_strict_raises_on_permanently_failed_middle_page(monkeypatch):
    """A page that never succeeds, even after every retry, must raise
    IncompletePaginationError when strict=True -- not silently return
    whatever rows were collected before it."""
    rows = _make_rows(3500)
    fake_client = _PermanentlyFailingMiddlePageClient(rows, fail_start=2000)
    monkeypatch.setattr(supabase_data, "get_supabase_client", lambda: fake_client)

    with pytest.raises(supabase_data.IncompletePaginationError) as exc_info:
        supabase_data._fetch_table_df(
            "evidence_records", page_size=1000, max_retries=1, strict=True,
        )

    message = str(exc_info.value)
    assert "evidence_records" in message          # table name
    assert "offset 2000" in message                # failed start offset
    assert "after 1 retries" in message             # retry count
    assert "2000 row(s) had been collected" in message  # rows collected so far


def test_fetch_table_df_non_strict_retains_partial_result_behavior(monkeypatch):
    """strict=False (the default) must be unaffected: a permanently failed
    page still ends pagination with whatever rows were already collected,
    exactly as before this change."""
    rows = _make_rows(3500)
    fake_client = _PermanentlyFailingMiddlePageClient(rows, fail_start=2000)
    monkeypatch.setattr(supabase_data, "get_supabase_client", lambda: fake_client)

    df = supabase_data._fetch_table_df(
        "evidence_records", page_size=1000, max_retries=1, strict=False,
    )

    assert len(df) == 2000  # pages [0,999] and [1000,1999] only
    assert set(df["id"]) == set(range(1, 2001))


def test_load_evidence_records_df_strict_propagates_incomplete_pagination_error(monkeypatch):
    rows = [
        {
            "id": i, "plant_id": 1,
            "plants": {"scientific_name": "Plant", "common_name": ""},
            "sources": {"url": "", "title": "", "source_type": "journal"},
        }
        for i in range(1, 3501)
    ]
    fake_client = _PermanentlyFailingMiddlePageClient(rows, fail_start=2000)
    monkeypatch.setattr(supabase_data, "get_supabase_client", lambda: fake_client)

    with pytest.raises(supabase_data.IncompletePaginationError):
        supabase_data.load_evidence_records_df(strict=True)


def test_load_evidence_records_df_non_strict_still_returns_partial_dataframe(monkeypatch):
    """Confirms load_evidence_records_df's own broad except-and-return-
    empty-dataframe fallback still applies in non-strict mode -- but here
    the fetch itself already returned a (partial) non-empty dataframe
    rather than raising, so the normal flatten/return path is exercised."""
    rows = [
        {
            "id": i, "plant_id": 1,
            "plants": {"scientific_name": "Plant", "common_name": ""},
            "sources": {"url": "", "title": "", "source_type": "journal"},
        }
        for i in range(1, 3501)
    ]
    fake_client = _PermanentlyFailingMiddlePageClient(rows, fail_start=2000)
    monkeypatch.setattr(supabase_data, "get_supabase_client", lambda: fake_client)

    df = supabase_data.load_evidence_records_df(strict=False)

    assert len(df) == 2000
    assert set(df["Evidence_Record_ID"]) == set(range(1, 2001))


def test_backfill_engine_build_uses_strict_pagination_for_evidence_records(monkeypatch):
    """The backfill's engine construction must call
    load_evidence_records_df(strict=True), not the default strict=False --
    this is what makes a broken pagination run fail the GitHub Actions job
    instead of silently proceeding with a partial dataset."""
    calls = []

    def _fake_load_evidence_records_df(strict=False):
        calls.append(strict)
        return pd.DataFrame()

    class _FakeEngine:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr("supabase_data.load_evidence_records_df", _fake_load_evidence_records_df)
    monkeypatch.setattr("supabase_data.load_scientific_evidence_df", lambda: pd.DataFrame())
    monkeypatch.setattr("supabase_data.load_plant_compounds_df", lambda: pd.DataFrame())
    monkeypatch.setattr("supabase_data.load_compound_profiles_df", lambda: pd.DataFrame())
    monkeypatch.setattr("botanical_rd_candidate_engine.BotanicalRDCandidateEngine", _FakeEngine)

    backfill_mod._build_engine()

    assert calls == [True]
