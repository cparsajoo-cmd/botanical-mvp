"""Runtime wrapper for the match_evidence_embeddings Postgres RPC
(see 0005_add_evidence_embeddings.sql).

Called exactly ONCE per Step 5 discovery run, with the already-computed
query embedding -- never once per plant, never once per evidence record.
See indication_candidate_discovery.py's discover_indication_candidates().
"""
from __future__ import annotations

from embedding_service import EMBEDDING_MODEL, EMBEDDING_VERSION


def match_evidence_embeddings(
    query_embedding: list[float],
    *,
    match_count: int = 200,
    similarity_threshold: float = 0.0,
    plant_ids: list[int] | None = None,
    embedding_model: str = EMBEDDING_MODEL,
    embedding_version: str = EMBEDDING_VERSION,
    supabase=None,
) -> list[dict]:
    """Call the match_evidence_embeddings RPC once. Returns a list of dicts
    with evidence_record_id/plant_id/cosine_similarity/embedding_model/
    embedding_version, or an empty list if the RPC is unavailable or fails
    -- callers must treat an empty list as "no embedding matches", not as
    an error to propagate. This is what lets discover_indication_candidates()
    fall back to the deterministic engine without crashing Step 5 when the
    migration hasn't been applied yet, the RPC errors, or the database is
    briefly unavailable.
    """
    if not query_embedding:
        return []
    try:
        from supabase_client import get_supabase_client
        client = supabase or get_supabase_client()
        response = client.rpc(
            "match_evidence_embeddings",
            {
                "query_embedding": query_embedding,
                "match_count": match_count,
                "similarity_threshold": similarity_threshold,
                "embedding_model_filter": embedding_model,
                "embedding_version_filter": embedding_version,
                "optional_plant_ids": plant_ids,
            },
        ).execute()
        return list(response.data or [])
    except Exception as exc:
        print(f"[vector_search] match_evidence_embeddings RPC failed, falling back to lexical engine: {exc}")
        return []
