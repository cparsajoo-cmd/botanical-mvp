# Embedding Threshold Calibration

## What this document is

A methodology, a runnable tool (`embedding_threshold_calibration.py`), and
one illustrative dry-run of that tool, for choosing
`EMBEDDING_MIN_CONTRIBUTION`, `EMBEDDING_SEMANTIC_THRESHOLD`, and
`HYBRID_SEMANTIC_THRESHOLD` in `general_indication_relevance.py` based on
measured precision/recall/false-positive-rate/false-negative-rate across a
threshold sweep, rather than a threshold chosen because it makes one example
pass.

## What this document is NOT

**Not a measurement against real embeddings.** This development sandbox's
outbound-network allowlist does not include `api.openai.com` (see
`EMBEDDING_ARCHITECTURE_REVIEW.md` section 6), so no real
`text-embedding-3-small` vector was computed anywhere in this round. The
sweep below uses **synthetic, illustratively-constructed similarity
values** for real plant/indication pairs drawn from this repository's
actual Gold Cases — the *shape* of the exercise (real botanical names,
real indications, a mix of true synonym/mechanism pairs and true generic-
language negatives, plus deliberately borderline cases) is realistic, but
every `similarity` number was assigned by hand to plausibly illustrate how
a real embedding *should* behave, not measured from one. This is stated
explicitly on every figure below and must not be read as validated
production calibration.

**The provisional thresholds already in `general_indication_relevance.py`
(`EMBEDDING_MIN_CONTRIBUTION=0.55`, `EMBEDDING_SEMANTIC_THRESHOLD=0.82`,
`HYBRID_SEMANTIC_THRESHOLD=0.65`) remain provisional after this round.**
This document does not change them. It provides the tool and methodology
to change them correctly, once real embeddings are obtainable.

## How to run REAL calibration once deployed

1. Build a labeled case set: for each case, a `(query, record_text,
   is_relevant)` triple, drawn from real Gold Cases (`is_relevant=True`
   for the plant's own resolved-outcome evidence) plus deliberately
   constructed hard negatives (generic clinical language, a different
   plant's evidence, a different indication's evidence).
2. For each case, call `embedding_service.embed_query()` (or the batch
   equivalent) on both `query` and `record_text`, compute cosine
   similarity between the two vectors.
3. Build `embedding_threshold_calibration.CalibrationCase` objects with the
   real similarity values.
4. Call `sweep_thresholds()` / `format_report()` / `best_threshold_by_f1()`
   from `embedding_threshold_calibration.py` (already implemented and unit
   tested — see `test_embedding_threshold_calibration.py`).
5. Update `EMBEDDING_MIN_CONTRIBUTION` / `EMBEDDING_SEMANTIC_THRESHOLD` /
   `HYBRID_SEMANTIC_THRESHOLD` in `general_indication_relevance.py` from
   the measured result, and re-run the full test suite (the hybrid-engine
   unit tests assert relative ordering of thresholds, not their exact
   values, so they remain valid after a calibration-driven change).
6. Re-run this exercise periodically and whenever `EMBEDDING_VERSION`
   changes (a new embedding model/version can shift the similarity
   distribution).

## Illustrative dry-run (synthetic similarity values)

16 cases: 9 true positives (real synonym/mechanism pairs that should
match), 5 true negatives (generic clinical language or a genuinely
unrelated indication), 2 deliberately borderline cases near the
provisional thresholds.

```
threshold precision    recall       FPR       FNR   TP   FP   TN   FN
     0.05     0.562     1.000     1.000     0.000    9    7    0    0
     0.20     0.600     1.000     0.857     0.000    9    6    1    0
     0.35     0.692     1.000     0.571     0.000    9    4    3    0
     0.45     0.818     1.000     0.286     0.000    9    2    5    0
     0.55     0.818     1.000     0.286     0.000    9    2    5    0
     0.60     0.889     0.889     0.143     0.111    8    1    6    1
     0.65     1.000     0.889     0.000     0.111    8    0    7    1
     0.70     1.000     0.778     0.000     0.222    7    0    7    2
     0.75     1.000     0.667     0.000     0.333    6    0    7    3
     0.80     1.000     0.444     0.000     0.556    4    0    7    5
     0.85     1.000     0.333     0.000     0.667    3    0    7    6
     0.90     1.000     0.111     0.000     0.889    1    0    7    8
     0.95     0.000     0.000     0.000     1.000    0    0    7    9

Best by F1: threshold=0.65  precision=1.000  recall=0.889
```

(Full 19-row sweep at 0.05 increments is produced by
`format_report()`; abridged here for readability.)

### Reading this illustrative result

- Precision reaches 1.0 (zero false positives among these 16 hand-built
  cases) starting at threshold≈0.65 in this synthetic set — consistent
  with, but not proof of, the current provisional
  `HYBRID_SEMANTIC_THRESHOLD=0.65`.
- The two deliberately borderline cases behave as intended: a true
  positive assigned similarity 0.57 (`digestive comfort` /
  "carminative properties in a small preclinical study") is missed at the
  0.65 threshold (contributing to the recall drop at higher thresholds),
  and a true negative assigned similarity 0.61 (`eye health` / "antioxidant
  activity ... retinal cell culture" — deliberately generic-mechanism
  phrasing) is correctly excluded at 0.65 despite a moderately high
  similarity value — this is precisely the "generic mechanism support
  alone must not establish indication relevance" requirement, exercised
  here syntheticaly rather than measured for real.
- `EMBEDDING_MIN_CONTRIBUTION=0.55` sits at a point in this synthetic
  sweep where precision (0.818) is still well below 1.0 — meaning, if this
  synthetic distribution resembled the real one, the current provisional
  minimum-contribution threshold would admit some noise before the
  minimum-contribution gate is combined with the deterministic-support
  requirement in `score_record_relevance_hybrid()`. This is exactly why
  the hybrid engine never allows embedding similarity to stand alone
  below `EMBEDDING_SEMANTIC_THRESHOLD` (0.82) without additional
  deterministic support (`HYBRID_SEMANTIC_THRESHOLD` path) — the two-gate
  design is a real mitigation for this, not merely a hopeful default.

### Honest conclusion

This synthetic exercise is consistent with the current provisional
thresholds being *reasonable starting points*, not evidence that they are
*correct*. Real calibration against actual `text-embedding-3-small`
vectors over a larger, real Gold-Case-derived labeled set is required
before treating these thresholds as validated. The tool to do that
(`embedding_threshold_calibration.py`) is complete and unit-tested; running
it for real requires only network access to `api.openai.com`, which this
environment does not have.
