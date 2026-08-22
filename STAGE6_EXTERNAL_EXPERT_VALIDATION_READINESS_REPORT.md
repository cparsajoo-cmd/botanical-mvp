# Stage 6 — External Expert Validation Readiness

## Scope

Stage 6 adds validation-study tooling only. It does not modify the production decision engine, retrieval, scoring, ranking, evidence interpretation, safety gate, regulatory gate, non-compensatory eligibility, or final-decision policy.

The decision engine remains **1.10.2**.

## Repository finding before implementation

The repository already contained structured expert sign-off and reference-adjudication components, but those components address candidate review / Gold Case adjudication. They do not implement the prospective study design requested here: approximately 30–50 frozen genuine evidence records, two independent experts blinded to platform output, independent label preservation, third-expert/adjudication handling, exact-record platform comparison, and field-level metrics.

For that reason Stage 6 adds a separate validation-only layer rather than changing those existing components.

## What was added

### Prospective external study packet

`gold_corpus/external_expert_validation_v1/evidence_records.json` is intentionally empty and has development status. No evidence records or scientific labels were fabricated.

The intended study size is 30–50 genuine records. Each record must retain traceable source text and a source locator.

### Existing scientific taxonomies reused

The expert-validation fields reuse existing production concepts:

- Evidence Direction: positive / negative / null / mixed / unclear
- Study Design: the existing `evidence_interpretation.py` taxonomy
- Evidence Quality: high / moderate / low / unknown

Serious-safety and regulatory blocking observations use an evaluable flag plus a boolean signal. These are validation observations only; they do not add new production scoring dimensions or change production taxonomies.

### Blinding and independence guards

Completed expert files must attest that:

- each expert was blinded to platform output;
- each expert worked independently;
- labels were completed before platform-output disclosure;
- Expert A and Expert B use different expert codes;
- every frozen record is labeled exactly once.

Original expert files are never rewritten by adjudication or scoring.

### Adjudication

A separate adjudication artifact preserves the two original expert files and records a consensus/reference label for every record, with a stated reference basis. The protocol requires a predefined third-expert or adjudication procedure for disagreements.

### Leakage and freeze controls

The pre-freeze checker blocks exact historical DOI, PMID, or NCT overlap and duplicate identifiers within the proposed external dataset. Ambiguous study-level overlap that cannot be proven from identifiers is explicitly left for mandatory qualified human review rather than inferred from title similarity.

Freeze requires 30–50 records, completed historical-overlap review, completed manual study-overlap review, independent selection, and pre-execution selection. The freeze manifest is write-once and stores the evidence-packet SHA256 plus the exact engine version targeted for the first blind platform execution.

### Exact-record platform comparison

Platform-output validation requires the exact frozen record-ID set, the exact engine version, and an attestation that reference labels were not visible to the platform execution process before execution.

### Metrics

The scorer reports:

- Expert A vs Expert B field-level agreement before adjudication;
- platform vs adjudicated-reference agreement for each categorical field;
- confusion matrix for each field;
- per-class recall;
- explicit list of errors;
- serious-safety TP / FN / FP / recall / precision / denominator;
- regulatory TP / FN / FP / recall / precision / denominator;
- evaluable and non-evaluable counts.

A risk domain with zero reference-positive records is reported as **not evaluable**, not as evidence of a successful zero-false-negative result.

### Provenance and one-time first evaluation

The first blind evaluation is recorded through the Stage 4 immutable provenance mechanism as `independent_frozen`. A write-once marker prevents a second run from being represented as another first independent evaluation.

Once the first result is inspected the dataset is exposed. If it is then used for remediation, later executions must be explicitly recorded as regression runs.

## Verification

Focused Stage 6 tests:

- **10 passed, 0 failed**

Relevant Stage 3–6 / holdout / expert / adjudication regression tests:

- **211 passed, 0 failed**

All Stage 6 Python files passed `py_compile`.

A full repository `pytest -q` run was attempted. Collection stopped with **19 environment-related import errors** because this execution environment does not provide `supabase` and `streamlit`. No full-suite success claim is made.

## Scientific interpretation

Stage 6 does **not** constitute external expert validation. It makes the repository ready to conduct that validation prospectively and audibly.

No external performance number, expert agreement number, safety recall, or regulatory recall has been fabricated or inferred. Those numbers only become scientifically meaningful after genuine records are selected, qualified experts complete blinded labels, disagreements are adjudicated, and the frozen engine is run on the exact same records.
