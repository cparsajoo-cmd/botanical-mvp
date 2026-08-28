"""Stage 5 candidate-funnel — single, central source for the configurable
candidate budget used by :mod:`stage5_candidate_prescreen`.

Every module that participates in the pre-screen / bounded-scoring
architecture (stage5_candidate_prescreen.py, step_rd_candidates.py) imports
its budget constants FROM HERE — no magic numbers are re-declared inline,
mirroring the pattern already established by phase5_scoring_config.py for
the scientific scoring weights.

PROVISIONAL. These are deliberate engineering defaults chosen to keep the
expensive full scientific-scoring pass (candidate_shortlisting.
build_plant_candidate_shortlist) bounded to a plausible candidate pool
instead of the entire internal botanical catalogue, while never dropping a
candidate the existing scientific logic would flag as high-priority from
cheap fields. They are not statistically calibrated and may be revised.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Candidate budget
# ---------------------------------------------------------------------------
# The number of NON-mandatory ("exploratory": supportive mechanistic match,
# weaker but traceable relevance) candidates the cheap pre-screen may admit
# to the expensive full scientific-scoring pass, on top of every mandatory
# candidate (direct evidence, hard-stop-flagged, or a validated Stage 2
# novel candidate — see stage5_candidate_prescreen.py). Mandatory candidates
# are NEVER counted against this budget or dropped because of it.
STAGE5_PRESCREEN_EXPLORATORY_BUDGET = {
    "quick": 90,
    "full": 300,
}

# Which budget key drives a Step 5 run when the caller does not pass an
# explicit ``mode``/``budget`` override. "full" is the safer default: it
# never silently narrows results relative to the pre-funnel behavior for
# indications with a modest exploratory pool, while still bounding the
# pathological case (thousands of catalogue plants with no direct evidence)
# that motivated this architecture change.
STAGE5_PRESCREEN_DEFAULT_MODE = "quick"

# Absolute ceiling on the exploratory pool regardless of ``mode``, purely as
# a defensive backstop against a misconfigured/overridden budget value.
STAGE5_PRESCREEN_EXPLORATORY_HARD_CEILING = 2000


def resolve_exploratory_budget(mode: str | None = None, override: int | None = None) -> int:
    """Return the configured exploratory-candidate budget for ``mode``.

    ``override`` — an explicit integer — always wins when provided (e.g. a
    caller that wants a one-off custom budget without editing this module).
    Falls back to :data:`STAGE5_PRESCREEN_DEFAULT_MODE` for an unrecognized
    or empty ``mode``, rather than raising, so a typo in a UI-supplied mode
    string degrades to the safe default instead of crashing Stage 5.
    """
    if override is not None:
        try:
            value = int(override)
        except (TypeError, ValueError):
            value = STAGE5_PRESCREEN_EXPLORATORY_BUDGET[STAGE5_PRESCREEN_DEFAULT_MODE]
    else:
        key = str(mode or "").strip().lower()
        value = STAGE5_PRESCREEN_EXPLORATORY_BUDGET.get(
            key, STAGE5_PRESCREEN_EXPLORATORY_BUDGET[STAGE5_PRESCREEN_DEFAULT_MODE]
        )
    return max(0, min(value, STAGE5_PRESCREEN_EXPLORATORY_HARD_CEILING))
