"""Level B vector-service tests: OpenAI embedding calls and Supabase
RPC/table calls are mocked throughout this file -- nothing here makes a
real network call, per the sandbox's outbound-network allowlist (does not
include api.openai.com or *.supabase.co; see EMBEDDING_ARCHITECTURE_REVIEW.md
section 6).
"""
from types import SimpleNamespace

import pytest

from embedding_service import (
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL,
    EMBEDDING_VERSION,
    embed_query,
    embed_texts_batched,
    fetch_existing_content_hashes,
    upsert_evidence_embeddings,
)
import backfill_evidence_embeddings as backfill_mod


def _fake_embedding_response(n: int, dim: int = EMBEDDING_DIMENSION):
    return SimpleNamespace(data=[SimpleNamespace(embedding=[0.01] * dim) for _ in range(n)])


class _FakeOpenAIClient:
    """Mocks the openai==2.45.0 client.embeddings.create(...) interface."""

    def __init__(self, fail_times: int = 0, dim: int = EMBEDDING_DIMENSION):
        self.calls: list[dict] = []
        self.fail_times = fail_times
        self.dim = dim

    class _Embeddings:
        def __init__(self, outer):
            self._outer = outer

        def create(self, *, model, input, timeout=None):  # noqa: A002 - matches SDK kwarg name
            self._outer.calls.append({"model": model, "input": list(input), "timeout": timeout})
            if self._outer.fail_times > 0:
                self._outer.fail_times -= 1
                raise RuntimeError("simulated transient failure")
            return _fake_embedding_response(len(input), self._outer.dim)

    @property
    def embeddings(self):
        return self._Embeddings(self)


class _FakeTable:
    def __init__(self, store: dict, name: str):
        self._store = store
        self._name = name
        self._filters: list[tuple[str, str, object]] = []
        self._select_cols = None

    def select(self, cols):
        self._select_cols = cols
        return self

    def eq(self, col, value):
        self._filters.append(("eq", col, value))
        return self

    def in_(self, col, values):
        self._filters.append(("in", col, set(values)))
        return self

    def upsert(self, rows, on_conflict=None):
        self._pending_upsert = rows
        return self

    def execute(self):
        if hasattr(self, "_pending_upsert"):
            table = self._store.setdefault(self._name, [])
            for row in self._pending_upsert:
                key = (row["evidence_record_id"], row["embedding_model"], row["embedding_version"])
                table[:] = [r for r in table if (r["evidence_record_id"], r["embedding_model"], r["embedding_version"]) != key]
                table.append(row)
            return SimpleNamespace(data=self._pending_upsert)
        rows = self._store.get(self._name, [])
        for kind, col, value in self._filters:
            if kind == "eq":
                rows = [r for r in rows if r.get(col) == value]
            elif kind == "in":
                rows = [r for r in rows if r.get(col) in value]
        return SimpleNamespace(data=rows)


class _FakeSupabaseClient:
    """Mocks the supabase-py .table(...)/.rpc(...) interface used by
    embedding_service.py and vector_search.py."""

    def __init__(self):
        self._store: dict[str, list[dict]] = {}
        self.rpc_calls: list[dict] = []
        self._rpc_result: list[dict] = []

    def table(self, name):
        return _FakeTable(self._store, name)

    def set_rpc_result(self, rows):
        self._rpc_result = rows

    def rpc(self, name, params):
        self.rpc_calls.append({"name": name, "params": params})
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=self._rpc_result))


# ---------------------------------------------------------------------------
# embed_query: exactly-once semantics, failure handling
# ---------------------------------------------------------------------------

def test_embed_query_calls_openai_exactly_once():
    client = _FakeOpenAIClient()
    vector = embed_query("cough", client=client)
    assert len(client.calls) == 1
    assert client.calls[0]["input"] == ["cough"]
    assert len(vector) == EMBEDDING_DIMENSION


def test_embed_query_returns_none_on_failure_never_raises():
    class _AlwaysFails:
        class embeddings:
            @staticmethod
            def create(**kwargs):
                raise RuntimeError("network down")
    result = embed_query("cough", client=_AlwaysFails())
    assert result is None


def test_embed_query_returns_none_for_empty_text():
    client = _FakeOpenAIClient()
    assert embed_query("", client=client) is None
    assert embed_query("   ", client=client) is None
    assert len(client.calls) == 0


def test_embed_query_returns_none_on_wrong_dimension():
    client = _FakeOpenAIClient(dim=42)
    assert embed_query("cough", client=client) is None


def test_embed_query_passes_timeout_through():
    client = _FakeOpenAIClient()
    embed_query("cough", client=client, timeout_seconds=7.5)
    assert client.calls[0]["timeout"] == 7.5


# ---------------------------------------------------------------------------
# Batching
# ---------------------------------------------------------------------------

def test_embed_texts_batched_splits_into_multiple_batches():
    client = _FakeOpenAIClient()
    texts = [f"text {i}" for i in range(25)]
    embeddings, errors = embed_texts_batched(texts, client=client, batch_size=10)
    assert len(embeddings) == 25
    assert errors == {}
    # 25 texts at batch_size=10 -> 3 API calls (10, 10, 5).
    assert len(client.calls) == 3
    assert [len(c["input"]) for c in client.calls] == [10, 10, 5]


def test_embed_texts_batched_single_batch_when_under_size():
    client = _FakeOpenAIClient()
    embeddings, errors = embed_texts_batched(["a", "b", "c"], client=client, batch_size=100)
    assert len(client.calls) == 1
    assert len(embeddings) == 3


# ---------------------------------------------------------------------------
# Retry with bounded exponential backoff
# ---------------------------------------------------------------------------

def test_embed_texts_batched_retries_and_recovers():
    client = _FakeOpenAIClient(fail_times=2)
    sleeps: list[float] = []
    embeddings, errors = embed_texts_batched(
        ["a"], client=client, max_retries=3, backoff_base_seconds=0.01,
        sleep=sleeps.append,
    )
    assert errors == {}
    assert len(embeddings) == 1
    # Two failures before success -> two backoff sleeps, exponential.
    assert sleeps == [0.01, 0.02]


def test_embed_texts_batched_records_failure_after_exhausting_retries():
    client = _FakeOpenAIClient(fail_times=99)
    embeddings, errors = embed_texts_batched(
        ["a"], client=client, max_retries=3, backoff_base_seconds=0.001, sleep=lambda s: None,
    )
    assert embeddings == {}
    assert 0 in errors
    assert "simulated transient failure" in errors[0]


def test_one_failed_batch_does_not_abort_remaining_batches():
    """A batch that exhausts retries must not prevent later batches from
    being attempted."""
    client = _FakeOpenAIClient(fail_times=99)  # every call fails
    embeddings, errors = embed_texts_batched(
        ["a", "b", "c", "d"], client=client, batch_size=2,
        max_retries=1, backoff_base_seconds=0.001, sleep=lambda s: None,
    )
    assert embeddings == {}
    assert set(errors.keys()) == {0, 1, 2, 3}
    # Both batches were attempted despite the first failing.
    assert len(client.calls) == 2


# ---------------------------------------------------------------------------
# Idempotent upsert / content-hash-gated backfill
# ---------------------------------------------------------------------------

def test_upsert_is_idempotent_on_evidence_record_model_version():
    supabase = _FakeSupabaseClient()
    row = {
        "evidence_record_id": 1, "plant_id": 1, "embedding": [0.1] * EMBEDDING_DIMENSION,
        "embedding_text": "text v1", "embedding_model": EMBEDDING_MODEL,
        "embedding_version": EMBEDDING_VERSION, "content_hash": "hash1",
    }
    upsert_evidence_embeddings([row], supabase=supabase)
    upsert_evidence_embeddings([row], supabase=supabase)
    stored = supabase._store["evidence_embeddings"]
    assert len(stored) == 1  # second upsert replaced, did not duplicate


def test_fetch_existing_content_hashes_filters_by_model_and_version():
    supabase = _FakeSupabaseClient()
    supabase._store["evidence_embeddings"] = [
        {"evidence_record_id": 1, "content_hash": "h1", "embedding_model": EMBEDDING_MODEL, "embedding_version": EMBEDDING_VERSION},
        {"evidence_record_id": 2, "content_hash": "h2", "embedding_model": EMBEDDING_MODEL, "embedding_version": "v0-old"},
    ]
    hashes = fetch_existing_content_hashes([1, 2], supabase=supabase)
    assert hashes == {1: "h1"}  # record 2 excluded: different embedding_version


def test_backfill_skips_unchanged_hash_and_reembeds_changed_one():
    import pandas as pd
    from unittest.mock import patch
    from indication_candidate_discovery import _build_plant_evidence_index

    class _Engine:
        def __init__(self, rows):
            self.evidence_df = pd.DataFrame()
            self.scientific_evidence_df = pd.DataFrame()
            self.evidence_records_df = pd.DataFrame(rows)

        def _pick(self, row, names):
            for name in names:
                try:
                    value = row.get(name, "")
                except AttributeError:
                    value = ""
                if value is not None and str(value).strip() and str(value).lower() not in {"nan", "none", "null"}:
                    return str(value).strip()
            return ""

        def _split_compound_terms(self, value):
            return [x.strip() for x in str(value).split(";") if x.strip()]

        def _evidence_level(self, text):
            return "Unknown"

    engine = _Engine([
        {"Scientific_Name": "Ginkgo biloba", "Evidence_Record_ID": "1", "Plant_ID": 10, "Target_Indication": "Cognitive decline"},
        {"Scientific_Name": "Ginkgo biloba", "Evidence_Record_ID": "2", "Plant_ID": 10, "Target_Indication": "Memory support"},
    ])

    from evidence_embedding_text import build_evidence_embedding_text, compute_content_hash
    index = _build_plant_evidence_index(engine)
    all_records = [r for records in index.values() for r in records]
    hash_by_id = {}
    for r in all_records:
        r = dict(r)
        r["plant_name"] = "Ginkgo biloba"
        text = build_evidence_embedding_text(r)
        hash_by_id[r["record_id"]] = compute_content_hash(text)

    # Record "1" already stored under its CURRENT hash (unchanged) --
    # must be skipped. Record "2" stored under a STALE hash (content
    # changed since last embedded) -- must be re-embedded.
    existing_hashes = {"1": hash_by_id["1"], "2": "stale-hash-from-before"}

    fake_openai = _FakeOpenAIClient()

    def _fake_embed_texts_batched(texts, **kwargs):
        embeddings, errors = embed_texts_batched(texts, client=fake_openai)
        return embeddings, errors

    upserted_rows = []

    def _fake_upsert(rows, **kwargs):
        upserted_rows.extend(rows)

    with patch.object(backfill_mod, "fetch_existing_content_hashes", return_value=existing_hashes), \
         patch.object(backfill_mod, "embed_texts_batched", side_effect=_fake_embed_texts_batched), \
         patch.object(backfill_mod, "upsert_evidence_embeddings", side_effect=_fake_upsert):
        stats = backfill_mod.run_backfill(engine=engine, model=EMBEDDING_MODEL, version=EMBEDDING_VERSION)

    assert stats.scanned == 2
    assert stats.skipped == 1
    assert stats.updated == 1
    assert stats.embedded == 0
    assert stats.failed == 0
    assert len(fake_openai.calls) == 1  # only the changed record was embedded
    assert len(upserted_rows) == 1
    assert upserted_rows[0]["evidence_record_id"] == "2"


def test_hash_gated_skip_logic_directly():
    """Direct test of the skip-vs-reembed decision, independent of network
    plumbing: unchanged hash -> skip; changed hash -> re-embed."""
    existing = {1: "hash-A", 2: "hash-old"}
    candidates = [(1, 10, "Ginkgo biloba", "text unchanged", "hash-A"),
                  (2, 10, "Ginkgo biloba", "text changed", "hash-new")]
    to_embed = [c for c in candidates if existing.get(c[0]) != c[4]]
    skipped = [c for c in candidates if existing.get(c[0]) == c[4]]
    assert [c[0] for c in to_embed] == [2]
    assert [c[0] for c in skipped] == [1]


def test_model_version_change_forces_refresh():
    """A record with a stored hash under an OLD embedding_version must not
    be treated as already embedded under the NEW version -- fetch_existing_
    content_hashes filters by (model, version), so it simply won't appear,
    forcing a re-embed."""
    supabase = _FakeSupabaseClient()
    supabase._store["evidence_embeddings"] = [
        {"evidence_record_id": 5, "content_hash": "same-text-hash", "embedding_model": EMBEDDING_MODEL, "embedding_version": "v0"},
    ]
    hashes_under_new_version = fetch_existing_content_hashes(
        [5], embedding_model=EMBEDDING_MODEL, embedding_version="v1", supabase=supabase,
    )
    assert hashes_under_new_version == {}  # nothing found under v1 -> will re-embed


# ---------------------------------------------------------------------------
# RPC call shape
# ---------------------------------------------------------------------------

def test_match_evidence_embeddings_rpc_called_with_expected_params():
    from vector_search import match_evidence_embeddings

    supabase = _FakeSupabaseClient()
    supabase.set_rpc_result([
        {"evidence_record_id": 1, "plant_id": 10, "cosine_similarity": 0.9,
         "embedding_model": EMBEDDING_MODEL, "embedding_version": EMBEDDING_VERSION},
    ])
    results = match_evidence_embeddings([0.1] * EMBEDDING_DIMENSION, supabase=supabase)
    assert len(supabase.rpc_calls) == 1
    assert supabase.rpc_calls[0]["name"] == "match_evidence_embeddings"
    assert results == [
        {"evidence_record_id": 1, "plant_id": 10, "cosine_similarity": 0.9,
         "embedding_model": EMBEDDING_MODEL, "embedding_version": EMBEDDING_VERSION},
    ]


def test_match_evidence_embeddings_rpc_failure_returns_empty_list_not_raise():
    from vector_search import match_evidence_embeddings

    class _FailingSupabase:
        def rpc(self, name, params):
            raise RuntimeError("RPC unavailable")

    results = match_evidence_embeddings([0.1] * EMBEDDING_DIMENSION, supabase=_FailingSupabase())
    assert results == []


def test_match_evidence_embeddings_returns_empty_for_empty_query_embedding():
    from vector_search import match_evidence_embeddings
    assert match_evidence_embeddings([], supabase=_FakeSupabaseClient()) == []
    assert match_evidence_embeddings(None, supabase=_FakeSupabaseClient()) == []
