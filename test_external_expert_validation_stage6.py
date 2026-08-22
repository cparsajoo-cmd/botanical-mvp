from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from external_expert_validation import (
    build_external_validation_metrics,
    categorical_metrics,
    validate_adjudication,
    validate_evidence_packet,
    validate_expert_labels,
    validate_platform_output,
    write_json_exclusive,
)
from freeze_external_expert_validation_v1 import freeze


def _record(i: int) -> dict:
    return {
        "record_id": f"R{i:03d}",
        "source_title": f"Study {i}",
        "source_type": "journal_article",
        "source_url": f"https://example.org/{i}",
        "doi": f"10.9999/example.{i}",
        "pmid": "",
        "nct_id": "",
        "taxon": "Example plant",
        "indication": "Example indication",
        "record_text": "The intervention was more effective than placebo.",
        "text_origin": "verbatim_abstract",
        "source_locator": f"abstract:{i}",
        "platform_output_visible_during_selection": False,
    }


def _packet(n: int = 30) -> dict:
    return {
        "records_selected_independently_of_platform_output": True,
        "records_selected_before_platform_execution": True,
        "selection_curator_role": "independent curator",
        "historical_overlap_check_complete": True,
        "manual_study_overlap_review_complete": True,
        "records": [_record(i) for i in range(n)],
    }


def _label(rid: str, *, direction="positive", safety=False, safety_eval=True, reg_eval=False, reg=None) -> dict:
    return {
        "record_id": rid,
        "evidence_direction": direction,
        "study_design": "randomized_controlled_trial",
        "evidence_quality": "moderate",
        "serious_safety_evaluable": safety_eval,
        "serious_safety_signal": safety if safety_eval else None,
        "regulatory_evaluable": reg_eval,
        "regulatory_block_signal": reg if reg_eval else None,
    }


def _expert(ids, code="A") -> dict:
    return {
        "expert_code": code,
        "expert_role": "clinical pharmacology expert",
        "qualification_summary": "qualified independent reviewer",
        "blinded_to_platform_output": True,
        "worked_independently": True,
        "labels_completed_before_platform_output_disclosure": True,
        "labels": [_label(rid) for rid in ids],
    }


def test_external_packet_requires_30_to_50_records_for_freeze():
    assert validate_evidence_packet(_packet(30), require_freeze_ready=True).valid
    check = validate_evidence_packet(_packet(29), require_freeze_ready=True)
    assert not check.valid
    assert any("30–50" in e for e in check.errors)


def test_external_packet_rejects_duplicate_record_ids():
    packet = _packet(30)
    packet["records"][1]["record_id"] = packet["records"][0]["record_id"]
    check = validate_evidence_packet(packet, require_freeze_ready=True)
    assert not check.valid
    assert any("Duplicate record_id" in e for e in check.errors)


def test_expert_labels_require_blinding_independence_and_exact_record_set():
    ids = ["R001", "R002"]
    doc = _expert(ids)
    assert validate_expert_labels(doc, evidence_record_ids=ids, require_complete=True).valid
    doc["blinded_to_platform_output"] = False
    doc["labels"] = doc["labels"][:-1]
    check = validate_expert_labels(doc, evidence_record_ids=ids, require_complete=True)
    assert not check.valid
    assert any("blinded_to_platform_output" in e for e in check.errors)
    assert any("Missing labels" in e for e in check.errors)


def test_adjudication_requires_complete_consensus_and_reference_basis():
    ids = ["R001", "R002"]
    doc = {
        "adjudicator_role": "third expert",
        "adjudication_method": "independent third review of disagreements",
        "expert_a_original_labels_preserved": True,
        "expert_b_original_labels_preserved": True,
        "consensus_labels": [dict(_label(rid), reference_basis="expert agreement") for rid in ids],
    }
    assert validate_adjudication(doc, evidence_record_ids=ids, require_complete=True).valid
    doc["consensus_labels"][0]["reference_basis"] = ""
    assert not validate_adjudication(doc, evidence_record_ids=ids, require_complete=True).valid


def test_platform_output_must_cover_exact_frozen_record_set_and_be_blinded():
    ids = ["R001", "R002"]
    doc = {
        "engine_version": "1.10.2",
        "processed_exact_frozen_records": True,
        "reference_labels_visible_to_platform_before_execution": False,
        "outputs": [_label(rid) for rid in ids],
    }
    assert validate_platform_output(doc, evidence_record_ids=ids, require_complete=True).valid
    doc["outputs"].append(_label("EXTRA"))
    assert not validate_platform_output(doc, evidence_record_ids=ids, require_complete=True).valid


def test_field_metrics_report_confusion_recall_agreement_and_errors():
    ref = [_label("R1", direction="positive"), _label("R2", direction="negative")]
    pred = [_label("R1", direction="positive"), _label("R2", direction="null")]
    m = categorical_metrics(ref, pred, "evidence_direction")
    assert m["agreement"] == 0.5
    assert m["per_class_recall"]["positive"] == 1.0
    assert m["per_class_recall"]["negative"] == 0.0
    assert m["errors"] == [{"record_id": "R2", "expected": "negative", "actual": "null"}]


def test_high_risk_metrics_are_denominator_aware_and_not_evaluable_when_no_positive_reference():
    ids = ["R1", "R2"]
    a = _expert(ids, "A")
    b = _expert(ids, "B")
    consensus_rows = [
        dict(_label("R1", safety=True, safety_eval=True), reference_basis="adjudicated"),
        dict(_label("R2", safety=False, safety_eval=True), reference_basis="agreement"),
    ]
    adjudication = {"consensus_labels": consensus_rows}
    platform = {
        "engine_version": "1.10.2",
        "outputs": [_label("R1", safety=False, safety_eval=True), _label("R2", safety=False, safety_eval=True)],
    }
    metrics = build_external_validation_metrics(
        expert_a_labels=a,
        expert_b_labels=b,
        adjudication=adjudication,
        platform_output=platform,
    )
    safety = metrics["serious_safety_metrics"]
    assert safety["reference_positive_cases"] == 1
    assert safety["false_negatives"] == 1
    assert safety["recall"] == 0.0
    regulatory = metrics["regulatory_metrics"]
    assert regulatory["status"] == "not_evaluable"
    assert regulatory["reference_positive_cases"] == 0


def test_write_json_exclusive_never_overwrites(tmp_path: Path):
    target = tmp_path / "immutable.json"
    write_json_exclusive(target, {"a": 1})
    with pytest.raises(FileExistsError):
        write_json_exclusive(target, {"a": 2})
    assert json.loads(target.read_text()) == {"a": 1}


def test_empty_repository_template_cannot_be_frozen(tmp_path: Path):
    repo_root = Path(__file__).resolve().parent
    empty = json.loads((repo_root / "gold_corpus/external_expert_validation_v1/evidence_records.json").read_text())
    packet = tmp_path / "evidence_records.json"
    packet.write_text(json.dumps(empty), encoding="utf-8")
    with pytest.raises(ValueError, match="not freeze-ready"):
        freeze(packet_path=packet, manifest_path=tmp_path / "FREEZE_MANIFEST.json")


def test_dataset_registry_marks_external_study_as_development_only():
    repo_root = Path(__file__).resolve().parent
    registry = json.loads((repo_root / "gold_corpus/validation_dataset_registry.json").read_text())
    entry = next(x for x in registry["datasets"] if x["dataset_name"] == "external_expert_validation_v1")
    assert entry["current_status"] == "development"
    assert entry["permitted_current_use"] == "external_validation_construction_only"
    assert entry["historical_blind_result"] is None
