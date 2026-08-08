"""Regression tests for backfill_canonical_assertions.py.

Covers the two real bugs found in the 2026-08-08 audit (see that module's
docstring):

1. Silent pagination truncation -- proven here with a fake Supabase client
   that (a) rejects any .range() call not preceded by .order(), matching
   test_supabase_data_pagination.py's existing invariant, and (b) holds
   more rows than a single PostgREST page, so a regression back to an
   unbounded/unpaginated select would under-count.
2. Missing Source_Title in the extraction prompt -- proven by asserting on
   the exact `record` dict the fake LLM client received.

Also covers: never overwrites an existing result_direction/safety_signal,
the skipped_no_extractable_text bucket, retry-then-succeed and
retry-exhausted-then-fail for the LLM call, apply=False never writing, and
full-run stats reconciliation.

Nothing here makes a real network call (see test_embedding_vector_service.py's
module docstring for why: the sandbox's outbound-network allowlist does not
include api.openai.com or *.supabase.co).
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import backfill_canonical_assertions as backfill_mod


# ---------------------------------------------------------------------
# Fake Supabase client -- same ordered-pagination invariant as
# test_supabase_data_pagination.py's _FakePaginatedSupabaseClient, plus
# .update(...).eq(...).execute() support for the write side.
# ---------------------------------------------------------------------
class _FakeQuery:
    def __init__(self, client, name):
        self._client = client
        self._name = name
        self._order_col = None
        self._range = None
        self._pending_update = None
        self._eq_filters = []

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

    def update(self, payload):
        self._pending_update = dict(payload)
        return self

    def eq(self, col, value):
        self._eq_filters.append((col, value))
        return self

    def execute(self):
        if self._pending_update is not None:
            (col, value), = self._eq_filters or [(None, None)]
            for row in self._client.rows:
                if row.get(col) == value:
                    row.update(self._pending_update)
            self._client.update_calls.append(
                {"payload": self._pending_update, "filters": list(self._eq_filters)}
            )
            return SimpleNamespace(data=[self._pending_update])

        if self._order_col is None:
            # Exactly the production bug this test suite exists to catch:
            # pagination without a preceding .order() is not deterministic
            # and PostgREST silently caps unbounded selects.
            raise AssertionError(
                ".range() was called without a preceding .order() -- "
                "pagination is not guaranteed deterministic without it."
            )
        start, end = self._range
        self._client.range_calls.append((start, end))
        page = self._client.rows[start : end + 1]
        return SimpleNamespace(data=page)


class _FakeSupabaseClient:
    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.range_calls: list[tuple[int, int]] = []
        self.order_calls: list[str] = []
        self.select_calls: list[str] = []
        self.update_calls: list[dict] = []

    def table(self, name):
        return _FakeQuery(self, name)


def _make_row(i, *, notes="", title="", result_direction=None, safety_signal=None,
              scientific_name="Ginkgo biloba", target_indication="cognitive impairment"):
    return {
        "id": i,
        "target_indication": target_indication,
        "dosage_form": "extract",
        "notes": notes,
        "evidence_type": "Randomized Controlled Trial",
        "evidence_level": "High",
        "study_type": "RCT",
        "result_direction": result_direction,
        "safety_signal": safety_signal,
        "plants": {"scientific_name": scientific_name},
        "sources": {"title": title},
    }


# ---------------------------------------------------------------------
# Fake OpenAI-backed extractor. We patch extract_evidence_with_llm at the
# point backfill_canonical_assertions imported it, so the retry wrapper
# exercises real control flow.
# ---------------------------------------------------------------------
class _FakeExtractor:
    def __init__(self, *, fail_times=0, result_direction="Positive", safety_signal=""):
        self.calls: list[dict] = []
        self.fail_times = fail_times
        self.result_direction = result_direction
        self.safety_signal = safety_signal

    def __call__(self, record, *, selected_dosage_form="", selected_indication=""):
        self.calls.append(dict(record))
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("simulated transient OpenAI failure")
        return {
            "result_direction": self.result_direction,
            "safety_signal": self.safety_signal,
        }


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    # Keep tests fast; also lets us assert retry actually happened without
    # a real 0.5s+ delay.
    return None


# ---------------------------------------------------------------------
# Bug #1 regression: pagination must not silently truncate.
# ---------------------------------------------------------------------
def test_pagination_scans_every_row_across_multiple_pages(monkeypatch):
    rows = [_make_row(i, notes=f"note {i}") for i in range(1, 2501)]  # > 2 pages @1000
    fake_client = _FakeSupabaseClient(rows)
    monkeypatch.setattr(backfill_mod, "get_supabase_client", lambda: fake_client)
    monkeypatch.setattr(
        "supabase_data.get_supabase_client", lambda: fake_client
    )
    extractor = _FakeExtractor()
    monkeypatch.setattr(backfill_mod, "extract_evidence_with_llm", extractor)

    stats, failures = backfill_mod.backfill(apply=False, sleep_fn=lambda s: None)

    assert stats.scanned == 2500
    assert len(extractor.calls) == 2500
    assert not failures
    assert stats.reconciles()
    # Every page must have been ordered before ranged.
    assert fake_client.order_calls and all(c == "id" for c in fake_client.order_calls)
    assert len(fake_client.range_calls) >= 3  # 2500 rows / 1000 page_size


def test_unordered_range_call_raises_not_silently_truncates(monkeypatch):
    """Sanity check that the fake client itself would catch a regression
    back to unordered/unpaginated pagination (i.e. the test harness is not
    accidentally toothless)."""
    rows = [_make_row(1, notes="x")]
    client = _FakeSupabaseClient(rows)
    # Call range() without order() directly, bypassing the module under
    # test, to prove the fake enforces the invariant.
    with pytest.raises(AssertionError):
        client.table("evidence_records").select("id").range(0, 999).execute()


# ---------------------------------------------------------------------
# Bug #2 regression: Source_Title must reach the extractor.
# ---------------------------------------------------------------------
def test_source_title_is_populated_on_the_extraction_record(monkeypatch):
    rows = [_make_row(1, notes="Some result text.", title="A Real Article Title")]
    fake_client = _FakeSupabaseClient(rows)
    monkeypatch.setattr(backfill_mod, "get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("supabase_data.get_supabase_client", lambda: fake_client)
    extractor = _FakeExtractor()
    monkeypatch.setattr(backfill_mod, "extract_evidence_with_llm", extractor)

    backfill_mod.backfill(apply=False, sleep_fn=lambda s: None)

    assert extractor.calls[0]["Source_Title"] == "A Real Article Title"
    assert extractor.calls[0]["Notes"] == "Some result text."


# ---------------------------------------------------------------------
# Never overwrites existing structured direction/safety.
# ---------------------------------------------------------------------
def test_never_overwrites_existing_result_direction(monkeypatch):
    rows = [
        _make_row(1, notes="x", result_direction="Positive"),
        _make_row(2, notes="y", result_direction=None),
    ]
    fake_client = _FakeSupabaseClient(rows)
    monkeypatch.setattr(backfill_mod, "get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("supabase_data.get_supabase_client", lambda: fake_client)
    extractor = _FakeExtractor(result_direction="Negative")
    monkeypatch.setattr(backfill_mod, "extract_evidence_with_llm", extractor)

    stats, failures = backfill_mod.backfill(apply=True, sleep_fn=lambda s: None)

    assert stats.skipped_has_direction == 1
    assert stats.extracted == 1
    assert len(extractor.calls) == 1  # row 1 never sent to the LLM at all
    assert rows[0]["result_direction"] == "Positive"  # untouched
    assert rows[1]["result_direction"] == "Negative"  # backfilled


# ---------------------------------------------------------------------
# skipped_no_extractable_text bucket.
# ---------------------------------------------------------------------
def test_rows_with_no_notes_or_title_are_not_sent_to_llm(monkeypatch):
    rows = [_make_row(1, notes="", title="")]
    fake_client = _FakeSupabaseClient(rows)
    monkeypatch.setattr(backfill_mod, "get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("supabase_data.get_supabase_client", lambda: fake_client)
    extractor = _FakeExtractor()
    monkeypatch.setattr(backfill_mod, "extract_evidence_with_llm", extractor)

    stats, failures = backfill_mod.backfill(apply=True, sleep_fn=lambda s: None)

    assert stats.skipped_no_extractable_text == 1
    assert stats.extracted == 0
    assert not extractor.calls
    assert stats.reconciles()


# ---------------------------------------------------------------------
# Retry behaviour.
# ---------------------------------------------------------------------
def test_transient_failure_is_retried_then_succeeds(monkeypatch):
    rows = [_make_row(1, notes="x")]
    fake_client = _FakeSupabaseClient(rows)
    monkeypatch.setattr(backfill_mod, "get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("supabase_data.get_supabase_client", lambda: fake_client)
    extractor = _FakeExtractor(fail_times=1)
    monkeypatch.setattr(backfill_mod, "extract_evidence_with_llm", extractor)

    sleeps = []
    stats, failures = backfill_mod.backfill(apply=False, sleep_fn=sleeps.append)

    assert stats.extracted == 1
    assert not failures
    assert len(extractor.calls) == 2  # 1 failure + 1 success
    assert sleeps == [0.5]


def test_retries_exhausted_records_failure_not_silent_skip(monkeypatch):
    rows = [_make_row(1, notes="x")]
    fake_client = _FakeSupabaseClient(rows)
    monkeypatch.setattr(backfill_mod, "get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("supabase_data.get_supabase_client", lambda: fake_client)
    extractor = _FakeExtractor(fail_times=99)
    monkeypatch.setattr(backfill_mod, "extract_evidence_with_llm", extractor)

    stats, failures = backfill_mod.backfill(apply=False, sleep_fn=lambda s: None)

    assert stats.extracted == 0
    assert stats.failed == 1
    assert failures[0]["id"] == 1
    assert stats.reconciles()
    assert len(extractor.calls) == backfill_mod.MAX_EXTRACTION_RETRIES + 1


# ---------------------------------------------------------------------
# apply=False never writes.
# ---------------------------------------------------------------------
def test_dry_run_never_calls_update(monkeypatch):
    rows = [_make_row(1, notes="x")]
    fake_client = _FakeSupabaseClient(rows)
    monkeypatch.setattr(backfill_mod, "get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("supabase_data.get_supabase_client", lambda: fake_client)
    extractor = _FakeExtractor()
    monkeypatch.setattr(backfill_mod, "extract_evidence_with_llm", extractor)

    stats, failures = backfill_mod.backfill(apply=False, sleep_fn=lambda s: None)

    assert stats.extracted == 1
    assert stats.updated == 0
    assert not fake_client.update_calls
    assert rows[0]["result_direction"] is None


# ---------------------------------------------------------------------
# safety_signal is backfilled only when blank, alongside direction.
# ---------------------------------------------------------------------
def test_safety_signal_backfilled_only_when_blank(monkeypatch):
    rows = [
        _make_row(1, notes="x", safety_signal="Serious"),
        _make_row(2, notes="y", safety_signal=None),
    ]
    fake_client = _FakeSupabaseClient(rows)
    monkeypatch.setattr(backfill_mod, "get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("supabase_data.get_supabase_client", lambda: fake_client)
    extractor = _FakeExtractor(result_direction="Positive", safety_signal="Moderate")
    monkeypatch.setattr(backfill_mod, "extract_evidence_with_llm", extractor)

    backfill_mod.backfill(apply=True, sleep_fn=lambda s: None)

    assert rows[0]["safety_signal"] == "Serious"  # untouched
    assert rows[1]["safety_signal"] == "Moderate"  # backfilled


# ---------------------------------------------------------------------
# --limit still respects the ordered/paginated fetch underneath (applies
# the limit AFTER the full ordered fetch, not by short-circuiting
# pagination itself -- so a --limit run's sample is still deterministic).
# ---------------------------------------------------------------------
def test_limit_takes_first_n_of_the_ordered_fetch(monkeypatch):
    rows = [_make_row(i, notes=f"note {i}") for i in range(1, 51)]
    fake_client = _FakeSupabaseClient(rows)
    monkeypatch.setattr(backfill_mod, "get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("supabase_data.get_supabase_client", lambda: fake_client)
    extractor = _FakeExtractor()
    monkeypatch.setattr(backfill_mod, "extract_evidence_with_llm", extractor)

    stats, failures = backfill_mod.backfill(apply=False, limit=5, sleep_fn=lambda s: None)

    assert stats.scanned == 5
    assert [c["Notes"] for c in extractor.calls] == [f"note {i}" for i in range(1, 6)]


# ---------------------------------------------------------------------
# Full-run reconciliation across a mixed batch.
# ---------------------------------------------------------------------
def test_full_run_reconciles_with_mixed_row_kinds(monkeypatch):
    rows = []
    for i in range(1, 31):
        if i % 5 == 0:
            rows.append(_make_row(i, notes="x", result_direction="Positive"))
        elif i % 7 == 0:
            rows.append(_make_row(i, notes="", title=""))
        else:
            rows.append(_make_row(i, notes=f"note {i}"))
    fake_client = _FakeSupabaseClient(rows)
    monkeypatch.setattr(backfill_mod, "get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("supabase_data.get_supabase_client", lambda: fake_client)
    extractor = _FakeExtractor()
    monkeypatch.setattr(backfill_mod, "extract_evidence_with_llm", extractor)

    stats, failures = backfill_mod.backfill(apply=True, sleep_fn=lambda s: None)

    assert stats.scanned == 30
    assert stats.reconciles()
    assert stats.updated == stats.extracted
