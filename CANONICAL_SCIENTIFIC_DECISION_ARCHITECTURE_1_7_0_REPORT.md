# Canonical Scientific Decision Architecture — Engine 1.7.0

## Why earlier validation cycled
The engine had multiple competing interpretation layers. Structured fields
(`Result_Direction`, `LLM_Result_Direction`, `Safety_Signal`, regulatory
metadata) existed, but final decision logic repeatedly re-read prose through
heuristics. Separately, earlier benchmark labels sometimes violated the
project's own certainty policy (for example, labeling one synthesis + one
trial as unconditional GO).

## Production architecture fixed

### 1. Canonical efficacy direction
Precedence is now:
1. source/connector `Result_Direction`
2. `LLM_Result_Direction`
3. legacy `Evidence_Direction`
4. text fallback only for legacy records

Body-of-evidence resolution consumes the canonical record direction rather
than independently reinterpreting the prose.

### 2. Structured extraction activation
A pre-existing reliable `Evidence_Level` no longer suppresses result-direction
extraction. If `Result_Direction` is missing and the optional extractor is
available, extraction runs without overwriting reliable connector evidence
level/type fields.

### 3. Canonical safety
LLM safety output is constrained to:
`Serious / Moderate / Reassuring / None / Unknown`.

Structured `Safety_Signal` maps directly into `SafetyAssertion` severity.
It no longer has to be rediscovered by the hazard-word vocabulary.

### 4. Regulatory authorization state
A new structured field is supported:
`Regulatory_Authorization_Status`.

Controlled states:
- authorized
- not_authorized
- pending
- denied
- terminated
- unknown

`not_authorized`, `denied`, and `terminated` are market-blocking only when
this structured field is supplied by an authoritative connector/source that
has already matched jurisdiction/product context. Absence of the field is
never interpreted as lack of authorization.

`pending` remains a restriction/review state rather than a silent CLEAR.

### 5. Structured Mixed evidence
A `Mixed` direction supplied by a structured source/extractor at the governing
evidence tier is treated as material scientific conflict and routes to
`EXPERT REVIEW REQUIRED`.

A legacy text-fallback "mixed" classification is not automatically promoted to
a hard conflict, preserving backward compatibility and avoiding over-triggering
from heuristic wording.

## Reference-label rubric frozen
`gold_corpus/scientific_validity/REFERENCE_DECISION_RUBRIC_V1.json` separates
benchmark adjudication rules from production code.

Key rules:
- GO requires genuinely high body-level certainty.
- A single supportive synthesis normally maps to GO WITH CAUTION, not GO.
- EXPERT REVIEW requires material conflict; uncertainty alone is not conflict.
- INSUFFICIENT means no defensible demonstrated benefit without material
  opposing evidence.
- serious applicable safety and current marketability blockers remain hard stops.

This prevents future benchmarks from moving the scientific goalposts to fill
six classes.

## Tests
Focused evidence / decision / safety / regulatory / E2E regression:
214 passed, 0 failed.

## Exposed diagnostic — NOT independent validation
The previous v2 set was reused only to isolate architecture after its labels
and evidence were already exposed.

With structured assertions and the fixed authorization state, the initial
rubric diagnostic was 23/24 (95.8%). Safety was 4/4 and Regulatory was 4/4.
The remaining Soy case sits on a genuine adjudication boundary: one
systematic review is positive and another is structured as Mixed/inconclusive.
Engine 1.7.0 sends structured governing-tier Mixed evidence to Expert Review.
No production change was made to force that case to match a chosen label.

This 95.8% number is not a validation accuracy and must never be presented as
one.

## Remaining scientific validity question
The downstream decision architecture is now structurally coherent, but the
live `llm_extractor.py` itself has not been independently measured here because
this execution environment does not have the project's live OpenAI API secret.

Therefore the next meaningful test is NOT another downstream holdout.
It is a frozen extraction benchmark that measures whether live structured
extraction assigns `Result_Direction` / `Safety_Signal` correctly from unseen
source text. Only after that extraction layer passes should one final complete
reference-grounded end-to-end holdout be run.

## Version
1.5.2 -> 1.7.0
