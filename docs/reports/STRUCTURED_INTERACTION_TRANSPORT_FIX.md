# Structured Interaction Transport Fix

## Root cause

The conservative raw-text extractor correctly requires an explicit relationship phrase such as `interacts with`. However, `Interactions_Structured` is already an explicitly typed database field. Values such as `anticoagulants` and `antiplatelets` therefore carry the relationship through the schema itself and must not be rejected merely because the serialized value does not repeat a verb.

The previous implementation concatenated structured adverse-event and interaction values and sent both through the raw-prose attribution extractor. This preserved `bleeding` but dropped the structured interaction terms.

## Fix

- Added `normalize_structured_interactions()` in `safety_interaction_attribution.py`.
- Structured interaction lists/dicts/semicolon-separated values are normalized separately.
- Missing placeholders, low-quality source markers, comparator/general-treatment noise and duplicates are removed.
- Raw source prose remains subject to the strict plant-attribution and explicit-relation rules.
- Structured adverse-event prose remains conservatively filtered.
- `Safety_Data_Status` becomes `interaction_signal_present` when structured interactions exist and no adverse/reassurance signal supersedes it.

## Scope

No changes were made to scoring weights, discovery gates, normalization, validation, Supabase schema, reports, UI, or compound-substitution mode.

## Tests

Focused regression suite: `24 passed`.

The complete local suite could not be collected because this sandbox lacks the project runtime packages `supabase` and `streamlit`. GitHub Actions installs those dependencies from `requirements.txt`.
