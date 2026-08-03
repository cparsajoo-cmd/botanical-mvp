# Step 5 indication-centric correction (v2.1)

Replace the same-named files in the repository root, commit them, then reboot the Streamlit app.

## Corrected

- Removed indication-wide evidence leakage: general records about diabetes (or another indication) are no longer attached to every plant.
- Candidate-specific evidence is now collected only from records explicitly linked to that plant.
- Profile-level indication/mechanism fields can create only a Hold/exploratory hypothesis, never direct clinical evidence.
- Source URLs/record identifiers are taken only from the plant-specific supporting records.
- Shared chemistry remains non-gating and is capped at 5/100 in plant-level scoring.
- The old one-reference-plant warning is suppressed in indication mode and replaced by an accurate information message.
- Selection explanations no longer use the number of shared compounds as a reason for shortlist selection.

## Files

- `indication_candidate_discovery.py`
- `candidate_shortlisting.py`
- `step_rd_candidates.py`
- `test_indication_no_leakage.py`

## Validation

`152 passed` across the new leakage regression test plus the existing candidate-shortlisting, candidate-engine, and report-generator tests.
