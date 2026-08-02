#!/usr/bin/env python3
"""Backfill evidence_embeddings from evidence_records.

CLI-only, per architecture requirement -- Streamlit is never required to
run a bulk backfill.

Usage:
    python backfill_evidence_embeddings.py [--dry-run] [--plant NAME]
        [--evidence-record-id ID [--evidence-record-id ID ...]]
        [--limit N] [--batch-size N]

Idempotent and resumable: a record whose content_hash under the current
embedding_model/embedding_version already matches what's stored is
skipped, so re-running after a partial failure only (re-)processes what
did not complete last time.

Prints exact statistics: scanned, skipped, embedded, updated, failed.
"""
from __future__ import annotations

import argparse
import sys

from embedding_service import (
    EMBEDDING_MODEL,
    EMBEDDING_VERSION,
    BackfillStats,
    embed_texts_batched,
    fetch_existing_content_hashes,
    upsert_evidence_embeddings,
)
from evidence_embedding_text import build_evidence_embedding_text, compute_content_hash
from indication_candidate_discovery import _build_plant_evidence_index, _pick_from_row


def _build_engine():
    """Real production engine, backed by Supabase. Imported lazily so this
    module can be imported (e.g. by tests) without requiring Supabase
    credentials to be configured."""
    from botanical_rd_candidate_engine import BotanicalRDCandidateEngine
    import supabase_data

    return BotanicalRDCandidateEngine(
        evidence_df=supabase_data.load_scientific_evidence_df(),
        candidate_data=[],
        use_live_search=False,
        plant_compounds_df=supabase_data.load_plant_compounds_df(),
        compound_profiles_df=supabase_data.load_compound_profiles_df(),
        scientific_evidence_df=supabase_data.load_scientific_evidence_df(),
        evidence_records_df=supabase_data.load_evidence_records_df(),
    )


def _iter_embeddable_records(engine, *, plant_filter: str | None, record_id_filter: set):
    """Yield (evidence_record_id, plant_id, plant_name, embedding_text) for
    every embeddable record in the evidence index, applying filters.

    Reuses indication_candidate_discovery._build_plant_evidence_index()
    (the same per-record field extraction Step 5 itself uses) rather than
    re-deriving field names independently -- one source of truth for what
    a record's tier1/tier2/tier3 text is.
    """
    index = _build_plant_evidence_index(engine)
    evidence_df = getattr(engine, "evidence_records_df", None)
    plant_id_by_record_id: dict[object, object] = {}
    if evidence_df is not None and not evidence_df.empty:
        for _, row in evidence_df.iterrows():
            rid = row.get("Evidence_Record_ID", row.get("id"))
            pid = row.get("Plant_ID", row.get("plant_id"))
            if rid is not None:
                plant_id_by_record_id[rid] = pid

    for plant_key, records in index.items():
        for record in records:
            record_id = record.get("record_id")
            if record_id_filter and str(record_id) not in record_id_filter:
                continue
            plant_name = record.get("plant_name", plant_key)
            if plant_filter and plant_filter.strip().lower() not in str(plant_name).lower():
                continue
            plant_id = plant_id_by_record_id.get(record_id)
            embedding_record = dict(record)
            embedding_record["plant_name"] = plant_name
            text = build_evidence_embedding_text(embedding_record)
            if not text:
                continue  # proxy/excluded record, or genuinely empty -- not an error
            yield record_id, plant_id, plant_name, text


def run_backfill(
    *,
    dry_run: bool = False,
    plant_filter: str | None = None,
    record_id_filter: set | None = None,
    limit: int | None = None,
    batch_size: int = 100,
    model: str = EMBEDDING_MODEL,
    version: str = EMBEDDING_VERSION,
    engine=None,
) -> BackfillStats:
    stats = BackfillStats()
    engine = engine or _build_engine()
    record_id_filter = record_id_filter or set()

    candidates: list[tuple[object, object, str, str, str]] = []  # (id, plant_id, plant, text, hash)
    for record_id, plant_id, plant_name, text in _iter_embeddable_records(
        engine, plant_filter=plant_filter, record_id_filter=record_id_filter,
    ):
        stats.scanned += 1
        content_hash = compute_content_hash(text)
        candidates.append((record_id, plant_id, plant_name, text, content_hash))
        if limit and len(candidates) >= limit:
            break

    if not candidates:
        return stats

    existing_hashes = fetch_existing_content_hashes(
        (c[0] for c in candidates), embedding_model=model, embedding_version=version,
    )

    to_embed = []
    for record_id, plant_id, plant_name, text, content_hash in candidates:
        if existing_hashes.get(record_id) == content_hash:
            stats.skipped += 1
            continue
        to_embed.append((record_id, plant_id, text, content_hash))

    if not to_embed:
        return stats

    if dry_run:
        stats.embedded = len(to_embed)  # would-embed count, nothing written
        return stats

    texts = [t[2] for t in to_embed]
    embeddings, errors = embed_texts_batched(texts, batch_size=batch_size)

    rows = []
    for i, (record_id, plant_id, text, content_hash) in enumerate(to_embed):
        if i in errors:
            stats.failed += 1
            stats.failures.append((record_id, errors[i]))
            continue
        was_existing = record_id in existing_hashes
        rows.append({
            "evidence_record_id": record_id,
            "plant_id": plant_id,
            "embedding": embeddings[i],
            "embedding_text": text,
            "embedding_model": model,
            "embedding_version": version,
            "content_hash": content_hash,
        })
        if was_existing:
            stats.updated += 1
        else:
            stats.embedded += 1

    if rows:
        upsert_evidence_embeddings(rows)

    return stats


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Backfill evidence_embeddings.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--plant", default=None, help="Filter to plants whose scientific name contains this substring.")
    parser.add_argument("--evidence-record-id", action="append", default=[], help="Repeatable. Filter to specific evidence record IDs.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args(argv)

    stats = run_backfill(
        dry_run=args.dry_run,
        plant_filter=args.plant,
        record_id_filter=set(args.evidence_record_id) if args.evidence_record_id else None,
        limit=args.limit,
        batch_size=args.batch_size,
    )

    print(f"scanned={stats.scanned} skipped={stats.skipped} embedded={stats.embedded} "
          f"updated={stats.updated} failed={stats.failed}")
    if stats.failures:
        print("Failures:")
        for record_id, error in stats.failures:
            print(f"  evidence_record_id={record_id}: {error}")
    return 1 if stats.failed else 0


if __name__ == "__main__":
    sys.exit(main())
