import pandas as pd

import ai_rd_insight_service as svc


def _evidence_df():
    return pd.DataFrame([
        {
            "Scientific_Name": "Valeriana officinalis", "Evidence_Record_ID": "1",
            "Result_Direction": "positive", "Study_Model": "human",
            "Notes": "Reduced sleep latency in a randomized trial.",
        },
        {
            "Scientific_Name": "Valeriana officinalis", "Evidence_Record_ID": "2",
            "Result_Direction": "no_effect", "Study_Model": "human",
            "Notes": "No significant effect vs placebo.",
        },
        {
            "Scientific_Name": "Other Plant", "Evidence_Record_ID": "3",
            "Result_Direction": "positive", "Study_Model": "human",
            "Notes": "Unrelated plant evidence.",
        },
    ])


def test_evidence_adapter_filters_by_plant_and_maps_columns():
    items = svc._evidence_items_from_df(_evidence_df(), "Valeriana officinalis")
    assert len(items) == 2
    assert {i["evidence_id"] for i in items} == {"1", "2"}
    assert all(i["plant"] == "Valeriana officinalis" for i in items)


def test_evidence_adapter_empty_df_returns_empty_list():
    assert svc._evidence_items_from_df(pd.DataFrame(), "Valeriana officinalis") == []
    assert svc._evidence_items_from_df(None, "Valeriana officinalis") == []


def test_evidence_adapter_no_matching_plant_returns_empty_list():
    assert svc._evidence_items_from_df(_evidence_df(), "Nonexistent plant") == []


def test_generate_candidate_insights_runs_all_three_stages(monkeypatch):
    monkeypatch.setattr(
        svc, "reason_about_mechanisms",
        lambda items: [{"plant": "Valeriana officinalis", "relationship_type": "direct",
                         "supporting_evidence_ids": ["1"], "confidence": 0.8}],
    )
    monkeypatch.setattr(
        svc, "synthesize_evidence",
        lambda items: {"overall_consistency": "mixed", "heterogeneity_reason": "unresolved",
                        "contradictions": [], "summary": "mixed"},
    )
    monkeypatch.setattr(
        svc, "generate_hypotheses",
        lambda edges, synthesis, score_summary=None, evidence_ids=None: [
            {"hypothesis": "test", "evidence_label": "rd_hypothesis"}
        ],
    )

    result = svc.generate_candidate_insights("Valeriana officinalis", _evidence_df())
    assert result["evidence_items_count"] == 2
    assert len(result["mechanistic_edges"]) == 1
    assert result["evidence_synthesis"]["overall_consistency"] == "mixed"
    assert result["hypotheses"][0]["evidence_label"] == "rd_hypothesis"


def test_k_global_ai_outage_orchestrator_still_returns_well_formed_empty_result(monkeypatch):
    """Test K: with every underlying AI call failing (simulating OpenAI
    being globally unavailable), the orchestrator must never raise, and
    must return a well-formed (all-empty) result so a caller can still
    render Stage 5 output with zero AI sections -- the deterministic
    core is completely unaffected."""
    def _raise_mechanism(items):
        raise RuntimeError("OpenAI unavailable")

    def _raise_synthesis(items):
        raise RuntimeError("OpenAI unavailable")

    def _raise_hypotheses(edges, synthesis, score_summary=None, evidence_ids=None):
        raise RuntimeError("OpenAI unavailable")

    monkeypatch.setattr(svc, "reason_about_mechanisms", _raise_mechanism)
    monkeypatch.setattr(svc, "synthesize_evidence", _raise_synthesis)
    monkeypatch.setattr(svc, "generate_hypotheses", _raise_hypotheses)

    result = svc.generate_candidate_insights("Valeriana officinalis", _evidence_df())
    assert result["mechanistic_edges"] == []
    assert result["evidence_synthesis"] is None
    assert result["hypotheses"] == []
    # The evidence itself (raw, deterministic data) is completely
    # unaffected by the AI outage.
    assert result["evidence_items_count"] == 2


def test_one_stage_failing_does_not_prevent_the_others(monkeypatch):
    """Part 18: each AI capability degrades independently -- mechanism
    reasoning failing must not prevent synthesis/hypotheses from
    running on the same evidence."""
    def _raise_mechanism(items):
        raise RuntimeError("mechanism service down")

    monkeypatch.setattr(svc, "reason_about_mechanisms", _raise_mechanism)
    monkeypatch.setattr(
        svc, "synthesize_evidence",
        lambda items: {"overall_consistency": "mixed", "heterogeneity_reason": "unresolved",
                        "contradictions": [], "summary": "still works"},
    )
    monkeypatch.setattr(
        svc, "generate_hypotheses",
        lambda edges, synthesis, score_summary=None, evidence_ids=None: [],
    )

    result = svc.generate_candidate_insights("Valeriana officinalis", _evidence_df())
    assert result["mechanistic_edges"] == []
    assert result["evidence_synthesis"]["summary"] == "still works"


def test_never_raises_and_always_returns_dict_shape():
    # No monkeypatching at all -- real services run and fail open on
    # their own (no OpenAI reachable in this sandbox), and the
    # orchestrator must still return the expected dict shape.
    result = svc.generate_candidate_insights("Valeriana officinalis", _evidence_df())
    assert set(result.keys()) == {
        "evidence_items_count", "mechanistic_edges", "evidence_synthesis", "hypotheses",
    }
    assert isinstance(result["mechanistic_edges"], list)
    assert isinstance(result["hypotheses"], list)
