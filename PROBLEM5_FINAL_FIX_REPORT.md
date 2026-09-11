# Problem 5 — Final verification report

Status: **FIXED / awaiting clean GitHub CI confirmation**

## Root cause
The existing botanical-level `Outcome_Specific_Human_Evidence_Count` correctly remained preparation-agnostic, but no authoritative record-level subset was required to match the requested preparation and route before an actionable product-form recommendation could survive.

## Architecture retained
- `Outcome_Specific_Human_Evidence_Count` keeps its Problem-2 meaning: verified, candidate-specific, outcome-specific HUMAN evidence, regardless of formulation.
- `Verified_Formulation_Compatible_Outcome_Specific_Human_Evidence_Count` is the additive formulation-aware subset.
- Compatibility reuses the existing per-record `Dimension_Status` produced by `evaluate_applicability()`; no second formulation ontology was introduced.
- Problem 1 attribution, Problem 2 human-evidence sufficiency, and Problem 3 rationale authority remain unchanged in authority/order.

## Final audit fixes added after Claude
1. An existing hard `plant_part=MISMATCH` now prevents a record from being called directly formulation-transferable even when preparation and route match.
2. The legacy/no-`Dimension_Status` fallback now respects an explicit requested route and fails closed when the evidence route is missing or different. It also refuses an explicit known plant-part mismatch without creating a new plant-part ontology.
3. Rationale wording now derives the formulation state from the evidence counts themselves, not only from whether the Problem-5 gate happened to be the gate that changed the final status. Therefore a candidate already made non-actionable by another applicability gate still reports that its verified human evidence is formulation-mismatched.
4. When some verified human studies match the requested preparation/route and others do not, the rationale explicitly reports the compatible subset and labels the remainder transferability-limited rather than implying that all verified studies directly support the requested product form.

## Decision behavior
- Zero verified human evidence: Problem 2 remains authoritative.
- Verified human evidence exists but zero formulation-compatible verified human records: an otherwise actionable product-form recommendation is blocked to `EXPERT REVIEW REQUIRED`; genuine safety/regulatory NO-GO statuses remain untouched.
- At least one compatible verified human record: Problem 5 does not itself force GO; existing downstream logic continues normally.
- Mismatched records remain available as botanical-level / transferability-limited evidence; they are not deleted.

## Verification
- Production modules compiled successfully.
- Problem 5 + Problems 2/3 + changed decision/safety regression set after final audit fixes: **172 passed, 0 failed**.
- Independent post-Claude cases additionally verified:
  - hard plant-part mismatch blocks direct formulation support;
  - legacy explicit route mismatch blocks direct formulation support;
  - mismatch rationale is emitted even when another gate already made the row non-actionable;
  - mixed compatible/incompatible verified-human evidence reports the compatible subset explicitly.

A reconstructed historical repository copy contains several older tests/files that are not identical to the user's already-green current GitHub branch, so a full local repository result from that reconstruction is not a reliable CI-equivalent. The clean GitHub Actions run on the current branch is the final full-suite confirmation.
