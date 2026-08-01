# Step 5 evidence-level safety parser fix

Scope: safety/interaction attribution only. Discovery, scoring weights, thresholds,
normalization, validation, UI, Supabase schema, and compound-source mode are unchanged.

## Fixed false positives
- Pharmacological efficacy phrases such as `hypoglycemic activity/properties/effect`
  are not adverse events unless explicit event/risk language is present.
- Statements about a `current therapeutic regimen`, conventional treatment, or
  comparator side effects are not attributed to the botanical.
- A plant mentioned in an abstract introduction no longer anchors every later
  sentence. Raw-text attribution requires the plant in the same sentence or a
  tightly local intervention reference/reporting sentence.

## Preserved true signals
- Immediate study-result statements such as `Mild gastrointestinal adverse events
  were reported` remain attributable when the preceding sentence identifies the
  botanical intervention.
- Explicit plant-drug relations remain extractable from raw text.
- Already-structured interaction fields retain concise values such as
  `anticoagulants` and `antiplatelets`; they are not forced through raw-prose rules.
- Already-structured safety fields retain coded adverse values such as bleeding,
  while efficacy-only phrases are rejected.

## Tests
Focused regression suite: 20 passed.
The full repository suite could not be collected in this container because the
optional `supabase` and `streamlit` packages are not installed here.
