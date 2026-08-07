# Gold Corpus Recount + Extension 12

## Recount
The uploaded project was audited before construction.

Independent corpus records before Extension 12: **155**
Independent records after Extension 12: **167**

`human_evidence_direction_calibration_v1.json` is not counted as new evidence
because it re-aggregates already frozen human records.

Human direction balance before:
- positive: 28
- mixed: 24
- null: 15
- negative: 15

After Extension 12:
- positive: 28
- mixed: 24
- null: 21
- negative: 21

## Extension 12
12 newly verified PubMed records:
- 6 null
- 6 negative
- 0 PMID overlap with the 82 human-evidence PMIDs already present
- human-evidence unique PMID count rises to 94

## Current classifier measurement on these unseen records
- Overall: 3/12 = 25.0%
- Null: 2/6
- Negative: 1/6

No production tuning was performed against Extension 12.

## Remaining distance
Minimum corpus target: 180 independent records.
Current: 167.
Remaining to minimum: 13.

The next extension should therefore be selected by coverage gap, not simply by
adding another 12 human efficacy studies.
