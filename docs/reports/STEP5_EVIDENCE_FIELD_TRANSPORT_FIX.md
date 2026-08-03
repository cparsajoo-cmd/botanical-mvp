# Step 5 evidence-field transport fix

## Root cause
The Phase 2 columns existed in `evidence_records`, but the active Streamlit loader
(`supabase_data.load_evidence_records_df`) flattened only a subset of them.
Consequently `adverse_events`, `interactions_structured`, `effect_size`, route,
extraction and related values never reached indication discovery. A second loss
occurred in standardization: connector-provided outcome and safety fields could
be replaced by empty LLM fallback fields.

## Changes
- `supabase_data.py`: transports all relevant Phase 2 evidence fields and exposes
  direct aliases used by indication discovery.
- `evidence_standardizer.py`: preserves connector/source-provided outcome,
  safety, interaction, preparation and statistical fields through the legacy
  allowlist boundary.
- `standard_evidence_builder.py`: source values take precedence; LLM values are
  fallbacks only.
- `indication_candidate_discovery.py`: renders JSONB safety/interaction values
  deterministically and derives a canonical result direction only from explicit
  source wording when the structured direction field is empty.

## Scientific safeguards
- Missing values remain missing.
- No efficacy result is inferred from mechanism or indication language.
- Only explicit phrases such as “no significant difference” or “significantly
  reduced” are mapped when `Result_Direction` itself is absent.
- Existing evidence rows whose source fields are genuinely null remain
  “not reported”; this change cannot invent historical data.

## Tests
Focused regression suite: 45 passed.
