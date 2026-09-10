Final CI compatibility patch for the Step 5 stable rollback.

Replace these three files in the project root:
- evidence_consistency.py
- phase5_scoring_config.py
- candidate_shortlisting.py

Fixes:
1. Restores direction_data_completeness() required by current Phase 5 tests.
2. Adds INSUFFICIENT_DIRECTION_DATA to Phase 5 scoring configuration and factor maps.
3. Prevents an upstream "Direct human/clinical" label with zero verified outcome-specific human evidence from producing Go; it remains shortlist/investigate rather than being promoted.
4. Keeps the previously restored transferability semantics intact.

Verified locally:
- 5 targeted regression tests passed.
- All three modified files compile successfully.

The local container does not have Streamlit/OpenAI/Supabase installed, so the entire repository suite cannot be collected here. The user's GitHub CI environment already has those dependencies and should be used for the authoritative full-suite run.
