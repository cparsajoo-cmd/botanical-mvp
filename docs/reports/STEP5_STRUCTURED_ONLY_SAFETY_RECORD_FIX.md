# Step 5 structured-only safety/interaction record fix

## Symptom

A plant (observed case: Ginkgo biloba) has correctly populated structured
JSONB in Supabase — `adverse_events` (e.g. fatal breakthrough seizure,
spontaneous hyphema) and `interactions_structured` (interaction with
anticonvulsants phenytoin and valproate, mechanism CYP2C19 induction) — but
Step 5's final `Safety_Flags` / `Interaction_Flags` columns were empty for
that plant, or showed unrelated placeholder text.

## Root causes (two, independent)

### 1. The record was dropped before any safety logic ran

`_record_text()` in `indication_candidate_discovery.py` only read free-text
columns (Title, Abstract, Outcome, Notes, Target_Indication, etc.). A record
that exists solely to carry structured safety/interaction data — no
title/abstract/outcome of its own — produced an empty string from
`_record_text()`.

`_build_plant_evidence_index()` then executed:

```python
text = _record_text(row)
if not text:
    continue
```

so the record was skipped entirely and never entered the plant's evidence
index. Its `Adverse_Events` / `Interactions_Structured` never reached
`_aggregate_plant_safety()`, regardless of which indication the row was
filed under.

### 2. Once indexed, the term vocabulary was incomplete

`extract_structured_safety_interactions()` in
`safety_interaction_attribution.py` classifies each structured value as an
adverse event or a drug interaction using fixed term lists
(`_ADVERSE_PATTERNS`, `_DRUG_TERMS`). Those lists did not include "seizure",
"hyphema", or the anticonvulsant family (anticonvulsant, antiepileptic,
phenytoin, valproate, CYP2C19). A structured value naming exactly these
terms was therefore classified as `not_assessed` and discarded, even after
fix #1 let the record reach this stage.

## Changes

- `indication_candidate_discovery.py` — `_record_text()` now also renders
  `Adverse_Events` / `adverse_events` / `Interactions_Structured` /
  `interactions_structured` / `Safety_Findings` / `Interactions` (via the
  existing `_structured_text()` helper, which already safely handles JSONB
  dicts/lists) and includes that text in the record's transport text. A
  record with only structured safety/interaction content is no longer
  treated as textless.
- `safety_interaction_attribution.py` — added `seizure` and `hyphema` to the
  adverse-event pattern list and the structured-field coded-term list; added
  `anticonvulsant`, `antiepileptic`, `phenytoin`, `valproate`,
  `valproic acid`, and `cyp2c19` to the known drug/drug-class vocabulary,
  in the same style as the existing entries (warfarin, digoxin, cyp3a4,
  cyp2c9, ...).

## What this does not change

Ranking, scoring weights, diabetes-specific logic, UI, Gold Cases, evidence
collection/ingestion, and the database schema were not touched. The existing
conservative-attribution design (plant anchoring, rejection of comparator
noise, protective/negated toxicity, promotional/retracted sources) is
unchanged — only the vocabulary and the record-textless guard were extended.

## Tests

`test_step5_structured_only_safety_record_fix.py` (new, 5 tests):
- `_record_text()` is non-empty for a structured-only record and still empty
  for a genuinely empty one.
- `extract_structured_safety_interactions()` recognizes seizure/hyphema and
  the anticonvulsant interaction.
- End-to-end: `discover_indication_candidates()` carries the Ginkgo
  structured safety/interaction data into `Safety_Flags` / `Interaction_Flags`
  even when queried for an indication unrelated to the safety record's own
  text (cross-indication safety preservation, per the existing
  `_aggregate_plant_safety()` design).

Full suite: 1817 pre-existing tests + 5 new tests = 1822 passed, 0 failed.
