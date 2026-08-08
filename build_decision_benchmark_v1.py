"""Build leakage-controlled Decision Benchmark v1 artifacts.

Produces:
- split manifest (no engine outputs, no truth labels)
- blind expert adjudication packet (reference material, no engine/truth decision)
- development metrics from the seven already-remediated frozen snapshots
- prospective holdout status, intentionally UNSCORED until independent engine snapshots exist
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pandas as pd

from botanical_rd_candidate_engine import BotanicalRDCandidateEngine
from decision_benchmark_v1 import (
    BENCHMARK_VERSION, BenchmarkCohort, DEVELOPMENT_CASE_NUMBERS,
    compute_metrics, discover_reference_grounded_cases, split_cases,
)
from end_to_end_validation import _build_plant_df
from final_decision_policy import final_status_from_engine_row
from gold_corpus.e2e_snapshot_pilot import (
    load_snapshot, snapshot_question, snapshot_records, frozen_candidate_discovery,
)
from scientific_decision_validation import DecisionComparison, derive_reference_final_decision

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "gold_corpus" / "decision_benchmark_v1"
OUT.mkdir(parents=True, exist_ok=True)


def _v(x):
    return getattr(x, "value", x)


def _case_number(case_id: str) -> int:
    return int(case_id.split("_", 2)[1])


def _case_source_sha256(case) -> str:
    """Freeze the curated source record without committing the six-class label.

    A direct label hash would be brute-forceable because only six labels exist.
    Hashing the case source file instead proves which curated record belonged to
    v1 while keeping the benchmark manifest free of derived answer labels.
    """
    n = _case_number(case.case_id)
    matches = sorted((ROOT / "gold_cases").glob(f"gold_case_reference_grounded_{n:03d}_*.py"))
    if len(matches) != 1:
        raise RuntimeError(f"Expected one source file for {case.case_id}; found {len(matches)}")
    return hashlib.sha256(matches[0].read_bytes()).hexdigest()


def _engine_status_from_snapshot(n: int, case):
    snap = load_snapshot(n)
    q = snapshot_question(snap)
    recs = snapshot_records(snap)
    candidates = frozen_candidate_discovery(snap)(q)
    evidence_df = pd.DataFrame([
        r.to_engine_row(q.indication, q.dosage_form, q.market) for r in recs
    ])
    engine = BotanicalRDCandidateEngine(
        plant_compounds_df=_build_plant_df(candidates, q.indication),
        compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(),
        evidence_df=evidence_df,
        use_live_search=False,
    )
    output = engine.run(indication=q.indication, dosage_form=q.dosage_form, market=q.market)
    target = case.validation_unit.taxon.lower().split()[0]
    row = output[output["Alternative_Plant"].str.lower().str.startswith(target)].iloc[0]
    return final_status_from_engine_row(row), row


def _blind_packet_row(case):
    u = case.validation_unit
    refs = []
    for gr in case.references:
        r = gr.reference
        claims = []
        for c in gr.claims:
            claims.append({
                "domain": _v(c.domain),
                "assertion_type": _v(c.assertion_type),
                "subject": c.subject,
                "source_locator": c.source_locator,
                "evidence_text": c.evidence_text.original_text if c.evidence_text else None,
            })
        refs.append({
            "reference_id": r.reference_id,
            "source_type": r.source_type,
            "version": r.version,
            "document_date": r.document_date.isoformat() if r.document_date else None,
            "jurisdiction": r.jurisdiction,
            "claims": claims,
        })
    prep = u.preparation
    dose = u.dose
    return {
        "case_id": case.case_id,
        "taxon": u.taxon,
        "plant_part": u.plant_part,
        "dosage_form": prep.dosage_form if prep else None,
        "solvent": prep.solvent if prep else None,
        "der_min": prep.der_min if prep else None,
        "der_max": prep.der_max if prep else None,
        "dose_amount": dose.amount if dose else None,
        "dose_unit": dose.unit if dose else None,
        "dose_frequency": dose.frequency if dose else None,
        "duration": u.duration,
        "route": u.route_of_administration,
        "indication": u.indication,
        "population": u.population,
        "jurisdiction": u.jurisdiction,
        "references": refs,
        # Intentionally blank; expert must not see engine or derived reference label.
        "reviewer_1_decision": "",
        "reviewer_1_rationale": "",
        "reviewer_2_decision": "",
        "reviewer_2_rationale": "",
        "adjudicated_decision": "",
        "adjudication_rationale": "",
    }


def main():
    cases = discover_reference_grounded_cases(ROOT)
    split = split_cases(cases)
    dev = split[BenchmarkCohort.DEVELOPMENT]
    holdout = split[BenchmarkCohort.PROSPECTIVE_HOLDOUT]

    manifest = {
        "benchmark_version": BENCHMARK_VERSION,
        "policy": {
            "development_definition": "Cases used in prior final-decision remediation; never reported as holdout.",
            "holdout_definition": "Existing reference-grounded cases not used in prior final-decision remediation.",
            "holdout_scoring_rule": "Do not score until independent engine evidence/snapshot exists. Never derive engine evidence from GoldCase reference truth.",
            "expert_blinding_rule": "Adjudication packet omits engine decision, derived reference final decision, and resolved outcomes.",
        },
        "development": [
            {"case_id": c.case_id, "case_source_sha256": _case_source_sha256(c)} for c in dev
        ],
        "prospective_holdout": [
            {"case_id": c.case_id, "case_source_sha256": _case_source_sha256(c), "status": "UNSCORED_PENDING_INDEPENDENT_ENGINE_SNAPSHOT"}
            for c in holdout
        ],
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Blind packet: holdout only, no outcome labels or engine outputs.
    packet = [_blind_packet_row(c) for c in holdout]
    (OUT / "blind_expert_adjudication_packet.json").write_text(
        json.dumps(packet, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8"
    )
    csv_fields = [
        "case_id", "taxon", "plant_part", "dosage_form", "solvent", "der_min", "der_max",
        "dose_amount", "dose_unit", "dose_frequency", "duration", "route", "indication",
        "population", "jurisdiction", "reference_summary", "reviewer_1_decision", "reviewer_1_rationale",
        "reviewer_2_decision", "reviewer_2_rationale", "adjudicated_decision", "adjudication_rationale",
    ]
    with (OUT / "blind_expert_adjudication_packet.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=csv_fields); w.writeheader()
        for row in packet:
            flat = {k: row.get(k, "") for k in csv_fields}
            flat["reference_summary"] = json.dumps(row["references"], ensure_ascii=False)
            w.writerow(flat)

    # Development scoring uses only existing frozen snapshots.
    comparisons = []
    details = []
    for case in dev:
        n = _case_number(case.case_id)
        actual, row = _engine_status_from_snapshot(n, case)
        expected = derive_reference_final_decision(case)
        comparisons.append(DecisionComparison(case.case_id, expected, actual, expected == actual))
        details.append({
            "case_id": case.case_id,
            "expected_reference_curated": expected.value,
            "actual_engine": actual.value,
            "match": expected == actual,
            "ranking_partition": str(row.get("Ranking_Partition", "")),
            "eligible_for_normal_ranking": bool(row.get("Eligible_For_Normal_Ranking", False)),
        })
    metrics = compute_metrics(comparisons)
    metrics_obj = {
        "benchmark_version": BENCHMARK_VERSION,
        "cohort": "development",
        "not_external_expert_agreement": True,
        "n_scored": metrics.n_scored,
        "n_correct": metrics.n_correct,
        "accuracy": metrics.accuracy,
        "macro_f1": metrics.macro_f1,
        "per_class_recall": metrics.per_class_recall,
        "serious_safety_false_negatives": metrics.serious_safety_false_negatives,
        "regulatory_false_negatives": metrics.regulatory_false_negatives,
        "false_no_go": metrics.false_no_go,
        "expert_review_overuse": metrics.expert_review_overuse,
        "insufficient_evidence_miss": metrics.insufficient_evidence_miss,
        "confusion_matrix": metrics.confusion_matrix,
        "cases": details,
    }
    (OUT / "development_metrics.json").write_text(json.dumps(metrics_obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    holdout_reference_distribution = {}
    for c in holdout:
        label = derive_reference_final_decision(c).value
        holdout_reference_distribution[label] = holdout_reference_distribution.get(label, 0) + 1

    report = "# Decision Benchmark v1.0 — Leakage-Controlled Validation\n\n"
    report += f"**Development:** {len(dev)} existing cases previously used in remediation.  " \
              f"**Prospective holdout:** {len(holdout)} existing cases not used in that remediation.\n\n"
    report += "## Development result\n\n"
    report += f"Reference-curated agreement: **{metrics.n_correct}/{metrics.n_scored} = {metrics.accuracy:.1%}**.  " \
              "This is not external expert agreement.\n\n"
    report += f"Macro-F1: **{metrics.macro_f1:.3f}**. Serious-safety FN: **{metrics.serious_safety_false_negatives}**; " \
              f"regulatory FN: **{metrics.regulatory_false_negatives}**; false NO-GO: **{metrics.false_no_go}**; " \
              f"expert-review overuse: **{metrics.expert_review_overuse}**; insufficient-evidence misses: **{metrics.insufficient_evidence_miss}**.\n\n"
    report += "## Prospective holdout status\n\n"
    report += "**UNSCORED.** No independent frozen E2E engine-evidence snapshot exists for these 15 cases. " \
              "Using their GoldCase reference claims as engine evidence would leak the answer into the system and invalidate the holdout.\n\n"
    report += "Reference-truth class distribution (for coverage audit only; not a model score):\n\n"
    for k, v in sorted(holdout_reference_distribution.items()):
        report += f"- {k}: {v}\n"
    report += "\n## Blind expert adjudication\n\n"
    report += "`blind_expert_adjudication_packet.csv/json` contains the 15 holdout case contexts and source excerpts, " \
              "but deliberately omits engine outputs, resolved outcomes, and derived reference final decisions. Two reviewers can assign " \
              "one of the six final-decision classes independently, followed by adjudication.\n\n"
    report += "## Freeze rule\n\n"
    report += "Do not modify the 15-case holdout membership after seeing engine results. Do not create or tune production rules from holdout failures. " \
              "If a failure is found, diagnose it on development data or a new future validation cycle; preserve this v1 holdout result as historical evidence.\n"
    (OUT / "REPORT.md").write_text(report, encoding="utf-8")

    print(json.dumps({
        "development": len(dev), "holdout": len(holdout),
        "development_accuracy": metrics.accuracy,
        "development_macro_f1": metrics.macro_f1,
        "holdout_status": "UNSCORED_PENDING_INDEPENDENT_ENGINE_SNAPSHOT",
        "output_dir": str(OUT),
    }, indent=2))


if __name__ == "__main__":
    main()
