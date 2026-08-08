# Fresh Holdout v2 Patch Manifest

Validation-only patch. No production engine rule is changed.

Files:
- decision_holdout_v2.py
- test_decision_holdout_v2.py
- gold_corpus/decision_holdout_v2/frozen_reference_labels.json
- gold_corpus/decision_holdout_v2/results.json
- gold_corpus/decision_holdout_v2/HOLDOUT_V2_REPORT.md
- gold_corpus/decision_holdout_v2/snapshots/*.json

Result on the patched current baseline: 1/5 correct (20.0%), Macro-F1 0.3333.
Dominant observed root cause: systematic-review evidence reaches the candidate but Evidence_Direction is `unclear` for four positive/cautious cases, causing final fallback to INSUFFICIENT EVIDENCE.

These five cases are now exposed and must be treated as development/regression cases, not reused as an unseen holdout after remediation.
