# Holdout Structural Blocker Remediation — Changed Files

This patch is intended to be applied on top of the previously merged Decision Benchmark / Independent Holdout patch.

Changed production/support modules:
- knowledge_retrieval_engine.py
- therapeutic_area_registry.py
- independent_holdout_e2e.py
- build_independent_holdout_e2e.py

Changed/added tests:
- test_independent_holdout_e2e.py
- test_candidate_discovery_generalization_phase.py
- test_holdout_structural_executability_phase.py

Updated validation outputs:
- gold_corpus/decision_benchmark_v1/independent_holdout_metrics.json
- gold_corpus/decision_benchmark_v1/INDEPENDENT_HOLDOUT_REPORT.md

Key result: structural executability improved from 2/15 to 15/15 without changing holdout membership, expected labels, frozen snapshots, or final-decision rules. Scored subset remains 1/2 until 13 new independent snapshots are captured.
