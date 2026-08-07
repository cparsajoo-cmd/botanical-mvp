# Human Evidence Direction Benchmark — Baseline Report
Date: 2026-08-07

## Scope

Benchmark-only evaluation of the existing `evidence_interpretation.py` classifier on
12 real, traceable human-study examples from PubMed.

No Production Logic, scoring, safety rules, regulatory rules, market logic, GoldCase
truth, or source precedence was modified.

## Frozen benchmark composition

- 12 independent source records
- 3 expected positive
- 3 expected null
- 3 expected negative
- 3 expected mixed
- RCTs plus one meta-analysis
- Every record has a PMID and PubMed URL

## Baseline result

- Direction accuracy: 3/12 = 25.0%
- Study-design accuracy: 6/12 = 50.0%

### By expected direction

- Positive: 1/3
- Null: 2/3
- Negative: 0/3
- Mixed: 0/3

## Main diagnostic finding

The current bounded phrase classifier performs best on explicit null phrasing
(e.g. "not statistically significant") but misses much ordinary clinical language.

Observed failure patterns include:
- positive conclusions written as "significantly greater reduction" or
  "statistically significant change";
- negative conclusions written as "was not effective" or "fails to support efficacy";
- mixed results where a significant secondary outcome coexists with a
  non-significant primary outcome;
- study-design phrasing with punctuation variants such as
  "randomized, double-blind, placebo-controlled".

These are benchmark observations only. No phrase tables were changed.

## Scientific interpretation

This benchmark does not measure overall clinical validity of the platform.
It isolates one existing component: free-text study-design and evidence-direction
classification on real human-study wording.

The 25% baseline should therefore be read as a calibration finding, not as the
accuracy of the complete Botanical R&D engine.

## Regression

Targeted canonical suite after adding the benchmark:
- 176 passed
- 0 failed

## Files added

- `gold_corpus/human_evidence_direction_benchmark.json`
- `gold_corpus/human_evidence_direction_benchmark.py`
- `gold_corpus/run_human_evidence_direction_benchmark.py`
- `gold_corpus/test_human_evidence_direction_benchmark.py`
- `gold_corpus/human_evidence_direction_benchmark_run.json`
- `gold_corpus/HUMAN_EVIDENCE_DIRECTION_BENCHMARK_REPORT_2026-08-07.md`

## Next scientific step

Do not tune the classifier yet.

First expand the frozen human-direction benchmark with additional independently
curated real sources, especially:
- additional negative RCTs,
- additional mixed-outcome RCTs,
- objective-vs-subjective discordance,
- preparation-specific human trials.

Only after the benchmark is large enough should production changes be considered
in a separate, explicitly authorized phase.
