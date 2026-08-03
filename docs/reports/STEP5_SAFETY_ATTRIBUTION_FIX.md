# Step 5 conservative safety / interaction attribution fix

This change replaces broad keyword matching with conservative, plant-attributed extraction.

## What is accepted

- An adverse event explicitly attributable to the candidate plant/intervention.
- A reassurance statement such as `well tolerated` or `no serious adverse events`, stored separately.
- A drug interaction only when the same attributed sentence contains both an explicit interaction relation and a drug/drug-class object.

## What is rejected

- General statements about synthetic or conventional drugs.
- Adverse effects belonging to a comparator, disease, treatment class, or another botanical.
- Protective or negated toxicity language such as `protects against liver injury` or `not toxic`.
- Promotional, affiliate, customer-review, or retracted source text.
- A drug name alone without an explicit interaction relationship.

## New auditable fields

- `Safety_Reassurance`
- `Safety_Data_Status`

`Safety_Flags` now contains only attributable adverse-event statements. Absence of an accepted statement is not interpreted as evidence of safety.

## Scope

Changed only the safety/interaction extraction and Step 5 aggregation path. Candidate discovery, evidence collection, normalization, validation, scoring weights, database migrations, reports, and compound-substitution mode were not redesigned.
