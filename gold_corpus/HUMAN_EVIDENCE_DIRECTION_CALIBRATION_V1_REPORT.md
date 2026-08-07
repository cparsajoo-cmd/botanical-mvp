# Human Evidence Direction Calibration V1

## Integrity correction

The previous Extension 01 contained 5 PMIDs already present in the original 12-record benchmark.
Those duplicates were removed before any combined calibration score was accepted.

Extension 01 is now fully disjoint from the original benchmark:
- original PMIDs: 12 unique
- extension PMIDs: 12 unique
- overlap: 0
- combined calibration set: 24 unique PubMed records

## Corrected Extension 01 baseline

- Direction accuracy: 0/12 = 0.0%

## Frozen combined calibration V1

- Direction accuracy: 3/24 = 12.5%

By direction:
- Positive: 1/6
- Null: 2/5
- Negative: 0/7
- Mixed: 0/6

## Governance

This 24-record set is frozen before any production calibration change.
No production phrase table, score, safety rule, regulatory rule, market rule, or Gold Case truth was changed.

The next phase, if authorized, may change the production direction classifier, but it must be evaluated against this frozen V1 set without changing its labels.
