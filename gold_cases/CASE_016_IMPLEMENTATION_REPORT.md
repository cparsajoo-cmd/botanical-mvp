# Gold Case 016 — Implementation Report

## Scope

- **Taxon:** *Piper methysticum* G.Forst. (Kava-kava)
- **Domain:** `REGULATORY_STATUS`
- **Assertion:** `PROHIBITION`
- **Assertion state:** `PRESENT`
- **Jurisdiction:** UK
- **Governing source type:** `NATIONAL_REGULATORY`

## Regulatory ground truth

The MHRA banned/restricted-herbal-ingredients guidance identifies The Medicines
for Human Use (Kava-kava) (Prohibition) Order 2002 (SI 2002/3170). It states
that Piper methysticum is not permitted in unlicensed medicines except those
exclusively for external use. The case therefore targets oral medicines and
preserves the external-use exception.

The case does **not** generalize this determination to foods, food supplements,
cosmetics, other countries, or external-use-only medicines.

## Architecture fit

- `ReferenceDomain.REGULATORY_STATUS`
- `AssertionType.PROHIBITION`
- `source_type="NATIONAL_REGULATORY"`, the highest-ranked source type for this domain
- applicability is evaluated against UK jurisdiction and oral route
- resolution result: `SELECTED`
- no Engine Evidence is constructed or inferred
- case remains unlocked and is not promoted to holdout

## Validation

- Case 016 dedicated tests: **8/8 passed**
- Active Case test files executed: **13/13 passed**
- No changes to production engine or validation architecture

## Files

- `gold_case_reference_grounded_016_piper_methysticum_regulatory_prohibition.py`
- `test_case_016_piper_methysticum_regulatory_prohibition.py`
- `case_016_source_record.json`
- `case_016_quality_record.json`
