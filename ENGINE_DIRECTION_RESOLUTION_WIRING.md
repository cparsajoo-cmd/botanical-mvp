# Wiring `resolve_record_direction()` into the production scoring path (2026-08-08)

## What changed

Before this change, `botanical_rd_candidate_engine.py`'s scoring path
(`_collect_raw_evidence()` → `interpret_evidence()`) computed
`Evidence_Direction` (and therefore the Clinical-evidence-tier
contribution to `R&D_Opportunity_Score`/`Overall_Score`) by running
`evidence_interpretation.classify_evidence_direction()` — a phrase/regex
text classifier — on a single POOLED text blob concatenated from every
evidence record that matched a given plant/compound/indication key. It
never looked at any individual record's own structured
`Result_Direction`/`LLM_Result_Direction`, even when one already existed
(e.g. after running `backfill_canonical_assertions.py`).

`canonical_scientific_assertion.resolve_record_direction()` already
existed, already implements the correct precedence (structured source
assertion → LLM extraction → legacy reported direction → per-record text
fallback), and was already used correctly by the Reference-Grounded
Validation decision path (`evidence_body_assessment.py` /
`final_decision_policy.py`). The production scoring path was the one
place that still bypassed it entirely.

This change wires the two together, reusing the existing function rather
than adding a second, parallel precedence implementation.

## Files changed

- `evidence_interpretation.py` — `interpret_evidence()` gained a new
  optional keyword argument, `contributing_records`. New helper function
  `_resolve_pooled_direction()`. New diagnostic field
  `EvidenceInterpretation.direction_provenance`.
- `botanical_rd_candidate_engine.py` — one call site changed: the
  existing `interpret_evidence(...)` call now also passes
  `contributing_records=evidence_contributing_records` (the 4th return
  value of `_collect_raw_evidence()`, which was already being computed
  and already threaded through the row loop for Safety/Regulatory gate
  evidence ids — nothing new had to be built to get this data to this
  call site).
- `test_evidence_direction_structured_resolution.py` — new, 13 tests.

## Backward compatibility

`contributing_records` defaults to `None`. When it is `None` or empty,
`interpret_evidence()`'s behavior — `study_design`, `evidence_direction`,
`evidence_quality`, `evidence_applicability`, `contribution` — is
byte-identical to before. This covers every other existing caller:
`final_decision_policy.py`'s `_final_decision_direction()`,
`end_to_end_validation.py`, and every existing test. Only the one call
site in `botanical_rd_candidate_engine.py` was changed to opt in.

`study_design`, `evidence_quality`, and `evidence_applicability` are
still derived from the pooled text blob exactly as before, even when
`contributing_records` is supplied — only `evidence_direction` changes.
Widening the other three was out of scope for this pass.

## What the new resolution actually does

Per contributing record, via `resolve_record_direction()` (imported, not
reimplemented):

1. Prefer the record's own structured `source_result_direction`.
2. Then its `llm_result_direction`.
3. Then a legacy `reported_direction`.
4. Only if none of those exist: classify that ONE record's own
   text/assertion_text — never the pooled blob — via the existing
   `classify_evidence_direction()`.

The per-record results are aggregated with a simple, conservative rule
that introduces no new direction value:

- No informative (non-"unclear") record → overall `"unclear"`.
- Exactly one distinct informative direction across all records → that
  direction.
- More than one distinct informative direction → `"mixed"` (reusing the
  existing `DIRECTION_MIXED` contribution ratio, unchanged).

## Why per-record fallback matters even with zero backfilled data

Independent of whether `backfill_canonical_assertions.py` has been run
yet, this change already helps: classifying each record's own text
individually, instead of a blob concatenated from every contributing
source, removes the dilution mechanism the Reference-Grounded Validation
v2 report's own sanity check pointed at — a real positive-direction
sentence from one record can get buried among unrelated text from other
records once everything is joined into one string before classification.
`test_per_record_fallback_finds_signal_pooling_would_dilute` exercises
this directly.

## What this does NOT fix

- It does not add any new vocabulary/phrases to
  `evidence_interpretation.py`'s phrase tables. A record with no
  structured direction AND text that genuinely doesn't match any known
  phrase (e.g. the exact "more effective than placebo" /
  "confirmed efficacy" gap identified in the RGV v2 sanity check) is
  still unresolved by text fallback alone — this change makes the
  fallback run on cleaner, per-record text, but doesn't teach it new
  phrases.
- It does not run the Reference-Grounded Validation blind holdout again.
  That 24-case set is already exposed and can only be used as a
  regression check now, not a fresh validity estimate — a genuinely new
  blind estimate needs a newly frozen, disjoint case set, per the
  integrity rule already documented in both existing RGV reports.
- `study_design`/`evidence_quality`/`evidence_applicability` still come
  from the pooled blob. If the same dilution problem affects those
  (plausible, not verified here), that's a separate, unaudited scope.

## Test results

New file: `test_evidence_direction_structured_resolution.py`, 13/13
passed — backward compatibility, structured-direction precedence
(source > LLM > legacy > text), the "explicit Unknown is not
overridden" fail-safe rule, per-record vs. pooled-blob dilution, and the
aggregation rule (unclear/single-direction/mixed) at both the
`interpret_evidence()` level and the `_resolve_pooled_direction()` unit
level.

Full existing suite re-run after this change: same 2933 pre-existing
passing tests still pass + 13 new = 2946 passed. Same 9 pre-existing
failures as before this change (confirmed unrelated in the prior audit
of `backfill_canonical_assertions.py` — quarantining these new/changed
files reproduces the identical 9 failures). No new failures introduced.

## Suggested next step

Run `backfill_canonical_assertions.py --apply` against the real
`evidence_records` table so structured `Result_Direction` actually
exists for records that currently have none — this wiring change has
nothing to prefer over the text fallback until that data exists. After
a meaningful fraction of the table is backfilled, a NEW, independently
frozen Reference-Grounded Validation holdout (not the already-exposed
v1/v2 sets) would be the honest way to measure whether accuracy actually
improved.
