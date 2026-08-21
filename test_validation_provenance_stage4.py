from __future__ import annotations

import json
from pathlib import Path

import pytest

from validation_provenance import DatasetStatus, persist_validation_run, write_immutable_json


def test_immutable_artifact_refuses_overwrite(tmp_path):
    target = tmp_path / "historical_blind.json"
    write_immutable_json(target, {"accuracy": 0.30})
    with pytest.raises(FileExistsError):
        write_immutable_json(target, {"accuracy": 0.80})
    assert json.loads(target.read_text())["accuracy"] == 0.30


def test_regression_run_gets_new_artifact_and_append_only_registry(tmp_path):
    kwargs = dict(
        repo_root=tmp_path,
        dataset_name="decision_holdout_v5",
        dataset_version="1.0.0",
        dataset_status=DatasetStatus.REGRESSION,
        engine_version="1.10.2",
        result_payload={"metrics": {"accuracy": 0.8}},
        labels_visible_before_execution=True,
        results_previously_inspected=True,
        used_for_remediation=True,
        run_kind="post_remediation_rerun",
        overall_result={"accuracy": 0.8, "n_scored": 10},
        per_class_metrics={"GO": 0.0},
        safety_regulatory_metrics={"serious_safety": {"false_negatives": 0, "reference_positive_cases": 2}},
        historical_blind_result_path="gold_corpus/decision_holdout_v5/blind_run_historical_result.json",
        timestamp="2026-08-21T10:00:00+00:00",
    )
    artifact, registry, record = persist_validation_run(**kwargs)
    assert artifact.exists()
    assert artifact.name != "results.json"
    assert record.dataset_status == "regression"
    stored = json.loads(artifact.read_text())
    assert stored["validation_provenance"]["labels_visible_before_execution"] is True
    assert stored["validation_provenance"]["historical_blind_result_path"].endswith("blind_run_historical_result.json")
    lines = registry.read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["output_artifact_path"].startswith("gold_corpus/validation_runs/")


def test_independent_status_cannot_be_inferred_from_a_regression_rerun(tmp_path):
    _, _, record = persist_validation_run(
        repo_root=tmp_path,
        dataset_name="rgv_v3",
        dataset_version="3",
        dataset_status=DatasetStatus.EXPOSED,
        engine_version="1.10.2",
        result_payload={"metrics": {"accuracy": 0.5}},
        labels_visible_before_execution=True,
        results_previously_inspected=True,
        used_for_remediation=True,
        run_kind="regression",
        overall_result={"accuracy": 0.5},
        per_class_metrics={},
        safety_regulatory_metrics={},
        timestamp="2026-08-21T10:01:00+00:00",
    )
    assert record.dataset_status != DatasetStatus.INDEPENDENT_FROZEN.value
    assert record.run_kind == "regression"


def test_known_runners_do_not_overwrite_legacy_result_artifacts():
    for name in [
        "decision_holdout_v2.py",
        "decision_holdout_v3.py",
        "decision_holdout_v4.py",
        "decision_holdout_v5.py",
    ]:
        source = Path(name).read_text(encoding="utf-8")
        assert "(BASE/'results.json').write_text" not in source
        assert "persist_validation_run(" in source

    rgv = Path("run_final_reference_holdout_v1.py").read_text(encoding="utf-8")
    assert "blind_results_{tag}.json\").write_text" not in rgv
    assert "release_gate_result_{tag}.json\").write_text" not in rgv
    assert "persist_validation_run(" in rgv
    assert "engine_blinded_to_reference_labels=False" in rgv
    assert "remediation_cases_excluded=False" in rgv


def test_dataset_registry_preserves_v5_blind_vs_post_remediation_distinction():
    registry = json.loads(Path("gold_corpus/validation_dataset_registry.json").read_text())
    v5 = next(x for x in registry["datasets"] if x["dataset_name"] == "decision_holdout_v5")
    assert v5["historical_blind_result"]["agreement"] == 0.3
    assert v5["post_remediation_result"]["agreement"] == 0.8
    assert v5["current_status"] == "exposed"
    assert v5["permitted_current_use"] == "regression"


def test_rgv3_registry_does_not_invent_missing_aggregate_result():
    registry = json.loads(Path("gold_corpus/validation_dataset_registry.json").read_text())
    v3 = next(x for x in registry["datasets"] if x["dataset_name"] == "reference_grounded_validation_v3")
    assert v3["historical_engine_version"] == "1.8.0"
    assert v3["historical_blind_result"] is None
    assert v3["current_status"] == "exposed"


def test_independent_frozen_status_rejects_exposed_provenance(tmp_path):
    with pytest.raises(ValueError, match="Cannot record dataset_status='independent_frozen'"):
        persist_validation_run(
            repo_root=tmp_path, dataset_name="bad_claim", dataset_version="1",
            dataset_status=DatasetStatus.INDEPENDENT_FROZEN, engine_version="1.10.2",
            result_payload={}, labels_visible_before_execution=True,
            results_previously_inspected=False, used_for_remediation=False,
            run_kind="blind", overall_result={}, per_class_metrics={},
            safety_regulatory_metrics={}, timestamp="2026-08-21T10:02:00+00:00",
        )
