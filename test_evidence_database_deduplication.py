"""Regression tests for activating deduplication_engine.py inside
evidence_database.py — the platform's single production evidence-read
path (consumed by BotanicalRDCandidateEngine, app.py's Supabase preview
panel, and pages/Plant_Profile.py).

Before this task: deduplication_engine.py existed but was never
imported by app.py or any page — see .github/legacy-files.txt and
ARCHITECTURE.md. These tests lock in that it is now (a) actually
exercised by every evidence_database.py read function, and (b) no
longer listed as a legacy/unreachable candidate.
"""

import os

import pandas as pd
import pytest

import evidence_database


def _sample_raw_records():
    """Three rows: two are near-duplicates of the same source for the
    same plant/indication/dosage_form (should collapse to the
    higher-scoring one), one is genuinely distinct.
    """
    return pd.DataFrame([
        {
            "Scientific_Name": "Melissa officinalis",
            "Target_Indication": "Sleep support",
            "Dosage_Form": "Infusion",
            "Source_URL": "https://pubmed.ncbi.nlm.nih.gov/12345",
            "Source_Title": "A randomized trial of lemon balm infusion for sleep",
            "Notes": "",
            "Evidence_Score": 40,
            "Evidence_Quality_Score": 10,
        },
        {
            # Same source (by URL), same plant/indication/dosage_form,
            # but a lower combined score — this is the duplicate that
            # deduplicate_evidence() should drop.
            "Scientific_Name": "Melissa officinalis",
            "Target_Indication": "Sleep support",
            "Dosage_Form": "Infusion",
            "Source_URL": "https://pubmed.ncbi.nlm.nih.gov/12345",
            "Source_Title": "A randomized trial of lemon balm infusion for sleep",
            "Notes": "",
            "Evidence_Score": 5,
            "Evidence_Quality_Score": 5,
        },
        {
            # Genuinely distinct source — must survive deduplication.
            "Scientific_Name": "Valeriana officinalis",
            "Target_Indication": "Sleep support",
            "Dosage_Form": "Infusion",
            "Source_URL": "https://pubmed.ncbi.nlm.nih.gov/67890",
            "Source_Title": "Valerian root extract and sleep quality",
            "Notes": "",
            "Evidence_Score": 30,
            "Evidence_Quality_Score": 10,
        },
    ])


def test_load_evidence_database_deduplicates_records(monkeypatch):
    monkeypatch.setattr(
        evidence_database, "load_evidence_records", _sample_raw_records
    )

    df = evidence_database.load_evidence_database()

    assert len(df) == 2
    melissa_rows = df[df["Scientific_Name"] == "Melissa officinalis"]
    assert len(melissa_rows) == 1
    # The higher-scoring duplicate (40 + 10) must be the one kept, not
    # the lower-scoring one (5 + 5).
    assert melissa_rows.iloc[0]["Evidence_Score"] == 40


def test_load_evidence_database_empty_input_does_not_error(monkeypatch):
    monkeypatch.setattr(
        evidence_database, "load_evidence_records", lambda: pd.DataFrame()
    )

    df = evidence_database.load_evidence_database()
    assert df is not None
    assert len(df) == 0


def test_load_sheet_also_deduplicates(monkeypatch):
    monkeypatch.setattr(
        evidence_database, "load_evidence_records", _sample_raw_records
    )

    df = evidence_database.load_sheet("any_sheet_name")
    assert len(df) == 2


def test_with_meta_completeness_uses_raw_count_not_deduplicated_count(monkeypatch):
    # total_records mirrors the raw (pre-dedup) row count on the
    # server, so completeness must be judged against the RAW fetch
    # count (3), not the deduplicated count (2) — otherwise a fully
    # complete fetch that happens to contain duplicates would be
    # misreported as partial.
    monkeypatch.setattr(evidence_database, "get_evidence_record_count", lambda: 3)
    monkeypatch.setattr(
        evidence_database, "load_evidence_records", _sample_raw_records
    )

    df, meta = evidence_database.load_evidence_database_with_meta()

    assert meta["total_records"] == 3
    assert meta["returned_records"] == 3
    assert meta["is_complete"] is True
    assert meta["data_source_mode"] == "Full Supabase data"

    # But the DataFrame actually handed back — the one app.py displays
    # and stores in session_state — is the deduplicated one.
    assert len(df) == 2
    assert meta["deduplicated_records"] == 2
    assert meta["duplicates_removed"] == 1


def test_with_meta_reports_zero_duplicates_removed_when_none_found(monkeypatch):
    distinct_only = _sample_raw_records().iloc[[0, 2]].reset_index(drop=True)
    monkeypatch.setattr(evidence_database, "get_evidence_record_count", lambda: 2)
    monkeypatch.setattr(
        evidence_database, "load_evidence_records", lambda: distinct_only
    )

    df, meta = evidence_database.load_evidence_database_with_meta()

    assert meta["duplicates_removed"] == 0
    assert meta["deduplicated_records"] == meta["returned_records"] == 2
    assert len(df) == 2


def test_with_meta_unavailable_path_still_reports_dedup_keys(monkeypatch):
    def _boom():
        raise RuntimeError("Supabase unreachable")

    monkeypatch.setattr(evidence_database, "get_evidence_record_count", lambda: None)
    monkeypatch.setattr(evidence_database, "load_evidence_records", _boom)

    df, meta = evidence_database.load_evidence_database_with_meta()

    assert meta["data_source_mode"] == "Unavailable"
    assert meta["deduplicated_records"] == 0
    assert meta["duplicates_removed"] == 0
    assert len(df) == 0


@pytest.mark.parametrize("path", ["legacy-files.txt", os.path.join(".github", "legacy-files.txt")])
def test_deduplication_engine_no_longer_listed_as_legacy(path):
    with open(path, encoding="utf-8") as f:
        lines = {line.strip() for line in f}

    assert "deduplication_engine.py" not in lines
