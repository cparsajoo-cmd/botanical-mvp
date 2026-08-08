# Regulatory Constituent Matching Generalization Fix — Engine 1.5.2

## Root cause
The 1.5.1 numeric regulatory comparator correctly stopped using the first arbitrary quantity in candidate text, but it still assumed the regulated constituent name appeared after the numeric limit (for example `800 mg Compound-X`). Common regulatory grammar also places the entity before the comparator (`Compound-X shall not exceed 800 mg`). Parenthetical aliases could also prevent matching a full source name to an abbreviated candidate declaration.

## Fix
- Constituent extraction is now bidirectional: before or after the numeric comparator.
- Generic parenthetical aliases are captured without hard-coded compound names.
- Candidate quantity lookup remains constituent-specific and supports quantity before or after the constituent.
- Parsing stops at regulatory/dose clause words such as `per`, `is`, `are`, `shall`, `permitted`, and `prohibited`, preventing greedy entity capture.
- Existing strict/inclusive boundary semantics are unchanged.

## Adversarial coverage
Examples now correctly handled:
- `Compound-X shall not exceed 800 mg` + `900 mg Compound-X` -> violation.
- `The amount of Compound-X shall not exceed 50 mg` + `60 mg Compound-X` -> violation.
- `less than 800 mg Long-Compound-Name (LCN)` + `900 mg LCN` -> violation.
- Multiple unrelated quantities do not interfere.
- `less than 800 mg` keeps 800 as a violation.
- `no more than 800 mg` keeps 800 compliant.

## Tests
Relevant Regulatory/Eligibility/E2E regression: 163 passed, 0 failed.

The full local pytest collection could not start because this runtime lacks `supabase` and `streamlit`; 14 test modules fail during import for those missing dependencies. This is an environment collection limitation, not a logical failure from this patch.

## Version
Decision Engine: 1.5.1 -> 1.5.2.
