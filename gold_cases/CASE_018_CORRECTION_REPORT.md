# Case 018 Correction Report

## Corrected interpretation

The MHRA Schedule 20 Part 2 values of **600 mg maximum dose** and **1800 mg maximum daily dose** are not an absolute ban on higher-dose products. They define the limits for supply following a one-to-one consultation with a practitioner outside registered pharmacy premises. If either threshold is exceeded, the herbal medicine may only be supplied from registered pharmacy premises by or under pharmacist supervision.

## File corrections

- Reframed the claim as a supply-channel restriction.
- Preserved the exact 600 mg / 1800 mg thresholds.
- Removed unsupported `population="General population"`.
- Documented the platform mapping from source term `internal use` to route `Oral`.
- Replaced `RiskStratum.CLEAN_BASELINE` with an empty risk-strata list.
- Added tests preventing future reinterpretation as an absolute maximum or prohibition.

## Governing source

MHRA, *Banned and restricted herbal ingredients*, Human Medicines Regulations 2012, Schedule 20 Part 2. The guidance states that Part 2 plants may be supplied after one-to-one practitioner consultation at or below the listed dose, and that products exceeding the threshold require registered-pharmacy supply under pharmacist supervision. The Ephedra row lists 600 mg (MD) and 1800 mg (MDD).

## Validation

- Builder: successful
- Case tests: 9/9 passed
- Outcome: `SELECTED`
- Assertion: `RESTRICTION / PRESENT`
- Engine evidence: empty
- Locked: false
