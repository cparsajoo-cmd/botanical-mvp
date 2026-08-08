# Pharmaceutical Safety Hardening — Before / After

| Area | Before | After |
|---|---|---|
| Explicit contraindication | SERIOUS only when recognized high-risk drug class also detected | Explicit contraindication itself is a structured SERIOUS assertion |
| Pregnancy/lactation/pediatric/organ context | Mostly soft vocabulary / indirect flags | Structured assertion taxonomy with population/risk type |
| CYP/P-gp | Keyword/interaction flags; serious only in narrow combinations | Mechanism-only assertions explicitly non-blocking; clinical interaction assertions separately graded |
| Gate input | Safety flags / hard-term intersection | Structured assertion severity feeds SafetyFinding; legacy terms retained for compatibility |
| Evidence conflict | Pooled text could effectively collapse signals | Risk + reassurance assertions retained simultaneously; conflict exposed |
| Confidence | Safety gate primarily categorical | Independent High/Moderate/Low/Insufficient safety confidence |
| Authority | EMA/WHO/ESCOP plus generic literature tiers; FDA/HC/TGA/guideline not distinct | FDA, Health Canada, TGA and Clinical Guideline added to shared authority policy |
| Traceability | Evidence IDs + gate reason | Evidence ID + exact sentence + assertion + authority/confidence + severity rule + gate |
| Multi-compound merge | Safety flags merged but authoritative eligibility could stay inherited from best row | Assertions merged and eligibility fields recomputed across all sub-rows |
| False-positive control | Existing negation handling | Reassurance polarity, protective-toxicity exclusion, mechanism-only non-blocking retained |
| Pharmaceutical-grade status | Not sufficient | Materially hardened, but still blocked by candidate-specific applicability, dose/route normalization, formal conflict synthesis, and vocabulary-bounded extraction |

## Tests added

`test_pharmaceutical_safety_engine.py` adds adversarial coverage for:

- pregnancy contraindication without drug-class whitelist;
- live-engine non-pass behavior;
- conflict retention;
- authority affecting confidence but not semantic severity;
- protective hepatotoxicity context false-positive prevention;
- CYP mechanism-only non-blocking behavior;
- full safety explainability trace;
- FDA / Health Canada / TGA / clinical-guideline authority separation.

An obsolete regression expectation that “contraindicated in pregnancy” free text must pass the safety gate was intentionally replaced because that behavior is incompatible with the current pharmaceutical-safety requirement.
