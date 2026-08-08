# Final Reference-Grounded Validation v1 — Blind Result

Engine version: 1.4.0
Benchmark: 24 frozen cases, 4 per six-class decision state.
Production rules changed during benchmark: NO.

## Result
- Accuracy: 0.375 (9/24)
- Macro-F1: 0.416
- Serious safety false negatives: 2
- Regulatory false negatives: 4
- Release gate: FAIL

## Per-class recall
- GO: 0.25
- GO WITH CAUTION: 0.5
- EXPERT REVIEW REQUIRED: 0.25
- NO GO SAFETY: 0.5
- NO GO REGULATORY: 0.0
- INSUFFICIENT EVIDENCE: 0.75

## Release blockers
- Accuracy=0.375; require >= 0.80.
- Macro-F1=0.41595238095238096; require >= 0.75.
- GO WITH CAUTION recall=0.5; require >= 0.75.
- EXPERT REVIEW REQUIRED recall=0.25; require >= 0.70.
- Serious safety false negatives=2; zero tolerated.
- Regulatory false negatives=4; zero tolerated.
- INSUFFICIENT EVIDENCE miss rate=0.250; require <= 0.20.

## Root-cause interpretation (no remediation performed during the blind run)

1. The engine remains over-conservative in some efficacy-positive cases: several reference GO/CAUTION cases are downgraded to CAUTION/INSUFFICIENT because evidence direction or body certainty is not recovered robustly from heterogeneous review wording.

2. Conflict recognition remains incomplete: only one of four EXPERT REVIEW cases was detected as such. The architecture can represent conflict, but the direction extraction feeding it still misses ordinary scientific negation/qualification language.

3. Two serious safety cases were missed. The underlying gate path still contains self-row handling that can turn a detected safety signal into NOT_EVALUABLE rather than a hard safety decision.

4. Regulatory generalization is the largest failure: none of four frozen NO GO REGULATORY cases were classified correctly. The production path recognizes some regulatory terms, but scope/context and self-row handling prevent a clear prohibition/restriction from consistently becoming NO GO REGULATORY.

5. The release failure is therefore structural, not a matter of needing more random cases. Engine 1.4.0 must not be described as reference-grounded validated.

## Integrity rule
This 24-case set is now exposed. It must NEVER be reused as a fresh/unseen validity estimate after remediation. It may only be used as a regression set. Any future validity estimate requires a new frozen set after a new engine version.
