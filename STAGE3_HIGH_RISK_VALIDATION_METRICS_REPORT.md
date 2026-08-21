# Stage 3 — Formal Safety and Regulatory Validation Metrics

## Scope

Stage 3 changes validation/reporting only. It does not modify production scoring, ranking, evidence interpretation, evidence-body aggregation, eligibility, hard safety gates, hard regulatory gates, or final-decision policy.

Current Decision Engine version remains **1.10.2**.

## Root cause verified

Existing validation code counted `serious_safety_false_negatives` and `regulatory_false_negatives`, but did not make the relevant denominators first-class. This allowed stored reports to show `0` false negatives even when a target class had zero reference-positive cases.

Decision Holdout v5 demonstrates the issue directly: its current post-remediation/regression result has two `NO GO SAFETY` reference cases but zero `NO GO REGULATORY` reference cases. Therefore serious-safety recall is evaluable, while regulatory recall is not evaluable.

## Implementation

### `validation_risk_metrics.py`

Adds denominator-aware high-risk metrics for `NO GO SAFETY` and `NO GO REGULATORY`:

- true positives
- false negatives
- false positives
- reference-positive denominator
- recall
- precision where defined
- total evaluable cases
- non-evaluable cases
- explicit `evaluable` / `not_evaluable` status

A zero reference-positive denominator produces `recall = null` and `status = not_evaluable`, never an apparent successful zero-FN result.

### `high_risk_validation_gate.py`

Adds a minimal validation-only regression gate. Zero false negatives are required for represented high-risk target classes. If one high-risk target class is absent, the overall status is `partial_pass`, not `pass`. If both are absent, status is `not_evaluable`.

These thresholds are explicitly classified as **engineering regression thresholds / internal scientific targets**, not evidence of clinical or regulatory validation.

### `scientific_validity_release_gate.py`

Strengthens the existing scientific release gate without changing its architecture. A final reference-grounded release can no longer pass when either serious-safety or regulatory reference support is zero. False-negative blockers now report the denominator, e.g. `1/4`, instead of an unqualified count.

Backward compatibility is preserved for callers that populate the legacy false-negative fields separately from the confusion matrix: the gate conservatively respects both representations.

### `validation_high_risk_report.py`

Adds a sidecar-report utility for stored validation artifacts. It refuses to overwrite the source result file. This supports historical-result immutability while Stage 4 later formalizes provenance/registry behavior.

## Decision Holdout v5 — denominator-aware interpretation

The existing `gold_corpus/decision_holdout_v5/results.json` is a post-remediation/regression result and was not modified.

The Stage 3 sidecar reports:

- Serious safety: TP = 2, FN = 0, reference-positive = 2, recall = 1.0, precision = 0.667.
- Regulatory: TP = 0, FN = 0, reference-positive = 0, recall = not defined, status = `not_evaluable`.
- Overall high-risk regression-gate status = `partial_pass`, not `pass`, because regulatory performance cannot be evaluated on this dataset.

This does not upgrade Decision Holdout v5 to an independent holdout and does not reinterpret its historical blind result.

## Tests

Focused and broader Stage 3 regression suite:

- **118 passed, 0 failed**

Coverage includes:

- denominator-aware safety/regulatory metrics
- zero-support `not_evaluable` behavior
- false-negative denominator reporting
- precision behavior
- non-evaluable row accounting
- sidecar overwrite protection
- scientific release gate
- decision benchmark
- Decision Holdout v5 runner
- pharmaceutical safety zero-FN tests
- regulatory authorization tests
- gate-layer tests
- structured serious-interaction tests
- structured safety interaction semantics
- structured final-decision authority

All modified/new Python files passed `py_compile`.

A full repository `pytest -q` attempt was also made. Collection could not complete in the local environment because optional/runtime dependencies are unavailable, specifically `supabase` and `streamlit`. Nineteen test modules failed during collection for those missing dependencies. This is an environment limitation, not a claimed passing full-suite result.

## Scientific interpretation

### Improved

High-risk validation reporting is now denominator-aware and cannot describe an absent regulatory/safety reference class as successful zero-FN validation. Existing release gating is stricter about evaluability, and targeted regression reporting distinguishes full pass, partial pass, fail, and not-evaluable states.

### Not scientifically validated by this stage

Stage 3 does not establish broad safety sensitivity, regulatory sensitivity, clinical validity, or external expert agreement. In particular, `0/2` safety false negatives in Decision Holdout v5 remains evidence only about two reference-positive safety cases in a post-remediation/regression dataset.
