# Step 5 Stable Rollback for Investor Demo

Source: the user's previous-day repository `botanical-mvp-main (25)(3).zip`, which the user reported was working.

Purpose: restore ONLY the Step 5 scientific candidate discovery/scoring/triage stack to the known-working previous-day implementation. The rest of the current platform should remain unchanged.

Replace these files in the project root:

- botanical_rd_candidate_engine.py
- candidate_shortlisting.py
- evidence_adjudication_engine.py
- evidence_consistency.py
- indication_candidate_discovery.py
- phase5_scoring_config.py
- standard_evidence_builder.py
- step_rd_candidates.py

Do NOT replace app.py, database files, Supabase configuration, Step 0-4 modules, or Step 6 modules beyond the shared `step_rd_candidates.py` file supplied here.

Validation performed in the previous-day repository:

`python -m pytest -q test_candidate_shortlisting.py test_scoring_config.py test_phase5_scoring_calibration_addendum.py test_step5_scientific_result_preparation_safety.py`

Result: 101 passed, 0 failed.

After replacement, perform a full Streamlit reboot/redeploy, not merely a browser refresh.

Rationale: the current version introduced stricter evidence-verification/triage logic across several coupled modules. In the live Sleep run those coupled changes reduced the primary shortlist to one plant. Restoring only one function was not a reliable rollback because the relevance, consistency, candidate discovery, scoring config, and final triage logic changed together. This package restores the coherent Step 5 stack from the known-working prior version instead of mixing incompatible generations of the scoring pipeline.
