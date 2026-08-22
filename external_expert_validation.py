"""Stage 6 — tooling for a prospective external expert validation study.

Validation infrastructure only.  This module does not modify production
retrieval, evidence interpretation, scoring, ranking, safety/regulatory gates,
eligibility, or final-decision policy.

The intended workflow is prospective:
1. independently select and freeze 30–50 genuine evidence records;
2. Expert A and Expert B label the same frozen records independently and while
   blinded to platform output;
3. adjudicate disagreements without rewriting either expert's original labels;
4. run the platform on the exact same frozen records with an explicitly recorded
   engine version;
5. compare platform output with the adjudicated reference and report field-level
   agreement plus denominator-aware safety/regulatory false-negative metrics.

This module deliberately does not create scientific ground truth.  It only
validates study artifacts and computes metrics from labels supplied by qualified
humans.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Optional

from evidence_interpretation import (
    DIRECTION_MIXED,
    DIRECTION_NEGATIVE,
    DIRECTION_NULL,
    DIRECTION_POSITIVE,
    DIRECTION_UNCLEAR,
    QUALITY_HIGH,
    QUALITY_LOW,
    QUALITY_MODERATE,
    QUALITY_UNKNOWN,
    STUDY_DESIGN_ANIMAL_STUDY,
    STUDY_DESIGN_CLINICAL_TRIAL,
    STUDY_DESIGN_CLINICAL_TRIAL_PROTOCOL,
    STUDY_DESIGN_IN_VITRO_STUDY,
    STUDY_DESIGN_RCT,
    STUDY_DESIGN_REVIEW,
    STUDY_DESIGN_UNSPECIFIED,
)

EVIDENCE_DIRECTIONS = {
    DIRECTION_POSITIVE,
    DIRECTION_NEGATIVE,
    DIRECTION_NULL,
    DIRECTION_MIXED,
    DIRECTION_UNCLEAR,
}
STUDY_DESIGNS = {
    STUDY_DESIGN_RCT,
    STUDY_DESIGN_CLINICAL_TRIAL_PROTOCOL,
    STUDY_DESIGN_CLINICAL_TRIAL,
    STUDY_DESIGN_REVIEW,
    STUDY_DESIGN_ANIMAL_STUDY,
    STUDY_DESIGN_IN_VITRO_STUDY,
    STUDY_DESIGN_UNSPECIFIED,
}
EVIDENCE_QUALITIES = {QUALITY_HIGH, QUALITY_MODERATE, QUALITY_LOW, QUALITY_UNKNOWN}
CATEGORICAL_FIELDS = ("evidence_direction", "study_design", "evidence_quality")
BINARY_RISK_FIELDS = (
    ("serious_safety_evaluable", "serious_safety_signal"),
    ("regulatory_evaluable", "regulatory_block_signal"),
)
TARGET_RECORD_MIN = 30
TARGET_RECORD_MAX = 50


@dataclass(frozen=True)
class ValidationCheck:
    valid: bool
    errors: tuple[str, ...]


@dataclass(frozen=True)
class BinaryRiskMetrics:
    true_positives: int
    false_negatives: int
    false_positives: int
    true_negatives: int
    reference_positive_cases: int
    evaluable_cases: int
    non_evaluable_cases: int
    recall: Optional[float]
    precision: Optional[float]
    status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _safe_div(num: int, den: int) -> Optional[float]:
    return None if den == 0 else num / den


def sha256_file(path: str | Path) -> str:
    h = sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json_exclusive(path: str | Path, payload: Any) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, default=str)
        handle.write("\n")
    return target


def _nonempty(value: Any) -> bool:
    return bool(str(value or "").strip())


def validate_evidence_packet(document: Mapping[str, Any], *, require_freeze_ready: bool) -> ValidationCheck:
    errors: list[str] = []
    records = document.get("records")
    if not isinstance(records, list):
        return ValidationCheck(False, ("'records' must be a list",))

    if require_freeze_ready and not (TARGET_RECORD_MIN <= len(records) <= TARGET_RECORD_MAX):
        errors.append(
            f"Freeze-ready external validation requires {TARGET_RECORD_MIN}–{TARGET_RECORD_MAX} records; found {len(records)}"
        )

    if require_freeze_ready:
        if document.get("records_selected_independently_of_platform_output") is not True:
            errors.append("records_selected_independently_of_platform_output must be true")
        if document.get("records_selected_before_platform_execution") is not True:
            errors.append("records_selected_before_platform_execution must be true")
        if not _nonempty(document.get("selection_curator_role")):
            errors.append("selection_curator_role is required")
        if document.get("historical_overlap_check_complete") is not True:
            errors.append("historical_overlap_check_complete must be true")
        if document.get("manual_study_overlap_review_complete") is not True:
            errors.append("manual_study_overlap_review_complete must be true")

    seen: set[str] = set()
    for index, record in enumerate(records):
        prefix = f"records[{index}]"
        if not isinstance(record, Mapping):
            errors.append(f"{prefix} must be an object")
            continue
        rid = str(record.get("record_id") or "").strip()
        if not rid:
            errors.append(f"{prefix}.record_id is required")
        elif rid in seen:
            errors.append(f"Duplicate record_id: {rid}")
        seen.add(rid)

        for field in ("source_title", "source_type", "taxon", "record_text", "source_locator"):
            if not _nonempty(record.get(field)):
                errors.append(f"{prefix}.{field} is required")
        if not any(_nonempty(record.get(k)) for k in ("doi", "pmid", "nct_id", "source_url", "source_locator")):
            errors.append(f"{prefix} requires a stable identifier or source locator")
        if record.get("platform_output_visible_during_selection") is True:
            errors.append(f"{prefix}.platform_output_visible_during_selection must not be true")

    return ValidationCheck(not errors, tuple(errors))


def _validate_label_row(row: Mapping[str, Any], *, prefix: str) -> list[str]:
    errors: list[str] = []
    direction = row.get("evidence_direction")
    design = row.get("study_design")
    quality = row.get("evidence_quality")
    if direction not in EVIDENCE_DIRECTIONS:
        errors.append(f"{prefix}.evidence_direction must use the existing five-class taxonomy")
    if design not in STUDY_DESIGNS:
        errors.append(f"{prefix}.study_design must use the existing production taxonomy")
    if quality not in EVIDENCE_QUALITIES:
        errors.append(f"{prefix}.evidence_quality must use the existing production taxonomy")

    for evaluable_field, signal_field in BINARY_RISK_FIELDS:
        evaluable = row.get(evaluable_field)
        signal = row.get(signal_field)
        if not isinstance(evaluable, bool):
            errors.append(f"{prefix}.{evaluable_field} must be boolean")
        elif evaluable and not isinstance(signal, bool):
            errors.append(f"{prefix}.{signal_field} must be boolean when evaluable")
        elif not evaluable and signal is not None:
            errors.append(f"{prefix}.{signal_field} must be null when not evaluable")
    return errors


def validate_expert_labels(
    document: Mapping[str, Any], *, evidence_record_ids: Iterable[str], require_complete: bool
) -> ValidationCheck:
    errors: list[str] = []
    required_ids = list(evidence_record_ids)
    required_set = set(required_ids)

    if require_complete:
        for field in ("expert_code", "expert_role", "qualification_summary"):
            if not _nonempty(document.get(field)):
                errors.append(f"{field} is required")
        for field in (
            "blinded_to_platform_output",
            "worked_independently",
            "labels_completed_before_platform_output_disclosure",
        ):
            if document.get(field) is not True:
                errors.append(f"{field} must be true")

    labels = document.get("labels")
    if not isinstance(labels, list):
        return ValidationCheck(False, tuple(errors + ["'labels' must be a list"]))

    seen: set[str] = set()
    for i, row in enumerate(labels):
        prefix = f"labels[{i}]"
        if not isinstance(row, Mapping):
            errors.append(f"{prefix} must be an object")
            continue
        rid = str(row.get("record_id") or "").strip()
        if not rid:
            errors.append(f"{prefix}.record_id is required")
            continue
        if rid in seen:
            errors.append(f"Duplicate label record_id: {rid}")
        seen.add(rid)
        if require_complete:
            errors.extend(_validate_label_row(row, prefix=prefix))

    if require_complete:
        missing = sorted(required_set - seen)
        extra = sorted(seen - required_set)
        if missing:
            errors.append(f"Missing labels for record_ids: {', '.join(missing)}")
        if extra:
            errors.append(f"Labels contain unknown record_ids: {', '.join(extra)}")

    return ValidationCheck(not errors, tuple(errors))


def validate_adjudication(
    document: Mapping[str, Any], *, evidence_record_ids: Iterable[str], require_complete: bool
) -> ValidationCheck:
    errors: list[str] = []
    required_ids = set(evidence_record_ids)
    if require_complete:
        if document.get("expert_a_original_labels_preserved") is not True:
            errors.append("expert_a_original_labels_preserved must be true")
        if document.get("expert_b_original_labels_preserved") is not True:
            errors.append("expert_b_original_labels_preserved must be true")
        if not _nonempty(document.get("adjudicator_role")):
            errors.append("adjudicator_role is required")
        if not _nonempty(document.get("adjudication_method")):
            errors.append("adjudication_method is required")

    labels = document.get("consensus_labels")
    if not isinstance(labels, list):
        return ValidationCheck(False, tuple(errors + ["'consensus_labels' must be a list"]))
    seen: set[str] = set()
    for i, row in enumerate(labels):
        prefix = f"consensus_labels[{i}]"
        if not isinstance(row, Mapping):
            errors.append(f"{prefix} must be an object")
            continue
        rid = str(row.get("record_id") or "").strip()
        if not rid:
            errors.append(f"{prefix}.record_id is required")
            continue
        if rid in seen:
            errors.append(f"Duplicate consensus record_id: {rid}")
        seen.add(rid)
        if require_complete:
            errors.extend(_validate_label_row(row, prefix=prefix))
            if not _nonempty(row.get("reference_basis")):
                errors.append(f"{prefix}.reference_basis is required")

    if require_complete:
        missing = sorted(required_ids - seen)
        extra = sorted(seen - required_ids)
        if missing:
            errors.append(f"Missing consensus labels for record_ids: {', '.join(missing)}")
        if extra:
            errors.append(f"Consensus contains unknown record_ids: {', '.join(extra)}")
    return ValidationCheck(not errors, tuple(errors))


def validate_platform_output(
    document: Mapping[str, Any], *, evidence_record_ids: Iterable[str], require_complete: bool
) -> ValidationCheck:
    errors: list[str] = []
    required_ids = set(evidence_record_ids)
    if require_complete:
        if not _nonempty(document.get("engine_version")):
            errors.append("engine_version is required")
        if document.get("processed_exact_frozen_records") is not True:
            errors.append("processed_exact_frozen_records must be true")
        if document.get("reference_labels_visible_to_platform_before_execution") is not False:
            errors.append("reference_labels_visible_to_platform_before_execution must be false")

    outputs = document.get("outputs")
    if not isinstance(outputs, list):
        return ValidationCheck(False, tuple(errors + ["'outputs' must be a list"]))
    seen: set[str] = set()
    for i, row in enumerate(outputs):
        prefix = f"outputs[{i}]"
        if not isinstance(row, Mapping):
            errors.append(f"{prefix} must be an object")
            continue
        rid = str(row.get("record_id") or "").strip()
        if not rid:
            errors.append(f"{prefix}.record_id is required")
            continue
        if rid in seen:
            errors.append(f"Duplicate platform output record_id: {rid}")
        seen.add(rid)
        if require_complete:
            errors.extend(_validate_label_row(row, prefix=prefix))

    if require_complete:
        missing = sorted(required_ids - seen)
        extra = sorted(seen - required_ids)
        if missing:
            errors.append(f"Missing platform outputs for record_ids: {', '.join(missing)}")
        if extra:
            errors.append(f"Platform outputs contain unknown record_ids: {', '.join(extra)}")
    return ValidationCheck(not errors, tuple(errors))


def _by_id(rows: Iterable[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    return {str(row["record_id"]): row for row in rows}


def categorical_metrics(reference_rows: Iterable[Mapping[str, Any]], predicted_rows: Iterable[Mapping[str, Any]], field: str) -> dict[str, Any]:
    ref = _by_id(reference_rows)
    pred = _by_id(predicted_rows)
    ids = sorted(set(ref) & set(pred))
    labels = sorted({str(ref[i][field]) for i in ids} | {str(pred[i][field]) for i in ids})
    matrix = {expected: {actual: 0 for actual in labels} for expected in labels}
    errors: list[dict[str, Any]] = []
    correct = 0
    for rid in ids:
        expected = str(ref[rid][field])
        actual = str(pred[rid][field])
        matrix[expected][actual] += 1
        if expected == actual:
            correct += 1
        else:
            errors.append({"record_id": rid, "expected": expected, "actual": actual})
    per_class_recall = {}
    for label in labels:
        denominator = sum(matrix[label].values())
        per_class_recall[label] = _safe_div(matrix[label].get(label, 0), denominator)
    return {
        "field": field,
        "n": len(ids),
        "agreement": _safe_div(correct, len(ids)),
        "confusion_matrix": matrix,
        "per_class_recall": per_class_recall,
        "errors": errors,
    }


def interexpert_metrics(expert_a_rows: Iterable[Mapping[str, Any]], expert_b_rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        field: categorical_metrics(expert_a_rows, expert_b_rows, field)
        for field in CATEGORICAL_FIELDS
    }


def binary_risk_metrics(
    reference_rows: Iterable[Mapping[str, Any]],
    predicted_rows: Iterable[Mapping[str, Any]],
    *,
    evaluable_field: str,
    signal_field: str,
) -> BinaryRiskMetrics:
    ref = _by_id(reference_rows)
    pred = _by_id(predicted_rows)
    ids = sorted(set(ref) & set(pred))
    tp = fn = fp = tn = non_eval = 0
    for rid in ids:
        rr, pp = ref[rid], pred[rid]
        if rr.get(evaluable_field) is not True or pp.get(evaluable_field) is not True:
            non_eval += 1
            continue
        expected = rr.get(signal_field) is True
        actual = pp.get(signal_field) is True
        if expected and actual:
            tp += 1
        elif expected and not actual:
            fn += 1
        elif not expected and actual:
            fp += 1
        else:
            tn += 1
    evaluable = tp + fn + fp + tn
    ref_positive = tp + fn
    return BinaryRiskMetrics(
        true_positives=tp,
        false_negatives=fn,
        false_positives=fp,
        true_negatives=tn,
        reference_positive_cases=ref_positive,
        evaluable_cases=evaluable,
        non_evaluable_cases=non_eval,
        recall=_safe_div(tp, ref_positive),
        precision=_safe_div(tp, tp + fp),
        status="not_evaluable" if ref_positive == 0 else "evaluable",
    )


def build_external_validation_metrics(
    *,
    expert_a_labels: Mapping[str, Any],
    expert_b_labels: Mapping[str, Any],
    adjudication: Mapping[str, Any],
    platform_output: Mapping[str, Any],
) -> dict[str, Any]:
    a_rows = expert_a_labels["labels"]
    b_rows = expert_b_labels["labels"]
    reference_rows = adjudication["consensus_labels"]
    platform_rows = platform_output["outputs"]

    platform_field_metrics = {
        field: categorical_metrics(reference_rows, platform_rows, field)
        for field in CATEGORICAL_FIELDS
    }
    safety = binary_risk_metrics(
        reference_rows,
        platform_rows,
        evaluable_field="serious_safety_evaluable",
        signal_field="serious_safety_signal",
    )
    regulatory = binary_risk_metrics(
        reference_rows,
        platform_rows,
        evaluable_field="regulatory_evaluable",
        signal_field="regulatory_block_signal",
    )
    return {
        "engine_version": platform_output.get("engine_version"),
        "record_count": len(reference_rows),
        "interexpert_agreement_before_adjudication": interexpert_metrics(a_rows, b_rows),
        "platform_vs_adjudicated_reference": platform_field_metrics,
        "serious_safety_metrics": safety.to_dict(),
        "regulatory_metrics": regulatory.to_dict(),
        "scientific_claim_boundary": (
            "These are external-study agreement and high-risk error metrics for the frozen record set. "
            "They are not a claim of clinical validation, calibrated probability, or universal safety/regulatory performance."
        ),
    }


def current_engine_version_from_source(repo_root: str | Path) -> str:
    """Read the engine version without importing the production engine."""
    text = (Path(repo_root) / "botanical_rd_candidate_engine.py").read_text(encoding="utf-8")
    match = re.search(r'^DECISION_ENGINE_VERSION\s*=\s*["\']([^"\']+)["\']', text, re.M)
    if not match:
        raise ValueError("Could not find DECISION_ENGINE_VERSION in botanical_rd_candidate_engine.py")
    return match.group(1)
