# Step 5 deep fix — 2026-09-10

## Root cause
The previous evidence-authority hardening correctly prevented unverified human-study signals from being labelled verified direct clinical evidence, but it also forced every `UNVERIFIED_DIRECT_HUMAN_SIGNAL` candidate into `Exploratory` regardless of evidence depth. In live data, the strict outcome-specific parser can be incomplete even when traceable human records and adequate evidence quality are present. This collapsed the primary Scientific Shortlist to zero.

## Fix
`candidate_shortlisting.py` now permits a **provisional scientific shortlist** for `UNVERIFIED_DIRECT_HUMAN_SIGNAL` when all of the following hold:

- Indication relevance score >= 20
- Evidence quality score >= 12
- At least one primary-tier record
- At least one traceable primary-tier source

Scientific safeguards remain:

- unverified direct-human relevance stays capped below verified direct-human scoring (max 24/35)
- `Outcome_Specific_Human_Evidence_Count == 0` is still explicit
- such a candidate can never receive `Go` solely through this path
- such a candidate receives `Investigate — verify before proceeding`
- it cannot receive `B — Established scientific candidate`
- the selection explanation explicitly says outcome verification is pending

## Reliability fixes retained
The package also retains the latest Step-5 reliability files:

- `step_rd_candidates.py`: downstream adjudication/report failures do not erase a valid deterministic candidate set
- `evidence_adjudication_engine.py`: scalar/NaN evidence-ID values are handled safely instead of being treated as iterables

## Tests
- Python compile check passed
- `test_candidate_shortlisting.py`
- `test_phase5_scoring_calibration_addendum.py`

Result: **92 passed, 0 failed**

Two other suites requiring Streamlit could not be collected in this local environment because Streamlit is not installed; this is an environment limitation, not a production-code failure.

## Installation
Replace these three files in the repository root, commit/push, then fully reboot the Streamlit app:

1. `candidate_shortlisting.py`
2. `step_rd_candidates.py`
3. `evidence_adjudication_engine.py`

Do not only refresh the browser; reboot the Streamlit app so cached code is cleared.
