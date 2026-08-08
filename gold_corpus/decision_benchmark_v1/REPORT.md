# Decision Benchmark v1.0 — Leakage-Controlled Validation

**Development:** 7 existing cases previously used in remediation.  **Prospective holdout:** 15 existing cases not used in that remediation.

## Development result

Reference-curated agreement: **7/7 = 100.0%**.  This is not external expert agreement.

Macro-F1: **1.000**. Serious-safety FN: **0**; regulatory FN: **0**; false NO-GO: **0**; expert-review overuse: **0**; insufficient-evidence misses: **0**.

## Prospective holdout status

**UNSCORED.** No independent frozen E2E engine-evidence snapshot exists for these 15 cases. Using their GoldCase reference claims as engine evidence would leak the answer into the system and invalidate the holdout.

Reference-truth class distribution (for coverage audit only; not a model score):

- EXPERT REVIEW REQUIRED: 6
- GO: 5
- GO WITH CAUTION: 1
- INSUFFICIENT EVIDENCE: 3

## Blind expert adjudication

`blind_expert_adjudication_packet.csv/json` contains the 15 holdout case contexts and source excerpts, but deliberately omits engine outputs, resolved outcomes, and derived reference final decisions. Two reviewers can assign one of the six final-decision classes independently, followed by adjudication.

## Freeze rule

Do not modify the 15-case holdout membership after seeing engine results. Do not create or tune production rules from holdout failures. If a failure is found, diagnose it on development data or a new future validation cycle; preserve this v1 holdout result as historical evidence.
