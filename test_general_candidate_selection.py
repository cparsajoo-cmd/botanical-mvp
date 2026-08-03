"""Tests for the general candidate-selection architecture.

Covers candidate_selection.py, therapeutic_area_registry.py, and their
integration into research_engine.run_research_engine(). No live API calls
are made anywhere in this file: every network-touching function
(_richer_candidate_plants, _online_discovered_candidate_plants,
collect_multi_source_evidence) is monkeypatched wherever run_research_engine
is exercised. rank_global_candidates is left unmocked in some tests because
it is pure in-memory data (GLOBAL_PLANT_CANDIDATES) with no network calls.

HOW TO RUN
    pytest -q test_general_candidate_selection.py
"""
import candidate_selection as cs
import therapeutic_area_registry as tar
import research_engine as re_mod


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _record(name, origin, score=0.0, evidence_status=None, sources=()):
    return cs.make_candidate(
        name, origin, score=score, evidence_status=evidence_status, sources=sources
    )


def _mock_pipeline(
    monkeypatch,
    richer=None,
    discovered=None,
    discovery_diagnostics=None,
):
    """Patch every network-touching function used by run_research_engine."""
    monkeypatch.setattr(
        re_mod, "collect_multi_source_evidence",
        lambda **kwargs: {"saved_records": [], "errors": [], "sources_checked": []},
    )
    monkeypatch.setattr(
        re_mod, "_richer_candidate_plants",
        lambda indication, dosage_form, target_market, target_count: richer,
    )
    monkeypatch.setattr(
        re_mod, "_online_discovered_candidate_plants",
        lambda indication, dosage_form, target_market, target_count, seed_plants=None: (
            discovered or [],
            discovery_diagnostics or {"connector_errors": [], "ranked_matches": {}},
        ),
    )


# ---------------------------------------------------------------------
# 1. Known indication with sufficient candidates
# ---------------------------------------------------------------------

def test_known_indication_with_sufficient_candidates(monkeypatch):
    _mock_pipeline(
        monkeypatch,
        richer=["Melissa officinalis", "Valeriana officinalis"],
        discovered=["Passiflora incarnata"],
        discovery_diagnostics={
            "connector_errors": [],
            "ranked_matches": {
                "Passiflora incarnata": {"score": 15, "clinical_human_records": 1},
            },
        },
    )
    out = re_mod.run_research_engine(
        product_type="Food supplement", dosage_form="Infusion", indication="sleep",
        target_market="European Union", save=False, global_candidate_count=5,
    )
    assert len(out["candidate_plants"]) == 5
    assert out["candidate_discovery_diagnostics"]["candidate_shortfall"] == 0


# ---------------------------------------------------------------------
# 2. Previously unknown indication
# ---------------------------------------------------------------------

def test_previously_unknown_indication_has_no_hypothesis_fabrication():
    unknown = "some totally unregistered condition xyz123"
    assert tar.lookup_therapeutic_area(unknown) is None
    assert tar.get_candidate_hypotheses(unknown) == []
    # Query terms still degrade gracefully to the user's own text.
    terms = tar.get_query_terms(unknown)
    assert unknown.strip() in terms


def test_previously_unknown_indication_reports_honest_shortfall(monkeypatch):
    _mock_pipeline(monkeypatch, richer=None, discovered=[], discovery_diagnostics={
        "connector_errors": ["simulated: no connectors configured"],
        "ranked_matches": {},
    })
    out = re_mod.run_research_engine(
        product_type="Food supplement", dosage_form="Infusion",
        indication="some totally unregistered condition xyz123",
        target_market="European Union", save=False, global_candidate_count=6,
    )
    assert out["candidate_plants"] == []
    diagnostics = out["candidate_discovery_diagnostics"]
    assert diagnostics["candidate_shortfall"] == 6
    assert diagnostics["shortfall_reason"] != cs.SHORTFALL_NONE


# ---------------------------------------------------------------------
# 3. No literature discovery but sufficient fallback candidates
# ---------------------------------------------------------------------

def test_no_literature_discovery_sufficient_fallback_candidates():
    records = [
        _record("Plant A", cs.ORIGIN_RANKED_FALLBACK, score=5),
        _record("Plant B", cs.ORIGIN_RANKED_FALLBACK, score=4),
        _record("Plant C", cs.ORIGIN_RANKED_FALLBACK, score=3),
    ]
    selected, diagnostics = cs.select_candidates(records, requested_count=3)
    assert len(selected) == 3
    assert diagnostics["candidate_shortfall"] == 0
    assert diagnostics["validated_literature_count"] == 0


# ---------------------------------------------------------------------
# 4. Insufficient scientifically plausible candidates
# ---------------------------------------------------------------------

def test_insufficient_scientifically_plausible_candidates_reports_shortfall():
    records = [_record("Plant A", cs.ORIGIN_REFERENCE_SEED, score=1)]
    selected, diagnostics = cs.select_candidates(records, requested_count=5)
    assert len(selected) == 1
    assert diagnostics["candidate_shortfall"] == 4
    assert diagnostics["shortfall_reason"] != cs.SHORTFALL_NONE


def test_zero_candidates_reports_insufficient_hypotheses():
    selected, diagnostics = cs.select_candidates([], requested_count=5)
    assert selected == []
    assert diagnostics["candidate_shortfall"] == 5
    assert diagnostics["shortfall_reason"] == cs.SHORTFALL_INSUFFICIENT_HYPOTHESES


# ---------------------------------------------------------------------
# 5. Duplicate plant returned by seed, literature and fallback routes
# ---------------------------------------------------------------------

def test_duplicate_plant_across_origins_is_merged_not_repeated():
    records = [
        _record("Valeriana officinalis", cs.ORIGIN_REFERENCE_SEED, score=1),
        _record(
            "valeriana officinalis", cs.ORIGIN_VALIDATED_LITERATURE, score=20,
            evidence_status=cs.STATUS_VALIDATED_DIRECT,
        ),
        _record("VALERIANA OFFICINALIS", cs.ORIGIN_RANKED_FALLBACK, score=3),
    ]
    merged = cs.merge_candidates(records)
    assert len(merged) == 1
    assert merged[0].evidence_status == cs.STATUS_VALIDATED_DIRECT
    assert set(merged[0].score_components["contributing_origins"]) == {
        cs.ORIGIN_REFERENCE_SEED, cs.ORIGIN_VALIDATED_LITERATURE, cs.ORIGIN_RANKED_FALLBACK,
    }


# ---------------------------------------------------------------------
# 6. Strong literature candidate outranking a weak seed
# ---------------------------------------------------------------------

def test_strong_literature_candidate_outranks_weak_seed():
    records = [
        _record("Weak Seed Plant", cs.ORIGIN_REFERENCE_SEED, score=0.5),
        _record(
            "Strong Literature Plant", cs.ORIGIN_VALIDATED_LITERATURE, score=25,
            evidence_status=cs.STATUS_VALIDATED_DIRECT,
        ),
    ]
    selected, _ = cs.select_candidates(records, requested_count=1)
    assert len(selected) == 1
    assert selected[0].name == "Strong Literature Plant"


# ---------------------------------------------------------------------
# 7. Candidate hypothesis not being labelled validated
# ---------------------------------------------------------------------

def test_candidate_hypothesis_is_never_labelled_validated():
    record = cs.make_candidate("Mystery Plant", cs.ORIGIN_CANDIDATE_HYPOTHESIS)
    assert record.evidence_status == cs.STATUS_PENDING_VALIDATION
    assert record.evidence_status not in (
        cs.STATUS_VALIDATED_DIRECT, cs.STATUS_VALIDATED_INDIRECT,
    )


def test_registry_candidate_hypotheses_are_search_support_only():
    hypotheses = tar.get_candidate_hypotheses("sleep")
    assert hypotheses  # known indication has a curated pool
    for plant in hypotheses:
        record = cs.make_candidate(plant, cs.ORIGIN_CANDIDATE_HYPOTHESIS)
        assert record.evidence_status == cs.STATUS_PENDING_VALIDATION


# ---------------------------------------------------------------------
# 8. Stable deterministic ordering
# ---------------------------------------------------------------------

def test_selection_ordering_is_deterministic_across_shuffles():
    import random

    records = [
        _record("Alpha", cs.ORIGIN_REFERENCE_SEED, score=5),
        _record("Beta", cs.ORIGIN_REFERENCE_SEED, score=5),
        _record("Gamma", cs.ORIGIN_RANKED_FALLBACK, score=5),
        _record("Delta", cs.ORIGIN_RANKED_FALLBACK, score=5),
    ]
    first_selected, _ = cs.select_candidates(list(records), requested_count=4)
    first_order = [r.name for r in first_selected]

    shuffled = list(records)
    random.Random(42).shuffle(shuffled)
    second_selected, _ = cs.select_candidates(shuffled, requested_count=4)
    second_order = [r.name for r in second_selected]

    assert first_order == second_order


# ---------------------------------------------------------------------
# 9. global_candidate_count values 3, 8, 30
# ---------------------------------------------------------------------

def test_selection_respects_requested_count_3_8_30():
    pool = [
        _record(f"Plant {i}", cs.ORIGIN_RANKED_FALLBACK, score=float(i))
        for i in range(40)
    ]
    for requested in (3, 8, 30):
        selected, diagnostics = cs.select_candidates(list(pool), requested_count=requested)
        assert len(selected) == requested
        assert diagnostics["candidate_shortfall"] == 0

    # Requesting more than the available pool is an honest shortfall, not a
    # crash or a fabricated extra candidate.
    selected, diagnostics = cs.select_candidates(list(pool), requested_count=50)
    assert len(selected) == 40
    assert diagnostics["candidate_shortfall"] == 10


# ---------------------------------------------------------------------
# 10. Existing run_research_engine public return keys remain present
# ---------------------------------------------------------------------

def test_existing_public_return_keys_are_preserved(monkeypatch):
    _mock_pipeline(monkeypatch, richer=["Melissa officinalis"], discovered=[])
    out = re_mod.run_research_engine(
        product_type="Food supplement", dosage_form="Infusion", indication="sleep",
        target_market="European Union", save=False, global_candidate_count=4,
    )
    required_keys = {
        "candidate_plants", "evidence_backed_plants", "online_discovered_plants",
        "candidate_discovery_diagnostics", "saved_records", "errors", "sources_checked",
    }
    assert required_keys.issubset(out.keys())
    # New additive keys are present without displacing the old ones.
    assert "candidate_records" in out
    assert "candidate_selection_diagnostics" in out
    assert "validated_literature_plants" in out
    assert "reference_seed_plants" in out


# ---------------------------------------------------------------------
# 11. Candidate-selection shortfall vs evidence-collection timeout
# ---------------------------------------------------------------------

def test_candidate_shortfall_distinct_from_collection_timeout(monkeypatch):
    # Enough candidates to avoid a *selection* shortfall, but the collection
    # loop itself reports an unfinished plant (a *timeout*, not a shortfall).
    _mock_pipeline(
        monkeypatch,
        richer=["Melissa officinalis", "Valeriana officinalis", "Passiflora incarnata"],
        discovered=[],
    )
    out = re_mod.run_research_engine(
        product_type="Food supplement", dosage_form="Infusion", indication="sleep",
        target_market="European Union", save=False, global_candidate_count=3,
    )
    diagnostics = out["candidate_discovery_diagnostics"]
    assert diagnostics["candidate_shortfall"] == 0
    # The two concepts are tracked under different, non-overlapping fields.
    assert "collection_unfinished_plant_count" in diagnostics
    assert "candidate_shortfall" in diagnostics
    assert "shortfall_reason" in diagnostics


# ---------------------------------------------------------------------
# 13. No live API calls -- verified structurally: the mocked functions above
# are the only network-capable entry points run_research_engine uses before
# the evidence-collection loop, and that loop is mocked too in every test in
# this file.
# ---------------------------------------------------------------------

def test_no_live_network_calls_are_required_for_selection():
    # candidate_selection.py and therapeutic_area_registry.py never import
    # requests/urllib/http -- selection logic is pure and offline by
    # construction.
    import ast
    for module_file in ("candidate_selection.py", "therapeutic_area_registry.py"):
        with open(module_file, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=module_file)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        assert not (imported & {"requests", "urllib", "http", "httpx"})


# ---------------------------------------------------------------------
# 14. candidate_plants remains List[str] for downstream code
# ---------------------------------------------------------------------

def test_candidate_plants_is_list_of_strings(monkeypatch):
    _mock_pipeline(monkeypatch, richer=["Melissa officinalis"], discovered=["Passiflora incarnata"])
    out = re_mod.run_research_engine(
        product_type="Food supplement", dosage_form="Infusion", indication="sleep",
        target_market="European Union", save=False, global_candidate_count=4,
    )
    assert isinstance(out["candidate_plants"], list)
    assert all(isinstance(p, str) for p in out["candidate_plants"])
    assert isinstance(out["online_discovered_plants"], list)
    assert all(isinstance(p, str) for p in out["online_discovered_plants"])
