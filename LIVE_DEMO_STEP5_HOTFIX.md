# Live Demo Step 5 Hotfix

This hotfix is intended to be applied on top of BOTANICAL_FINAL_DEMO_SAFE_FILES.

Modified production files:
- candidate_shortlisting.py
- step_rd_candidates.py

Changes:
1. `rescore_commercial_component()` now normalizes scalar/NaN/single-value `plants` input instead of assuming it is iterable. This prevents `TypeError: 'float' object is not iterable` from malformed or collapsed caller state.
2. Step 5 commercial re-scoring is now fail-open. Commercial scoring is additive/optional; if it raises, the already-computed scientific shortlist is preserved and the workflow continues with a clear limitation warning rather than returning 0 plants.

Validation performed:
- Both modified files compile successfully with `python -m py_compile`.
- Candidate/shortlisting-related tests available in this environment: 84 passed. Two additional market/Step-5 tests could not collect because this sandbox does not have Streamlit installed; this is an environment dependency, not a test assertion failure.

After replacement:
- Restart the Streamlit app fully (reboot/redeploy), do not rely only on browser refresh.
- Re-run the exact Sleep scenario from Step 0 through Step 6.
