# Step 5 general indication-relevance wiring fix

## The real question

Is Step 5's indication matching genuinely general, or does it only work for
a handful of hardcoded diseases? Concretely: querying "Cough" returned zero
candidates, even for plants (Thymus vulgaris, licorice) with real clinical
evidence for it.

## What was actually found

There were **two separate, disconnected pieces already in the repo**, not
one missing feature:

1. `indication_candidate_discovery.py` (the stage that decides which
   evidence records/plants even enter the candidate list) resolved an
   indication via its own local `_terms()` function and a **4-family**
   `DISEASE_FAMILIES` dict (metabolic, sleep, cognitive, skin_aging). For
   any indication outside those four, it fell back to a bare literal
   single/few-word substring match with **no synonyms and no mechanistic
   terms at all**.

2. `indication_semantics.py` already existed, with a **27-family**,
   alias-aware term set — covering Cough, Migraine (as "Headache / mood
   support"), Eczema (as "Skin inflammation"), and everything in the
   product's actual indication dropdown — with real clinical direct terms
   (e.g. "antitussive", "cough frequency") and mechanistic terms (e.g.
   "expectorant", "demulcent"). Its own module docstring already states it
   is meant to be *"the single source of truth used by both raw candidate
   discovery and plant-level shortlisting."* It was already imported and
   used by the later scoring stage, `candidate_shortlisting.py` — but it
   was **never imported by `indication_candidate_discovery.py`**, the
   earlier stage that actually gates which plants get considered at all.

So the system was never missing a generalization engine. It had one, built
and already partially wired in, and the earlier pipeline stage — the one
that actually matters for "does Cough return anything" — was quietly left
on the old, narrow path.

### Why the existing Cough test gave false confidence

`test_cough_indication_generalization.py` already existed and was passing.
It calls `discover_indication_candidates(..., "Cough", ...)` with synthetic
evidence whose `Primary_Outcome` text happens to contain the literal phrase
"Reduced cough frequency" — so the old bare-token fallback (direct_terms =
`("cough",)`) matched it by literal coincidence. The test never exercised
the actual synonym/mechanism path it was named for. A reproduction using
evidence phrased only as "antitussive and bronchorelaxant activity" (real
scientific-paper phrasing, no literal "cough" anywhere) returned zero
candidates before this fix, confirming the gap the passing test was masking.

## Changes

- `indication_candidate_discovery.py` — `_terms()` now delegates entirely to
  `indication_semantics.indication_terms()` instead of reading from the
  local `DISEASE_FAMILIES` dict. `DISEASE_FAMILIES` itself is left in the
  file (unused, annotated as superseded) rather than deleted, to keep this
  change minimal and reversible; nothing else in the codebase imports it.
- `indication_semantics.py` — `resolve_indication_semantics()` now also
  matches a free-text query against each family's `direct` clinical terms,
  not only its canonical name and curated `aliases`. Without this, a term
  already listed in `direct` (e.g. "migraine" under "Headache / mood
  support") could describe evidence once a family was found, but could
  never be used to *find* that family from a query in the first place —
  "Migraine" itself returned zero candidates until this second fix.

## What this does not change

Ranking, scoring weights, safety/interaction logic, UI, Gold Cases, the
database, and evidence collection were not touched. No new hardcoded
per-disease vocabulary was added anywhere — every indication now goes
through the same single, shared, alias-aware resolution path used by both
pipeline stages. Adding a genuinely new indication in the future means one
new entry in `indication_semantics.py`, used automatically by both stages —
not two separate edits in two files.

## Tests

`test_indication_semantics_wiring_fix.py` (new, 7 tests):
- `_terms()` now returns the same result as `indication_semantics.
  indication_terms()` for Cough.
- "Migraine" resolves to a family via its own `direct` term.
- The four previously-hardcoded indications (diabetes, insomnia, Alzheimer's,
  skin aging) still resolve sensibly — backward compatibility.
- End-to-end discovery succeeds for Cough, Migraine, and Eczema using
  evidence text that deliberately avoids the literal indication word, to
  prove genuine semantic matching rather than a lucky literal hit.
- A plant with unrelated (diabetes) evidence is still correctly excluded
  from a Cough query — no cross-indication leakage introduced.

Full suite: 1838 previously-passing tests (in this refreshed repo copy,
which also required re-applying the `_record_text` fixes from the prior two
rounds — see note below) + 7 new tests = 1845 passed, 0 failed.

## Separate note: CI failures in this repo copy

The uploaded repo's CI run showed 5 failing tests, all in the Safety_Flags
regression tests from the previous two fix rounds. The cause was simple:
this repo copy had `safety_interaction_attribution.py` and the three
Safety_Flags test files updated, but **`indication_candidate_discovery.py`
still had the pre-fix `_record_text()`** — the file update from those
rounds was not carried over. Both prior fixes (structured-column rendering
and the ". " sentence-boundary separator) were re-applied to
`indication_candidate_discovery.py` as part of delivering this fix, and the
full suite (including those 5 previously-failing tests) now passes. No new
Safety work was done — this is only restoring what was already reviewed and
approved in the last two rounds.
