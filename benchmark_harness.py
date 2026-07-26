"""
Task 5 — Benchmark harness (ENGINEERING SCAFFOLD ONLY).

======================================================================
READ THIS BEFORE TRUSTING ANY NUMBER THIS MODULE PRODUCES
======================================================================
This is NOT scientific validation. NOT benchmark calibration. NOT
domain validation. It is a small, standalone tool — same
not-imported-by-the-app pattern as repo_dependency_audit.py — that:

  1. loads a set of candidate cases from a JSON fixture,
  2. runs each one through the UNMODIFIED BotanicalRDCandidateEngine
     (no scoring/gating logic is reimplemented here, and none of it is
     altered by running this tool),
  3. compares the engine's real Decision_Class / Gate_Results output
     against each case's recorded "expected" values,
  4. reports agreement/disagreement.

The bundled fixture (benchmark_cases/smoke_cases.json) contains a
small number of SYNTHETIC, ENGINEER-AUTHORED cases chosen only to
exercise this harness's own mechanics end to end — loading, running,
comparing, reporting. They are NOT curated by a botanical/pharma
domain expert, are NOT drawn from real historical decisions, and their
"expected" values were derived by running the engine itself and
recording what it already does (a mechanics smoke test), not by an
independent scientific judgment. They must never be cited as evidence
that the engine's scoring or gating is scientifically correct.

Populating a REAL benchmark set — expert-reviewed historical
candidates, each with a defensible expected outcome an independent
domain expert would sign off on — is an explicitly SEPARATE,
NON-ENGINEERING, data-curation workstream. This harness's job is only
to be ready to consume that data the moment it exists, and to prove
today that its own mechanics (loading, running, comparing) work
correctly on whatever cases it's given.

WHY A SEPARATE STANDALONE MODULE, NOT INSIDE THE ENGINE OR THE APP
Nothing here is imported by app.py, step_rd_candidates.py, or any
other production page — this is a tool, run explicitly via its CLI or
via pytest, exactly like repo_dependency_audit.py. It reuses
test_botanical_rd_candidate_engine.py's existing make_engine() helper
rather than reimplementing engine construction, and calls
BotanicalRDCandidateEngine.run() completely unmodified.

HOW TO RUN
    python3 benchmark_harness.py run benchmark_cases/smoke_cases.json
    pytest -q test_benchmark_harness.py
"""

from __future__ import annotations

import json
import sys

import pandas as pd


def load_benchmark_cases(path: str) -> list:
    """Loads a JSON fixture of benchmark cases. Returns [] for an
    empty file. Raises on malformed JSON or a top-level shape that
    isn't a list — a fixture file is developer-authored input, not
    runtime data from an untrusted source, so a loud failure here is
    the right behavior (unlike the engine's own connectors, which must
    degrade gracefully against unpredictable live data)."""
    with open(path, encoding="utf-8") as f:
        cases = json.load(f)
    if not isinstance(cases, list):
        raise ValueError(f"{path}: expected a JSON list of cases, got {type(cases).__name__}")
    return cases


def _build_engine_for_case(case: dict):
    """Reuses test_botanical_rd_candidate_engine.make_engine() — no
    engine-construction logic is reimplemented here. similar_groups/
    compound_targets are optional case fields, passed straight through
    to make_engine() unchanged (needed by cases that rely on
    SIMILAR_COMPOUND_GROUPS, e.g. to exercise a shared-compound safety
    match — see smoke_safety_exclusion in the bundled fixture).

    IMPORTANT: make_engine() only OVERRIDES the module-level
    SIMILAR_COMPOUND_GROUPS/COMPOUND_TARGETS globals when a case
    explicitly provides them — it does not reset them otherwise. Since
    this harness runs many cases in one process, the previous case's
    values could otherwise silently leak into a case that doesn't
    specify its own. Resetting to {} here, before every case, is what
    prevents that cross-case leakage.
    """
    import botanical_rd_candidate_engine as engine_module
    from test_botanical_rd_candidate_engine import make_engine

    engine_module.SIMILAR_COMPOUND_GROUPS = {}
    engine_module.COMPOUND_TARGETS = {}

    engine = make_engine(
        case.get("rows", []),
        similar_groups=case.get("similar_groups"),
        compound_targets=case.get("compound_targets"),
    )
    evidence_rows = case.get("evidence")
    if evidence_rows:
        engine.evidence_df = pd.DataFrame(evidence_rows)
    return engine


def run_benchmark(cases: list) -> pd.DataFrame:
    """Runs every case through the UNMODIFIED engine (engine.run(),
    untouched by this module) and returns one row per (case_id,
    reference_plant, alternative_plant) actually produced, carrying
    the real Decision_Class and Gate_Results this run computed —
    nothing here recomputes or reinterprets either."""
    all_rows = []
    for case in cases:
        case_id = case.get("case_id", "<unnamed case>")
        run_params = case.get("run_params", {})
        try:
            engine = _build_engine_for_case(case)
            result = engine.run(
                indication=run_params.get("indication", ""),
                dosage_form=run_params.get("dosage_form", ""),
                market=run_params.get("market", "EU"),
            )
        except Exception as exc:  # noqa: BLE001 — a case that fails to
            # build or run at all is itself a reportable result, not a
            # harness crash.
            all_rows.append({
                "case_id": case_id,
                "reference_plant": None,
                "alternative_plant": None,
                "decision_class": None,
                "gate_results": None,
                "run_error": f"{type(exc).__name__}: {exc}",
            })
            continue

        for _, row in result.iterrows():
            all_rows.append({
                "case_id": case_id,
                "reference_plant": row.get("Reference_Plant"),
                "alternative_plant": row.get("Alternative_Plant"),
                "decision_class": row.get("Decision_Class"),
                "gate_results": row.get("Gate_Results"),
                "run_error": None,
            })

    return pd.DataFrame(all_rows, columns=[
        "case_id", "reference_plant", "alternative_plant",
        "decision_class", "gate_results", "run_error",
    ])


def _gate_statuses_match(actual_gates: dict, expected_gate_status: dict) -> bool:
    if not isinstance(actual_gates, dict):
        return False
    for gate_name, expected_status in expected_gate_status.items():
        actual = actual_gates.get(gate_name, {})
        actual_status = actual.get("status")
        # Gate_Results stores GateStatus enum members; compare by value
        # so a fixture's plain string ("failed") matches either form.
        actual_value = actual_status.value if hasattr(actual_status, "value") else actual_status
        if actual_value != expected_status:
            return False
    return True


def compare_to_expected(results_df: pd.DataFrame, cases: list) -> dict:
    """Compares run_benchmark()'s real output against each case's
    "expected" pairs. Returns a plain agreement/disagreement report —
    performs no scoring, no reclassification, no judgment of its own
    beyond string/value equality against what the fixture recorded."""
    agreements = []
    disagreements = []
    missing_pairs = []

    cases_by_id = {c.get("case_id", "<unnamed case>"): c for c in cases}

    for case_id, case in cases_by_id.items():
        case_results = results_df[results_df["case_id"] == case_id]
        for expected_pair in case.get("expected", {}).get("pairs", []):
            ref = expected_pair.get("reference_plant")
            alt = expected_pair.get("alternative_plant")
            matched = case_results[
                (case_results["reference_plant"] == ref)
                & (case_results["alternative_plant"] == alt)
            ]
            if matched.empty:
                missing_pairs.append({
                    "case_id": case_id, "reference_plant": ref, "alternative_plant": alt,
                    "reason": "no matching output row was produced for this pair",
                })
                continue

            actual_row = matched.iloc[0]
            checks_ok = True
            detail = {}

            if "decision_class" in expected_pair:
                expected_dc = expected_pair["decision_class"]
                actual_dc = actual_row["decision_class"]
                detail["decision_class"] = {"expected": expected_dc, "actual": actual_dc}
                if actual_dc != expected_dc:
                    checks_ok = False

            if "gate_status" in expected_pair:
                expected_gates = expected_pair["gate_status"]
                matched_gates = _gate_statuses_match(actual_row["gate_results"], expected_gates)
                detail["gate_status"] = {
                    "expected": expected_gates,
                    "actual": {
                        name: (g.get("status").value if hasattr(g.get("status"), "value") else g.get("status"))
                        for name, g in (actual_row["gate_results"] or {}).items()
                    },
                }
                if not matched_gates:
                    checks_ok = False

            entry = {"case_id": case_id, "reference_plant": ref, "alternative_plant": alt, **detail}
            (agreements if checks_ok else disagreements).append(entry)

    total_checked = len(agreements) + len(disagreements)
    return {
        "total_pairs_checked": total_checked,
        "agreements": agreements,
        "disagreements": disagreements,
        "missing_pairs": missing_pairs,
        "agreement_rate": (len(agreements) / total_checked) if total_checked else None,
    }


def _print_report(report: dict) -> None:
    print(f"Pairs checked: {report['total_pairs_checked']}")
    if report["agreement_rate"] is not None:
        print(f"Agreement rate: {report['agreement_rate']:.0%}")
    print(f"Agreements: {len(report['agreements'])}")
    print(f"Disagreements: {len(report['disagreements'])}")
    for d in report["disagreements"]:
        print(f"  DISAGREE case={d['case_id']} {d['reference_plant']} vs {d['alternative_plant']}: {d}")
    if report["missing_pairs"]:
        print(f"Missing pairs (no output row produced): {len(report['missing_pairs'])}")
        for m in report["missing_pairs"]:
            print(f"  MISSING case={m['case_id']} {m['reference_plant']} vs {m['alternative_plant']}")
    print()
    print("Reminder: this report reflects the bundled SYNTHETIC smoke-test")
    print("fixture unless a different, expert-curated cases file was passed.")
    print("It is not scientific validation, benchmark calibration, or domain")
    print("validation — see this module's own docstring.")


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) < 2 or argv[0] != "run":
        print("Usage: python3 benchmark_harness.py run <cases.json>")
        return 2

    cases = load_benchmark_cases(argv[1])
    results_df = run_benchmark(cases)
    report = compare_to_expected(results_df, cases)
    _print_report(report)
    return 0 if not report["disagreements"] and not report["missing_pairs"] else 1


if __name__ == "__main__":
    sys.exit(main())
