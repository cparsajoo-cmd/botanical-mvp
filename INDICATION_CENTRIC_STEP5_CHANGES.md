# Step 5 indication-centric redesign

## What changed
- Added `indication_candidate_discovery.py`.
- `BotanicalRDCandidateEngine.run()` now accepts `discovery_mode`.
- Default mode is `indication`; candidate entry is based on plant–indication evidence and mechanisms, not shared compounds.
- Legacy compound matching remains available as `compound_substitution`.
- Step 5 UI now asks the user which scientific question they are asking.
- In indication mode, compounds contribute at most 5 supportive points and never determine candidate eligibility.

## Important limitation
This release changes the architecture and prevents chemical similarity from defining the candidate universe. The quality of results still depends on whether Step 2/Supabase records contain plant-specific indication, outcome, preparation, dose and source fields. Missing record-level data is reported rather than inferred.

## Test
Run:

```bash
pytest -q test_indication_candidate_discovery.py
```
