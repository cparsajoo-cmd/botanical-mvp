# Gold Case correction report — Cases 008, 009, 010 and 012

Date: 2026-08-01

## Result

All four previously non-canonical cases were replaced with protocol-compatible reference-grounded cases. Each now uses `source_type="EMA_HMPC"`, production applicability, production precedence, one `SELECTED` outcome, and no EngineEvidenceInput leakage.

### Case 008
- Rebuilt from non-canonical hard-coded indication case to canonical EMA preparation-specification case.
- Domain: `PREPARATION_SPEC`
- Official source: EMA/HMPC/321097/2012
- Focused tests: 5/5 passed
- Resolution: SELECTED

### Case 009
- Replaced unrecognized Journal Article source_type with official EMA/HMPC mental-stress claim.
- Domain: `INDICATION_EVIDENCE`
- Official source: EMA/HMPC/310761/2013; monograph EMA/HMPC/196745/2012
- Focused tests: 5/5 passed
- Resolution: SELECTED

### Case 010
- Replaced unrecognized Journal Article source_type with official EMA/HMPC traditional-use claim.
- Domain: `INDICATION_EVIDENCE`
- Official source: EMA/275240/2014; monograph EMA/HMPC/669740/2013
- Focused tests: 5/5 passed
- Resolution: SELECTED

### Case 012
- Replaced unrecognized Journal Article source_type with official EMA/HMPC sleep claim.
- Domain: `INDICATION_EVIDENCE`
- Official source: EMA/HMPC/530968/2012; monograph EMA/HMPC/143181/2010
- Focused tests: 5/5 passed
- Resolution: SELECTED

## Regression

- Existing focused suites for Cases 003, 005, 006, 007 and 015 passed.
- Every active numbered Gold Case builder from 001 through 015 (excluding abandoned 002) now produces exactly one `SELECTED` resolved outcome.

## Important boundary

These files complete the reference-grounded Ground Truth layer. They do not fabricate independent engine evidence and do not claim whole-case engine agreement unless a separate engine-run artifact exists.