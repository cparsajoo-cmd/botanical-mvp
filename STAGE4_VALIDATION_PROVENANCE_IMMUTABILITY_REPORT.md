# Stage 4 — Validation Provenance and Immutability

## Scope

Stage 4 changes only validation execution/provenance infrastructure. It does not modify the production decision pipeline, evidence scoring/ranking, evidence-direction resolver, study-linkage logic, hard safety gate, hard regulatory gate, non-compensatory eligibility, or final-decision policy. `DECISION_ENGINE_VERSION` remains `1.10.2`.

## Repository-grounded root cause

The repository already preserved some historical narrative reports, but execution provenance was not consistently immutable:

- `decision_holdout_v2.py` through `decision_holdout_v5.py` wrote reruns directly to each dataset's `results.json`.
- Decision Holdout v5 separately preserved its historical blind result (`3/10`, 30%) in `blind_run_historical_result.json`, while `results.json` currently contains the later post-remediation regression result (`8/10`, 80%). The distinction existed in prose/files but was not enforced by the runner.
- The RGV runner had previously been improved to version filenames, but its current documentation still described RGV v3 as a genuine blind holdout even though repository tests/comments document that the v3 output was inspected and v3 cases were subsequently used for remediation.
- No general append-only machine-readable execution registry existed.

## Implementation

### 1. Immutable run artifacts

`validation_provenance.py` adds a validation-only persistence helper. Every new execution receives a unique output under:

`gold_corpus/validation_runs/<dataset_name>/<timestamp>__engine-<version>.json`

Artifacts are opened with exclusive-create mode (`x`). An existing result can therefore not be silently overwritten.

### 2. Append-only execution registry

Each persisted execution appends one JSON object to:

`gold_corpus/validation_run_registry.jsonl`

The record contains:

- dataset name/version/status;
- engine version;
- git/repository identifier when available;
- UTC timestamp;
- whether labels were visible before execution;
- whether prior results had been inspected;
- whether the dataset was used for remediation (nullable when not established);
- run kind;
- overall result;
- per-class metrics;
- safety/regulatory metrics;
- immutable output path;
- historical blind-result path where available.

### 3. Claim-consistency guard

A run cannot be recorded as `independent_frozen` if labels were visible, prior results were already inspected, or the dataset was used for remediation. This makes a false independent-validation status fail closed at persistence time.

### 4. Known dataset-status catalog

`gold_corpus/validation_dataset_registry.json` records repository-supported status for:

- Reference-Grounded Validation v1, v2, v3;
- Decision Holdout v2, v3, v4, v5.

Historical unseen performance is kept separate from current permitted use. For RGV v3, no aggregate blind-result number is reconstructed because no finalized aggregate result artifact was located in the audited repository.

### 5. Existing runner hardening

`decision_holdout_v2.py` through `decision_holdout_v5.py` no longer write reruns to legacy `results.json`. New runs are explicitly persisted as regression/post-remediation executions.

`run_final_reference_holdout_v1.py` now treats v1/v2/v3 as exposed regression sets for all current executions. It no longer writes `blind_results_<tag>.json` or `release_gate_result_<tag>.json`. Its release-gate protocol also records that current reruns are not label-blinded and do not exclude remediation cases, preventing a rerun from presenting itself as a clean independent release validation.

## Historical result distinctions preserved

- RGV v1: historical blind agreement 37.5%; current use regression only.
- RGV v2: historical blind agreement 20.8%; current use regression only.
- RGV v3: frozen at engine 1.8.0, subsequently exposed/remediation-used; aggregate blind result not reconstructed.
- Decision Holdout v2: historical agreement 20%; current use regression only.
- Decision Holdout v3: historical agreement 40%; current use regression only.
- Decision Holdout v4: historical agreement 20%; current use regression only.
- Decision Holdout v5: historical blind agreement 30%; later post-remediation regression artifact 80%; these remain separate.

## Tests

Focused and relevant regression suite:

- `test_validation_provenance_stage4.py`
- `test_validation_risk_metrics_stage3.py`
- `test_scientific_validity_release_gate.py`
- `test_decision_holdout_v5.py`
- Stage 1 Evidence Direction regression
- Stage 2 study-linkage regressions
- final-decision authority
- regulatory authorization
- serious-safety regressions

Result: **69 passed, 0 failed**.

All changed Python files also passed `py_compile`.

A full `pytest -q` run was attempted. Collection stopped on 19 modules because this execution environment does not have the repository's `supabase` and `streamlit` packages installed. This is an environment limitation; the full suite is therefore **not claimed as passed**.

## Scientific interpretation

Stage 4 improves provenance integrity and prevents future reruns from overwriting or masquerading as historical independent results. It does **not** create new scientific validation evidence and does not improve historical benchmark scores. A new untouched holdout remains necessary for a new independent estimate of generalization.
