# Case 015 Implementation Report

## Scope

- Taxon: *Hypericum perforatum* L.
- Plant part: herba
- Domain: `PREPARATION_SPEC`
- Assertion: `PREPARATION_SPECIFICATION`
- Assertion state: `PRESENT`

## Governing source

EMA/HMPC/7695/2021, final European Union herbal monograph on *Hypericum perforatum* L., herba, Revision 1, published 22 February 2023.

Source-grounded preparation specification:

> Dry extract (DER 3-7:1), extraction solvent methanol 80% (V/V)

Locator: section 2, well-established-use herbal preparation a, page 3/14.

## Validation

- Dedicated Case 015 tests: 8/8 passed
- Phase 1 baseline: passed
- Phase 1 regression: passed
- Mutation detection: 6/6 killed, 100%
- State transitions: passed
- Phase 1 exit code: 0

## Files

- `gold_case_reference_grounded_015_hypericum_perforatum_preparation_spec.py`
- `test_case_015_hypericum_perforatum_preparation_spec.py`
- `case_015_source_record.json`
- `case_015_quality_record.json`
