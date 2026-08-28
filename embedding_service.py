"""Embedding generation and storage service for evidence_embeddings.

Two distinct entry points, deliberately kept separate:

- embed_query(): used at Step 5 RUNTIME (indication_candidate_discovery.py),
  once per discovery run. Never raises -- any failure (missing API key,
  network error, timeout) is caught and returns None, so Step 5 falls back
  to the deterministic lexical engine instead of crashing.

- embed_texts_batched() / backfill_evidence_embeddings.py: used OFFLINE,
  via the CLI backfill script, to precompute and store evidence-record
  embeddings. This path DOES surface failures (as per-item stats), because
  a backfill run that silently drops failures is worse than one that
  reports them.

Reuses the existing get_openai_client() convention from llm_extractor.py
(OPENAI_API_KEY from st.secrets or env) rather than inventing a second one.

VERIFIED ENVIRONMENT CONSTRAINT: the sandbox this module was developed and
tested in has no outbound network access to api.openai.com or Supabase, so
the OpenAI/Supabase calls below are exercised in tests only via mocking
(see test_embedding_service.py), never against the real services. The
request/response shapes used here match the openai==2.45.0 SDK's
documented `client.embeddings.create(...)` interface and the supabase-py
`.table(...).upsert(...)`/`.rpc(...)` interface already used elsewhere in
this repository (database.py, supabase_data.py).
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

from evidence_embedding_text import build_evidence_embedding_text, compute_content_hash
from ai_usage_telemetry import (
    AIProviderCircuitOpenError,
    BREAKER_TRIPPING_CATEGORIES,
    classify_llm_error,
    get_ai_run_tracker,
)

TASK_EMBEDDING_QUERY = "embedding_query"

# Part 4/14 -- one query embedding is reused for as long as the process
# lives, keyed on (normalized text, model). This is what makes a
# Streamlit rerun on the SAME indication query never re-call OpenAI: the
# first run computes and caches the vector, every later rerun (or a
# second indication that happens to normalize the same way) is a plain
# dict lookup. Cleared only by clear_query_cache() (test-only) --
# there is no size/time eviction because one process handles at most a
# small, human-driven number of distinct queries.
_QUERY_EMBEDDING_CACHE: dict[str, list[float]] = {}


def _query_cache_key(text: str, model: str) -> str:
    normalized = " ".join(text.strip().lower().split())
    return hashlib.sha256(f"{model}|{normalized}".encode("utf-8")).hexdigest()


def clear_query_cache() -> None:
    """Test-only helper -- forces the next embed_query() call to hit the
    (mocked) API again."""
    _QUERY_EMBEDDING_CACHE.clear()

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSION = 1536
# Bump this when build_evidence_embedding_text()'s field composition
# changes in a way that meaningfully changes embedding meaning (not on
# every unrelated code change). A version bump makes every existing row's
# content_hash comparison irrelevant for that version, forcing a full
# re-embed under the new version while old-version rows remain queryable
# (and are excluded from RPC results once the runtime path is configured
# to request the new version -- see vector_search.py).
EMBEDDING_VERSION = "v1"

_DEFAULT_BATCH_SIZE = 100
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_TIMEOUT_SECONDS = 30
_DEFAULT_BACKOFF_BASE_SECONDS = 1.0
# PostgREST (Supabase's REST layer) rejects requests whose URL/JSON body
# grows too large -- a single `.in_("evidence_record_id", ids)` filter with
# many thousands of ids can exceed that limit and fail with a 400 ("JSON
# could not be generated") before any embedding work even starts. Querying
# in bounded pages avoids this regardless of how large a backfill run is.
_DEFAULT_HASH_FETCH_BATCH_SIZE = 150
# Each upsert row carries a full EMBEDDING_DIMENSION-length float vector
# (plus text/metadata), so it is far heavier per-row than an id-only hash
# lookup. Sending every pending row in one request risks the same
# request-size failure as the hash lookup did -- observed in production as
# a Supabase/Cloudflare 520 ("Web server is returning an unknown error")
# with a large limit=5000 run, because the oversized request body never
# reached PostgREST as valid JSON at all. Batching the write side keeps
# each request small regardless of how many rows a single backfill run
# needs to write.
_DEFAULT_UPSERT_BATCH_SIZE = 50


# OpenAI's text-embedding-3-small/large models reject any single input
# longer than this many tokens ("Invalid 'input[x]': maximum input length
# is 8192 tokens"). Some evidence records (long abstracts/raw source text)
# exceed this, which previously surfaced as a per-item backfill failure
# instead of being handled before the request was ever sent.
_EMBEDDING_MAX_INPUT_TOKENS = 8192
# Stay a little under the hard limit -- the fallback estimator below is
# approximate, so a small margin keeps a slightly-off estimate from still
# landing on or over the real boundary.
_EMBEDDING_TOKEN_SAFETY_MARGIN = 32


def get_openai_client():
    """Reuses llm_client.py's single centralized implementation rather
    than a second one (llm_extractor.py does the same). Imported lazily
    so importing this module never requires the `openai` package's
    client construction to succeed (useful for tests that only exercise
    pure functions)."""
    from llm_client import get_openai_client as _get_client
    return _get_client()


_token_encoding = None
_token_encoding_load_failed = False


def _get_token_encoding():
    """Lazily load a tiktoken encoding for exact token counting.

    Returns None if tiktoken is not installed, or if loading its encoding
    data fails for any reason (e.g. no network access to fetch it on first
    use -- tiktoken downloads its BPE ranks file the first time an
    encoding is requested and caches it locally after that). Callers must
    treat None as "use the conservative character-based estimate instead"
    and must never raise or block backfill/runtime embedding on this.

    cl100k_base is the tokenizer used by the text-embedding-3-small/large
    models (same family as EMBEDDING_MODEL).
    """
    global _token_encoding, _token_encoding_load_failed
    if _token_encoding is not None or _token_encoding_load_failed:
        return _token_encoding
    try:
        import tiktoken
        _token_encoding = tiktoken.get_encoding("cl100k_base")
    except Exception as exc:
        print(
            "[embedding_service] tiktoken encoding unavailable, falling "
            f"back to a conservative character-based token estimate: {exc}"
        )
        _token_encoding_load_failed = True
        _token_encoding = None
    return _token_encoding


def _truncate_to_token_limit(
    text: str, *, max_tokens: int = _EMBEDDING_MAX_INPUT_TOKENS, label: str = "input",
) -> str:
    """Return ``text``, truncated if necessary so it never exceeds
    ``max_tokens`` tokens for the embedding model -- this is what makes
    OpenAI's per-input token limit ("Invalid 'input[x]': maximum input
    length is 8192 tokens") impossible to hit, rather than something the
    caller has to recover from after the API rejects a batch.

    Uses an exact tiktoken count when available. When it is not (see
    ``_get_token_encoding``), falls back to a deliberately conservative
    character-based estimate: ~3 characters/token, well below the ~4
    chars/token typical of English prose, so the estimate errs toward
    truncating a bit more than strictly necessary rather than risking an
    under-count that would still exceed the real limit.

    Logs once whenever truncation actually occurs, naming ``label`` so the
    backfill log can identify which record was affected.
    """
    if not text:
        return text
    budget = max(1, max_tokens - _EMBEDDING_TOKEN_SAFETY_MARGIN)

    encoding = _get_token_encoding()
    if encoding is not None:
        tokens = encoding.encode(text)
        if len(tokens) <= budget:
            return text
        truncated = encoding.decode(tokens[:budget])
        print(
            f"[embedding_service] Truncated {label} from {len(tokens)} to "
            f"{budget} tokens (exceeded the embedding model's "
            f"{max_tokens}-token input limit)."
        )
        return truncated

    char_budget = budget * 3
    if len(text) <= char_budget:
        return text
    print(
        f"[embedding_service] Truncated {label} from {len(text)} to "
        f"{char_budget} characters (no tokenizer available; applied a "
        f"conservative character-based limit for the embedding model's "
        f"{max_tokens}-token input limit)."
    )
    return text[:char_budget]


@dataclass
class BackfillStats:
    scanned: int = 0
    skipped: int = 0
    embedded: int = 0
    updated: int = 0
    failed: int = 0
    failures: list[tuple[object, str]] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "scanned": self.scanned,
            "skipped": self.skipped,
            "embedded": self.embedded,
            "updated": self.updated,
            "failed": self.failed,
        }


def embed_query(
    query_text: str,
    *,
    client=None,
    model: str = EMBEDDING_MODEL,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
) -> list[float] | None:
    """Embed one query string for a single Step 5 run.

    Never raises. Any failure (missing OPENAI_API_KEY, network error,
    timeout, malformed response) is caught and logged; the caller receives
    None and must fall back to the deterministic lexical engine.
    """
    text = str(query_text or "").strip()
    if not text:
        return None
    text = _truncate_to_token_limit(text, label="query")

    # Cache only calls using the production-owned client.  An explicitly
    # injected client is a test/admin boundary and must exercise that client
    # on every invocation; otherwise a prior production/test cache entry can
    # mask failures, wrong dimensions, or timeout plumbing.
    use_query_cache = client is None
    cache_key = _query_cache_key(text, model)
    if use_query_cache and cache_key in _QUERY_EMBEDDING_CACHE:
        get_ai_run_tracker().record_call(TASK_EMBEDDING_QUERY, cached=True, success=True)
        return list(_QUERY_EMBEDDING_CACHE[cache_key])

    tracker = get_ai_run_tracker()
    if tracker.breaker_active():
        # Part 13 -- a prior insufficient-quota/auth failure this run
        # already means every further OpenAI call is doomed; skip
        # straight to the lexical fallback without attempting one.
        tracker.record_skipped_breaker(TASK_EMBEDDING_QUERY)
        print(
            "[embedding_service] embed_query skipped, provider circuit "
            f"open this run ({tracker.breaker_category}): falling back to lexical engine"
        )
        return None
    if not tracker.check_budget(TASK_EMBEDDING_QUERY):
        print("[embedding_service] embed_query: AI_BUDGET_EXHAUSTED, falling back to lexical engine")
        return None

    _t0 = time.monotonic()
    try:
        active_client = client or get_openai_client()
        tracker.record_provider_attempt(TASK_EMBEDDING_QUERY)
        response = active_client.embeddings.create(
            model=model, input=[text], timeout=timeout_seconds,
        )
        vector = response.data[0].embedding
        if not vector or len(vector) != EMBEDDING_DIMENSION:
            print(
                f"[embedding_service] embed_query: unexpected embedding "
                f"dimension {len(vector) if vector else 0}, expected "
                f"{EMBEDDING_DIMENSION}"
            )
            tracker.record_call(
                TASK_EMBEDDING_QUERY, cached=False, success=False,
                elapsed_seconds=time.monotonic() - _t0, error_category="malformed_model_output",
            )
            return None
        vector_list = list(vector)
        if use_query_cache:
            _QUERY_EMBEDDING_CACHE[cache_key] = vector_list
        usage = getattr(response, "usage", None)
        embedding_input_tokens = 0
        if usage is not None:
            # Embeddings API currently exposes prompt_tokens/total_tokens.
            # Accept input_tokens too for forward compatibility.
            embedding_input_tokens = int(
                getattr(usage, "prompt_tokens", 0)
                or getattr(usage, "input_tokens", 0)
                or getattr(usage, "total_tokens", 0)
                or 0
            )
        tracker.record_call(
            TASK_EMBEDDING_QUERY, cached=False, success=True,
            elapsed_seconds=time.monotonic() - _t0,
            input_tokens=embedding_input_tokens, model=model,
        )
        return vector_list
    except Exception as exc:
        error_category = classify_llm_error(exc)
        tracker.record_call(
            TASK_EMBEDDING_QUERY, cached=False, success=False,
            elapsed_seconds=time.monotonic() - _t0, error_category=error_category,
        )
        if tracker.managed_run and error_category in BREAKER_TRIPPING_CATEGORIES:
            tracker.trip_breaker(error_category, str(exc))
        print(f"[embedding_service] embed_query failed, falling back to lexical engine: {exc}")
        return None


def _embed_batch_with_retry(
    client, texts: list[str], model: str, timeout_seconds: float,
    max_retries: int, backoff_base_seconds: float,
    sleep: Callable[[float], None] = time.sleep,
) -> list[list[float]]:
    """Embed one batch, retrying with bounded exponential backoff.
    Raises the last exception if every attempt fails -- the caller
    (embed_texts_batched) is responsible for turning that into a per-item
    failure record rather than aborting the whole backfill run."""
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = client.embeddings.create(
                model=model, input=texts, timeout=timeout_seconds,
            )
            return [list(item.embedding) for item in response.data]
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                sleep(backoff_base_seconds * (2 ** attempt))
    raise last_exc  # type: ignore[misc]


def embed_texts_batched(
    texts: Sequence[str],
    *,
    client=None,
    model: str = EMBEDDING_MODEL,
    batch_size: int = _DEFAULT_BATCH_SIZE,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    backoff_base_seconds: float = _DEFAULT_BACKOFF_BASE_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[dict[int, list[float]], dict[int, str]]:
    """Embed many texts in batches. Returns (embeddings_by_index,
    errors_by_index) -- a failed batch marks every index in that batch as
    failed (with the error message) and processing continues with the next
    batch, so one bad batch does not abort an entire backfill run."""
    active_client = client or get_openai_client()
    embeddings: dict[int, list[float]] = {}
    errors: dict[int, str] = {}

    indices = list(range(len(texts)))
    for start in range(0, len(indices), batch_size):
        batch_indices = indices[start:start + batch_size]
        batch_texts = [
            _truncate_to_token_limit(texts[i], label=f"evidence embedding text (index {i})")
            for i in batch_indices
        ]
        try:
            vectors = _embed_batch_with_retry(
                active_client, batch_texts, model, timeout_seconds,
                max_retries, backoff_base_seconds, sleep,
            )
            for idx, vector in zip(batch_indices, vectors):
                embeddings[idx] = vector
        except Exception as exc:
            for idx in batch_indices:
                errors[idx] = str(exc)
    return embeddings, errors


def _canonical_id_key(value) -> str:
    """Return a stable STRING identity key for an id, tolerating harmless
    representation differences (10 / 10.0 / "10" all -> "10"). Mirrors
    backfill_evidence_embeddings._canonical_id_key; duplicated here (rather
    than imported) so embedding_service.py has no dependency on the
    backfill CLI module."""
    if value is None:
        return ""
    try:
        if value != value:  # pandas / NumPy NaN
            return ""
    except Exception:
        pass
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return ""
    try:
        numeric = float(text)
        if numeric.is_integer():
            return str(int(numeric))
    except (TypeError, ValueError, OverflowError):
        pass
    return text


def _to_bigint(value) -> int | None:
    """Normalize a value to a Postgres-bigint-compatible int, or None if it
    cannot be represented as one. Used only when building the real database
    payload immediately before the Supabase call -- never applied to rows
    handed back to a caller."""
    key = _canonical_id_key(value)
    if not key:
        return None
    try:
        return int(key)
    except (TypeError, ValueError, OverflowError):
        return None


def upsert_evidence_embeddings(
    rows: list[dict], *, supabase=None, batch_size: int = _DEFAULT_UPSERT_BATCH_SIZE,
) -> None:
    """Idempotently upsert one row per conflict key.

    The caller's rows (and each row dict inside it) are never mutated --
    this is the externally observed boundary: a caller (including test
    mocks that patch this function out entirely) must see exactly the
    evidence_record_id/plant_id representation it was given, e.g. a string
    "2", not an int.

    A SEPARATE database payload is built here, immediately before the real
    Supabase call, with evidence_record_id/plant_id normalized to
    Postgres-bigint-compatible ints (bigint foreign-key columns require it).
    That payload is deduplicated defensively by conflict key -- PostgreSQL
    rejects a single INSERT .. ON CONFLICT DO UPDATE command when the
    submitted payload contains the same conflict key more than once
    ("cannot affect row a second time") -- even though the canonical
    backfill iterator and its own pre-upsert dedupe pass also guarantee
    uniqueness. This keeps every future caller safe and makes the storage
    boundary authoritative.

    The deduplicated payload is then written in bounded pages of
    ``batch_size`` rows (default ``_DEFAULT_UPSERT_BATCH_SIZE``) rather than
    one single request. Each row carries a full embedding vector, so a
    large backfill run (thousands of rows to write) can produce a request
    body large enough that Supabase/Cloudflare reject it outright -- this
    surfaced in production as a 520 ("Web server is returning an unknown
    error") on `.execute()`, not a normal PostgREST error, because the
    oversized body never made it to PostgREST as valid JSON. Paging the
    write keeps every request small regardless of how many rows a run
    produces, exactly mirroring the paging already applied to
    fetch_existing_content_hashes() on the read side.
    """
    if not rows:
        return

    db_payload: dict[tuple[int, str, str], dict] = {}
    for row in rows:
        record_id = _to_bigint(row.get("evidence_record_id"))
        plant_id = _to_bigint(row.get("plant_id"))
        model = str(row.get("embedding_model") or "").strip()
        version = str(row.get("embedding_version") or "").strip()
        if record_id is None or plant_id is None:
            raise ValueError(
                "Each evidence embedding row requires a bigint-compatible "
                "evidence_record_id and plant_id value."
            )
        if not model or not version:
            raise ValueError(
                "Each evidence embedding row requires embedding_model and "
                "embedding_version."
            )
        db_row = dict(row)  # copy -- never mutate the caller-owned row
        db_row["evidence_record_id"] = record_id
        db_row["plant_id"] = plant_id
        # Last occurrence wins deterministically; canonical callers should
        # normally submit only one occurrence per conflict key.
        db_payload[(record_id, model, version)] = db_row

    if supabase is None:
        from supabase_client import get_supabase_client
        client = get_supabase_client()
    else:
        client = supabase

    page_size = batch_size if batch_size and batch_size > 0 else _DEFAULT_UPSERT_BATCH_SIZE
    values = list(db_payload.values())
    for start in range(0, len(values), page_size):
        chunk = values[start:start + page_size]
        client.table("evidence_embeddings").upsert(
            chunk,
            on_conflict="evidence_record_id,embedding_model,embedding_version",
        ).execute()


def fetch_existing_content_hashes(
    evidence_record_ids: Iterable[int],
    *,
    embedding_model: str = EMBEDDING_MODEL,
    embedding_version: str = EMBEDDING_VERSION,
    supabase=None,
    batch_size: int = _DEFAULT_HASH_FETCH_BATCH_SIZE,
) -> dict[int, str]:
    """Map evidence_record_id -> content_hash for already-stored embeddings
    under this model/version, used to skip unchanged records during
    backfill (idempotent, resumable).

    Queries in bounded pages of ``batch_size`` ids at a time (default
    ``_DEFAULT_HASH_FETCH_BATCH_SIZE``) rather than sending every id in one
    ``.in_(...)`` filter. A single request with many thousands of ids can
    exceed PostgREST's request-size/URL limit and fail with a 400 ("JSON
    could not be generated") -- and it does so before any embedding call
    happens, so a large backfill run would fail immediately with no
    progress at all. Paging keeps each request small regardless of how
    many evidence records are being backfilled (tens of thousands or more),
    and the results from every page are merged into one dict, so callers
    see exactly the same return shape as a single-request call.
    """
    ids = []
    for raw_id in evidence_record_ids:
        if raw_id is None:
            continue
        bigint_id = _to_bigint(raw_id)
        ids.append(bigint_id if bigint_id is not None else raw_id)
    if not ids:
        return {}
    if supabase is None:
        from supabase_client import get_supabase_client
        client = get_supabase_client()
    else:
        client = supabase

    page_size = batch_size if batch_size and batch_size > 0 else _DEFAULT_HASH_FETCH_BATCH_SIZE

    hashes: dict[int, str] = {}
    for start in range(0, len(ids), page_size):
        page_ids = ids[start:start + page_size]
        response = (
            client.table("evidence_embeddings")
            .select("evidence_record_id,content_hash")
            .eq("embedding_model", embedding_model)
            .eq("embedding_version", embedding_version)
            .in_("evidence_record_id", page_ids)
            .execute()
        )
        for row in (response.data or []):
            hashes[row["evidence_record_id"]] = row["content_hash"]
    return hashes
