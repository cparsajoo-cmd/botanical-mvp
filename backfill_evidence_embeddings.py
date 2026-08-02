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
from indication_candidate_discovery import _pick_from_row


def _canonical_id_key(value):
    """Return a stable lookup key for IDs coming from pandas/Supabase.

    ``_record_id`` intentionally converts evidence IDs to strings for output,
    while ``evidence_records_df`` may retain them as Python/NumPy integers.
    Normalising both sides prevents a valid plant_id from becoming ``None``
    merely because one representation is ``27901`` and the other is
    ``"27901"`` (or ``27901.0``).
    """
    if value is None:
        return ""
    try:
        # Handles pandas/NumPy NaN without importing either package here.
        if value != value:
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


def _as_int_id(value):
    """Return a canonical integer database ID, or ``None`` when invalid.

    ``evidence_embeddings.evidence_record_id`` and ``plant_id`` are bigint
    foreign-key columns.  The Supabase loader may expose those IDs as Python
    ints, NumPy ints, numeric strings, or integral floats; normalise all of
    those representations before lookup/write and reject non-integral values.
    """
    key = _canonical_id_key(value)
    if not key:
        return None
    try:
        return int(key)
    except (TypeError, ValueError, OverflowError):
        return None


def _clean_text(value) -> str:
    """Conservatively stringify a persisted evidence field."""
    if value is None:
        return ""
    try:
        if value != value:  # pandas / NumPy NaN
            return ""
    except Exception:
        pass
    if isinstance(value, (dict, list, tuple, set)):
        import json
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            return str(value)
    text = str(value).strip()
    return "" if text.lower() in {"", "nan", "none", "null"} else text


def _first(row, *names):
    """Return the first non-empty value among dataframe column aliases."""
    for name in names:
        try:
            value = row.get(name)
        except AttributeError:
            value = None
        if _clean_text(value):
            return value
    return None


def _iter_embeddable_records(engine, *, plant_filter: str | None, record_id_filter: set):
    """Yield canonical persisted ``evidence_records`` rows for embedding.

    Backfill storage must be keyed only by the real ``evidence_records.id``.
    The previous implementation reused Step 5's combined evidence index,
    which merges three dataframes and may assign transient dataframe indices
    or IDs from ``scientific_evidence`` to a record.  Those IDs either had no
    matching plant_id or collided with a genuine evidence-record ID, causing
    NULL plant IDs and duplicate ON CONFLICT keys.

    This function therefore reads ``engine.evidence_records_df`` directly,
    preserves one row per canonical evidence-record primary key, and builds
    the exact field-aware mapping expected by
    ``build_evidence_embedding_text``.
    """
    evidence_df = getattr(engine, "evidence_records_df", None)
    if evidence_df is None or getattr(evidence_df, "empty", True):
        return

    canonical_filter = {
        rid for rid in (_as_int_id(v) for v in (record_id_filter or set()))
        if rid is not None
    }
    seen_record_ids: set[int] = set()

    for _, row in evidence_df.iterrows():
        record_id = _as_int_id(_first(row, "Evidence_Record_ID", "evidence_record_id", "id"))
        plant_id = _as_int_id(_first(row, "Plant_ID", "plant_id"))

        if record_id is None:
            print("[backfill_evidence_embeddings] Skipping row: no canonical evidence_record_id.")
            continue
        if record_id in seen_record_ids:
            # Defensive against duplicated REST/join rows. One persisted PK
            # must produce exactly one embedding row per model/version.
            continue
        seen_record_ids.add(record_id)

        if canonical_filter and record_id not in canonical_filter:
            continue
        if plant_id is None:
            print(
                "[backfill_evidence_embeddings] Skipping evidence record "
                f"{record_id!r}: no canonical plant_id could be resolved."
            )
            continue

        plant_name = _clean_text(_first(
            row, "Scientific_Name", "scientific_name", "Plant", "plant",
            "Botanical", "botanical", "Common_Name", "common_name",
        ))
        if plant_filter and plant_filter.strip().lower() not in plant_name.lower():
            continue

        tier1 = " ".join(filter(None, [
            _clean_text(_first(row, "Target_Indication", "target_indication")),
            _clean_text(_first(row, "Extracted_Indication", "extracted_indication")),
            _clean_text(_first(row, "Target_Indication_Detected", "target_indication_detected")),
            _clean_text(_first(row, "Detected_Indications", "detected_indications")),
        ]))
        tier2 = " ".join(filter(None, [
            _clean_text(_first(row, "Primary_Outcome", "primary_outcome", "Outcome", "outcome")),
            _clean_text(_first(row, "Result_Direction", "result_direction")),
            _clean_text(_first(row, "Mechanism", "mechanism")),
            _clean_text(_first(row, "Target", "target")),
        ]))
        tier3 = " ".join(filter(None, [
            _clean_text(_first(row, "Source_Title", "source_title", "Title", "title")),
            _clean_text(_first(row, "Abstract", "abstract")),
            _clean_text(_first(row, "Notes", "notes")),
            _clean_text(_first(row, "Source_Raw_Text", "source_raw_text", "Raw_Text", "raw_text")),
            _clean_text(_first(row, "Study_Type", "study_type")),
            _clean_text(_first(row, "Evidence_Type", "evidence_type", "Evidence_Level", "evidence_level")),
        ]))

        embedding_record = {
            "plant_name": plant_name,
            "tier1_text": tier1,
            "tier2_text": tier2,
            "tier3_text": tier3,
            "study_type": _clean_text(_first(row, "Study_Type", "study_type")),
            "evidence_level": _clean_text(_first(row, "Evidence_Level", "evidence_level")),
            "preparation": _clean_text(_first(
                row, "Preparation", "preparation", "Extraction_Method", "extraction_method",
                "Dosage_Form", "dosage_form", "Administration_Route", "administration_route",
            )),
            "source_type": _clean_text(_first(row, "Source_Type", "source_type")),
            "evidence_type": _clean_text(_first(row, "Evidence_Type", "evidence_type")),
        }
        text = build_evidence_embedding_text(embedding_record)
        if not text:
            continue
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

    candidates: list[tuple[int, int, str, str, str]] = []  # (id, plant_id, plant, text, hash)
    seen_candidate_ids: set[int] = set()
    for record_id, plant_id, plant_name, text in _iter_embeddable_records(
        engine, plant_filter=plant_filter, record_id_filter=record_id_filter,
    ):
        if record_id in seen_candidate_ids:
            continue
        seen_candidate_ids.add(record_id)
        stats.scanned += 1
        content_hash = compute_content_hash(text)
        candidates.append((record_id, plant_id, plant_name, text, content_hash))
        if limit and len(candidates) >= limit:
            break

    if not candidates:
        return stats

    existing_hashes_raw = fetch_existing_content_hashes(
        (c[0] for c in candidates), embedding_model=model, embedding_version=version,
    )
    # Supabase normally returns integer bigint IDs, while tests/legacy mocks
    # may return numeric strings. Canonicalise once so hash-gated idempotency
    # is representation-independent.
    existing_hashes = {
        rid: content_hash
        for key, content_hash in existing_hashes_raw.items()
        for rid in [_as_int_id(key)]
        if rid is not None
    }

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
