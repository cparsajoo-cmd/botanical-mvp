# Final Reference-Grounded Validation v2 — Blind Run

Engine: 1.5.2
Run date: 2026-08-08

## Integrity
- 24 cases frozen before engine execution.
- Exactly 4 cases per final-decision class.
- No exact botanical+indication overlap with the 59 previously frozen cases found in the repository.
- Reference-defining sources were not supplied as the same test evidence records.
- No production code, rule, threshold, or expected label was changed after the blind run began.
- This set is now EXPOSED and can never be reused as an independent validation estimate.

## Result
- Accuracy: 0.208 (5/24)
- Macro-F1: 0.319
- Serious safety false negatives: 2
- Regulatory false negatives: 3
- Release gate: FAIL

## Per-class recall
- GO: 0.000
- GO WITH CAUTION: 0.000
- EXPERT REVIEW REQUIRED: 0.000
- NO GO SAFETY: 0.500
- NO GO REGULATORY: 0.250
- INSUFFICIENT EVIDENCE: 0.500

## Case results
- rgv2_001_ginkgo_dementia: GO -> INSUFFICIENT EVIDENCE (MISS)
- rgv2_002_pumpkin_bph: GO -> INSUFFICIENT EVIDENCE (MISS)
- rgv2_003_phyllanthus_stones: GO -> INSUFFICIENT EVIDENCE (MISS)
- rgv2_004_ruscus_cvi: GO -> INSUFFICIENT EVIDENCE (MISS)
- rgv2_005_hypericum_depression: GO WITH CAUTION -> INSUFFICIENT EVIDENCE (MISS)
- rgv2_006_urtica_bph: GO WITH CAUTION -> INSUFFICIENT EVIDENCE (MISS)
- rgv2_007_rosehip_oa: GO WITH CAUTION -> INSUFFICIENT EVIDENCE (MISS)
- rgv2_008_teatree_acne: GO WITH CAUTION -> INSUFFICIENT EVIDENCE (MISS)
- rgv2_009_soy_hotflush: EXPERT REVIEW REQUIRED -> GO WITH CAUTION (MISS)
- rgv2_010_moringa_t2dm: EXPERT REVIEW REQUIRED -> GO WITH CAUTION (MISS)
- rgv2_011_eleuthero_fatigue: EXPERT REVIEW REQUIRED -> INSUFFICIENT EVIDENCE (MISS)
- rgv2_012_cannabis_neuropathic: EXPERT REVIEW REQUIRED -> INSUFFICIENT EVIDENCE (MISS)
- rgv2_013_bacopa_alzheimer: INSUFFICIENT EVIDENCE -> INSUFFICIENT EVIDENCE (MATCH)
- rgv2_014_arnica_homeopathic: INSUFFICIENT EVIDENCE -> INSUFFICIENT EVIDENCE (MATCH)
- rgv2_015_calendula_radiation: INSUFFICIENT EVIDENCE -> GO WITH CAUTION (MISS)
- rgv2_016_eurycoma_ed: INSUFFICIENT EVIDENCE -> GO WITH CAUTION (MISS)
- rgv2_017_aconitum_oral: NO GO SAFETY -> NO GO SAFETY (MATCH)
- rgv2_018_datura_oral: NO GO SAFETY -> INSUFFICIENT EVIDENCE (MISS)
- rgv2_019_colchicum_oral: NO GO SAFETY -> NO GO SAFETY (MATCH)
- rgv2_020_belladonna_oral: NO GO SAFETY -> INSUFFICIENT EVIDENCE (MISS)
- rgv2_021_yohimbe_eu_food: NO GO REGULATORY -> NO GO REGULATORY (MATCH)
- rgv2_022_cbd_eu_food: NO GO REGULATORY -> GO WITH CAUTION (MISS)
- rgv2_023_acmella_eu_food: NO GO REGULATORY -> GO WITH CAUTION (MISS)
- rgv2_024_epimedium_eu_food: NO GO REGULATORY -> INSUFFICIENT EVIDENCE (MISS)

## Release blockers
- Accuracy=0.20833333333333334; require >= 0.80.
- Macro-F1=0.3192982456140351; require >= 0.75.
- GO precision=None; require >= 0.85.
- GO WITH CAUTION recall=0.0; require >= 0.75.
- EXPERT REVIEW REQUIRED recall=0.0; require >= 0.70.
- Serious safety false negatives=2; zero tolerated.
- Regulatory false negatives=3; zero tolerated.
- INSUFFICIENT EVIDENCE miss rate=0.500; require <= 0.20.

## Sanity-check / first divergence
The test transport was checked after the run without modifying the benchmark. For a representative strong-positive Ginkgo case, two independent systematic-review records reached the engine correctly, were classified at the systematic-review/meta-analysis hierarchy, and had complete structured-domain coverage. The scientific resolver nevertheless received governing directions=['unclear'] because ordinary efficacy language such as `more effective than placebo` and `confirmed efficacy` was not converted to a positive direction.

This demonstrates that the low result is not explained by a missing-dataframe-column or broken snapshot transport. It exposes a real remaining language-normalization/generalization problem in the Evidence Direction layer.

Safety and Regulatory also still have independent generalization misses in this fresh set, so Evidence Direction is not the only blocker.

## Interpretation
Engine 1.5.2 is NOT reference-grounded validated. The excellent performance on the previous exposed 24-case regression set did not generalize to this fresh benchmark.

Do not tune labels or snapshots in this directory. If remediation is performed, this v2 set becomes regression-only. Any new validity claim must use a newly frozen independent benchmark after a new engine version.
