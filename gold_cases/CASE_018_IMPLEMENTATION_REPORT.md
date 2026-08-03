# Case 018 Implementation Report

## Scope

- Taxon: *Ephedra sinica* Stapf
- Domain: `REGULATORY_STATUS`
- Assertion: `RESTRICTION`
- State: `PRESENT`
- Jurisdiction: UK
- Route: Oral/internal use

## Governing source

UK MHRA, **Banned and restricted herbal ingredients for medicinal use**, implementing Human Medicines Regulations 2012, Schedule 20, Parts II and III.

The official table names *Ephedra sinica* and states a maximum single dose of **600 mg** and maximum daily dose of **1800 mg** for internal use.

## Architectural value

Case 018 complements Case 016:

- Case 016 tests a regulatory `PROHIBITION`.
- Case 018 tests a regulatory `RESTRICTION` with quantitative dose limits.

This is the first Gold Case to exercise `AssertionType.RESTRICTION` in `ReferenceDomain.REGULATORY_STATUS`.

## Validation

- Dedicated tests: 8/8 passed.
- Applicability: applicable.
- Resolution: `SELECTED`.
- Ground Truth remains leakage-free: no EngineEvidenceInput, unlocked, not promoted to holdout.
