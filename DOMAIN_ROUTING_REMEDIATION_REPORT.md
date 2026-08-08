# Domain Routing Remediation Report

## Scope
Root-cause remediation only. No UI changes and no plant/case-specific production rules.

## Changes
1. Added explicit assessment-domain routing in `final_decision_policy.py` for:
   - therapeutic
   - preparation specification
   - identity/quality
   - safety
2. Preparation/identity-quality questions with usable domain evidence now route to `EXPERT REVIEW REQUIRED` rather than being forced through therapeutic efficacy GO/INSUFFICIENT logic.
3. Safety-domain questions with explicit interaction precaution or stronger interaction language route to `EXPERT REVIEW REQUIRED` unless a higher-priority hard NO-GO already applies.
4. `interaction_severity_classifier.py` now recognizes generic phrasing such as `advises caution ...` as precaution language instead of leaving it as mechanism-only.
5. The engine now passes the assessment domain and contributing evidence records into the final-decision policy.

## Regression cases fixed
- Case 007 Valeriana preparation: GO -> EXPERT REVIEW REQUIRED
- Case 008 Ginkgo preparation: GO -> EXPERT REVIEW REQUIRED
- Case 013 Echinacea identity/quality: INSUFFICIENT EVIDENCE -> EXPERT REVIEW REQUIRED
- Case 014 Ginkgo safety interaction: INSUFFICIENT EVIDENCE -> EXPERT REVIEW REQUIRED
- Case 015 Hypericum preparation: GO -> EXPERT REVIEW REQUIRED
- Case 017 Matricaria identity/quality: INSUFFICIENT EVIDENCE -> EXPERT REVIEW REQUIRED

All six now match their curated reference decisions.

## 15-case regression status
These 15 cases are no longer an independent holdout after remediation and are used only as regression fixtures.

- Before this remediation baseline: 5/15 correct (33.3%)
- After evidence transport + domain routing remediation: 11/15 correct (73.3%)
- Macro-F1 on this regression set: 0.68345
- Serious safety false negatives: 0
- Regulatory false negatives: 0
- False NO-GO: 0

Remaining mismatches:
- Case 003: GO WITH CAUTION -> GO
- Case 005: INSUFFICIENT EVIDENCE -> GO
- Case 011: GO -> INSUFFICIENT EVIDENCE
- Case 023: INSUFFICIENT EVIDENCE -> EXPERT REVIEW REQUIRED (reference refresh/adjudication concern already identified)

## Tests
- Focused remediation/interaction/decision tests: 65 passed.
- Broad suite collection still has the same 12 environment blockers because `supabase` / `streamlit` are unavailable in this sandbox.
- A historical Case 003 characterization test encodes pre-remediation evidence-transport behavior and is stale relative to the already-applied transport fix.
- `test_app_py_and_direct_production_modules_are_import_resolvable` remains order/state-sensitive in the aggregate suite but passes when run independently.
- Broad run reached 1755 passed, 3 xfailed before the known aggregate app-import failure; no domain-routing regression appeared before that point.

## Next root cause
Evidence Interpretation / uncertainty propagation for Cases 003, 005, and 011. Case 023 should be adjudicated against the newer conflicting evidence before production logic is changed for it.
