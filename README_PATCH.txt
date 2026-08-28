Stage 5/6 cumulative scientific + AI wiring fix

Production files to overwrite:
- candidate_shortlisting.py
- step_rd_candidates.py

What is preserved:
- Stage 2 collection path
- deterministic scoring formulas/weights
- safety and regulatory hard gates
- existing AI services and budgets

What is fixed:
1) Stage 6 receives plant-level indication relevance/direct-evidence fields from the authoritative shortlist merge.
2) Mechanistic/indirect-only candidates are separated from the primary Recommended bucket into Exploratory hypotheses.
3) Existing structured AI evidence adjudication fields are visible in Stage 6.
4) Existing AI R&D insight outputs (mechanism/synthesis/hypothesis) are attached to rd_report_ready_df and therefore visible/exportable.
5) If AI is unavailable/fallback, Stage 6 says so explicitly instead of appearing AI-reviewed.
6) AI narrative cannot overwrite deterministic scores or hard safety/regulatory gates.

Validation in local dependency-light environment:
- py_compile: PASS for both production files
- test_stage6_direct_relevance_gate_regression.py: PASS
- test_stage6_ai_wiring_regression.py: PASS
