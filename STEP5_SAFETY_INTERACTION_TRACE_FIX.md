# Step 5 safety / interaction trace fix

## Root cause

The Phase-2 JSONB columns were transported correctly when populated, but most
legacy evidence rows have `adverse_events` and `interactions_structured` empty.
Their original source text is stored in `sources.raw_text`; however,
`load_evidence_records_df()` did not flatten that field, so Step 5 had no text
from which to recover explicit source-carried safety statements.

## Changes

- `supabase_data.py` exposes `sources.raw_text` as `Source_Raw_Text`.
- `indication_candidate_discovery.py` includes that text in each evidence
  record and uses a strict source-text fallback only when structured safety or
  interaction fields are empty.
- The fallback extracts only fragments containing explicit safety/interaction
  language. It never inserts plant knowledge from a hard-coded lookup and never
  interprets silence as proof of safety.
- `evidence_extractor.py` now preserves explicit safety/interaction fragments
  into `Adverse_Events` and `Interactions_Structured` for newly collected
  evidence, so future records are structured at ingestion time.

## Important limitation

If both the structured fields and `sources.raw_text`/record notes are empty,
Step 5 will still honestly report that no explicit safety or interaction
information was captured. This change does not fabricate or externally enrich
old records.

## Tests

Focused regression suite: 8 passed.
