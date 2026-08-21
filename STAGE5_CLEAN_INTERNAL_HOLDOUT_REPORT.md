# Stage 5 — Clean New Internal Holdout Readiness

## Scope

Stage 5 prepared a future `reference_grounded_validation_v4` (RGV v4) without changing the production decision architecture. No retrieval, evidence interpretation, scoring, ranking, hard safety gate, hard regulatory gate, eligibility rule, or final-decision policy was modified. `DECISION_ENGINE_VERSION` remains `1.10.2`.

## Scientific boundary

RGV v4 is **not yet a validation dataset and has not been run**. The repository now contains an empty case document and tooling only. No model-generated or platform-generated reference labels were created. Scientific reference labels must be established independently by qualified human/expert review and/or a separately established authoritative reference source before freeze.

## What was added

- A reusable RGV v4 case/schema validator that preserves the existing six-class decision vocabulary.
- A conservative leakage checker for exact historical case-context overlap and DOI/PMID/NCT overlap.
- Within-new-holdout duplicate DOI/PMID/NCT and explicit study-identity checks.
- Mandatory manual study-level overlap review for dependency that cannot be proven automatically.
- A write-once freeze tool that records SHA256 hashes, engine version, class distribution, and anti-overfitting rules.
- Automatic freeze rejection if reference-defining DOI/PMID/NCT identifiers also appear in the engine-input snapshot.
- A freeze-integrity and engine-version verifier.
- A guarded one-time RGV v4 execution runner that reuses the existing reference-grounded engine pathway and Stage 4 immutable provenance, rather than creating a second decision architecture.
- A write-once `FIRST_BLIND_RUN_RECORDED.json` marker after successful first execution; subsequent invocations are refused and the dataset is thereafter exposed/regression-only.
- A Stage 5 dataset-registry entry marking RGV v4 as `development` / `holdout_construction_only` until an actual independent freeze occurs.

## Current RGV v4 status

- Dataset status: `development`
- Cases: `0`
- Scientific reference labels: `0`
- Frozen: `no`
- Executed: `no`
- Independent performance estimate: `none`
- Engine target currently recorded in the template: `1.10.2`

This is intentional. A scientifically defensible holdout cannot be created by fabricating reference labels from the repository or from the model performing the implementation work.

## Required human/reference step before freeze

For every proposed case, an independent process must provide the final reference decision, rationale, authoritative/reference evidence provenance, and confirmation that the assessment was completed without seeing platform output. The engine-input snapshot must then be prepared separately, leakage checks must pass, and manual study-level overlap review must be completed.

## Leakage policy

The automated checker blocks:

- exact prior case-context overlap;
- historical DOI overlap;
- historical PMID overlap;
- historical NCT overlap;
- duplicate DOI/PMID/NCT within RGV v4;
- duplicate explicit `study_identity` within RGV v4.

It explicitly does **not** pretend that title similarity can prove study identity. Possible study-level relationships without stable shared identifiers remain a required manual review item. A systematic review is not automatically collapsed into an included RCT.

## Freeze policy

`freeze_internal_holdout_v4.py` refuses to freeze unless:

- at least one completed case exists;
- every expected label uses the existing six-class vocabulary;
- independent reference establishment is explicitly confirmed;
- expert/authoritative reference review is explicitly complete;
- reference rationale and evidence provenance are present;
- labels were not visible before the first engine execution;
- the dataset was not used for remediation;
- reference-defining evidence is declared excluded from engine input;
- automated identifier overlap checks pass;
- manual study-overlap review is complete;
- every engine-input snapshot exists;
- reference DOI/PMID/NCT identifiers do not reappear in the corresponding engine-input snapshot.

The freeze manifest is created with exclusive write semantics and cannot silently overwrite a previous freeze.

## One-time execution policy

`run_internal_holdout_v4.py` remains blocked until a valid freeze exists and the current engine version exactly matches the frozen engine version. It then uses the same `BotanicalRDCandidateEngine`, RGV row construction, final-decision mapping, decision metrics, release gate, high-risk metrics, and Stage 4 immutable provenance infrastructure already present in the repository.

After the successful first execution, it writes a write-once marker stating that RGV v4 is exposed and may subsequently be used only as regression data. A later rerun cannot be presented as another independent result.

## Tests executed

Focused Stage 5 tests:

- `9 passed, 0 failed`

Focused + Stage 3/4/holdout regression set:

- `115 passed, 0 failed`

Python syntax compilation for all Stage 5 Python files:

- passed

Full repository `pytest -q` was attempted. Collection stopped on 19 modules because the local execution environment lacks `supabase` and/or `streamlit`. These are environment/dependency limitations, not counted as passing tests and not claimed as code failures caused by Stage 5.

## What has improved vs what is validated

**Improved:** the repository now has a controlled, reproducible pathway for constructing, leakage-checking, freezing, integrity-verifying, executing once, and provenance-recording a genuinely new internal holdout.

**Scientifically validated by Stage 5:** nothing new. RGV v4 has no cases, labels, freeze, or result yet. Scientific validity will depend on the quality and independence of the future reference-label process and the subsequent one-time frozen execution.
