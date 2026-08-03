"""Regression tests for the 2026-08 "10,611 rows disappear after loading"
investigation.

Production symptom: [supabase_data] Fetched 21806 row(s) from
'evidence_records'. -- but scanned=11195. All 21,806 canonical rows loaded
successfully (the earlier pagination/strict-mode fixes are proven
unaffected here too); the loss happened AFTER loading and BEFORE
stats.scanned, inside backfill_evidence_embeddings.py's own iterator.

Root cause: build_evidence_embedding_text() returned an empty string for
any record whose plant_name, tier1 (indication), tier2 (outcome/mechanism)
and tier3 (title/abstract/notes/raw text/study type/evidence type) were
ALL empty -- which happens for a real evidence_records row whose plant_id
resolves but whose related `plants` row wasn't matched/joined (so
Scientific_Name comes back empty) and which carries no target_indication/
primary_outcome/study_type/abstract of any kind, e.g. a bare citation
record. _iter_embeddable_records() then silently `continue`d past such a
row with no counter tracking it at all -- it simply never became a
candidate, and stats.scanned only ever counts candidates.

These tests prove, with a fully instrumented run:
  1. every row is accounted for by LoadDiagnostics's counters (they
     reconcile exactly for a full/unfiltered run);
  2. BotanicalRDCandidateEngine.__init__ does not mutate, filter,
     deduplicate, or replace the supplied evidence_records_df;
  3. the reference-text fallback now recovers exactly the class of record
     described above (empty tiers + empty plant_name but real citation
     fields), instead of silently dropping it.
"""
from __future__ import annotations

import pandas as pd
import pytest

import backfill_evidence_embeddings as backfill_mod
import botanical_rd_candidate_engine as eng
from backfill_evidence_embeddings import LoadDiagnostics, _iter_embeddable_records
from evidence_embedding_text import build_evidence_embedding_text


class _Engine:
    """Minimal stand-in exposing exactly what _iter_embeddable_records
    reads: engine.evidence_records_df."""

    def __init__(self, rows: list[dict]):
        self.evidence_records_df = pd.DataFrame(rows)


def _full_row(record_id, plant_id=10) -> dict:
    """A normal, fully-populated evidence_records row -- must always be
    yielded."""
    return {
        "Evidence_Record_ID": str(record_id),
        "Plant_ID": plant_id,
        "Scientific_Name": "Ginkgo biloba",
        "Target_Indication": "Cognitive decline",
        "Primary_Outcome": "Memory improved",
        "Study_Type": "RCT",
    }


def _bare_citation_row(record_id, plant_id=10) -> dict:
    """The exact class of row that was previously silently dropped: a
    resolvable plant_id, but no matched plant name and no indication/
    outcome/study/title/abstract/notes/raw-text of any kind -- only a bare
    identifier (PMID) that none of the three primary tiers include."""
    return {
        "Evidence_Record_ID": str(record_id),
        "Plant_ID": plant_id,
        "Scientific_Name": "",
        "PMID": "12345678",
    }


def _truly_empty_row(record_id, plant_id=10) -> dict:
    """Genuinely nothing persisted beyond identity -- not even a title or
    PMID/DOI/NCT_ID/source_url. Must still be skipped even after the
    fallback (there is nothing to build ANY text from)."""
    return {"Evidence_Record_ID": str(record_id), "Plant_ID": plant_id}


def _excluded_label_row(record_id, plant_id=10) -> dict:
    """A DailyMed / safety-label record with ABUNDANT primary text --
    Scientific_Name, Target_Indication, Study_Type, Evidence_Level,
    Source_Title, Notes, Source_Raw_Text are all populated. Must be
    classified as excluded-by-policy, never as empty text: none of that
    text is ever missing, it's the record TYPE that's excluded (a
    composition/label proxy, not efficacy evidence)."""
    return {
        "Evidence_Record_ID": str(record_id),
        "Plant_ID": plant_id,
        "Scientific_Name": "Ginkgo biloba",
        "Target_Indication": "Cognitive decline",
        "Study_Type": "Label",
        "Evidence_Level": "Label",
        "Source_Title": "DailyMed structured product label",
        "Notes": "Multi-ingredient label text",
        "Source_Raw_Text": "Full label raw text goes here.",
        "Source_Type": "dailymed",
        "Evidence_Type": "safety/label",
    }


def _excluded_patent_row(record_id, plant_id=10) -> dict:
    """A patent/literature record, also with abundant primary text --
    same point as _excluded_label_row but for the other exclusion path
    (Source_Type rather than Evidence_Type)."""
    return {
        "Evidence_Record_ID": str(record_id),
        "Plant_ID": plant_id,
        "Scientific_Name": "Ginkgo biloba",
        "Target_Indication": "Cognitive decline",
        "Study_Type": "Patent",
        "Source_Title": "Patent covering an extraction method",
        "Notes": "Protection landscape note",
        "Source_Type": "patent/literature",
    }


def _excluded_chebi_row(record_id, plant_id=10) -> dict:
    """A ChEBI chemical-ontology record -- Evidence_Type-based exclusion,
    also with abundant text."""
    return {
        "Evidence_Record_ID": str(record_id),
        "Plant_ID": plant_id,
        "Scientific_Name": "Ginkgo biloba",
        "Study_Type": "Chemical ontology",
        "Source_Title": "ChEBI chemical composition entry",
        "Source_Type": "chebi",
        "Evidence_Type": "chemical composition",
    }


# ---------------------------------------------------------------------------
# 1) Diagnostic counters must reconcile exactly for a full, unfiltered run
# ---------------------------------------------------------------------------

def test_diagnostics_reconcile_across_every_skip_reason():
    rows = [
        _full_row(1),
        _full_row(2),
        {"Plant_ID": 10},  # missing Evidence_Record_ID
        {**_full_row(3), "Evidence_Record_ID": "3"},
        {**_full_row(3), "Evidence_Record_ID": "3"},  # duplicate of record 3
        {"Evidence_Record_ID": "5", "Scientific_Name": "Ginkgo biloba"},  # missing Plant_ID
        _truly_empty_row(6),  # empty even after fallback
        _bare_citation_row(7),  # recovered by the fallback
        _excluded_label_row(8),  # excluded by policy, despite abundant text
        _excluded_patent_row(9),  # excluded by policy, despite abundant text
    ]
    engine = _Engine(rows)
    diagnostics = LoadDiagnostics()

    yielded = list(_iter_embeddable_records(
        engine, plant_filter=None, record_id_filter=set(), diagnostics=diagnostics,
    ))

    assert diagnostics.iterator_input_rows == len(rows)
    assert diagnostics.skipped_missing_record_id == 1
    assert diagnostics.skipped_duplicate_record_id == 1
    assert diagnostics.skipped_missing_plant_id == 1
    assert diagnostics.skipped_proxy_or_excluded_record == 2  # records 8, 9
    assert diagnostics.skipped_empty_embedding_text == 1  # record 6 only
    assert diagnostics.skipped_by_user_filter == 0
    assert diagnostics.yielded_embeddable_records == 4  # records 1, 2, 3, 7
    assert len(yielded) == 4
    assert diagnostics.reconciles()
    assert diagnostics.accounted_for() == diagnostics.iterator_input_rows


def test_diagnostics_reconcile_at_scale_21806_rows():
    """Reproduces the exact reported scale: 21806 fully-populated rows,
    all of which must be yielded, with counters reconciling exactly --
    proving no silent, unaccounted-for loss at production scale."""
    rows = [_full_row(i, plant_id=(i % 50) + 1) for i in range(1, 21807)]
    engine = _Engine(rows)
    diagnostics = LoadDiagnostics()

    yielded = list(_iter_embeddable_records(
        engine, plant_filter=None, record_id_filter=set(), diagnostics=diagnostics,
    ))

    assert diagnostics.iterator_input_rows == 21806
    assert diagnostics.yielded_embeddable_records == 21806
    assert len(yielded) == 21806
    assert diagnostics.skipped_missing_record_id == 0
    assert diagnostics.skipped_duplicate_record_id == 0
    assert diagnostics.skipped_missing_plant_id == 0
    assert diagnostics.skipped_empty_embedding_text == 0
    assert diagnostics.skipped_proxy_or_excluded_record == 0
    assert diagnostics.reconciles()


def test_diagnostics_reconcile_at_scale_with_exclusions_mixed_in():
    """Same production scale (21806 rows), but with a realistic mix of
    excluded (label/patent) records interleaved -- counters must still
    reconcile exactly, and none of the excluded records leak into
    skipped_empty_embedding_text or yielded_embeddable_records."""
    rows = []
    for i in range(1, 21807):
        if i % 7 == 0:
            rows.append(_excluded_label_row(i, plant_id=(i % 50) + 1))
        elif i % 11 == 0:
            rows.append(_excluded_patent_row(i, plant_id=(i % 50) + 1))
        else:
            rows.append(_full_row(i, plant_id=(i % 50) + 1))
    expected_excluded = sum(1 for i in range(1, 21807) if i % 7 == 0 or i % 11 == 0)
    expected_yielded = 21806 - expected_excluded

    engine = _Engine(rows)
    diagnostics = LoadDiagnostics()

    yielded = list(_iter_embeddable_records(
        engine, plant_filter=None, record_id_filter=set(), diagnostics=diagnostics,
    ))

    assert diagnostics.iterator_input_rows == 21806
    assert diagnostics.skipped_proxy_or_excluded_record == expected_excluded
    assert diagnostics.skipped_empty_embedding_text == 0
    assert diagnostics.yielded_embeddable_records == expected_yielded
    assert len(yielded) == expected_yielded
    assert diagnostics.reconciles()


def test_run_backfill_attaches_diagnostics_to_returned_stats():
    engine = _Engine([_full_row(1), _bare_citation_row(2), _truly_empty_row(3)])

    from unittest.mock import patch
    with patch.object(backfill_mod, "fetch_existing_content_hashes", return_value={}), \
         patch.object(backfill_mod, "embed_texts_batched", return_value=({0: [0.1], 1: [0.2]}, {})), \
         patch.object(backfill_mod, "upsert_evidence_embeddings", return_value=None):
        stats = backfill_mod.run_backfill(engine=engine)

    assert hasattr(stats, "diagnostics")
    assert stats.diagnostics.iterator_input_rows == 3
    assert stats.diagnostics.yielded_embeddable_records == 2  # record 1 + fallback-recovered record 2
    assert stats.diagnostics.skipped_empty_embedding_text == 1  # record 3
    assert stats.diagnostics.reconciles()
    assert stats.scanned == 2


# ---------------------------------------------------------------------------
# 2) BotanicalRDCandidateEngine.__init__ must not mutate, filter,
#    deduplicate, or replace the supplied evidence_records_df
# ---------------------------------------------------------------------------

def test_engine_construction_preserves_every_row_of_evidence_records_df():
    input_df = pd.DataFrame([_full_row(i) for i in range(1, 501)])

    engine = eng.BotanicalRDCandidateEngine(
        plant_compounds_df=pd.DataFrame(),
        compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(),
        evidence_records_df=input_df,
        use_live_search=False,
    )

    assert len(engine.evidence_records_df) == len(input_df) == 500
    assert set(engine.evidence_records_df["Evidence_Record_ID"]) == {
        str(i) for i in range(1, 501)
    }


def test_engine_construction_preserves_rows_at_21806_scale():
    """Same proof at the exact reported production scale."""
    input_df = pd.DataFrame([_full_row(i, plant_id=(i % 50) + 1) for i in range(1, 21807)])

    engine = eng.BotanicalRDCandidateEngine(
        plant_compounds_df=pd.DataFrame(),
        compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(),
        evidence_records_df=input_df,
        use_live_search=False,
    )

    assert len(engine.evidence_records_df) == 21806


def test_build_engine_raw_loader_and_engine_row_counts_match(monkeypatch):
    """End-to-end proof through _build_engine() itself: raw_loader_rows
    (what the Supabase loader returned) and engine_evidence_records_rows
    (what the engine actually holds right after construction) must be
    equal -- disproving any transformation/reassignment between the two."""
    df = pd.DataFrame([_full_row(i, plant_id=(i % 50) + 1) for i in range(1, 21807)])

    import supabase_data
    monkeypatch.setattr(supabase_data, "load_evidence_records_df", lambda strict=False: df)
    monkeypatch.setattr(supabase_data, "load_scientific_evidence_df", lambda: pd.DataFrame())
    monkeypatch.setattr(supabase_data, "load_plant_compounds_df", lambda: pd.DataFrame())
    monkeypatch.setattr(supabase_data, "load_compound_profiles_df", lambda: pd.DataFrame())

    diagnostics = LoadDiagnostics()
    engine = backfill_mod._build_engine(diagnostics=diagnostics)

    assert diagnostics.raw_loader_rows == 21806
    assert diagnostics.engine_evidence_records_rows == 21806
    assert diagnostics.raw_loader_rows == diagnostics.engine_evidence_records_rows
    assert len(engine.evidence_records_df) == 21806


# ---------------------------------------------------------------------------
# 3) The reference-text fallback recovers records that were previously
#    silently dropped, using only persisted, non-disease-specific fields
# ---------------------------------------------------------------------------

def test_build_evidence_embedding_text_falls_back_to_reference_fields_when_primary_empty():
    record = {
        "plant_name": "", "tier1_text": "", "tier2_text": "", "tier3_text": "",
        "study_type": "", "evidence_level": "", "preparation": "",
        "fallback_plant_id": "10",
        "fallback_source_title": "A bare citation with no extracted content",
        "fallback_pmid": "12345678",
    }
    text = build_evidence_embedding_text(record)
    assert text != ""
    assert "12345678" in text
    assert "bare citation" in text
    # No disease-specific vocabulary is introduced -- only verbatim
    # persisted field values appear.
    assert "Plant ID: 10" in text


def test_build_evidence_embedding_text_prefers_primary_fields_over_fallback():
    """When primary content exists, the fallback fields must have zero
    effect on the result, even if present."""
    record = {
        "plant_name": "Ginkgo biloba", "tier1_text": "Cognitive decline",
        "tier2_text": "", "tier3_text": "", "study_type": "", "evidence_level": "",
        "preparation": "",
        "fallback_source_title": "should never appear",
    }
    text = build_evidence_embedding_text(record)
    assert "should never appear" not in text
    assert "Ginkgo biloba" in text


def test_build_evidence_embedding_text_still_empty_when_truly_nothing_persisted():
    record = {
        "plant_name": "", "tier1_text": "", "tier2_text": "", "tier3_text": "",
        "study_type": "", "evidence_level": "", "preparation": "",
    }
    assert build_evidence_embedding_text(record) == ""


def test_iter_embeddable_records_recovers_bare_citation_records():
    """Integration-level proof: a record with a resolvable plant_id but no
    matched plant name and no indication/outcome/study text -- exactly the
    class of record the production run was silently dropping -- is now
    yielded, using only its citation fields."""
    engine = _Engine([_bare_citation_row(42)])
    diagnostics = LoadDiagnostics()

    yielded = list(_iter_embeddable_records(
        engine, plant_filter=None, record_id_filter=set(), diagnostics=diagnostics,
    ))

    assert len(yielded) == 1
    record_id, plant_id, plant_name, text = yielded[0]
    assert record_id == "42"
    assert "12345678" in text  # PMID
    assert "Plant ID: 10" in text  # supplements the PMID, doesn't stand alone
    assert diagnostics.skipped_empty_embedding_text == 0
    assert diagnostics.yielded_embeddable_records == 1


# ---------------------------------------------------------------------------
# 4) Exclusion classification bug fix: an excluded (proxy/composition/
#    protection-source) record must never be counted or logged as "empty
#    text", even though build_evidence_embedding_text() also happens to
#    return "" for it. is_proxy_or_excluded_record() is now evaluated
#    explicitly, BEFORE build_evidence_embedding_text() is even called.
# ---------------------------------------------------------------------------

def test_dailymed_label_record_with_abundant_text_is_counted_as_excluded_not_empty():
    """The exact production symptom: a DailyMed/safety-label record logged
    non-empty Scientific_Name, Target_Indication, Study_Type,
    Evidence_Level, Source_Title, Notes, and Source_Raw_Text -- it must be
    classified as excluded-by-policy, never as empty text."""
    engine = _Engine([_excluded_label_row(1)])
    diagnostics = LoadDiagnostics()

    yielded = list(_iter_embeddable_records(
        engine, plant_filter=None, record_id_filter=set(), diagnostics=diagnostics,
    ))

    assert yielded == []
    assert diagnostics.skipped_proxy_or_excluded_record == 1
    assert diagnostics.skipped_empty_embedding_text == 0  # never mislabeled
    assert diagnostics.reconciles()


def test_patent_literature_record_is_counted_as_excluded_not_empty():
    engine = _Engine([_excluded_patent_row(1)])
    diagnostics = LoadDiagnostics()

    yielded = list(_iter_embeddable_records(
        engine, plant_filter=None, record_id_filter=set(), diagnostics=diagnostics,
    ))

    assert yielded == []
    assert diagnostics.skipped_proxy_or_excluded_record == 1
    assert diagnostics.skipped_empty_embedding_text == 0
    assert diagnostics.reconciles()


def test_chebi_record_is_counted_as_excluded_not_empty():
    engine = _Engine([_excluded_chebi_row(1)])
    diagnostics = LoadDiagnostics()

    yielded = list(_iter_embeddable_records(
        engine, plant_filter=None, record_id_filter=set(), diagnostics=diagnostics,
    ))

    assert yielded == []
    assert diagnostics.skipped_proxy_or_excluded_record == 1
    assert diagnostics.skipped_empty_embedding_text == 0
    assert diagnostics.reconciles()


def test_genuinely_empty_non_excluded_record_is_still_counted_as_empty():
    """The other direction of the same fix: a record that is NOT excluded
    (no recognized Source_Type/Evidence_Type) and genuinely has no usable
    text anywhere must still land in skipped_empty_embedding_text, not
    skipped_proxy_or_excluded_record."""
    engine = _Engine([_truly_empty_row(1)])
    diagnostics = LoadDiagnostics()

    yielded = list(_iter_embeddable_records(
        engine, plant_filter=None, record_id_filter=set(), diagnostics=diagnostics,
    ))

    assert yielded == []
    assert diagnostics.skipped_empty_embedding_text == 1
    assert diagnostics.skipped_proxy_or_excluded_record == 0
    assert diagnostics.reconciles()


def test_excluded_records_never_reach_build_evidence_embedding_text_as_empty(monkeypatch, capsys):
    """The exclusion log line must report evidence_record_id, Source_Type,
    Evidence_Type, and an explicit exclusion reason -- not the generic
    empty-columns message."""
    engine = _Engine([_excluded_label_row(99)])
    diagnostics = LoadDiagnostics()

    list(_iter_embeddable_records(
        engine, plant_filter=None, record_id_filter=set(), diagnostics=diagnostics,
    ))

    output = capsys.readouterr().out
    assert "evidence_record_id='99'" in output
    assert "excluded as a proxy/composition/protection source" in output
    assert "Source_Type='dailymed'" in output
    assert "Evidence_Type='safety/label'" in output
    assert "empty embedding text" not in output  # never the generic empty-text message


def test_load_diagnostics_log_line_and_reconciliation_include_exclusion_counter():
    diagnostics = LoadDiagnostics(
        iterator_input_rows=5,
        skipped_missing_record_id=1,
        skipped_proxy_or_excluded_record=2,
        skipped_empty_embedding_text=1,
        yielded_embeddable_records=1,
    )
    assert diagnostics.accounted_for() == 5
    assert diagnostics.reconciles()
    assert "skipped_proxy_or_excluded_record=2" in diagnostics.as_log_line()
