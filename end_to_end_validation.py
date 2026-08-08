"""Phase 7 — End-to-End scientific validation and reproducible benchmarking.

This module EXTENDS the existing GoldCase/EvaluationRun architecture rather than
creating a second notion of scientific truth. GoldCase remains the truth unit;
ValidationScope.PROVIDED_EVIDENCE remains owned by evaluation_run.py. This file
implements the reserved ValidationScope.END_TO_END path where evidence must be
obtained through a retrieval adapter from the clinical/botanical question.

FrozenSnapshotRetriever is deterministic and intended for CI/regression. A live
retriever is supplied as the same callable interface and is recorded as LIVE;
results from the two modes are never pooled.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Iterable, Optional

import pandas as pd

from assertion_vocabulary import ValidationScope
from botanical_rd_candidate_engine import BotanicalRDCandidateEngine
from evidence_interpretation import interpret_evidence
from gold_case import DecisionDirection, GoldCase
from knowledge_retrieval_engine import get_candidate_plants
from metric_report import MetricReport, build_proportion_metric, build_continuous_metric


class BenchmarkMode(str, Enum):
    FROZEN_SNAPSHOT = "frozen-snapshot"
    LIVE_RETRIEVAL = "live-retrieval"


class FailureStage(str, Enum):
    RETRIEVAL_FAILURE = "RETRIEVAL_FAILURE"
    DEDUPLICATION_FAILURE = "DEDUPLICATION_FAILURE"
    CLASSIFICATION_FAILURE = "CLASSIFICATION_FAILURE"
    DIRECTION_FAILURE = "DIRECTION_FAILURE"
    APPLICABILITY_FAILURE = "APPLICABILITY_FAILURE"
    SAFETY_GATE_FAILURE = "SAFETY_GATE_FAILURE"
    REGULATORY_GATE_FAILURE = "REGULATORY_GATE_FAILURE"
    SCORING_FAILURE = "SCORING_FAILURE"
    DECISION_FAILURE = "DECISION_FAILURE"
    RANKING_FAILURE = "RANKING_FAILURE"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    REFERENCE_AMBIGUITY = "REFERENCE_AMBIGUITY"


class FailureSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class SourceRole(str, Enum):
    CRITICAL = "critical"
    SUPPORTING = "supporting"
    OPTIONAL = "optional"
    IRRELEVANT = "irrelevant"
    DUPLICATE = "duplicate"


@dataclass(frozen=True)
class GoldSourceExpectation:
    reference_id: str
    role: SourceRole
    source_type: Optional[str] = None
    expected_study_design: Optional[str] = None
    expected_direction: Optional[str] = None
    expected_applicability: Optional[str] = None
    expected_source_authority: Optional[str] = None
    expected_evidence_quality: Optional[str] = None
    safety_critical: bool = False
    regulatory_critical: bool = False
    duplicate_of: Optional[str] = None


@dataclass(frozen=True)
class GoldSourceSet:
    sources: tuple[GoldSourceExpectation, ...] = ()

    def by_role(self, role: SourceRole) -> tuple[GoldSourceExpectation, ...]:
        return tuple(s for s in self.sources if s.role == role)

    def relevant_ids(self) -> set[str]:
        return {s.reference_id for s in self.sources if s.role in {SourceRole.CRITICAL, SourceRole.SUPPORTING}}

    def critical_ids(self) -> set[str]:
        return {s.reference_id for s in self.sources if s.role == SourceRole.CRITICAL}


@dataclass(frozen=True)
class ValidationQuestion:
    question: str
    indication: str
    dosage_form: str
    market: str
    product_type: str = "Botanical"


@dataclass(frozen=True)
class RetrievedEvidence:
    reference_id: str
    scientific_name: str
    notes: str
    source_type: str = ""
    source_title: str = ""
    source_url: str = ""
    pmid: str = ""
    doi: str = ""
    nct_id: str = ""
    target_indication: str = ""
    dosage_form: str = ""
    study_design: Optional[str] = None
    evidence_direction: Optional[str] = None
    applicability: Optional[str] = None
    source_authority: Optional[str] = None
    evidence_quality: Optional[str] = None
    source_available: bool = True
    publication_year: Optional[int] = None

    def article_identity(self) -> str:
        for prefix, value in (("doi", self.doi), ("pmid", self.pmid), ("nct", self.nct_id)):
            if value and str(value).strip():
                return f"{prefix}:{str(value).strip().lower()}"
        title = " ".join(self.source_title.lower().split())
        if title:
            return f"title:{title}"
        return f"ref:{self.reference_id.lower()}"

    def to_engine_row(self, indication: str, dosage_form: str, market: str) -> dict:
        return {
            "Evidence_Record_ID": self.reference_id,
            "Scientific_Name": self.scientific_name,
            "Target_Indication": self.target_indication or indication,
            "Dosage_Form": self.dosage_form or dosage_form,
            "Target_Market": market,
            "Notes": self.notes,
            "Source_Type": self.source_type,
            "Source_Title": self.source_title,
            "Source_URL": self.source_url,
            "PMID": self.pmid,
            "DOI": self.doi,
            "NCT_ID": self.nct_id,
            "Study_Type": self.study_design or "",
            "Result_Direction": self.evidence_direction or "",
            "Evidence_Level": self.evidence_quality or "",
            "Source_Authority": self.source_authority or "",
            "Source_Year": self.publication_year or "",
        }


@dataclass
class ValidationFailure:
    case_id: str
    stage: FailureStage
    severity: FailureSeverity
    code: str
    detail: str
    reference_id: Optional[str] = None


@dataclass(frozen=True)
class BenchmarkVersions:
    benchmark_version: str
    gold_corpus_version: str
    scoring_model_version: str
    ruleset_version: str
    evidence_schema_version: str
    connector_versions: dict = field(default_factory=dict)


@dataclass
class EndToEndCaseResult:
    case_id: str
    retrieved_reference_ids: list[str] = field(default_factory=list)
    unique_reference_ids: list[str] = field(default_factory=list)
    candidate_ranking: list[str] = field(default_factory=list)
    decision_class: Optional[str] = None
    decision_direction: Optional[DecisionDirection] = None
    gate_results: dict = field(default_factory=dict)
    failures: list[ValidationFailure] = field(default_factory=list)
    source_counts: dict = field(default_factory=dict)
    classification_checks: list[dict] = field(default_factory=list)
    expected_gold_candidate: Optional[str] = None
    expected_decision_direction: Optional[DecisionDirection] = None
    expected_decision_class_min: Optional[str] = None
    expected_decision_class_max: Optional[str] = None


@dataclass
class EndToEndEvaluationRun:
    evaluation_run_id: str
    validation_scope: ValidationScope
    mode: BenchmarkMode
    versions: BenchmarkVersions
    execution_timestamp: datetime
    data_snapshot: str
    configuration_hash: str
    case_results: list[EndToEndCaseResult]
    metrics: list[MetricReport]
    limitations: list[str] = field(default_factory=list)


class FrozenSnapshotRetriever:
    """Deterministic retrieval over a frozen connector-output snapshot.

    Search uses only question/candidate fields. It never receives GoldCase or
    case_id, which prevents gold-case identifiers from changing retrieval.
    """
    version = "frozen-snapshot-retriever/1"

    def __init__(self, records: Iterable[RetrievedEvidence]):
        self.records = tuple(records)

    def __call__(self, question: ValidationQuestion, candidates: list[str]) -> list[RetrievedEvidence]:
        cand = {_norm_taxon(x) for x in candidates}
        indication = _norm(question.indication)
        out = []
        for rec in self.records:
            if cand and _norm_taxon(rec.scientific_name) not in cand:
                continue
            if rec.target_indication and indication and indication not in _norm(rec.target_indication) and _norm(rec.target_indication) not in indication:
                continue
            out.append(rec)
        return out


def _norm(v) -> str:
    return " ".join(str(v or "").strip().lower().split())


def _norm_taxon(v) -> str:
    # authority suffixes are often absent from production candidate tables;
    # species binomial is the stable comparison key, not a GoldCase-specific rule.
    parts = _norm(v).replace("×", "x").split()
    return " ".join(parts[:2]) if len(parts) >= 2 else " ".join(parts)


def _derive_direction(decision_class: Optional[str]) -> Optional[DecisionDirection]:
    if decision_class in {
        "Strong R&D candidate",
        "Promising candidate; verify safety and standardization",
        "Early-stage candidate; more evidence needed",
    }:
        return DecisionDirection.POSITIVE
    if decision_class in {
        "Safety concern — not suitable without expert review",
        "Regulatory prohibition — not suitable without regulatory review",
    }:
        return DecisionDirection.NEGATIVE
    if decision_class == "Low priority / insufficient data":
        return DecisionDirection.HOLD
    return None


def _deduplicate(records: list[RetrievedEvidence]) -> tuple[list[RetrievedEvidence], int]:
    seen = set(); unique = []; duplicates = 0
    for rec in records:
        key = rec.article_identity()
        if key in seen:
            duplicates += 1
            continue
        seen.add(key); unique.append(rec)
    return unique, duplicates


def _classification_for(rec: RetrievedEvidence) -> dict:
    interpreted = interpret_evidence(rec.notes or "")
    return {
        "study_design": rec.study_design or interpreted.study_design,
        "evidence_direction": rec.evidence_direction or interpreted.evidence_direction,
        "applicability": rec.applicability or interpreted.evidence_applicability,
        "evidence_quality": rec.evidence_quality or interpreted.evidence_quality,
        "source_authority": rec.source_authority,
    }


def _build_plant_df(candidates: list[str], indication: str) -> pd.DataFrame:
    # Neutral shared compound is plumbing needed by the existing production
    # engine. Candidate names come from discovery, never from expected output.
    return pd.DataFrame([
        {"scientific_name": c, "compound_name": "validation_shared_compound", "indication": indication,
         "target": "unspecified", "common_name": "", "plant_part": "", "extraction_method": ""}
        for c in candidates
    ])


def default_candidate_discovery(question: ValidationQuestion) -> list[str]:
    return list(get_candidate_plants(question.indication))


def run_end_to_end_case(
    gold_case: GoldCase,
    question: ValidationQuestion,
    gold_sources: GoldSourceSet,
    retriever: Callable[[ValidationQuestion, list[str]], list[RetrievedEvidence]],
    candidate_discovery: Callable[[ValidationQuestion], list[str]] = default_candidate_discovery,
    use_live_search: bool = False,
) -> EndToEndCaseResult:
    result = EndToEndCaseResult(
        case_id=gold_case.case_id,
        expected_gold_candidate=gold_case.validation_unit.taxon,
        expected_decision_direction=gold_case.expected_output.expected_decision_direction,
        expected_decision_class_min=gold_case.expected_output.acceptable_decision_class_min,
        expected_decision_class_max=gold_case.expected_output.acceptable_decision_class_max,
    )
    candidates = list(dict.fromkeys(candidate_discovery(question) or []))
    gold_taxon_norm = _norm_taxon(gold_case.validation_unit.taxon)

    if gold_taxon_norm not in {_norm_taxon(c) for c in candidates}:
        result.failures.append(ValidationFailure(
            gold_case.case_id, FailureStage.RETRIEVAL_FAILURE, FailureSeverity.HIGH,
            "GOLD_CANDIDATE_NOT_DISCOVERED", "Expected botanical candidate was not discovered from the question/input."
        ))

    try:
        retrieved = list(retriever(question, candidates) or [])
    except Exception as exc:  # live connector failures are data availability, not clearance
        result.failures.append(ValidationFailure(
            gold_case.case_id, FailureStage.SOURCE_UNAVAILABLE, FailureSeverity.HIGH,
            "RETRIEVER_EXCEPTION", f"{type(exc).__name__}: {exc}"
        ))
        retrieved = []

    unavailable = [r for r in retrieved if not r.source_available]
    for rec in unavailable:
        result.failures.append(ValidationFailure(
            gold_case.case_id, FailureStage.SOURCE_UNAVAILABLE, FailureSeverity.HIGH,
            "SOURCE_UNAVAILABLE", "Retriever reported source unavailable.", rec.reference_id
        ))
    retrieved = [r for r in retrieved if r.source_available]
    result.retrieved_reference_ids = [r.reference_id for r in retrieved]

    unique, duplicate_count = _deduplicate(retrieved)
    result.unique_reference_ids = [r.reference_id for r in unique]
    result.source_counts["retrieved"] = len(retrieved)
    result.source_counts["unique"] = len(unique)
    result.source_counts["duplicates"] = duplicate_count

    expected_by_id = {s.reference_id: s for s in gold_sources.sources}
    retrieved_ids = set(result.unique_reference_ids)
    critical = gold_sources.critical_ids()
    relevant = gold_sources.relevant_ids()
    irrelevant = {s.reference_id for s in gold_sources.by_role(SourceRole.IRRELEVANT)}
    missing_critical = sorted(critical - retrieved_ids)
    for ref_id in missing_critical:
        exp = expected_by_id[ref_id]
        severity = FailureSeverity.CRITICAL if exp.safety_critical or exp.regulatory_critical else FailureSeverity.HIGH
        result.failures.append(ValidationFailure(
            gold_case.case_id, FailureStage.RETRIEVAL_FAILURE, severity,
            "CRITICAL_SOURCE_MISSED", "Critical gold source was not retrieved.", ref_id
        ))
    safety_critical_ids = {s.reference_id for s in gold_sources.sources if s.safety_critical}
    regulatory_critical_ids = {s.reference_id for s in gold_sources.sources if s.regulatory_critical}
    result.source_counts.update({
        "critical_total": len(critical),
        "critical_retrieved": len(critical & retrieved_ids),
        "relevant_total": len(relevant),
        "relevant_retrieved": len(relevant & retrieved_ids),
        "known_irrelevant_retrieved": len(irrelevant & retrieved_ids),
        "safety_critical_total": len(safety_critical_ids),
        "safety_critical_retrieved": len(safety_critical_ids & retrieved_ids),
        "regulatory_critical_total": len(regulatory_critical_ids),
        "regulatory_critical_retrieved": len(regulatory_critical_ids & retrieved_ids),
    })

    for rec in unique:
        exp = expected_by_id.get(rec.reference_id)
        if not exp:
            continue
        actual = _classification_for(rec)
        check = {"reference_id": rec.reference_id, "actual": actual, "expected": {}}
        field_map = {
            "expected_study_design": "study_design",
            "expected_direction": "evidence_direction",
            "expected_applicability": "applicability",
            "expected_source_authority": "source_authority",
            "expected_evidence_quality": "evidence_quality",
        }
        for field_name, actual_name in field_map.items():
            expected_value = getattr(exp, field_name)
            if expected_value is None:
                continue
            check["expected"][actual_name] = expected_value
            if actual.get(actual_name) != expected_value:
                stage = {
                    "study_design": FailureStage.CLASSIFICATION_FAILURE,
                    "evidence_direction": FailureStage.DIRECTION_FAILURE,
                    "applicability": FailureStage.APPLICABILITY_FAILURE,
                    "source_authority": FailureStage.CLASSIFICATION_FAILURE,
                    "evidence_quality": FailureStage.CLASSIFICATION_FAILURE,
                }[actual_name]
                result.failures.append(ValidationFailure(
                    gold_case.case_id, stage, FailureSeverity.HIGH,
                    f"{actual_name.upper()}_MISMATCH",
                    f"Expected {expected_value!r}, got {actual.get(actual_name)!r}.", rec.reference_id
                ))
        result.classification_checks.append(check)

    # Run the REAL production engine only from discovered candidates + retrieved evidence.
    if candidates:
        evidence_df = pd.DataFrame([r.to_engine_row(question.indication, question.dosage_form, question.market) for r in unique])
        try:
            engine = BotanicalRDCandidateEngine(
                plant_compounds_df=_build_plant_df(candidates, question.indication),
                compound_profiles_df=pd.DataFrame(), scientific_evidence_df=pd.DataFrame(),
                evidence_df=evidence_df, use_live_search=use_live_search,
            )
            output = engine.run(indication=question.indication, dosage_form=question.dosage_form, market=question.market)
            if not output.empty:
                # ranking is the engine's actual output order after its production partition/sort.
                result.candidate_ranking = list(dict.fromkeys(output["Alternative_Plant"].astype(str).tolist()))
                target_rows = output[output["Alternative_Plant"].map(_norm_taxon) == gold_taxon_norm]
                if not target_rows.empty:
                    row = target_rows.iloc[0]
                    result.decision_class = row.get("Decision_Class")
                    result.decision_direction = _derive_direction(result.decision_class)
                    result.gate_results = row.get("Gate_Results") or {}
        except Exception as exc:
            result.failures.append(ValidationFailure(
                gold_case.case_id, FailureStage.DECISION_FAILURE, FailureSeverity.HIGH,
                "ENGINE_EXECUTION_ERROR", f"{type(exc).__name__}: {exc}"
            ))

    expected_direction = gold_case.expected_output.expected_decision_direction
    if expected_direction is not None and result.decision_direction is not None and result.decision_direction != expected_direction:
        result.failures.append(ValidationFailure(
            gold_case.case_id, FailureStage.DECISION_FAILURE, FailureSeverity.HIGH,
            "DECISION_DIRECTION_MISMATCH", f"Expected {expected_direction.value}, got {result.decision_direction.value}."
        ))

    # Zero-tolerance safety/regulatory: if a critical source WAS retrieved yet the corresponding gate did not fail,
    # attribution belongs to the gate, not retrieval.
    from data_contracts import GateStatus
    safety_critical_retrieved = any(s.safety_critical and s.reference_id in retrieved_ids for s in gold_sources.sources)
    reg_critical_retrieved = any(s.regulatory_critical and s.reference_id in retrieved_ids for s in gold_sources.sources)
    if safety_critical_retrieved:
        status = ((result.gate_results.get("safety") or {}).get("status"))
        if status != GateStatus.FAILED:
            result.failures.append(ValidationFailure(
                gold_case.case_id, FailureStage.SAFETY_GATE_FAILURE, FailureSeverity.CRITICAL,
                "SERIOUS_SAFETY_EVIDENCE_IGNORED", "Serious safety evidence was retrieved but the safety gate did not fail."
            ))
    if reg_critical_retrieved:
        status = ((result.gate_results.get("regulatory") or {}).get("status"))
        if status != GateStatus.FAILED:
            result.failures.append(ValidationFailure(
                gold_case.case_id, FailureStage.REGULATORY_GATE_FAILURE, FailureSeverity.CRITICAL,
                "REGULATORY_PROHIBITION_IGNORED", "Critical regulatory evidence was retrieved but the regulatory gate did not fail."
            ))

    safety_status = ((result.gate_results.get("safety") or {}).get("status"))
    regulatory_status = ((result.gate_results.get("regulatory") or {}).get("status"))
    result.source_counts["safety_gate_failed"] = int(safety_status == GateStatus.FAILED)
    result.source_counts["regulatory_gate_failed"] = int(regulatory_status == GateStatus.FAILED)

    # Ranking safety invariants.
    no_go = result.decision_direction == DecisionDirection.NEGATIVE
    if no_go and result.candidate_ranking and result.expected_gold_candidate in result.candidate_ranking[:5]:
        result.failures.append(ValidationFailure(
            gold_case.case_id, FailureStage.RANKING_FAILURE, FailureSeverity.CRITICAL,
            "NO_GO_IN_TOP5", "A NO_GO/negative candidate appears in Top-5 ranking."
        ))
    return result


def _aggregate_metrics(case_results: list[EndToEndCaseResult]) -> tuple[list[MetricReport], list[str]]:
    metrics: list[MetricReport] = []
    limitations: list[str] = []

    critical_num = sum(r.source_counts.get("critical_retrieved", 0) for r in case_results)
    critical_den = sum(r.source_counts.get("critical_total", 0) for r in case_results)
    metrics.append(build_proportion_metric("critical_source_recall", critical_num, critical_den,
        "Critical sources retrieved / critical gold sources."))

    rel_num = sum(r.source_counts.get("relevant_retrieved", 0) for r in case_results)
    rel_den = sum(r.source_counts.get("relevant_total", 0) for r in case_results)
    metrics.append(build_proportion_metric("evidence_retrieval_recall", rel_num, rel_den))

    unique_total = sum(r.source_counts.get("unique", 0) for r in case_results)
    irrelevant_num = sum(r.source_counts.get("known_irrelevant_retrieved", 0) for r in case_results)
    if unique_total:
        metrics.append(build_proportion_metric("irrelevant_evidence_rate", irrelevant_num, unique_total))
    else:
        metrics.append(build_proportion_metric("irrelevant_evidence_rate", 0, 0))

    retrieved_total = sum(r.source_counts.get("retrieved", 0) for r in case_results)
    dup_total = sum(r.source_counts.get("duplicates", 0) for r in case_results)
    metrics.append(build_proportion_metric("duplicate_retrieval_rate", dup_total, retrieved_total))

    # Precision is only valid where the GoldSourceSet explicitly enumerates known irrelevant/relevant corpus labels.
    labelled_retrieved = 0; relevant_labelled = 0
    for r in case_results:
        labelled_retrieved += r.source_counts.get("relevant_retrieved", 0) + r.source_counts.get("known_irrelevant_retrieved", 0)
        relevant_labelled += r.source_counts.get("relevant_retrieved", 0)
    metrics.append(build_proportion_metric("evidence_retrieval_precision_labelled_subset", relevant_labelled, labelled_retrieved,
        "Computed only over explicitly gold-labelled relevant/irrelevant retrieved sources; not full-corpus precision."))
    limitations.append("Retrieval precision is restricted to the explicitly labelled Gold Source subset unless a fully adjudicated retrieval corpus is supplied.")

    for metric_field, metric_name in [
        ("study_design", "study_design_accuracy"),
        ("evidence_direction", "evidence_direction_accuracy"),
        ("applicability", "applicability_classification_accuracy"),
        ("source_authority", "source_authority_classification_accuracy"),
        ("evidence_quality", "evidence_quality_classification_agreement"),
    ]:
        num=den=0
        for r in case_results:
            for chk in r.classification_checks:
                if metric_field in chk["expected"]:
                    den += 1
                    num += int(chk["actual"].get(metric_field) == chk["expected"][metric_field])
        metrics.append(build_proportion_metric(metric_name, num, den))

    # Safety: retrieval and gate failure are separate causal stages.
    safety_total = sum(r.source_counts.get("safety_critical_total", 0) for r in case_results)
    safety_retrieved = sum(r.source_counts.get("safety_critical_retrieved", 0) for r in case_results)
    metrics.append(build_proportion_metric("safety_source_recall", safety_retrieved, safety_total))
    safety_case_results = [r for r in case_results if r.source_counts.get("safety_critical_total", 0) > 0]
    safety_fn = sum(1 for r in safety_case_results if r.source_counts.get("safety_critical_retrieved",0)==0 or not r.source_counts.get("safety_gate_failed",0))
    metrics.append(build_proportion_metric("serious_safety_false_negative_rate", safety_fn, len(safety_case_results),
        "Zero-tolerance; retrieval misses and retrieved-but-ignored gate misses remain separately attributed in failures."))
    safety_gate_eligible = [r for r in safety_case_results if r.source_counts.get("safety_critical_retrieved",0)>0]
    metrics.append(build_proportion_metric("safety_gate_sensitivity", sum(r.source_counts.get("safety_gate_failed",0) for r in safety_gate_eligible), len(safety_gate_eligible)))
    safety_negative_cases = [r for r in case_results if r.source_counts.get("safety_critical_total",0)==0 and r.gate_results]
    metrics.append(build_proportion_metric("safety_gate_specificity", sum(1-int(r.source_counts.get("safety_gate_failed",0)) for r in safety_negative_cases), len(safety_negative_cases)))
    expert_review_cases = sum(1 for r in case_results if r.decision_class and "expert review" in r.decision_class.lower())
    metrics.append(build_proportion_metric("safety_expert_review_rate", expert_review_cases, sum(1 for r in case_results if r.decision_class is not None)))

    # Regulatory metrics.
    reg_total = sum(r.source_counts.get("regulatory_critical_total",0) for r in case_results)
    reg_retrieved = sum(r.source_counts.get("regulatory_critical_retrieved",0) for r in case_results)
    metrics.append(build_proportion_metric("regulatory_prohibition_recall", reg_retrieved, reg_total))
    reg_eligible = [r for r in case_results if r.source_counts.get("regulatory_critical_retrieved",0)>0]
    metrics.append(build_proportion_metric("restriction_detection_rate", sum(r.source_counts.get("regulatory_gate_failed",0) for r in reg_eligible), len(reg_eligible)))
    metrics.append(build_proportion_metric("regulatory_status_agreement", sum(r.source_counts.get("regulatory_gate_failed",0) for r in reg_eligible), len(reg_eligible),
        "For currently labelled prohibition/restriction Gold cases; broader status categories require additional adjudicated corpus."))

    # decision direction agreement
    dir_den=dir_num=0
    for r in case_results:
        # mismatch failure means expected existed; absence of mismatch with actual direction is agreement.
        mismatch = any(f.code == "DECISION_DIRECTION_MISMATCH" for f in r.failures)
        if r.decision_direction is not None:
            dir_den += 1; dir_num += int(not mismatch)
    metrics.append(build_proportion_metric("decision_direction_agreement", dir_num, dir_den))
    negative_expected = [r for r in case_results if r.expected_decision_direction == DecisionDirection.NEGATIVE]
    metrics.append(build_proportion_metric("no_go_recall", sum(r.decision_direction == DecisionDirection.NEGATIVE for r in negative_expected), len(negative_expected)))
    positive_or_strong = [r for r in case_results if r.decision_direction == DecisionDirection.POSITIVE]
    unsafe_positive = sum(any(f.severity == FailureSeverity.CRITICAL and f.stage in {FailureStage.RETRIEVAL_FAILURE, FailureStage.SAFETY_GATE_FAILURE, FailureStage.REGULATORY_GATE_FAILURE} for f in r.failures) for r in positive_or_strong)
    metrics.append(build_proportion_metric("unsafe_positive_decision_rate", unsafe_positive, len(positive_or_strong)))
    strong = [r for r in case_results if r.decision_class == "Strong R&D candidate"]
    invalid_strong = sum(any(f.severity in {FailureSeverity.CRITICAL, FailureSeverity.HIGH} for f in r.failures) for r in strong)
    metrics.append(build_proportion_metric("invalid_strong_recommendation_rate", invalid_strong, len(strong)))
    incomplete = [r for r in case_results if r.decision_direction == DecisionDirection.HOLD]
    incomplete_as_validated = sum(r.expected_decision_direction == DecisionDirection.POSITIVE for r in incomplete)
    metrics.append(build_proportion_metric("incomplete_as_validated_error_rate", incomplete_as_validated, len(incomplete)))

    # Top-k inclusion for expected gold botanical when ranking has enough candidates.
    for k in (3,5):
        den=num=0
        for r in case_results:
            if len(r.candidate_ranking) >= k and r.expected_gold_candidate:
                den += 1
                normalized = {_norm_taxon(x) for x in r.candidate_ranking[:k]}
                num += int(_norm_taxon(r.expected_gold_candidate) in normalized)
        metrics.append(build_proportion_metric(f"top_{k}_inclusion", num, den))

    gold_ranks = []
    for r in case_results:
        target = _norm_taxon(r.expected_gold_candidate) if r.expected_gold_candidate else None
        ranked = [_norm_taxon(x) for x in r.candidate_ranking]
        if target and target in ranked:
            gold_ranks.append(ranked.index(target) + 1)
    metrics.append(build_continuous_metric("gold_candidate_rank", gold_ranks))

    unsafe_top5_num = sum(any(f.code == "NO_GO_IN_TOP5" for f in r.failures) for r in case_results)
    unsafe_top5_den = sum(1 for r in case_results if len(r.candidate_ranking) >= 1)
    metrics.append(build_proportion_metric("unsafe_candidate_in_top5_rate", unsafe_top5_num, unsafe_top5_den))
    return metrics, limitations


def configuration_hash(config: dict) -> str:
    payload = json.dumps(config, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(payload).hexdigest()


def build_end_to_end_evaluation_run(
    cases: list[tuple[GoldCase, ValidationQuestion, GoldSourceSet]],
    retriever,
    versions: BenchmarkVersions,
    mode: BenchmarkMode,
    candidate_discovery: Callable[[ValidationQuestion], list[str]] = default_candidate_discovery,
    data_snapshot: str = "unspecified",
    config: Optional[dict] = None,
    execution_timestamp: Optional[datetime] = None,
    evaluation_run_id: Optional[str] = None,
) -> EndToEndEvaluationRun:
    results = [run_end_to_end_case(gc, q, gs, retriever, candidate_discovery, mode == BenchmarkMode.LIVE_RETRIEVAL) for gc,q,gs in cases]
    metrics, limitations = _aggregate_metrics(results)
    return EndToEndEvaluationRun(
        evaluation_run_id=evaluation_run_id or str(uuid.uuid4()),
        validation_scope=ValidationScope.END_TO_END,
        mode=mode,
        versions=versions,
        execution_timestamp=execution_timestamp or datetime.now(timezone.utc),
        data_snapshot=data_snapshot,
        configuration_hash=configuration_hash(config or {}),
        case_results=results,
        metrics=metrics,
        limitations=limitations,
    )


def compare_benchmark_runs(baseline: EndToEndEvaluationRun, current: EndToEndEvaluationRun) -> dict:
    if baseline.mode != current.mode:
        raise ValueError("Frozen Snapshot and Live Retrieval runs must not be compared as if they were the same benchmark mode.")
    def points(run):
        out={}
        for m in run.metrics:
            if m.proportion and m.proportion.point_estimate is not None:
                out[m.metric_name]=m.proportion.point_estimate
            elif m.continuous and m.continuous.mean is not None:
                out[m.metric_name]=m.continuous.mean
        return out
    b=points(baseline); c=points(current)
    improved=[]; worsened=[]
    lower_is_better={"irrelevant_evidence_rate","duplicate_retrieval_rate","serious_safety_false_negative_rate","unsafe_candidate_in_top5_rate"}
    for name in sorted(b.keys() & c.keys()):
        if c[name] == b[name]: continue
        good = c[name] < b[name] if name in lower_is_better else c[name] > b[name]
        (improved if good else worsened).append({"metric":name,"before":b[name],"after":c[name]})
    bcases={r.case_id:r for r in baseline.case_results}; ccases={r.case_id:r for r in current.case_results}
    def critical(r): return {f.code for f in r.failures if f.severity == FailureSeverity.CRITICAL}
    new_critical=[]; resolved_critical=[]; cases_fixed=[]; cases_regressed=[]; decision_changes=[]; ranking_changes=[]; retrieval_changes=[]
    for cid in sorted(bcases.keys() & ccases.keys()):
        br,cr=bcases[cid],ccases[cid]
        bc,cc=critical(br),critical(cr)
        if cc-bc: new_critical.append({"case_id":cid,"failures":sorted(cc-bc)})
        if bc-cc: resolved_critical.append({"case_id":cid,"failures":sorted(bc-cc)})
        if br.failures and not cr.failures: cases_fixed.append(cid)
        if not br.failures and cr.failures: cases_regressed.append(cid)
        if br.decision_class != cr.decision_class: decision_changes.append({"case_id":cid,"before":br.decision_class,"after":cr.decision_class})
        if br.candidate_ranking != cr.candidate_ranking: ranking_changes.append(cid)
        if br.unique_reference_ids != cr.unique_reference_ids: retrieval_changes.append(cid)
    return {"metric_improved":improved,"metric_worsened":worsened,"cases_fixed":cases_fixed,"cases_regressed":cases_regressed,
            "new_critical_failures":new_critical,"resolved_critical_failures":resolved_critical,"retrieval_changes":retrieval_changes,
            "decision_changes":decision_changes,"ranking_changes":ranking_changes}


def run_to_dict(run: EndToEndEvaluationRun) -> dict:
    """JSON-safe snapshot; append-only persistence can store this without overwriting prior runs."""
    def conv(obj):
        if isinstance(obj, Enum): return obj.value
        if isinstance(obj, datetime): return obj.isoformat()
        if hasattr(obj, "__dataclass_fields__"): return {k: conv(v) for k,v in asdict(obj).items()}
        if isinstance(obj, dict): return {str(k):conv(v) for k,v in obj.items()}
        if isinstance(obj, (list,tuple)): return [conv(v) for v in obj]
        return obj
    return conv(run)

class LiveMultiSourceRetriever:
    """Adapter over the repository's existing production multi-source collector.

    Import is deliberately lazy so CI/frozen benchmarks do not require Supabase.
    Each discovered candidate is retrieved independently from the same question;
    no GoldCase identifier or expected result is passed to the collector.
    Connector errors are exposed as unavailable pseudo-records so validation can
    attribute SOURCE_UNAVAILABLE rather than silently treating absence as clear.
    """
    version = "multi-source-collector-adapter/1"

    def __init__(self, max_results_per_source: int = 5):
        self.max_results_per_source = max_results_per_source

    @staticmethod
    def _record_from_legacy(item: dict, candidate: str, question: ValidationQuestion, index: int) -> RetrievedEvidence:
        rec = item.get("record") if isinstance(item.get("record"), dict) else item
        ref_id = (
            rec.get("Evidence_Record_ID") or rec.get("DOI") or rec.get("PMID") or
            rec.get("NCT_ID") or rec.get("Source_URL") or
            f"live:{_norm_taxon(candidate)}:{index}"
        )
        return RetrievedEvidence(
            reference_id=str(ref_id), scientific_name=rec.get("Scientific_Name") or candidate,
            notes=rec.get("Notes") or rec.get("Evidence_Text") or rec.get("Abstract") or rec.get("Raw_Text") or "",
            source_type=rec.get("Source_Type") or "", source_title=rec.get("Source_Title") or rec.get("Title") or "",
            source_url=rec.get("Source_URL") or rec.get("URL") or "", pmid=str(rec.get("PMID") or item.get("pmid") or ""),
            doi=str(rec.get("DOI") or ""), nct_id=str(rec.get("NCT_ID") or ""),
            target_indication=rec.get("Target_Indication") or question.indication,
            dosage_form=rec.get("Dosage_Form") or question.dosage_form,
            study_design=rec.get("Study_Type") or None, evidence_direction=rec.get("Result_Direction") or None,
            source_authority=rec.get("Source_Authority") or None, evidence_quality=rec.get("Evidence_Level") or None,
        )

    def __call__(self, question: ValidationQuestion, candidates: list[str]) -> list[RetrievedEvidence]:
        try:
            from multi_source_collector import collect_multi_source_evidence
        except Exception as exc:
            return [RetrievedEvidence(
                reference_id="live-collector-unavailable", scientific_name="", notes="",
                source_type="MULTI_SOURCE", source_available=False,
                source_title=f"Collector import unavailable: {type(exc).__name__}: {exc}",
            )]
        out: list[RetrievedEvidence] = []
        for candidate in candidates:
            try:
                payload = collect_multi_source_evidence(
                    scientific_name=candidate, indication=question.indication,
                    dosage_form=question.dosage_form, market=question.market,
                    save=False, max_results_override=self.max_results_per_source,
                )
                for i, item in enumerate(payload.get("saved_records") or []):
                    if isinstance(item, dict):
                        out.append(self._record_from_legacy(item, candidate, question, i))
                for err in payload.get("errors") or []:
                    source = err.get("source", "unknown") if isinstance(err, dict) else "unknown"
                    detail = err.get("error", str(err)) if isinstance(err, dict) else str(err)
                    out.append(RetrievedEvidence(
                        reference_id=f"unavailable:{_norm_taxon(candidate)}:{source}", scientific_name=candidate,
                        notes="", source_type=source, source_title=detail, source_available=False,
                        target_indication=question.indication, dosage_form=question.dosage_form,
                    ))
            except Exception as exc:
                out.append(RetrievedEvidence(
                    reference_id=f"unavailable:{_norm_taxon(candidate)}:collector", scientific_name=candidate,
                    notes="", source_type="MULTI_SOURCE", source_title=f"{type(exc).__name__}: {exc}",
                    source_available=False, target_indication=question.indication, dosage_form=question.dosage_form,
                ))
        return out


def persist_end_to_end_run(run: EndToEndEvaluationRun, directory: str) -> str:
    """Append-only filesystem persistence for reproducible benchmark snapshots.

    A run ID maps to one immutable JSON file. Existing files are never replaced.
    """
    from pathlib import Path
    target_dir = Path(directory)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{run.evaluation_run_id}.json"
    if path.exists():
        raise FileExistsError(f"Benchmark run {run.evaluation_run_id!r} already exists; append-only persistence refuses overwrite.")
    path.write_text(json.dumps(run_to_dict(run), indent=2, sort_keys=True, default=str), encoding="utf-8")
    return str(path)
