# RGV v4 — Clean Internal Holdout Selection Protocol

## Status

**NOT YET A VALIDATION DATASET.** This directory contains tooling and an empty schema only. No model-generated or platform-generated scientific ground truth is permitted.

## Purpose

RGV v4 is the next candidate internal reference-grounded holdout after RGV v1/v2/v3 and Decision Holdout v1-v5 became exposed. It may provide a new internal independent estimate only if every requirement below is satisfied before the first engine execution.

## Required sequence

1. Select fresh botanical/indication contexts without consulting platform output for those cases.
2. Build the reference corpus independently of the platform retrieval output.
3. Establish the expected six-class final decision using qualified independent review and/or separately established authoritative reference sources.
4. Record source provenance, DOI/PMID/NCT identifiers where available, and an explicit study identity when known.
5. Prepare the exact engine-input evidence snapshot separately from the reference-defining evidence. Reference-defining evidence must not be injected merely to make the engine agree with the label.
6. Run `check_internal_holdout_v4_leakage.py` against all historical repository validation material.
7. Complete manual study-level overlap review for relationships that cannot be proven from DOI/PMID/NCT alone.
8. Freeze cases, labels, and input snapshots with `freeze_internal_holdout_v4.py` while the engine remains at the recorded version.
9. Verify the freeze immediately before execution with `verify_internal_holdout_v4_freeze.py`.
10. Perform exactly one blind engine run with `run_internal_holdout_v4.py`. It reuses the existing reference-grounded engine pathway, persists the result immutably through `validation_provenance.py`, and writes a one-time exposure marker.
11. As soon as the output is inspected, mark RGV v4 exposed. If any case informs remediation, its permitted use is regression only. A later rerun is not another independent validation.

## Overlap rules

A proposed case is rejected before freeze when any of the following is found:

- exact prior case-context overlap;
- DOI overlap with historical validation material;
- PMID overlap;
- NCT overlap;
- repeated explicit `study_identity` inside the new holdout;
- obvious underlying-study overlap identified during manual review.

A systematic review is not automatically a duplicate of its included trials. Its dependency must be documented, not silently discarded.

## Reference-label requirements

Every frozen case must contain:

- one existing final-decision label from the platform's six-class vocabulary;
- `reference_established_independently_of_platform_output = true`;
- `expert_or_authoritative_reference_review_complete = true`;
- a written reference rationale;
- independently selected reference evidence with stable identifiers/locators;
- a frozen engine-input snapshot;
- no prior exposure of the expected label to the engine/team responsible for the blind execution.

## Scientific claim boundary

Passing RGV v4 would be evidence of internal performance on one frozen benchmark. It would **not** constitute clinical validation, regulatory approval, or external expert validation of the platform.
