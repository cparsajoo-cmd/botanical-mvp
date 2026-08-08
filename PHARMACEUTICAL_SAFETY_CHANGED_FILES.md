# Changed Files — Pharmaceutical Safety Hardening

## Production code
- `safety_assertion_engine.py` — new structured SafetyAssertion taxonomy/classifier/conflict/confidence model.
- `botanical_rd_candidate_engine.py` — structured assertion wiring, record-level provenance, hardening of serious contraindications, merge-safe eligibility recomputation, new safety outputs.
- `eligibility_gate.py` — SafetyFinding now consumes structured assertions and carries confidence/conflict/severity-rule metadata.
- `evidence_authority.py` — FDA, Health Canada, TGA and Clinical Guideline authority tiers added.
- `decision_explainability.py` — assertion-to-gate causal trace and severity-rule attribution.

## Tests
- `test_pharmaceutical_safety_engine.py` — new adversarial pharmaceutical-safety tests.
- `test_gold_case_execution.py` — obsolete “pregnancy contraindication must pass” expectation replaced by fail-closed expectation.
- `test_gate_layer.py` — additive output-contract count updated for four new structured safety fields.
- `test_task5_sensitivity_analysis_activation.py` — output-contract count updated for four new structured safety fields.

## Reports
- `PHARMACEUTICAL_SAFETY_AUDIT.md`
- `PHARMACEUTICAL_SAFETY_BEFORE_AFTER.md`
- `PHARMACEUTICAL_SAFETY_CHANGED_FILES.md`
