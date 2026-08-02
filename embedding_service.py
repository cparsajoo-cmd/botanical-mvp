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

import time
from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

from evidence_embedding_text import build_evidence_embedding_text, compute_content_hash

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


def get_openai_client():
    """Reuses llm_extractor.py's exact existing convention rather than a
    second one. Imported lazily so importing this module never requires
    the `openai` package's client construction to succeed (useful for
    tests that only exercise pure functions)."""
    from llm_extractor import get_openai_client as _get_client
    return _get_client()


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
    try:
        active_client = client or get_openai_client()
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
            return None
        return list(vector)
    except Exception as exc:
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
        batch_texts = [texts[i] for i in batch_indices]
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


def upsert_evidence_embeddings(rows: list[dict], *, supabase=None) -> None:
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
    client.table("evidence_embeddings").upsert(
        list(db_payload.values()),
        on_conflict="evidence_record_id,embedding_model,embedding_version",
    ).execute()


def fetch_existing_content_hashes(
    evidence_record_ids: Iterable[int],
    *,
    embedding_model: str = EMBEDDING_MODEL,
    embedding_version: str = EMBEDDING_VERSION,
    supabase=None,
) -> dict[int, str]:
    """Map evidence_record_id -> content_hash for already-stored embeddings
    under this model/version, used to skip unchanged records during
    backfill (idempotent, resumable)."""
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
    response = (
        client.table("evidence_embeddings")
        .select("evidence_record_id,content_hash")
        .eq("embedding_model", embedding_model)
        .eq("embedding_version", embedding_version)
        .in_("evidence_record_id", ids)
        .execute()
    )
    return {row["evidence_record_id"]: row["content_hash"] for row in (response.data or [])}
