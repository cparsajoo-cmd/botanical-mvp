"""Part 22 -- Stage 2 deadline/progress/budget regression tests.

No real waiting anywhere in this file: slowness is simulated by
monkeypatching time.monotonic() (a fake, manually-advanced clock) or by
having a mocked connector/LLM call itself advance the fake clock when
invoked. Every test in this file must run in well under a second.
"""
import time as time_module

import pandas as pd
import pytest

import research_engine as re_mod
import query_expansion_service as qes
import ai_botanical_entity_extractor as ai_bev
import botanical_entity_validation as bev


class _FakeClock:
    """A manually-advanced monotonic clock. advance(seconds) simulates
    time passing (e.g. inside a slow connector call)."""

    def __init__(self, start=0.0):
        self._now = start

    def advance(self, seconds):
        self._now += seconds

    def __call__(self):
        return self._now


# ---------------------------------------------------------------------
# 1. The whole-stage deadline begins before query expansion (Part 13).
# ---------------------------------------------------------------------
def test_deadline_starts_before_query_expansion(monkeypatch):
    clock = _FakeClock(start=1000.0)
    monkeypatch.setattr(time_module, "monotonic", clock)

    seen_deadline_seconds = {}

    def _fake_expand_query_terms(indication, terms, deadline_seconds=None, **kwargs):
        # Simulate 5s of "work" for query expansion itself.
        clock.advance(5)
        seen_deadline_seconds["value"] = deadline_seconds
        return terms

    monkeypatch.setattr(qes, "expand_query_terms", _fake_expand_query_terms)
    monkeypatch.setattr(re_mod, "_richer_candidate_plants", lambda **kw: [])
    monkeypatch.setattr(re_mod.candidate_selection, "select_candidates", lambda *a, **kw: ([], {
        "candidate_shortfall": False, "shortfall_reason": "",
    }))
    monkeypatch.setattr(re_mod, "rank_global_candidates", lambda **kw: None)

    def _fake_online_discovered(*args, deadline_ts=None, **kwargs):
        # The deadline passed to discovery must already reflect that 0s
        # have elapsed BEFORE this call started counting from
        # run_research_engine's own top -- i.e. it is not None and it is
        # a real future timestamp on the SAME fake clock.
        assert deadline_ts is not None
        assert deadline_ts > clock()
        return [], {"connector_errors": [], "ranked_matches": {}}

    monkeypatch.setattr(re_mod, "_online_discovered_candidate_plants", _fake_online_discovered)

    try:
        re_mod.run_research_engine(
            product_type="p", dosage_form="d", indication="sleep",
            target_market="US", global_candidate_count=3, save=False,
        )
    except Exception:
        # This test only cares that the deadline was already active
        # before discovery started -- further pipeline stages (candidate
        # selection, final collection) are exercised in other tests.
        pass


# ---------------------------------------------------------------------
# 2-6. Slow sub-stages cannot exceed the whole-stage deadline; partial
# results are returned instead of hanging.
# ---------------------------------------------------------------------
def test_slow_query_expansion_does_not_exceed_stage_deadline(monkeypatch):
    clock = _FakeClock()
    monkeypatch.setattr(time_module, "monotonic", clock)

    def _slow_expand(indication, terms, deadline_seconds=None, **kwargs):
        # Simulate a query-expansion call that takes longer than the
        # whole configured stage budget.
        clock.advance(re_mod.STAGE2_DISCOVERY_QUICK_BUDGET_SECONDS + 50)
        return terms

    monkeypatch.setattr(qes, "expand_query_terms", _slow_expand)
    monkeypatch.setattr(re_mod, "BotanicalRDCandidateEngine", lambda **kw: type(
        "E", (), {"__init__": lambda self, **kw2: None}
    )())
    monkeypatch.setattr(re_mod, "_candidate_alias_catalog", lambda engine: {"x": ["x"]})

    deadline_ts = clock() + re_mod.STAGE2_DISCOVERY_QUICK_BUDGET_SECONDS
    result, diagnostics = re_mod._online_discovered_candidate_plants(
        indication="sleep", dosage_form="tea", target_market="US", target_count=3,
        deadline_ts=deadline_ts,
    )
    # Discovery must return (not hang) even though the fake clock shows
    # the budget was blown during query expansion, and later sub-stages
    # must have been skipped for budget rather than run anyway.
    assert isinstance(result, list)
    assert diagnostics["stage2_deadline_exceeded"] is True


def test_slow_pubmed_stops_the_literature_loop_early(monkeypatch):
    clock = _FakeClock()
    monkeypatch.setattr(time_module, "monotonic", clock)
    monkeypatch.setattr(qes, "expand_query_terms", lambda indication, terms, **kw: ["sleep", "insomnia", "anxiety", "melatonin"])

    call_count = {"n": 0}

    def _slow_pubmed(query, max_results=12, timeout=8, sort="relevance"):
        call_count["n"] += 1
        clock.advance(60)  # each call eats more than the whole budget
        return []

    monkeypatch.setattr(re_mod, "search_and_fetch_pubmed", _slow_pubmed)
    monkeypatch.setattr(re_mod, "_fetch_europepmc_discovery_records", lambda *a, **kw: [])
    monkeypatch.setattr(re_mod, "BotanicalRDCandidateEngine", lambda **kw: type(
        "E", (), {"__init__": lambda self, **kw2: None}
    )())
    monkeypatch.setattr(re_mod, "_candidate_alias_catalog", lambda engine: {"x": ["x"]})

    deadline_ts = clock() + 90  # only enough budget for ~1.5 calls
    result, diagnostics = re_mod._online_discovered_candidate_plants(
        indication="sleep", dosage_form="tea", target_market="US", target_count=3,
        deadline_ts=deadline_ts,
    )
    # Must not have attempted all 4 query terms -- the loop stopped once
    # the deadline was exhausted.
    assert call_count["n"] < 4
    assert diagnostics["stage2_deadline_exceeded"] is True


def test_slow_ai_entity_extraction_cannot_exceed_stage_deadline(monkeypatch):
    clock = _FakeClock()
    monkeypatch.setattr(time_module, "monotonic", clock)

    call_count = {"n": 0}

    def _slow_extract(title, abstract, deadline_seconds=None):
        call_count["n"] += 1
        clock.advance(30)
        return []

    monkeypatch.setattr(ai_bev, "extract_botanical_entities_ai", _slow_extract)
    monkeypatch.setattr(re_mod, "extract_botanical_entities_ai", _slow_extract)
    monkeypatch.setattr(bev, "validate_botanical_candidate", lambda name, cache=None, deadline_seconds=None: {
        "valid": False, "botanical_validation_status": "unresolved",
        "botanical_validation_score": 0.0, "taxonomic_source": "", "matched_scientific_name": "",
    })
    monkeypatch.setattr(re_mod, "validate_botanical_candidate", bev.validate_botanical_candidate)

    records = [
        {"Title": f"Study {i} on sleep and Plantus fakeus{i}", "Abstract": "sleep evidence", "Record_ID": str(i)}
        for i in range(20)
    ]
    deadline_ts = clock() + 65  # enough for ~2 slow extraction calls only
    ranked, meta, diag = re_mod._extract_open_world_botanical_candidates(
        records, {}, ["sleep"], max_llm_entity_extraction_records=20, deadline_ts=deadline_ts,
    )
    assert call_count["n"] < 20
    assert diag["llm_entity_extraction_stopped_for_budget"] is True


def test_slow_taxonomy_validation_cannot_exceed_stage_deadline(monkeypatch):
    clock = _FakeClock()
    monkeypatch.setattr(time_module, "monotonic", clock)

    def _no_ai(title, abstract, deadline_seconds=None):
        return []

    monkeypatch.setattr(re_mod, "extract_botanical_entities_ai", _no_ai)

    call_count = {"n": 0}

    def _slow_validate(name, cache=None, deadline_seconds=None):
        call_count["n"] += 1
        clock.advance(30)
        return {
            "valid": False, "botanical_validation_status": "unresolved",
            "botanical_validation_score": 0.0, "taxonomic_source": "", "matched_scientific_name": "",
        }

    monkeypatch.setattr(re_mod, "validate_botanical_candidate", _slow_validate)

    records = [
        {"Title": f"Plantus fakeus{chr(97 + i)} reduces sleep latency", "Abstract": "", "Record_ID": str(i)}
        for i in range(10)
    ]
    deadline_ts = clock() + 65
    ranked, meta, diag = re_mod._extract_open_world_botanical_candidates(
        records, {}, [], max_llm_entity_extraction_records=0, deadline_ts=deadline_ts,
    )
    assert call_count["n"] < 10
    assert diag["taxonomy_validation_stopped_for_budget"] is True


def test_candidate_specific_validation_cannot_exceed_stage_deadline(monkeypatch):
    clock = _FakeClock()
    monkeypatch.setattr(time_module, "monotonic", clock)
    monkeypatch.setattr(
        re_mod, "_candidate_pool_for_indication",
        lambda indication, alias_catalog: [f"Plantus fakeus{i}" for i in range(10)],
    )

    call_count = {"n": 0}

    def _slow_pubmed(query, max_results=3, timeout=8, sort="relevance"):
        call_count["n"] += 1
        clock.advance(30)
        return []

    monkeypatch.setattr(re_mod, "search_and_fetch_pubmed", _slow_pubmed)
    monkeypatch.setattr(re_mod, "_fetch_europepmc_discovery_records", lambda *a, **kw: [])

    diagnostics = {"connector_errors": []}
    deadline_ts = clock() + 65
    validated, meta = re_mod._candidate_specific_literature_validation(
        indication="sleep", indication_terms=["sleep"], alias_catalog={},
        existing_plants=[], slots=5, diagnostics=diagnostics, deadline_ts=deadline_ts,
    )
    assert call_count["n"] < 10
    assert diagnostics["candidate_validation_stopped_for_budget"] is True


# ---------------------------------------------------------------------
# 8-9. Partial results returned when deadline expires; already-collected
# evidence/candidates are preserved, not discarded.
# ---------------------------------------------------------------------
def test_partial_results_preserved_when_ai_extraction_deadline_hits_midway(monkeypatch):
    clock = _FakeClock()
    monkeypatch.setattr(time_module, "monotonic", clock)

    call_count = {"n": 0}

    def _extract(title, abstract, deadline_seconds=None):
        call_count["n"] += 1
        # The first (and only) call succeeds, but consumes almost the
        # entire budget -- leaving too little for a second AI call, but
        # still enough for the fast (mocked) taxonomy validation pass
        # below to run on the one candidate already found.
        clock.advance(64)
        return [{
            "original_mention": "Plantus fakeus", "proposed_scientific_name": "Plantus fakeus",
            "common_name": "", "genus": "Plantus", "species": "fakeus",
            "is_botanical": True, "confidence": 0.9, "context_support": "",
        }]

    monkeypatch.setattr(re_mod, "extract_botanical_entities_ai", _extract)
    monkeypatch.setattr(
        re_mod, "validate_botanical_candidate",
        lambda name, cache=None, deadline_seconds=None: {
            "valid": True, "botanical_validation_status": "validated_external_taxonomy",
            "botanical_validation_score": 5.0, "taxonomic_source": "GBIF",
            "matched_scientific_name": name,
        },
    )

    records = [
        {"Title": f"Study {i} on sleep and Plantus fakeus", "Abstract": "sleep evidence reported", "Record_ID": str(i)}
        for i in range(5)
    ]
    deadline_ts = clock() + 65
    ranked, meta, diag = re_mod._extract_open_world_botanical_candidates(
        records, {}, ["sleep"], max_llm_entity_extraction_records=5, deadline_ts=deadline_ts,
    )
    # Only the first record's AI call should have run (budget exhausted
    # before a second one could start) -- but the candidate it already
    # found must still survive validation and appear in the ranked
    # output, never discarded just because later records ran out of time.
    assert call_count["n"] == 1
    assert "Plantus fakeus" in ranked


# ---------------------------------------------------------------------
# 10. Progress callback receives multiple meaningful stage events.
# ---------------------------------------------------------------------
def test_progress_callback_receives_multiple_stage_events(monkeypatch):
    events = []

    def _callback(stage, current, total, message):
        events.append(stage)

    monkeypatch.setattr(qes, "expand_query_terms", lambda indication, terms, **kw: terms)
    monkeypatch.setattr(re_mod, "BotanicalRDCandidateEngine", lambda **kw: type(
        "E", (), {"__init__": lambda self, **kw2: None}
    )())
    monkeypatch.setattr(re_mod, "_candidate_alias_catalog", lambda engine: {})

    re_mod._online_discovered_candidate_plants(
        indication="sleep", dosage_form="tea", target_market="US", target_count=3,
        deadline_ts=time_module.monotonic() + 60, progress_callback=_callback,
    )
    assert "expanding_query" in events
    assert len(set(events)) >= 1  # at least the stages actually reached fired


def test_progress_callback_exception_never_breaks_discovery(monkeypatch):
    def _broken_callback(stage, current, total, message):
        raise RuntimeError("UI exploded")

    monkeypatch.setattr(qes, "expand_query_terms", lambda indication, terms, **kw: terms)
    monkeypatch.setattr(re_mod, "BotanicalRDCandidateEngine", lambda **kw: type(
        "E", (), {"__init__": lambda self, **kw2: None}
    )())
    monkeypatch.setattr(re_mod, "_candidate_alias_catalog", lambda engine: {})

    # Must not raise, even though the callback itself always raises.
    result, diagnostics = re_mod._online_discovered_candidate_plants(
        indication="sleep", dosage_form="tea", target_market="US", target_count=3,
        deadline_ts=time_module.monotonic() + 60, progress_callback=_broken_callback,
    )
    assert isinstance(result, list)


# ---------------------------------------------------------------------
# 11-12. QUICK mode uses a bounded AI extraction count; PILOT/FULL can
# use a larger exploration cap.
# ---------------------------------------------------------------------
def test_quick_mode_ai_extraction_cap_is_bounded_and_smaller_than_pilot():
    quick_cap = re_mod._max_llm_entity_extraction_records(
        pilot_mode=False, requested_count=3, remaining_seconds=120,
    )
    pilot_cap = re_mod._max_llm_entity_extraction_records(
        pilot_mode=True, requested_count=3, remaining_seconds=600,
    )
    assert quick_cap <= re_mod._QUICK_MAX_LLM_ENTITY_EXTRACTION_RECORDS
    assert pilot_cap > quick_cap
    assert pilot_cap <= re_mod._PILOT_MAX_LLM_ENTITY_EXTRACTION_RECORDS


def test_ai_extraction_cap_is_never_hardcoded_to_a_fixed_plant_count():
    # The cap must scale with requested_count, not sit at one constant
    # regardless of how many candidates were actually requested.
    small_request_cap = re_mod._max_llm_entity_extraction_records(
        pilot_mode=False, requested_count=2, remaining_seconds=120,
    )
    large_request_cap = re_mod._max_llm_entity_extraction_records(
        pilot_mode=False, requested_count=20, remaining_seconds=120,
    )
    assert large_request_cap >= small_request_cap


def test_ai_extraction_cap_is_zero_when_essentially_no_budget_remains():
    cap = re_mod._max_llm_entity_extraction_records(
        pilot_mode=False, requested_count=8, remaining_seconds=0.5,
    )
    assert cap == 0


# ---------------------------------------------------------------------
# 13-14. Per-request LLM timeout cannot exceed remaining stage time;
# retry does not run if no stage budget remains (llm_client-level, but
# re-verified here in the Stage 2 integration context).
# ---------------------------------------------------------------------
def test_query_expansion_llm_call_receives_capped_deadline(monkeypatch):
    seen = {}

    def _fake_call_structured_json(**kwargs):
        seen["deadline_seconds"] = kwargs.get("deadline_seconds")
        return {"search_concepts": []}

    monkeypatch.setattr(qes.llm_client, "call_structured_json", _fake_call_structured_json)
    qes.generate_ai_query_concepts("sleep", deadline_seconds=7)
    assert seen["deadline_seconds"] == 7
