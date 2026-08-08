"""Decision Benchmark v1: leakage-controlled final-decision validation.

This module is validation-only. It does not change production rules and never
passes GoldCase truth objects/labels into the engine.

Cohorts
-------
DEVELOPMENT: the seven cases already used during final-decision remediation.
PROSPECTIVE_HOLDOUT: all other currently reference-grounded GoldCases. These
cases are deliberately unscored until independent engine evidence/snapshots
exist; reference claims must never be converted into engine input to make the
holdout executable.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import glob
import importlib.util
import inspect
import os
from pathlib import Path
from typing import Iterable, Mapping, Optional

from final_decision_policy import FinalDecisionStatus
from scientific_decision_validation import DecisionComparison, agreement, build_confusion_matrix


BENCHMARK_VERSION = "1.0.0"
DEVELOPMENT_CASE_NUMBERS = frozenset({6, 16, 18, 19, 20, 21, 22})


class BenchmarkCohort(str, Enum):
    DEVELOPMENT = "development"
    PROSPECTIVE_HOLDOUT = "prospective_holdout"


@dataclass(frozen=True)
class DecisionMetrics:
    n_scored: int
    n_correct: int
    accuracy: Optional[float]
    macro_f1: Optional[float]
    per_class_recall: dict[str, Optional[float]]
    serious_safety_false_negatives: int
    regulatory_false_negatives: int
    false_no_go: int
    expert_review_overuse: int
    insufficient_evidence_miss: int
    confusion_matrix: dict[str, dict[str, int]]


def _case_number(case_id: str) -> int:
    try:
        return int(case_id.split("_", 2)[1])
    except Exception as exc:
        raise ValueError(f"Unparseable GoldCase id: {case_id!r}") from exc


def cohort_for_case_id(case_id: str) -> BenchmarkCohort:
    return (
        BenchmarkCohort.DEVELOPMENT
        if _case_number(case_id) in DEVELOPMENT_CASE_NUMBERS
        else BenchmarkCohort.PROSPECTIVE_HOLDOUT
    )


def discover_reference_grounded_cases(root: str | Path = ".") -> list:
    """Load existing reference-grounded GoldCases without creating new cases."""
    root = Path(root)
    cases = []
    pattern = str(root / "gold_cases" / "gold_case_reference_grounded_*.py")
    for path in sorted(glob.glob(pattern)):
        mod_name = "_decision_benchmark_" + os.path.basename(path).replace(".py", "")
        spec = importlib.util.spec_from_file_location(mod_name, path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        builders = [
            fn for name, fn in inspect.getmembers(module, inspect.isfunction)
            if name.startswith("build_gold_case_refgrounded_")
        ]
        if len(builders) != 1:
            raise RuntimeError(f"Expected exactly one GoldCase builder in {path}; found {len(builders)}")
        cases.append(builders[0]())
    return cases


def split_cases(cases: Iterable) -> dict[BenchmarkCohort, list]:
    out = {BenchmarkCohort.DEVELOPMENT: [], BenchmarkCohort.PROSPECTIVE_HOLDOUT: []}
    for case in cases:
        out[cohort_for_case_id(case.case_id)].append(case)
    return out


def compute_metrics(comparisons: Iterable[DecisionComparison]) -> DecisionMetrics:
    rows = [r for r in comparisons if r.actual is not None]
    correct, n, acc = agreement(rows)
    matrix = build_confusion_matrix(rows)
    labels = [x.value for x in FinalDecisionStatus]

    recalls: dict[str, Optional[float]] = {}
    f1s = []
    for label in labels:
        tp = matrix[label][label]
        support = sum(matrix[label].values())
        predicted = sum(matrix[e][label] for e in labels)
        recalls[label] = (tp / support) if support else None
        precision = (tp / predicted) if predicted else None
        recall = recalls[label]
        if precision is not None and recall is not None:
            f1s.append(0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall))

    hard_no_go = {FinalDecisionStatus.NO_GO_SAFETY, FinalDecisionStatus.NO_GO_REGULATORY}
    serious_fn = sum(
        1 for r in rows
        if r.expected == FinalDecisionStatus.NO_GO_SAFETY and r.actual != FinalDecisionStatus.NO_GO_SAFETY
    )
    regulatory_fn = sum(
        1 for r in rows
        if r.expected == FinalDecisionStatus.NO_GO_REGULATORY and r.actual != FinalDecisionStatus.NO_GO_REGULATORY
    )
    false_no_go = sum(
        1 for r in rows if r.expected not in hard_no_go and r.actual in hard_no_go
    )
    expert_overuse = sum(
        1 for r in rows
        if r.actual == FinalDecisionStatus.EXPERT_REVIEW_REQUIRED
        and r.expected != FinalDecisionStatus.EXPERT_REVIEW_REQUIRED
    )
    insufficient_miss = sum(
        1 for r in rows
        if r.expected == FinalDecisionStatus.INSUFFICIENT_EVIDENCE
        and r.actual != FinalDecisionStatus.INSUFFICIENT_EVIDENCE
    )

    return DecisionMetrics(
        n_scored=n,
        n_correct=correct,
        accuracy=acc,
        macro_f1=(sum(f1s) / len(f1s)) if f1s else None,
        per_class_recall=recalls,
        serious_safety_false_negatives=serious_fn,
        regulatory_false_negatives=regulatory_fn,
        false_no_go=false_no_go,
        expert_review_overuse=expert_overuse,
        insufficient_evidence_miss=insufficient_miss,
        confusion_matrix=matrix,
    )


def validate_no_holdout_leakage(case_ids_used_for_remediation: Iterable[str], holdout_case_ids: Iterable[str]) -> None:
    overlap = set(case_ids_used_for_remediation) & set(holdout_case_ids)
    if overlap:
        raise ValueError(f"Holdout leakage: remediation set overlaps holdout: {sorted(overlap)}")
