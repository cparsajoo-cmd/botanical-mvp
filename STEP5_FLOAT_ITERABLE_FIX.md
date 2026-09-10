# Step 5 float-iterable live-demo fix

Root cause hardened in this patch:

- Cached/legacy evidence-ID fields used by AI adjudication can arrive as scalar `NaN`/float values instead of list values.
- Downstream adjudication logic used set/list/len operations on those fields, which can raise `TypeError: 'float' object is not iterable` after the scientific shortlist has already been computed.
- The scientific shortlist was persisted too late, so a downstream adjudication/reporting exception could leave the UI showing `Scientific shortlist — 0 plant(s)` even though deterministic scoring had succeeded.

Changes:

1. `evidence_adjudication_engine.py`
   - Normalizes all evidence-ID collection fields before iteration.
   - Treats NaN/empty scalar values as an empty ID list.
   - Tolerates one legacy scalar ID without crashing.
   - Hardens calibration of direct-human ID fields.

2. `step_rd_candidates.py`
   - Safely counts evidence IDs regardless of list/scalar/NaN shape.
   - Wraps AI evidence adjudication as an optional downstream layer so it cannot discard the deterministic shortlist.
   - Persists the deterministic shortlist immediately after finalization, before AI/report layers.
   - Wraps report/explainability enrichment so a malformed optional field cannot turn a valid Step-5 run into zero candidates.

The scientific scoring/gating formulas are not changed by this patch.
