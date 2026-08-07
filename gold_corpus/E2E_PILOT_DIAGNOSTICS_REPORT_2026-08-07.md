# E2E Pilot Diagnostics Report

**Date:** 2026-08-07  
**Scope:** Gold Corpus frozen-snapshot pilot only  
**Production logic modified:** No

## Why this diagnostic layer was added

The pilot's aggregate `evidence_direction_accuracy` was 1/9 (11.1%). That metric mixes fundamentally different semantics:

- scientific study-result direction (positive / negative / null / unclear),
- affirmative presence of a safety contraindication,
- affirmative presence of a regulatory prohibition/restriction,
- therapeutic-indication statements in regulatory/monograph summaries.

The production free-text direction classifier was designed around study-result language. Therefore the mixed-domain 1/9 value is retained as a descriptive benchmark output, but it is not relabelled as overall scientific accuracy.

## Direction diagnostics

- Raw mixed-domain direction accuracy: **1/9 = 11.1%**
- Indication-domain-only direction accuracy: **1/6 = 16.7%**
- Study-result-eligible direction accuracy (SYSTEMATIC_REVIEW sources in this pilot): **1/3 = 33.3%**

The narrower metric is still poor. This is a real benchmark finding, not a reason to tune the engine on these cases.

## Serious-safety causal diagnostic

Case 006 (*Hypericum perforatum*) shows:

- safety-critical source recall: **1/1 = 100%**
- safety gate failed: **No**
- serious-safety false-negative rate: **1/1 = 100%**
- failure code: `SERIOUS_SAFETY_EVIDENCE_IGNORED`

This localizes the observed miss **downstream of retrieval**. The critical EMA source was present; the production safety gate did not fail. No safety rule or plant-specific tuning was added.

## What was not changed

- Production engine
- Scoring
- Safety rules
- Regulatory rules
- Market engine
- GoldCase truth
- Reference precedence
- Existing pilot snapshots

## Validation

Command:

```bash
pytest -q gold_cases gold_corpus/test_gold_corpus_manifest.py gold_corpus/test_e2e_snapshot_pilot.py gold_corpus/test_e2e_pilot_diagnostics.py test_phase7_end_to_end_validation.py
```

Result:

```text
170 passed
```

## Next scientific-validation step

Do not tune against Case 006 or the three systematic-review direction examples. The next useful step is to enlarge the **frozen raw-source benchmark** with additional independently adjudicated texts, especially positive, negative and null human-study conclusions, then estimate direction-classification performance on that held-out corpus.
