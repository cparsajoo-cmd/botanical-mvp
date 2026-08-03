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

Also prints a row-count diagnostics line (see LoadDiagnostics below) that
must reconcile exactly for a full, unfiltered run: it exists to answer,
for one concrete run, precisely which stage between the Supabase loader
and the final embeddable set drops rows and why -- see the 2026-08
investigation into why only 11195 of 21806 loaded evidence_records were
ever scanned (root cause: most were skipped for having no text any of the
existing tiers could produce -- see the fallback-text mechanism below).
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from embedding_service import (
    EMBEDDING_MODEL,
    EMBEDDING_VERSION,
    BackfillStats,
    embed_texts_batched,
    fetch_existing_content_hashes,
    upsert_evidence_embeddings,
)
from evidence_embedding_text import build_evidence_embedding_text, compute_content_hash


@dataclass
class LoadDiagnostics:
    """Row-count accounting across every stage between the Supabase loader
    and the final set of records actually queued for embedding.

    For a full run (no --plant / --evidence-record-id / --limit narrowing
    the result), the following must hold exactly -- ``reconciles()``
    checks it:

        iterator_input_rows =
            skipped_missing_record_id
            + skipped_duplicate_record_id
            + skipped_missing_plant_id
            + skipped_empty_embedding_text
            + skipped_by_user_filter   (0 for an unfiltered run)
            + yielded_embeddable_records

    If it doesn't hold, some row was dropped somewhere without being
    counted -- that is itself a bug to find, not something to paper over.
    """

    raw_loader_rows: int = 0
    engine_evidence_records_rows: int = 0
    iterator_input_rows: int = 0
    skipped_missing_record_id: int = 0
    skipped_duplicate_record_id: int = 0
    skipped_missing_plant_id: int = 0
    skipped_empty_embedding_text: int = 0
    skipped_by_user_filter: int = 0
    yielded_embeddable_records: int = 0

    def accounted_for(self) -> int:
        return (
            self.skipped_missing_record_id
            + self.skipped_duplicate_record_id
            + self.skipped_missing_plant_id
            + self.skipped_empty_embedding_text
            + self.skipped_by_user_filter
            + self.yielded_embeddable_records
        )

    def reconciles(self) -> bool:
        return self.iterator_input_rows == self.accounted_for()

    def as_log_line(self) -> str:
        return (
            f"raw_loader_rows={self.raw_loader_rows} "
            f"engine_evidence_records_rows={self.engine_evidence_records_rows} "
            f"iterator_input_rows={self.iterator_input_rows} "
            f"skipped_missing_record_id={self.skipped_missing_record_id} "
            f"skipped_duplicate_record_id={self.skipped_duplicate_record_id} "
            f"skipped_missing_plant_id={self.skipped_missing_plant_id} "
            f"skipped_empty_embedding_text={self.skipped_empty_embedding_text} "
            f"skipped_by_user_filter={self.skipped_by_user_filter} "
            f"yielded_embeddable_records={self.yielded_embeddable_records} "
            f"reconciles={self.reconciles()}"
        )


def _canonical_id_key(value) -> str:
    """Return a stable STRING lookup/identity key for IDs coming from
    pandas/Supabase/CLI args.

    IDs must be compared and carried around as their canonical string
    representation everywhere in this module -- ``evidence_record_id`` is
    an externally observed value (tests and any caller of the mocked
    ``upsert_evidence_embeddings``/``fetch_existing_content_hashes``
    boundary see exactly this string, e.g. ``"2"``), so this function must
    never collapse to an ``int``. Only the real database adapter
    (embedding_service.py, immediately before the actual Supabase request)
    is allowed to convert to a bigint, and it does so on a private copy
    without touching the value produced here.

    Normalises harmless representation differences -- ``10``, ``10.0``,
    ``"10"`` -- to the same key (``"10"``) so a valid record/plant is never
    treated as unresolved merely because one side is a Python/NumPy int
    and the other is a numeric string or an integral float.
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


def _build_engine(diagnostics: LoadDiagnostics | None = None):
    """Real production engine, backed by Supabase. Imported lazily so this
    module can be imported (e.g. by tests) without requiring Supabase
    credentials to be configured.

    When ``diagnostics`` is supplied, records ``raw_loader_rows`` (the row
    count load_evidence_records_df() itself returned) and
    ``engine_evidence_records_rows`` (the row count actually held on
    ``engine.evidence_records_df`` right after construction) -- this is
    what proves or disproves whether BotanicalRDCandidateEngine.__init__
    mutates, filters, deduplicates, or replaces the supplied DataFrame:
    ``_load_supabase_df`` (see botanical_rd_candidate_engine.py) treats an
    explicitly-passed DataFrame as authoritative and only ever
    ``.copy()``s it via ``_to_dataframe`` -- verified by inspection, and
    the two counters below make that verifiable at runtime for a real
    Supabase-backed run too, not just by reading the source.
    """
    from botanical_rd_candidate_engine import BotanicalRDCandidateEngine
    import supabase_data

    # strict=True: a backfill run must fail loudly (raising
    # IncompletePaginationError, which surfaces as a failed GitHub Actions
    # run) rather than silently proceeding to embed a partial
    # evidence_records dataset if pagination can't complete.
    evidence_records_df = supabase_data.load_evidence_records_df(strict=True)
    if diagnostics is not None:
        diagnostics.raw_loader_rows = len(evidence_records_df)

    engine = BotanicalRDCandidateEngine(
        evidence_df=supabase_data.load_scientific_evidence_df(),
        candidate_data=[],
        use_live_search=False,
        plant_compounds_df=supabase_data.load_plant_compounds_df(),
        compound_profiles_df=supabase_data.load_compound_profiles_df(),
        scientific_evidence_df=supabase_data.load_scientific_evidence_df(),
        evidence_records_df=evidence_records_df,
    )

    if diagnostics is not None:
        diagnostics.engine_evidence_records_rows = len(engine.evidence_records_df)

    return engine


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


# Columns inspected to explain WHY a record's primary embedding text (and
# fallback reference text) both came out empty -- printed once per such
# record so a real run's log says exactly which persisted fields were
# empty, instead of just "skipped".
_EMPTY_TEXT_DIAGNOSTIC_COLUMNS = [
    ("Scientific_Name", "scientific_name"),
    ("Target_Indication", "target_indication"),
    ("Extracted_Indication", "extracted_indication"),
    ("Primary_Outcome", "primary_outcome"),
    ("Result_Direction", "result_direction"),
    ("Mechanism", "mechanism"),
    ("Study_Type", "study_type"),
    ("Evidence_Level", "evidence_level"),
    ("Source_Title", "source_title"),
    ("Abstract", "abstract"),
    ("Notes", "notes"),
    ("Source_Raw_Text", "source_raw_text"),
    ("PMID", "pmid"),
    ("DOI", "doi"),
    ("NCT_ID", "nct_id"),
]


def _log_empty_embedding_text_columns(record_id: str, row) -> None:
    empty_cols = [
        label for label, alt in _EMPTY_TEXT_DIAGNOSTIC_COLUMNS
        if not _clean_text(_first(row, label, alt))
    ]
    present_cols = [
        label for label, alt in _EMPTY_TEXT_DIAGNOSTIC_COLUMNS
        if _clean_text(_first(row, label, alt))
    ]
    print(
        f"[backfill_evidence_embeddings] evidence_record_id={record_id!r}: "
        "empty embedding text even after the reference-text fallback -- "
        f"empty columns: {', '.join(empty_cols) if empty_cols else '(none)'}; "
        f"non-empty columns: {', '.join(present_cols) if present_cols else '(none)'}"
    )


def _iter_embeddable_records(
    engine, *, plant_filter: str | None, record_id_filter: set,
    diagnostics: LoadDiagnostics | None = None,
):
    """Yield canonical persisted ``evidence_records`` rows for embedding.

    Backfill storage must be keyed only by the real ``evidence_records.id``.
    This function reads ``engine.evidence_records_df`` directly -- never
    Step 5's combined evidence index (``_build_plant_evidence_index``),
    which merges ``evidence_df``, ``evidence_records_df`` and
    ``scientific_evidence_df`` and may surface a transient dataframe index
    or an id from a different source table under the same key. Mixing
    those in is what previously produced records with no resolvable
    plant_id and duplicate ON CONFLICT keys.

    ``evidence_record_id`` and ``plant_id`` are both yielded as their
    canonical STRING representation (see ``_canonical_id_key``) and are
    never converted to ``int`` in this module.

    When ``diagnostics`` is supplied, every row is accounted for by
    exactly one counter on it -- see ``LoadDiagnostics.reconciles()``.
    """
    evidence_df = getattr(engine, "evidence_records_df", None)
    if evidence_df is None or getattr(evidence_df, "empty", True):
        return

    if diagnostics is not None:
        diagnostics.iterator_input_rows = len(evidence_df)

    canonical_filter = {
        key for key in (_canonical_id_key(v) for v in (record_id_filter or set()))
        if key
    }
    seen_record_ids: set[str] = set()

    for _, row in evidence_df.iterrows():
        record_id = _canonical_id_key(_first(row, "Evidence_Record_ID", "evidence_record_id", "id"))
        plant_id = _canonical_id_key(_first(row, "Plant_ID", "plant_id"))

        if not record_id:
            print("[backfill_evidence_embeddings] Skipping row: no canonical evidence_record_id.")
            if diagnostics is not None:
                diagnostics.skipped_missing_record_id += 1
            continue
        if record_id in seen_record_ids:
            # Defensive against duplicated REST/join rows. One persisted PK
            # must produce exactly one embedding row per model/version.
            if diagnostics is not None:
                diagnostics.skipped_duplicate_record_id += 1
            continue
        seen_record_ids.add(record_id)

        if canonical_filter and record_id not in canonical_filter:
            if diagnostics is not None:
                diagnostics.skipped_by_user_filter += 1
            continue
        if not plant_id:
            print(
                "[backfill_evidence_embeddings] Skipping evidence record "
                f"{record_id!r}: no canonical plant_id could be resolved."
            )
            if diagnostics is not None:
                diagnostics.skipped_missing_plant_id += 1
            continue

        plant_name = _clean_text(_first(
            row, "Scientific_Name", "scientific_name", "Plant", "plant",
            "Botanical", "botanical", "Common_Name", "common_name",
        ))
        if plant_filter and plant_filter.strip().lower() not in plant_name.lower():
            if diagnostics is not None:
                diagnostics.skipped_by_user_filter += 1
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
            # General, non-disease-specific fallback fields -- used by
            # build_evidence_embedding_text() ONLY when every field above
            # is empty (e.g. a record whose plant_id resolves but whose
            # `plants` join found no scientific_name, and which carries no
            # indication/outcome/study text of any kind). Every value here
            # is a direct, unmodified copy of an already-persisted field;
            # nothing is inferred or invented. See evidence_embedding_text.py
            # for exactly when this tier is used.
            "fallback_plant_id": plant_id,
            "fallback_source_title": _clean_text(_first(row, "Source_Title", "source_title", "Title", "title")),
            "fallback_source_type": _clean_text(_first(row, "Source_Type", "source_type")),
            "fallback_pmid": _clean_text(_first(row, "PMID", "pmid")),
            "fallback_doi": _clean_text(_first(row, "DOI", "doi")),
            "fallback_nct_id": _clean_text(_first(row, "NCT_ID", "nct_id")),
            "fallback_source_url": _clean_text(_first(row, "Source_URL", "source_url")),
        }
        text = build_evidence_embedding_text(embedding_record)
        if not text:
            if diagnostics is not None:
                diagnostics.skipped_empty_embedding_text += 1
            _log_empty_embedding_text_columns(record_id, row)
            continue

        if diagnostics is not None:
            diagnostics.yielded_embeddable_records += 1
        yield record_id, plant_id, plant_name, text


def _dedupe_rows_for_upsert(rows: list[dict]) -> list[dict]:
    """Deterministically collapse rows so no single upsert payload contains
    the same (evidence_record_id, embedding_model, embedding_version)
    conflict key twice.

    The canonical iterator above already guarantees at most one row per
    evidence_record_id for a given run, so this is a second, defensive
    pass (as required at the real database boundary too). If two rows
    ever do share a conflict key with differing content_hash, the later
    row is kept -- deterministic on input order -- and the conflict is
    logged rather than silently dropped.
    """
    deduped: dict[tuple[str, str, str], dict] = {}
    for row in rows:
        key = (
            str(row.get("evidence_record_id")),
            str(row.get("embedding_model")),
            str(row.get("embedding_version")),
        )
        previous = deduped.get(key)
        if previous is not None and previous.get("content_hash") != row.get("content_hash"):
            print(
                "[backfill_evidence_embeddings] Conflicting rows for the same "
                f"evidence_record_id/embedding_model/embedding_version {key!r}; "
                "keeping the later row."
            )
        deduped[key] = row
    return list(deduped.values())


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
    diagnostics = LoadDiagnostics()

    if engine is None:
        engine = _build_engine(diagnostics=diagnostics)
    else:
        # Caller supplied the engine directly (e.g. tests): _build_engine()
        # never ran, so raw_loader_rows stays 0 (not meaningful here) --
        # engine_evidence_records_rows is still recorded from what was
        # supplied, and the iterator-level counters below still populate
        # normally.
        supplied_df = getattr(engine, "evidence_records_df", None)
        diagnostics.engine_evidence_records_rows = 0 if supplied_df is None else len(supplied_df)

    stats.diagnostics = diagnostics
    record_id_filter = record_id_filter or set()

    candidates: list[tuple[str, str, str, str, str]] = []  # (id, plant_id, plant, text, hash)
    seen_candidate_ids: set[str] = set()
    for record_id, plant_id, plant_name, text in _iter_embeddable_records(
        engine, plant_filter=plant_filter, record_id_filter=record_id_filter,
        diagnostics=diagnostics,
    ):
        if record_id in seen_candidate_ids:
            continue
        seen_candidate_ids.add(record_id)
        stats.scanned += 1
        content_hash = compute_content_hash(text)
        candidates.append((record_id, plant_id, plant_name, text, content_hash))
        if limit and len(candidates) >= limit:
            # NOTE: cuts the generator off early, so diagnostics for this
            # run will NOT reconcile (iterator_input_rows reflects every
            # row available, not just the ones actually visited before the
            # break) -- reconciliation is only guaranteed for a full,
            # unlimited run.
            break

    if not candidates:
        return stats

    existing_hashes_raw = fetch_existing_content_hashes(
        (c[0] for c in candidates), embedding_model=model, embedding_version=version,
    )
    # Supabase normally returns bigint evidence_record_id values as Python
    # ints, while tests/legacy mocks may return numeric strings. Canonicalise
    # once (to the same STRING form used throughout this module) so
    # hash-gated idempotency is representation-independent -- this never
    # converts anything to int.
    existing_hashes = {
        key: content_hash
        for raw_key, content_hash in existing_hashes_raw.items()
        for key in [_canonical_id_key(raw_key)]
        if key
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
        rows = _dedupe_rows_for_upsert(rows)
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

    diagnostics = getattr(stats, "diagnostics", None)
    if diagnostics is not None:
        print(f"[backfill_evidence_embeddings] diagnostics: {diagnostics.as_log_line()}")

    # NOTE: the workflow greps for a line matching ^scanned= -- keep this
    # exact format/position (start of line) unchanged.
    print(f"scanned={stats.scanned} skipped={stats.skipped} embedded={stats.embedded} "
          f"updated={stats.updated} failed={stats.failed}")
    if stats.failures:
        print("Failures:")
        for record_id, error in stats.failures:
            print(f"  evidence_record_id={record_id}: {error}")
    return 1 if stats.failed else 0


if __name__ == "__main__":
    sys.exit(main())
