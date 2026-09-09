"""Scientific vs. commercial implementation fingerprints (Section 6 of the
2026-09-09 "finish the missing parts" cahier des charges).

WHAT WAS WRONG
step_rd_candidates.py's original ``_PIPELINE_FINGERPRINT_FILES`` hashed one
combined list of 8 files, including step_rd_candidates.py itself and
botanical_rd_candidate_engine.py. Both files mix scientific orchestration
with commercial/presentation code, so ANY change to either -- even a pure
investor-view/commercial edit -- changed the single resulting hash. That
hash gates ``_stage6_stale_pipeline_warning()``, which BLOCKS Stage 6
rendering and tells the user to rerun the (expensive, potentially
AI-calling) Candidate Discovery pipeline. A commercial-only change was
therefore indistinguishable from a scientific one at that gate.

THE FIX (this module)
Two separate, independently-hashed file lists:

  SCIENTIFIC_FINGERPRINT_FILES -- files that can alter scientific candidate
  generation, mechanistic discovery, scientific scoring, or safety/
  scientific decisions. step_rd_candidates.py is deliberately NOT in this
  list: every module this pass adds for commercial/investor-view work
  (commercial_evidence_provider.py, commercial_evidence_import.py,
  commercial_opportunity_classification.py, post_discovery_investor_view.py)
  lives outside this file entirely, and step_rd_candidates.py itself is,
  going forward, where commercial/presentation call-site glue lives.

  COMMERCIAL_FINGERPRINT_FILES -- step_rd_candidates.py plus the dedicated
  commercial/investor-view modules above.

KNOWN, DOCUMENTED LIMITATION (not hidden)
botanical_rd_candidate_engine.py remains in SCIENTIFIC_FINGERPRINT_FILES.
It is overwhelmingly the core scientific engine (compound resolution,
mechanistic matching, safety assertions, evidence adjudication), so it
belongs there -- but it also still contains a few now-thin commercial
delegate methods (e.g. ``_search_retail_products()``, which now just calls
commercial_evidence_provider.dispatch_retail_provider_search()). Editing
those few lines will still change the scientific fingerprint. Fully
splitting an ~8,000-line file at function granularity was judged out of
scope for this pass; the practical goal -- ALL NEW commercial/investor-view
work landing in files outside the scientific fingerprint -- is achieved,
since that is where this pass's real work happens and where future
commercial work is expected to continue happening.

``_pipeline_implementation_fingerprint()`` in step_rd_candidates.py (the
original, combined, 8-file hash) is left UNCHANGED and still gates the
per-session exact-input result-reuse key
(``_candidate_discovery_run_key()``/``ENGINE_CACHE_VERSION``) -- a
cautious "recompute rather than silently reuse a stale in-session cache
entry" behavior, which is wasteful but not incorrect, and touching it was
judged higher-risk than worthwhile for this pass. The two NEW fingerprints
in this module instead replace the STALENESS-BLOCKING gate at the real
Stage 6 boundary (``_report_ready_matches_current_pipeline()`` /
``_stage6_stale_pipeline_warning()``), which is the mechanism the cahier
des charges' Section 6 complaint is actually about ("commercial/UI change
must NOT invalidate a scientifically valid Stage-5 result").
"""

from __future__ import annotations

import hashlib
from pathlib import Path

SCIENTIFIC_FINGERPRINT_FILES = (
    "botanical_rd_candidate_engine.py",
    "indication_candidate_discovery.py",
    "candidate_shortlisting.py",
    "rd_discovery_classification.py",
    "compound_plant_resolver.py",
    "phase5_scoring_config.py",
    "stage5_funnel_config.py",
)

COMMERCIAL_FINGERPRINT_FILES = (
    "step_rd_candidates.py",
    "commercial_evidence_provider.py",
    "commercial_evidence_import.py",
    "commercial_opportunity_classification.py",
    "post_discovery_investor_view.py",
    "evidence_id_parsing.py",
    "evidence_source_resolver.py",
)


def _hash_files(filenames, root: Path | None = None) -> str:
    root = root or Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for filename in filenames:
        digest.update(filename.encode("utf-8"))
        path = root / filename
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(b"<missing>")
    return digest.hexdigest()[:16]


def scientific_implementation_fingerprint(root: Path | None = None) -> str:
    return _hash_files(SCIENTIFIC_FINGERPRINT_FILES, root=root)


def commercial_implementation_fingerprint(root: Path | None = None) -> str:
    return _hash_files(COMMERCIAL_FINGERPRINT_FILES, root=root)
