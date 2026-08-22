# External Expert Validation v1 — Prospective Protocol

## Purpose

This folder supports a future external expert validation study. It does **not** contain completed scientific validation and does not create ground truth automatically.

## Core design

- Select approximately **30–50 genuine evidence records** before platform evaluation.
- Freeze the exact records and source text presented to experts and the platform.
- Use at least **two independent qualified experts**.
- Experts must be **blind to platform output** while labeling.
- Expert A and Expert B must label independently; their original files are preserved unchanged.
- Resolve disagreements using a predefined third-expert or adjudication procedure.
- Run the platform on the **same frozen records**, with the exact engine version recorded.
- Compare platform output with the adjudicated reference at field level.
- Report serious-safety and regulatory false negatives separately, with denominators.
- After results are inspected, the dataset is exposed. If it is used for remediation, all later runs are regression runs and must never be represented as a new independent validation.

## Fields assessed

The study deliberately reuses existing production concepts rather than adding new scoring dimensions:

- `evidence_direction`: positive / negative / null / mixed / unclear
- `study_design`: existing `evidence_interpretation.py` taxonomy
- `evidence_quality`: high / moderate / low / unknown
- serious-safety signal: represented by `serious_safety_evaluable` plus a boolean `serious_safety_signal`
- regulatory blocking signal: represented by `regulatory_evaluable` plus a boolean `regulatory_block_signal`

The boolean risk fields are validation observations, not new production taxonomies or scoring inputs.

## Required order

1. Select records independently of platform output.
2. Check historical DOI/PMID/NCT overlap and perform manual study-level overlap review.
3. Populate `evidence_records.json` with 30–50 traceable genuine records.
4. Freeze with `freeze_external_expert_validation_v1.py`.
5. Give the frozen packet to Expert A and Expert B separately.
6. Preserve both original expert label files.
7. Adjudicate disagreements and create the consensus reference file.
8. Run the platform on the exact frozen records while reference labels remain hidden from the platform execution process.
9. Populate the platform-output artifact with the exact engine version.
10. Score once with `score_external_expert_validation_v1.py`.
11. Inspect/report the result. From this point the dataset is exposed; if remediation follows, the dataset is regression data.

## What the tooling refuses to claim

A high agreement value on 30–50 records is evidence about that frozen study sample. It is not universal clinical validation, not calibrated probability validation, and not proof that all safety or regulatory cases will be detected. A risk category with zero reference-positive cases is **not evaluable**, not a successful zero-false-negative result.
