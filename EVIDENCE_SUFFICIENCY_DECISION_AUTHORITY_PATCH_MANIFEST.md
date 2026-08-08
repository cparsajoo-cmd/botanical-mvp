# Patch manifest

Place all files in the repository root.

- botanical_rd_candidate_engine.py — exposes authoritative Final_Decision_Status and preserves it through merge.
- final_decision_policy.py — final-status reader prefers structured six-class status, with legacy fallback.
- test_structured_final_decision_authority.py — regression tests for source-of-truth and single-review behavior.
- EVIDENCE_SUFFICIENCY_DECISION_AUTHORITY_REPORT.md — audit/remediation report.
