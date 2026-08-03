# Step 5 General Indication-Relevance Architecture — Completion Report

## 1. Audit of the production path (as found, before this round)

Tracing actual imports/call sites (not module names or isolated tests):

```
indication_candidate_discovery.py
    imports general_indication_relevance.build_indication_profile,
                                        score_record_relevance
    -> ALREADY authoritative for record-level relevance and candidate
       gating (discover_indication_candidates). indication_semantics.py
       was already demoted to a strictly-capped, disclosed
       curated_assist_fallback there, consulted only when the
       corpus-adaptive engine finds no match at all.

candidate_shortlisting.py
    imports indication_semantics.resolve_indication_semantics
    -> NOT wired to general_indication_relevance.py at all.
       _indication_relevance_detail() independently re-derived relevance
       from raw text blobs against indication_semantics.py's 27-family
       dictionary, ignoring the Indication_Match_* columns already
       computed upstream. This is the exact "two independent
       recalculations that can disagree" problem.
```

So the situation was more advanced than a first read suggests: the
authoritative engine already existed and was already the entry gate for
discovery. The one production disagreement was entirely in the second
(shortlisting) stage.

Separately, `general_indication_relevance.py`'s own stopword list had a
real gap: generic outcome-direction words ("reduced", "improved") and
clinical-trial-methodology words ("randomized", "rct") were not excluded
from corpus-derived expansion-term learning, so they could link unrelated
records purely through shared generic phrasing. This is exactly the class
of failure constraint 5/8 in your brief warns against, and it was caught by
one of the mandatory tests, not invented for this report.

## 2. Changes made this round

| File | Change | Why |
|---|---|---|
| `general_indication_relevance.py` | Added ~35 generic outcome-direction and clinical-trial-methodology words to `_STOPWORDS` (`reduced`, `improved`, `randomized`, `rct`, `controlled`, `placebo`, `baseline`, etc.) | Prevented a diabetes record ("Reduced HbA1c") from being learned as corpus-derived-relevant to a "Cough" query purely via the shared generic word "reduced", and separately via shared RCT-methodology wording ("randomized"/"rct") in `Study_Type`/`Evidence_Level`. Caught by `test_cough_indication_generalization.py`'s pre-existing leakage assertion — not a new test written to force a pass. |
| `candidate_shortlisting.py` | `_indication_relevance_detail()` now branches: if the input rows carry the authoritative `Indication_Match_Type` column (i.e. came from `discover_indication_candidates()`), score via the upstream match_type/terms (`_indication_relevance_detail_authoritative`, new). Only when that column is entirely absent (compound-source mode, or any legacy caller) does it fall back to the pre-existing `indication_semantics.py`-based logic (`_indication_relevance_detail_legacy_fallback`, renamed/unchanged body). Added import of `general_indication_relevance`'s `MATCH_*` constants (grouped locally into `_MATCH_STRONG`/`_MATCH_SUPPORTIVE`, mirroring `indication_candidate_discovery.py`'s own grouping, to avoid a module-import cycle). | This is the actual missing piece: discovery and shortlisting now consume one shared relevance decision per record instead of computing two that can disagree. The tiered scoring math (human/preclinical source bonuses, outcome-profile adjustments, concept-breadth bonus) is unchanged — only the *source* of "is this row direct/mechanistic evidence" changed, from independent text-matching to reading what discovery already decided. |
| `test_general_indication_relevance_production_wiring.py` | New. 10 production-path tests (see §4). | Mandatory tests specified in your brief, run against the real `discover_indication_candidates()` → `build_plant_candidate_shortlist()` path, not isolated engine unit tests. |

`indication_candidate_discovery.py` and `indication_semantics.py` are
unchanged from the previous round's delivery (the `_record_text` fix and
the `_terms()`/`resolve_indication_semantics()` wiring already completed
then) — included again below only so this delivery is self-contained and
you don't have to reconcile two separate download batches.

## 3. Proof general_indication_relevance.py is the real production path

```
$ grep -n "general_indication_relevance" indication_candidate_discovery.py
20: from general_indication_relevance import (
22:     build_indication_profile,
24:     score_record_relevance,
...
629: relevance_profile = build_indication_profile(
638:     return score_record_relevance(
```

`discover_indication_candidates()` calls `build_indication_profile()` once
per query against the full evidence corpus, then `score_record_relevance()`
for every record of every candidate plant. The result (`Indication_Match_*`
columns) is what gates candidate entry (`_MATCH_STRONG`/`_MATCH_SUPPORTIVE`
membership) and is attached to every output row.

`candidate_shortlisting.py` now reads those same columns
(`_row_authoritative_relevance()`, `_group_has_authoritative_relevance()`)
rather than recomputing anything, whenever they are present.

## 4. Test report

```
$ python -m pytest -q
1855 passed in 16.83s
```

Breakdown of what changed the count from the prior round (1845) to this one:

- `test_general_indication_relevance_production_wiring.py`: **10 new
  tests**, all against the real production path:
  1. `test_unseen_indication_has_no_dictionary_entry_anywhere` — structural
     proof the synthetic phrase used below is absent from
     `indication_semantics.py`.
  2. `test_unseen_indication_end_to_end_discovery_and_shortlist` — full
     `discover_indication_candidates` → `build_plant_candidate_shortlist`
     for `"zelunergic mucosal discomfort"` (invented in the test, added
     nowhere in source). Relevant plant found, unrelated plant excluded,
     authoritative match fields present at both stages.
  3. `test_corpus_derived_semantic_relevance_is_bounded_and_disclosed` — a
     second record for the same plant, sharing only a corpus-learned
     mechanism term ("crosslinking") and no query words, scores lower than
     the direct/exact record, with the derived term named in the reason.
  4. `test_generic_shared_words_do_not_create_a_relevant_candidate` —
     negative control: a record built entirely from "treatment... effect...
     patients... extract... clinical study" does not pass the gate for an
     unrelated invented query.
  5. `test_cough_regression_via_corpus_evidence_no_hardcoded_cough_terms` —
     Cough found via "antitussive"/"expectorant" wording only.
  6. `test_diabetes_regression_no_leakage_from_unrelated_plant` — diabetes
     query finds the diabetes plant, not a cough-evidence plant.
  7. `test_shortlist_uses_authoritative_field_not_independent_recomputation`
     — direct proof: an authoritative-tagged row with an *empty* narrative
     blob (nothing the legacy indication_semantics.py path could match)
     still scores > 0; the same row with the authoritative column stripped
     scores exactly 0 — the contrast proves the field is actually driving
     the score, not coincidentally agreeing with a recomputation.
  8. `test_discovery_and_shortlist_never_disagree_about_match_type_source`
     — every relevant row's match_type read by shortlisting equals exactly
     what discovery wrote.
  9. `test_compound_source_mode_rows_use_legacy_fallback_unaffected` —
     rows without `Indication_Match_Type` (as compound-source mode
     produces) still resolve via the untouched legacy path.
  10. `test_ginkgo_safety_and_interaction_and_reassurance_survive_new_wiring`
      — structured Ginkgo safety/interaction/reassurance data (fatal
      breakthrough seizure, spontaneous hyphema, phenytoin, valproate,
      CYP2C19 induction, "no important safety concerns") still reaches
      Step 5 output after this round's changes.

- Previously-existing tests, all still passing, including the ones your
  brief specifically named as having recently failed:
  `test_step5_structured_only_safety_record_fix.py`,
  `test_step5_safety_flags_source_pointer_noise_fix.py`,
  `test_step5_safety_reassurance_vocabulary_fix.py`,
  `test_cough_indication_generalization.py` (now passing for the reason it
  claims to test, not by literal-word coincidence — see §1),
  `test_general_indication_relevance.py`, `test_candidate_shortlisting.py`
  (compound-source-shaped rows, exercising the legacy fallback), and all
  Gold Case / benchmark tests.

No test was weakened, skipped, or deleted to obtain this result. Two test
design mistakes of mine (not engine bugs) were caught and fixed during
development — documented in code comments in the new test file: an
accidental shared word between a query and a "generic-word" negative
control record, and a 2-record corpus too small for the ubiquity filter to
correctly judge a shared term as non-discriminative. Both are explained
inline in the test file so they're auditable, not hidden.

## 5. Remaining `indication_semantics.py` production imports

```
$ grep -rln "indication_semantics" --include="*.py" . | grep -v "^\./test_"
./indication_candidate_discovery.py
./indication_semantics.py
./candidate_shortlisting.py
./general_indication_relevance.py   <- comment references only, no import
```

- **`indication_candidate_discovery.py`** — imports `indication_terms()`,
  used only to build `assist_terms` passed into
  `score_record_relevance()`'s `curated_assist_fallback` branch, which is
  consulted only when the corpus-adaptive engine finds nothing at all, is
  capped below every corpus-adaptive match type, and always discloses its
  use in `Indication_Match_Reason`. Confirmed by code inspection at
  `indication_candidate_discovery.py:610-640`.
- **`candidate_shortlisting.py`** — imports `resolve_indication_semantics()`,
  used only inside `_indication_relevance_detail_legacy_fallback()`, which
  is only reached when `Indication_Match_Type` is absent from every row of
  a plant's group (rows that never went through the authoritative engine —
  compound-source discovery mode, or a hand-built legacy DataFrame, as in
  `test_candidate_shortlisting.py`'s existing tests).
- **`general_indication_relevance.py`** — no import; the two hits are
  docstring/comment references to the fallback design, confirming (not
  contradicting) the above.

No other production file (`pharma_report_generator.py`,
`step_rd_candidates.py`, `botanical_rd_candidate_engine.py`, `step_inputs.py`)
imports `indication_semantics.py`.

## 6. Statement: unseen indication works without a dictionary entry

Confirmed by test #2 above (`test_unseen_indication_end_to_end_discovery_and_shortlist`):
the phrase `"zelunergic mucosal discomfort"` — verified absent from
`indication_semantics.py` by `resolve_indication_semantics()` returning
`None` for it, and absent from every other source file (it does not exist
anywhere except inside the test itself) — is:

1. discovered correctly (relevant plant found, unrelated plant excluded)
   by `discover_indication_candidates()`,
2. carried through with `Indication_Match_Type == "exact_indication"` and
   `Indication_Match_Score > 0.9`,
3. shortlisted correctly by `build_plant_candidate_shortlist()`, with a
   positive `Indication_Relevance_Score` driven by that authoritative
   field, not a coincidental legacy-path match.

No code change, dictionary entry, or vocabulary addition was made anywhere
for this phrase. It is the invented indication requirement from your brief,
satisfied structurally.

## 7. Known limitations (stated honestly)

- **`_pick_from_row` single-column-wins quirk (pre-existing, not
  introduced or fixed this round).** If a single evidence_records row has
  *both* `Adverse_Events`/`Interactions_Structured` *and* `Safety_Findings`
  populated at once, `_pick_from_row`'s priority-ordered column list
  returns only the first non-empty match rather than merging them — one of
  the two would be silently dropped for that row. This was surfaced while
  building test #10 above (fixed in the test by using two separate rows,
  matching how your real Supabase data has actually been structured in
  every case reviewed so far — case-report safety data and meta-analysis
  reassurance data as separate `evidence_records` rows for Ginkgo). If a
  future evidence-ingestion source ever writes both structured fields onto
  one row, this would need a small, separate, explicitly-approved fix
  (merge instead of first-match in `_pick_from_row`, or a caller that reads
  multiple sub-fields directly) — flagged now rather than folded in
  unreviewed.
- **Corpus-adaptive learning is corpus-size-sensitive.** The
  ubiquity/specificity filters in `build_indication_profile()` (reject a
  term present in >80% of the corpus; require minimum seed support) behave
  correctly at realistic corpus sizes but can misjudge a genuinely shared
  term as either "ubiquitous, discard" or "rare, keep" in a very small
  corpus (a handful of records) — this is a statistical property of
  frequency-based term weighting, not a bug, but it means a synthetic
  2-3-record test corpus needs care to construct realistically (documented
  inline in the new test file after a design mistake there was caught).
- **The stopword list is a curated, growable set, not a closed one.**
  Today's fix removed two categories (outcome-direction verbs,
  trial-methodology nouns) that were demonstrated to leak. Other generic
  categories (e.g. dosage/route-of-administration words, statistical-test
  names) have not been audited and could in principle cause similar,
  as-yet-undemonstrated leaks in a larger real corpus. No claim is made
  that the stopword list is now exhaustive — only that the specific,
  demonstrated leak is fixed.
- **`indication_semantics.py` is not deleted, by design.** Per your
  instruction ("retain it only as an optional backward-compatibility
  fallback with a strictly capped contribution... it must not override the
  general engine"), it was kept rather than removed, in both its existing
  roles (capped assist in discovery, legacy fallback in shortlisting). If
  you'd prefer it removed entirely rather than retained as a fallback, that
  is a one-line-per-callsite deletion, not a redesign — flagging the choice
  rather than making it unilaterally.
