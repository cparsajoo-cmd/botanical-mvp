# Step 5 Safety_Flags source-pointer noise fix

## Symptom

In the production export, `Safety_Flags` for Ginkgo biloba (and 44 of 109
plant rows generally) contained garbled, duplicated text such as:

```
Unknown Unknown Cognitive decline / Alzheimer's support LiverTox
hepatotoxicity/safety source found for Ginkgo biloba.; ... OpenFDA FAERS
returned 5 adverse event records for Ginkgo biloba. (+8 more)
```

`Interaction_Flags` was correct at this point (the two fixes in
`STEP5_STRUCTURED_ONLY_SAFETY_RECORD_FIX.md` were already working). This is
a separate, pre-existing issue, not introduced by that change — it was
previously masked because affected records had enough other text to survive
`_record_text()` even before that fix, so the noise was already present, just
less visible while `Safety_Flags` was mostly empty.

## Root causes (two, independent)

### 1. Connector "a source exists" pointer statements were read as findings

`livertox_connector.py` and `openfda_connector.py` write a `Notes` sentence
that reports a safety-relevant *source* was found — not what that source
actually says:

- `"LiverTox hepatotoxicity/safety source found for {scientific_name}."`
- `"OpenFDA FAERS returned {N} adverse event records for {scientific_name}.
  This is a safety signal source and requires manual clinical
  interpretation."`

Because these sentences contain medical trigger words ("hepatotoxicity",
"adverse event"), `_is_adverse_statement()` in
`safety_interaction_attribution.py` accepted them as if they described an
actual finding, when they explicitly say the opposite — that a human still
needs to go read the source and interpret it.

### 2. Unrelated columns were glued into one run-on sentence

`_record_text()` in `indication_candidate_discovery.py` joined every column's
value with a bare space. When `Study_Type` / `Evidence_Level` held the
literal placeholder `"Unknown"`, and `Target_Indication` held a real value,
and `Notes` held the connector sentence above, they were concatenated with no
sentence boundary — one run-on fragment for the classifier to evaluate,
instead of separable sentences.

## Changes

- `indication_candidate_discovery.py` — `_record_text()` now joins column
  values with `". "` instead of `" "` (each value's own trailing period, if
  any, is stripped first to avoid doubling). Column content is unchanged;
  only the separator changed. This lets sentence-splitting downstream
  (`safety_interaction_attribution._split`) evaluate each column's content as
  its own fragment.
- `safety_interaction_attribution.py` — added `_SOURCE_POINTER_NOISE_PATTERNS`
  (four regexes matching the connector template wording: "safety source
  found for", "returned N adverse event records", "requires manual clinical
  interpretation", "is a safety signal source") and applied them inside
  `_is_noise()`, the same gate already used to reject promotional/retracted
  text and comparator noise. This applies to both the raw-text fallback path
  and the structured-field `items()` path, since both call `_is_noise()`.

## What this does not change

The connectors themselves, their Notes wording, ranking, scoring weights,
diabetes-specific logic, UI, Gold Cases, and the database schema were not
touched. Genuine adverse-event and interaction sentences are unaffected —
verified by a non-regression test.

## Tests

`test_step5_safety_flags_source_pointer_noise_fix.py` (new, 6 tests):
- `_record_text()` separates columns with a sentence boundary instead of
  gluing them.
- LiverTox and OpenFDA FAERS pointer sentences are rejected as noise, both
  via the raw-text path and the structured-field path.
- A genuine plant-attributed adverse-event sentence is still accepted
  (non-regression).
- End-to-end: a plant with one genuine structured safety/interaction record
  and one connector pointer-style record produces a `Safety_Flags` value that
  contains the real finding and none of "LiverTox", "source found for", or
  "Unknown".

Full suite: 1822 previously-passing tests + 6 new tests = 1828 passed, 0 failed.
