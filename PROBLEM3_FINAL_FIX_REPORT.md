# Problem 3 Final Fix Report

## Status
Problem 3 implementation is **FIXED, pending GitHub CI confirmation**.

## Root cause
`build_final_rationale()` previously allowed AI-generated `Evidence_Adjudication_Rationale` to become final scientific prose even when canonical verified evidence did not support the same quantity, strength, consistency, or direction claim.

## Final architecture
- Final efficacy-evidence wording is generated deterministically from canonical verified fields.
- `Outcome_Specific_Human_Evidence_Count` controls verified human-evidence quantity.
- `Final_Canonical_Evidence_Direction` is used only when its source is `VERIFIED`; otherwise the rationale stays conservative.
- Free-form `Evidence_Adjudication_Rationale` is not concatenated into the final rationale.
- Zero verified human evidence is described as insufficient verified evidence, never as evidence of inefficacy.
- One verified human study is explicitly described as one study and never upgraded to a consistent/strong body of evidence.
- Multiple verified studies can be described as multiple, but not automatically as proven/robust/established.
- Mixed/null/negative verified direction receives conservative direction-specific wording.
- Problem-2 gate-triggered wording is preserved exactly.
- Existing preparation, safety, commercial, and final-decision clauses remain downstream explanatory clauses.

## Independent review fixes added after Claude output
Two subtle fabrication paths were found and closed:
1. A negative verified-evidence rationale no longer invents the existence of positive mechanistic/AI signals merely to explain precedence.
2. The mere presence of free-form AI adjudication prose no longer causes the system to assert that mechanistic/indirect evidence exists. Only structured signal/count fields can trigger the neutral indirect-evidence clause.

## Tests
- Problem 3 + nearby Problem 2/safety regression: **113 passed**.
- Wider Problem 1 + Problem 2 + Problem 3 + shortlisting + adjudication + evidence transport + safety regression: **266 passed**.
- Production Python files compile successfully.

## Full-suite local limitation
A full local run hits a pre-existing order-dependent failure in the reconstructed Problem-2 baseline (`test_candidate_intervention_assertion_v1` persistence payload). The same failure occurs in the reconstructed Problem-2 baseline **without Problem-3 changes**, while the user's real GitHub Problem-2 baseline CI is already green. Therefore this local failure is not caused by Problem 3 and GitHub CI on the user's clean repository is the authoritative final confirmation.
