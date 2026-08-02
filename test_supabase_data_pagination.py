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
