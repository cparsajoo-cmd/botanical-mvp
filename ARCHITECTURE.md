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
it wasn't. The 67 files below are still sitting in the repo root as of
this writing.

67 files were confirmed — by automated import-reachability analysis
from `app.py` and every file under `pages/`, not by guessing — to be
unreachable from the app in any way. Each was a superseded/duplicate
engine, an old Step from before the Step 0-6 consolidation, or a
connector that was never wired in. The full list is in
`.github/legacy-files.txt`.

**To actually move them:** go to the repo's Actions tab, select
"Archive legacy files (Phase 7)", and click "Run workflow" (see
`.github/workflows/archive-legacy.yml` — it already exists and is
ready to run, it just hasn't been triggered yet). After it runs,
verify:
- `archive/` exists and contains the 67 files
- `archive/ARCHIVED_FILES.md` was generated
- `pytest -q` still passes (the workflow itself checks this before
  committing, but re-verify)
- Update this section of ARCHITECTURE.md to say "moved" only once
  that's actually confirmed true — do not restate it as done from
  intent alone again.

Two files that the same reachability script flags as "unreachable"
should NOT be included when the workflow runs, because unreachable-
from-app.py isn't the same as legacy — both are recent, intentionally
standalone additions not yet wired into the main pipeline by design:
- `data_contracts.py` (Phase 3) — pydantic-free dataclass schemas,
  meant to be adopted into the engine incrementally, not all at once.
- `scoring_sensitivity_report.py` (Phase 6) — a standalone analysis
  tool, meant to be imported and run manually against a `run()`
  result, not called by the app itself.

## How to re-verify any of the above

From the repo root, with no dependencies beyond the Python standard
library:

```python
import os, re

root = "."
py_files = [f for f in os.listdir(root) if f.endswith(".py")]

def local_imports(path):
    text = open(path, encoding="utf-8", errors="ignore").read()
    mods = set()
    for m in re.finditer(r"^\s*from\s+([\w\.]+)\s+import", text, re.M):
        mods.add(m.group(1).split(".")[0])
    for m in re.finditer(r"^\s*import\s+([\w\.]+)", text, re.M):
        mods.add(m.group(1).split(".")[0])
    return mods

modules = {f[:-3] for f in py_files}
graph = {f[:-3]: local_imports(f) & modules for f in py_files}

visited, queue = set(), ["app"]
while queue:
    m = queue.pop()
    if m in visited:
        continue
    visited.add(m)
    queue.extend(dep for dep in graph.get(m, []) if dep not in visited)

print("Reachable from app.py:", sorted(visited))
print("NOT reachable:", sorted(modules - visited))
```

This is exactly the method used to produce the Phase 1 audit's active/
legacy split and this file's legacy list — re-run it after any future
change to `app.py`'s import chain to catch drift.
