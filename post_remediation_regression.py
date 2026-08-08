"""Post-remediation regression over the 15 formerly prospective holdout cases.

IMPORTANT: this is NOT an unseen holdout benchmark. These cases were exposed
and used during root-cause remediation. This module exists only to verify that
all known failures remain closed after reference adjudication.
"""
from __future__ import annotations
import json
from pathlib import Path
from independent_holdout_e2e import evaluate_holdout

OUT = Path("gold_corpus/decision_benchmark_v1")


def main():
    statuses, metrics = evaluate_holdout()
    scored = [s for s in statuses if s.status == "SCORED"]
    obj = {
        "evaluation_type": "POST_REMEDIATION_REGRESSION_NOT_UNSEEN_VALIDATION",
        "n_cases": len(statuses),
        "n_scored": metrics.n_scored,
        "n_correct": metrics.n_correct,
        "agreement": metrics.accuracy,
        "macro_f1": metrics.macro_f1,
        "serious_safety_false_negatives": metrics.serious_safety_false_negatives,
        "regulatory_false_negatives": metrics.regulatory_false_negatives,
        "false_no_go": metrics.false_no_go,
        "expert_review_overuse": metrics.expert_review_overuse,
        "insufficient_evidence_miss": metrics.insufficient_evidence_miss,
        "cases": [s.__dict__ for s in scored],
        "interpretation": (
            "These 15 cases were previously exposed during root-cause analysis and remediation. "
            "Agreement is a regression-closure metric only and must not be reported as independent holdout performance."
        ),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "POST_REMEDIATION_REGRESSION_METRICS.json").write_text(
        json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    report = (
        "# Post-remediation regression — 15 previously exposed cases\n\n"
        "**Not an unseen holdout.** These cases were used during remediation.\n\n"
        f"Agreement: **{metrics.n_correct}/{metrics.n_scored} = {metrics.accuracy:.1%}**. "
        f"Macro-F1: **{metrics.macro_f1:.3f}**.\n\n"
        f"Serious-safety FN: **{metrics.serious_safety_false_negatives}**; "
        f"regulatory FN: **{metrics.regulatory_false_negatives}**; "
        f"false NO-GO: **{metrics.false_no_go}**.\n\n"
        "This result shows closure of known regression failures only. A new frozen, untouched holdout is required next.\n"
    )
    (OUT / "POST_REMEDIATION_REGRESSION_REPORT.md").write_text(report, encoding="utf-8")
    print(json.dumps({"correct": metrics.n_correct, "scored": metrics.n_scored, "agreement": metrics.accuracy}, indent=2))


if __name__ == "__main__":
    main()
