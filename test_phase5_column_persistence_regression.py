"""Regression test for a specific bug found during Phase 5 review
(IMPLEMENTATION_PLAN.md): indication_candidate_discovery.py's own module
docstring/comment claimed the Phase 5 diagnostic columns
(Normalization_Summary, Validation_Status, Validation_Summary) had been
added to every DataFrame this module returns — but the actual final
`reindex(columns=OUTPUT_COLUMNS)` call (and the empty-result early return)
still used only the legacy OUTPUT_COLUMNS list, silently dropping all
three columns before they ever left discover_indication_candidates().
The claim was true in a comment, not in the code.

This test calls discover_indication_candidates() directly (not through
the full BotanicalRDCandidateEngine.run() wrapper other Phase 5 tests
use) specifically so a future regression at this exact function boundary
is caught even if the wrapper's own behavior changes.
"""

import pandas as pd

from indication_candidate_discovery import discover_indication_candidates


class _FakeEngine:
    def __init__(self, evidence_rows, candidate_rows):
        self.evidence_df = pd.DataFrame(evidence_rows)
        self.scientific_evidence_df = pd.DataFrame()

    def _candidate_frame(self):
        return pd.DataFrame(self._candidates)

    def _pick(self, row, names):
        for n in names:
            if n in row and pd.notna(row[n]):
                return str(row[n])
        return ""

    def _split_compound_terms(self, v):
        return [x.strip() for x in str(v).split(";") if x.strip()]

    def _evidence_level(self, t):
        return "Clinical trial" if "randomized" in t.lower() else "Unknown"


def _make_engine():
    engine = _FakeEngine(
        evidence_rows=[{
            "Scientific_Name": "Valeriana officinalis",
            "Title": "Valeriana officinalis improved sleep insomnia in a randomized trial",
            "Source_URL": "https://example.org/a",
        }],
        candidate_rows=None,
    )
    engine._candidates = [
        {"Scientific_Name": "Valeriana officinalis", "Known_Active_Compounds": "x"},
    ]
    return engine


def test_phase5_diagnostic_columns_survive_the_final_reindex():
    out = discover_indication_candidates(_make_engine(), "insomnia")
    assert not out.empty
    for column in ("Normalization_Summary", "Validation_Status", "Validation_Summary"):
        assert column in out.columns, f"{column} was dropped before leaving discover_indication_candidates()"
    assert out.iloc[0]["Validation_Status"] in (
        "valid", "valid_with_limitations", "rejected", "not_assessable",
    )
    assert out.iloc[0]["Normalization_Summary"] != ""


def test_phase5_diagnostic_columns_present_even_on_the_empty_result_path():
    # The OTHER early-return in discover_indication_candidates() (no
    # candidates at all) must produce the same column schema, not a
    # narrower one — a caller should never have to branch on whether the
    # result happened to be empty to know which columns to expect.
    engine = _FakeEngine(evidence_rows=[], candidate_rows=None)
    engine._candidates = []
    out = discover_indication_candidates(engine, "insomnia")
    assert out.empty
    for column in ("Normalization_Summary", "Validation_Status", "Validation_Summary"):
        assert column in out.columns
