General scientific evidence alignment fix (2026-08-28)

Scope: generic across all indications and product forms. No disease-specific or sleep-specific rules were added.

Production files changed:
- evidence_adjudication_engine.py
- step_rd_candidates.py

Key fixes:
1. Structured AI adjudication and explanatory AI now consume the same processed Stage-5 evidence rows that produced the deterministic shortlist, rather than re-reading a differently interpreted raw evidence table.
2. Processed Stage-5 rows are first-class adjudication evidence: Alternative_Plant, Source_Record_IDs, Study_Design/Evidence_Hierarchy_Detail, Evidence_Direction, and Stage-5 relevance fields are supported directly.
3. Evidence records are deduplicated by traceable evidence ID before the AI cap, so row/compound/target projection multiplicity cannot make one record count multiple times in AI review.
4. Study-design ranking now uses the actual canonical vocabulary returned by evidence_hierarchy_classifier.py.
5. Logical bundle invariants prevent schema-valid but impossible AI outputs, e.g. Human_Evidence_Strength=NONE when a relevant human record was supplied.
6. Final decision reconciliation has a generic cross-layer coherence gate; contradictions require expert review instead of a green recommendation.
7. Evidence_Coherence_Status and Evidence_Adjudication_Evidence_Count are exposed in the final Stage-6 export/display for auditability.

Validation performed locally:
- py_compile passed for changed production files and regression test.
- 95 existing candidate/relevance/scoring calibration tests passed.
- 3 new generic evidence-alignment regression tests passed using dependency stubs only for the local environment (Streamlit/OpenAI packages are present in CI/production).
