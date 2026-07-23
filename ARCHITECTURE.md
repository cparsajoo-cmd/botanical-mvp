# Architecture — Botanical Product Intelligence Platform

Last updated: Phase 7 (repository cleanup), verified against the actual
codebase by automated import-reachability analysis, not written from
memory. If this file and the code ever disagree, the code is right —
re-run the verification method described at the bottom before trusting
either.

## The one real pipeline

Streamlit auto-loads `app.py` as the main entrypoint, plus every file
under `pages/` as separate, independently-loaded pages. These are the
ONLY two ways code in this repository actually runs in production.

```
app.py
 ├─ step_inputs.py            (Step 0: indication/dosage form/market)
 │   └─ regulatory_frameworks.py
 ├─ step_question.py          (Step 1: question understanding)
 │   └─ ai_discovery_engine.py
 │       └─ seed_data.py
 │           └─ schema.py (local SQLite — see "Known oddities" below)
 ├─ step_evidence.py          (Step 2: live evidence collection)
 │   └─ research_engine.py
 │       ├─ multi_source_collector.py  (+ per-source connectors, see below)
 │       ├─ global_candidate_ranking_engine.py  (fallback candidate list only)
 │       └─ botanical_rd_candidate_engine.py    (see Step 5, same engine)
 ├─ step_rd_candidates.py     (Steps 3-6: market landscape, existing
 │                              knowledge, R&D discovery, final recommendation —
 │                              one file implements all four UI steps
 │                              deliberately, not a missing-file gap: they
 │                              share the same cached engine instance and
 │                              session state, and splitting them into
 │                              separate files would mean either duplicating
 │                              that shared state or adding cross-file
 │                              plumbing for no functional benefit)
 │   └─ botanical_rd_candidate_engine.py
 │       ├─ concentration_normalizer.py       (Phase 4)
 │       ├─ evidence_hierarchy_classifier.py  (Phase 4)
 │       ├─ negative_evidence_classifier.py   (Phase 4)
 │       ├─ evidence_confidence.py            (Phase 6)
 │       ├─ decision_class_ah.py              (Phase 6)
 │       ├─ global_plant_candidate_database.py
 │       ├─ compound_occurrence_map.py
 │       └─ (per-source connectors — pubmed, europepmc, clinicaltrials,
 │           chembl, chebi, pubchem, dailymed, fda, openfda, crossref,
 │           openalex, semantic_scholar, livertox, patent, ema_regulatory,
 │           regulatory)
 ├─ step_import_data.py       (optional: manual data import)
 │   └─ supabase_client.py
 └─ evidence_database.py      (Supabase evidence_records preview)
     └─ database.py
         └─ supabase_client.py

pages/Bulk evidence.py         (SEPARATE from the Step 0-6 flow — manually
                                 triggered, not part of app.py's own run)
pages/Diagnostic.py             (debug-only; removed before investor demos)
pages/Plant_Profile.py
pages/Source_Ingestion.py
```

**BotanicalRDCandidateEngine is the one central R&D decision engine.**
It's instantiated in two places (Step 2's research_engine.py, for
candidate-plant selection only, and Step 5's step_rd_candidates.py, for
the actual scoring/decision output the user sees) but there is only
ONE implementation of the scoring/decision logic itself — the
duplicate parallel scoring system that used to run in Step 2
(decision_engine.py + friends) was removed in Phase 2, not fixed,
because nothing downstream ever read its output.

## Data flow, in one sentence per stage

1. **Step 0** — user picks indication (still a fixed selectbox, not
   free-text — a known open item, audit 4.1) / dosage form / target
   market. As of this session, indication/dosage_form/market can ALSO
   be pre-filled from a free-text question (`free_text_question_parser.py`,
   keyword/phrase matching against the same selectbox vocabularies —
   not a trained NLU model, see that file's own docstring for the
   honesty caveats) — the selectboxes themselves are unchanged and
   remain the actual source of truth; free text only pre-fills them.
   `question_understanding_engine.py` (previously imported nowhere,
   flagged across 3 external reviews) is now called from step_inputs.py
   to build a "Standardized Project Definition" (route, product type,
   regulatory focus, evidence requirements) surfaced in Step 0's UI and
   in the final report.
2. **Step 1** — question UNDERSTANDING (matching a free-text question to
   a known indication/dosage form/market) now has a real implementation
   (see Step 0 above) — but question ANALYSIS in this step still pulls
   targets/keywords from hardcoded seed data (`seed_data.py`'s
   `TARGET_DISEASES`/`COMPOUND_TARGETS`), not live-extracted from
   evidence. That distinction — recognizing WHAT the question is about
   vs. reasoning about WHICH targets/mechanisms are actually relevant —
   is still only solved for the first half.
3. **Step 2** — live evidence collection, per candidate plant, saved to
   Supabase's `evidence_records` table. Runs a SMALL number of results
   per source (`max_results: 5` in `source_registry.py`) — full bulk
   coverage only happens on the separate `pages/Bulk evidence.py` page,
   manually triggered, not part of this flow.
4. **Steps 3-6** — `BotanicalRDCandidateEngine.run()`: loads
   `plant_compounds`/`compound_profiles`/`scientific_evidence` from
   Supabase, cross-references against the reference plant/compound,
   scores every candidate, classifies it, and returns the final table.

## Known oddities (verified, not fixed — flagging so nobody "rediscovers" them)

- **A local SQLite database (`schema.py`, `botanical_platform.db`)
  is still in the active import chain**, via `seed_data.py`. It
  coexists with Supabase (the actual production data store) rather
  than replacing it. Nothing currently breaks because of this, but
  it's a second, unused-in-practice persistence layer worth removing
  in a future pass.
- **Retail product search is a stub** (`_search_retail_products()`
  literally returns `"Not implemented"`); **patent search** only
  activates with `EPO_OPS_KEY`/`EPO_OPS_SECRET` set. This is why
  `_market_status()` (Phase 5) defaults to `"Search not performed"`
  rather than claiming a real search ran.
- **`pages/Bulk evidence.py` is not part of the Step 0-6 flow.** It's
  a separate Streamlit page a user has to navigate to manually — full
  evidence coverage is opt-in, not automatic.

## Legacy files (identified, NOT yet moved to `archive/` — see status below)

**Current status, corrected (external review caught this drift): the
archive/ directory does not exist yet in this repository.** An earlier
version of this file claimed "67 legacy files were moved to archive/"
— that was aspirational/future-tense written as if already done, and
it wasn't. The 66 files below are still sitting in the repo root as of
this writing.

**⚠️ CRITICAL BUG FOUND AND FIXED (this revision) — read before ever
running the archive workflow.** `.github/legacy-files.txt` listed
`question_understanding_engine.py` as safe to archive, but a later
session (after the original 67-file list was generated) wired it into
production — `step_inputs.py` actively imports
`standardize_project_definition` from it. The static list was never
re-validated after that change. Had the archive workflow been run in
that state, it would have moved a live production dependency into
`archive/` and broken the app. `question_understanding_engine.py` has
been removed from the list (66 files remain, all individually
re-confirmed safe — see below), and the underlying process gap is now
closed structurally, not just patched once:
- `repo_dependency_audit.py` — a real, reusable tool (not an ad-hoc
  snippet) that recomputes the production/test/legacy classification
  fresh, every time it's run.
- `test_production_dependency_integrity.py` — runs that same check as
  a normal pytest test, so `pytest -q` (which every PR/CI run already
  executes) catches this class of drift automatically, not only when
  someone remembers to re-run a manual script.
- `archive-legacy.yml` now calls `repo_dependency_audit.py validate`
  as its FIRST step, before touching any file, and fails the whole job
  if anything listed is actually reachable from production.

66 files were confirmed — by `repo_dependency_audit.py`, run fresh
against the current codebase (not by trusting the original Phase 1/7
snapshot) — to be unreachable from `app.py` and every file under
`pages/`. Each was a superseded/duplicate engine, an old Step from
before the Step 0-6 consolidation, or a connector that was never wired
in. The full list is in `.github/legacy-files.txt`.

**To actually move them:** go to the repo's Actions tab, select
"Archive legacy files (Phase 7)", and click "Run workflow" (see
`.github/workflows/archive-legacy.yml` — it already exists and is
ready to run, it just hasn't been triggered yet). It now validates the
list itself before moving anything (see above), and runs both the
production smoke test and the full suite after moving, before
committing. After it runs, still verify by hand:
- `archive/` exists and contains the 66 files
- `archive/ARCHIVED_FILES.md` was generated
- `pytest -q` still passes
- Update this section of ARCHITECTURE.md to say "moved" only once
  that's actually confirmed true — do not restate it as done from
  intent alone again (this is the exact mistake that caused the
  "moved to archive/" claim to go stale the first time).

Files that `repo_dependency_audit.py` also flags as "not reachable
from production" but that should NOT be included in the archive list,
because unreachable-from-app.py isn't the same as legacy — both are
intentionally standalone dev tools, run manually, never imported by
the app itself:
- `scoring_sensitivity_report.py` (Phase 6) — a standalone analysis
  tool, meant to be imported and run manually against a `run()`
  result, not called by the app itself.
- `repo_dependency_audit.py` (this session) — the repository-integrity
  tool described above; deliberately not imported by the running app,
  only by its own test file and by `archive-legacy.yml`.

(`data_contracts.py`, previously listed here as a third standalone
exception, is no longer one — a later session wired it into production
via `candidate_output_adapter.py`, which `step_rd_candidates.py`
imports. `repo_dependency_audit.py` now correctly reports it as
production-active; this note is left here specifically so the same
"once true, assumed still true" mistake doesn't get made about it
either.)

## How to re-verify any of the above

Run the real tool, not an inline snippet — copying a snippet out of
this file is exactly how the original snapshot went stale (it was
never re-run after being pasted here once):

```
python3 repo_dependency_audit.py summary
python3 repo_dependency_audit.py validate . .github/legacy-files.txt
```

Or as a normal test: `pytest -q test_production_dependency_integrity.py`.
This is the same method used to produce this file's legacy list —
re-run it after any future change to `app.py`'s or any Step file's
import chain to catch drift, rather than trusting this document.
