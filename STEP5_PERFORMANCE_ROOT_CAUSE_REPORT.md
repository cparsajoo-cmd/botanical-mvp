# Step 5 Performance — Root Cause Report

## Request
Step 5 (Candidate Discovery, `discovery_mode="indication"` path) was running so long it was
unclear whether the system was working at all or had hung. Request: fix the performance issue
without changing any scientific information or the platform's overall structure.

## Method
Rather than guessing, an offline profiling harness was built (no live Supabase/OpenAI required)
using synthetic data at production scale: 2,100 candidate plants and 22,500 evidence records —
the same scale already referenced in the existing instrumentation in the code (the "Phase 2D
performance audit" comments). The existing instrumentation (`_perf`, `_section_add`) was then used
to measure the cost of each section directly.

## Confirmed root cause
Two loops in `indication_candidate_discovery.py` used `DataFrame.iterrows()`:

1. `_build_plant_evidence_index()` — over all 22,500 evidence rows.
2. The main per-plant loop in `discover_indication_candidates()` — over all 2,100 candidate plants.

`iterrows()` builds a full `pandas.Series` object (with its own index/dtype machinery) for every
single row, purely so the loop body can call `row.get(col)` a few times. That Series construction
— not the field reads themselves — was the measured dominant cost:

- `_build_plant_evidence_index`: **12.2 seconds** for 22,500 rows (measured directly, not
  estimated).

This is the exact same bug class already found and fixed once before in `run()` (the
`all_candidates.iterrows()` loop) — the same pattern was still present at these two other sites.

## What was deliberately NOT fixed
The remaining runtime (~45s out of ~62s in this benchmark) is spent in the actual scientific
classification functions: `_record_evidence_characteristics` (human/preclinical/hierarchy),
safety extraction (`extract_structured_safety_interactions` / `_extract_safety_details`),
`normalize_evidence_record`, and `validate_evidence_record`. These are scientific logic, not
engineering overhead, and were left untouched per your explicit instruction.

## Fix applied (purely mechanical, zero semantic change)
- `_build_plant_evidence_index()`: `frame.iterrows()` → `zip(frame.index, frame.to_dict("records"))`.
  `idx` is exactly the frame's original index (the fallback-index behavior in `_record_id` is
  unchanged).
- Main loop in `discover_indication_candidates()`: `candidates.iterrows()` →
  `candidates.to_dict("records")`. The only consumer of `item` is `engine._pick(item, [...])`,
  which only ever calls `.get(name, "")` — identical behavior on a dict and on a Series.
- Two `col in row.index` checks in `_record_text()` were changed to `col in row` — for a
  `pandas.Series`, `col in row` and `col in row.index` are exactly equivalent; this change only
  adds dict compatibility, it does not alter the Series-path behavior that was already in use.

No field, threshold, scoring rule, safety/regulatory gate rule, or scientific output changed —
only the pandas iteration mechanism.

## Result (measured, before/after)
| Section | Before | After |
|---|---|---|
| `_build_plant_evidence_index` (22,500 rows) | 12.232 s | 1.662 s (~7.4x) |
| `engine.run()` total (this synthetic benchmark) | ~62.2 s | ~52.0 s |

## Tests
- Full suite: **3172 passed, 3 xfailed, 0 failed** (no regressions).
- Directly related test files (`indication`, `step5`, `relevance`, `discovery`): **127 passed**.

## Delivered file
- `indication_candidate_discovery.py` (full file, the only file changed).

## Remaining honest caveat
This fix makes Step 5 more reliable and predictable (it's no longer ambiguous whether it's
"hung" or just slow — at least this part is no longer a bottleneck), but it does not make it
fast in the sense of a few seconds: most of the runtime is genuinely spent on per-record
scientific classification, which was left untouched. If you want to address that part too, it
needs an explicit decision on whether caching/vectorization without changing scientific logic is
acceptable there — that change carries more risk than this one and should get its own
architecture sign-off.
