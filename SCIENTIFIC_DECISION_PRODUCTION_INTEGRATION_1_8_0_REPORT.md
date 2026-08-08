# Scientific Decision Production Integration Hardening — Engine 1.8.0

## Strict finding
A fresh six-source raw-text diagnostic using previously unused botanicals/source conclusions found the legacy text interpretation correct in only 1/6 cases.

This is not an end-to-end validation result. It isolates the legacy raw-text interpretation layer and demonstrates why repeated regex remediation did not generalize.

## Actual production defects found
1. Pre-canonical Supabase evidence rows with no `Result_Direction` were never backfilled. They therefore continued to depend on the weak text fallback forever.
2. `Regulatory_Authorization_Status`, introduced as a structured regulatory decision input, was not persisted or loaded by `database.py`, so the value could disappear after database round-trip.
3. `EngineEvidenceInput`, used by the reference-grounded validation execution path, could not carry structured efficacy/safety/regulatory assertions at all. Validation plumbing therefore kept forcing evidence back into free text.
4. A failed/unavailable structured extractor could leave a new record without a canonical direction.

## Fix
- Production BotanicalRDCandidateEngine now defaults to `allow_legacy_text_fallback=False`.
- Missing structured direction is fail-safe `unclear`, not a heuristic positive/negative conclusion.
- Newly standardized evidence always leaves the standardization boundary with `Result_Direction`; if extraction is unavailable/fails it is persisted as `Unknown`.
- When LLM structured extraction succeeds, its direction is copied to canonical `Result_Direction`.
- Added `backfill_canonical_assertions.py` for existing Supabase rows. It is dry-run by default and never overwrites existing structured directions.
- Added database persistence/readback for `Regulatory_Authorization_Status`.
- Added migration `0008_add_regulatory_authorization_status.sql`.
- Extended `EngineEvidenceInput` and GoldCase execution transport to carry plain structured Result_Direction, Safety_Signal, Regulatory_Status, Regulatory_Authorization_Status and Regulatory_Evidence.
- Historical legacy regression tests may explicitly opt into the old fallback; production does not.

## Test status
Focused scientific decision / structured assertion / database / safety / regulatory / validation regression:
201 passed, 0 failed.

## What is still unmeasured
This runtime has no `OPENAI_API_KEY`, `SUPABASE_URL`, or `SUPABASE_KEY`. Therefore the live extractor cannot be honestly executed here against the project's production database.

The remaining empirical question is now sharply isolated:
Does the live structured extractor correctly assign Result_Direction and Safety_Signal on unseen real source text?

Until that live extraction benchmark is run with the project's real secret, do not claim full end-to-end scientific validation.

## Version
Engine 1.7.0 -> 1.8.0.
