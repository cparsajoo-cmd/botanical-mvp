"""End-to-end regression test for IMPLEMENTATION_PLAN.md Phase 4,
requirement 4: "report metadata matches persisted metadata". Builds ONE
decision_metadata dict via decision_metadata.build_decision_metadata(),
passes it to BOTH pharma_report_generator.generate_pharma_report() and
decision_record_persistence.persist_decision_record(), and proves every
field that lands in the report's Reproducibility section matches the
field actually persisted — because both consumers read the same object,
never a second independently-built one.
"""

import re

import data_contracts as dc
import pandas as pd

from decision_metadata import build_decision_metadata
from pharma_report_generator import generate_pharma_report
from decision_record_persistence import (
    DECISION_RECORD_TABLE_NAME,
    persist_decision_record,
)


class _FakeResponse:
    def __init__(self, data):
        self.data = data


class _FakeTable:
    def __init__(self, store, table_name):
        self._store = store
        self._table_name = table_name
        self._pending_row = None

    def insert(self, row):
        self._pending_row = row
        return self

    def execute(self):
        self._store.setdefault(self._table_name, []).append(self._pending_row)
        return _FakeResponse(None)


class _FakeSupabaseClient:
    def __init__(self):
        self.store = {}

    def table(self, name):
        return _FakeTable(self.store, name)


def _sample_candidate_assessment(**overrides):
    defaults = dict(
        project_id="p1", indication="sleep", product_type="Infusion",
        dosage_form="Infusion", target_market="EU",
        reference_plant="Indication-centric discovery", reference_plant_part=None,
        reference_compound="Not used as candidate gate", reference_compound_id=None,
        alternative_plant="Valeriana officinalis", alternative_plant_part=None,
        alternative_compound=None, alternative_compound_id=None,
        rd_opportunity_score=88.0,
        decision_class="B — Established scientific candidate",
        evidence_confidence=70.0,
        gate_results={"safety": {"gate_name": "safety", "status": "passed", "reason": "x", "evidence": "y"}},
        scoring_config_version="authoritative-plant-v1",
    )
    defaults.update(overrides)
    return dc.CandidateAssessment(**defaults)


def _extract_reproducibility_section(report_markdown: str) -> str:
    start = report_markdown.find("## Reproducibility")
    assert start != -1, "expected a Reproducibility section in the report"
    end = report_markdown.find("\n## ", start + 1)
    return report_markdown[start:end if end != -1 else None]


def test_report_and_persisted_record_use_the_identical_metadata_values():
    report_ready_df = pd.DataFrame([{
        "Alternative_Plant": "Valeriana officinalis",
        "Scientific_Triage_Status": "Shortlist",
        "Overall_Score": 88.0,
        "Source_Record_IDs": "PMID:111; PMID:222",
        "Reference_Plant": "Indication-centric discovery",
        "Reference_Compound": "Not used as candidate gate",
        "R&D_Opportunity_Score": 88.0,
        "Evidence_Confidence": 70.0,
        "Decision_Class_AH": "B — Established scientific candidate",
        "Go_Investigate_Hold_NoGo": "Go",
        "Score_Breakdown": {"Indication Relevance": 35, "Evidence Quality": 30},
        "Rationale": "Full narrative.",
    }])

    # Computed ONCE, per Phase 4 — the single object both consumers read.
    decision_metadata = build_decision_metadata(
        report_ready_df, indication="sleep", dosage_form="Infusion",
        market="EU", discovery_mode="indication",
    )

    report_markdown = generate_pharma_report(
        report_ready_df, indication="sleep", dosage_form="Infusion", market="EU",
        decision_metadata=decision_metadata,
    )
    repro_section = _extract_reproducibility_section(report_markdown)

    client = _FakeSupabaseClient()
    records = [_sample_candidate_assessment()]
    persist_decision_record(
        records, indication="sleep", supabase_client=client,
        decision_metadata=decision_metadata,
    )
    persisted_row = client.store[DECISION_RECORD_TABLE_NAME][0]

    # Every field that appears in the report's Reproducibility section
    # must equal the value actually persisted for that same field.
    assert decision_metadata["scoring_model_version"] in repro_section
    assert persisted_row["scoring_model_version"] == decision_metadata["scoring_model_version"]

    assert decision_metadata["normalization_version"] in repro_section
    assert persisted_row["normalization_version"] == decision_metadata["normalization_version"]

    assert decision_metadata["validation_version"] in repro_section
    assert persisted_row["validation_version"] == decision_metadata["validation_version"]

    assert decision_metadata["discovery_mode"] in repro_section
    assert persisted_row["discovery_mode"] == decision_metadata["discovery_mode"]

    snapshot_id = decision_metadata["evidence_snapshot_id"]
    assert snapshot_id is not None
    assert snapshot_id in repro_section
    assert persisted_row["evidence_snapshot_id"] == snapshot_id
    assert persisted_row["evidence_snapshot_status"] == decision_metadata["evidence_snapshot_status"]

    fingerprint = decision_metadata["candidate_set_fingerprint"]
    assert fingerprint is not None
    assert fingerprint in repro_section
    assert persisted_row["candidate_set_fingerprint"] == fingerprint

    assert persisted_row["dosage_form"] == decision_metadata["dosage_form"] == "Infusion"
    assert persisted_row["market"] == decision_metadata["market"] == "EU"


def test_missing_evidence_snapshot_is_reported_as_unavailable_in_both_places():
    # No Source_Record_IDs anywhere -> honestly "unavailable" in both the
    # report and the persisted record, never a fabricated ID in either.
    report_ready_df = pd.DataFrame([{
        "Alternative_Plant": "Valeriana officinalis",
        "Scientific_Triage_Status": "Shortlist",
        "Overall_Score": 88.0,
        "Reference_Plant": "Indication-centric discovery",
        "Reference_Compound": "Not used as candidate gate",
        "R&D_Opportunity_Score": 88.0,
        "Rationale": "Full narrative.",
    }])
    decision_metadata = build_decision_metadata(
        report_ready_df, indication="sleep", dosage_form="Infusion",
        market="EU", discovery_mode="indication",
    )
    assert decision_metadata["evidence_snapshot_id"] is None
    assert decision_metadata["evidence_snapshot_status"] == "unavailable"

    report_markdown = generate_pharma_report(
        report_ready_df, indication="sleep", dosage_form="Infusion", market="EU",
        decision_metadata=decision_metadata,
    )
    repro_section = _extract_reproducibility_section(report_markdown)
    assert "unavailable" in repro_section.lower()
    assert not re.search(r"Evidence snapshot ID: `[0-9a-f]{64}`", repro_section)

    client = _FakeSupabaseClient()
    persist_decision_record(
        [_sample_candidate_assessment()], indication="sleep", supabase_client=client,
        decision_metadata=decision_metadata,
    )
    persisted_row = client.store[DECISION_RECORD_TABLE_NAME][0]
    assert persisted_row["evidence_snapshot_id"] is None
    assert persisted_row["evidence_snapshot_status"] == "unavailable"
