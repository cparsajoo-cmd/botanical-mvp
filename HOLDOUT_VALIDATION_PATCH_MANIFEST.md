# Holdout Validation Patch Manifest

This patch is cumulative for the project ZIP `botanical-mvp-main - 2026-08-08T080010.696.zip`.
It contains the Decision Benchmark v1 files that were absent from that ZIP plus the new independent holdout E2E validation artifacts.

## Production logic
No production rule, scoring weight, eligibility rule, UI file, or production engine file was modified in this phase.

## Root files to add
- decision_benchmark_v1.py
- build_decision_benchmark_v1.py
- test_decision_benchmark_v1.py
- independent_holdout_e2e.py
- build_independent_holdout_e2e.py
- test_independent_holdout_e2e.py

## Directory to add/merge
- gold_corpus/decision_benchmark_v1/

## Result
- Prospective holdout total: 15
- Independently executable + frozen + scored: 2
- Structurally blocked: 13
- Executable-subset agreement: 1/2 = 50%
- Case 001: GO -> GO (match)
- Case 003: GO WITH CAUTION -> GO (mismatch)
- No remediation was made from the holdout result.
