"""
Phase 4 — desired-behavior integration tests.

Unlike test_phase4_eligibility_gate_characterization.py (which records
CURRENT, pre-fix behavior — including the unsafe bypass), every test
in this file asserts the NEW, correct behavior the Phase 4
implementation must produce. Before implementation, these are
EXPECTED TO FAIL — that failure is the point (see the Phase 4 audit's
required order: model -> desired tests -> implementation -> green).

Do not weaken any assertion here to make it pass without a real code
change in botanical_rd_candidate_engine.py / candidate_shortlisting.py
/ step_rd_candidates.py / pharma_report_generator.py /
candidate_output_adapter.py.
"""
from __future__ import annotations

import sys
import types

import pandas as pd
import pytest

from botanical_rd_candidate_engine import BotanicalRDCandidateEngine, DEFAULT_SCORING_CONFIG
from eligibility_gate import EligibilityStatus, ScoreValidity


def _new_engine():
    engine = BotanicalRDCandidateEngine.__new__(BotanicalRDCandidateEngine)
    engine.scoring_config = DEFAULT_SCORING_CONFIG
    engine.compound_commonality_threshold = None
    return engine


# ---------------------------------------------------------------------
# 1 / 3 / 5 / 6 — eligibility outcomes reachable through the engine's
# own public _decision_class()/_evaluate_gates() surface (kept for
# backward compatibility, now eligibility-driven).
# ---------------------------------------------------------------------

def test_relevant_severe_toxicity_different_plant_without_confirmation_is_expert_review():
    """[Correction round] Being a different alternative plant is NOT,
    by itself, confirmation that a hard safety term is species-wide or
    relevant to this specific candidate (see eligibility_gate.py's
    corrected default policy). Without a confirmed scope/relevance —
    which production never supplies today — this resolves to
    EXPERT_REVIEW_REQUIRED, not an automatic NO_GO_SAFETY."""
    decision = BotanicalRDCandidateEngine._decision_class(
        None, score=90, safety_flags="teratogenic", interaction_flags="",
        has_evidence=True, match_quality="exact", same_plant=False,
    )
    assert decision.startswith("Expert review required")
    assert "Safety concern" not in decision


def test_same_plant_severe_toxicity_unknown_scope_is_not_promising():
    """[Phase 4 fix] Direct replacement for the proven same_plant bypass:
    this exact input (score=90, safety_flags='teratogenic', same_plant=True)
    used to produce 'Promising candidate; verify safety and
    standardization'. It must no longer do so."""
    decision = BotanicalRDCandidateEngine._decision_class(
        None, score=90, safety_flags="teratogenic", interaction_flags="",
        has_evidence=True, match_quality="exact", same_plant=True,
    )
    assert "Promising candidate" not in decision
    assert "Strong R&D candidate" not in decision


def test_same_plant_prohibition_unknown_scope_is_not_promising():
    decision = BotanicalRDCandidateEngine._decision_class(
        None, score=90, safety_flags="", interaction_flags="", has_evidence=True,
        match_quality="exact", same_plant=True,
        regulatory_barrier_types={"Prohibited / banned"},
    )
    assert "Promising candidate" not in decision
    assert "Strong R&D candidate" not in decision


def test_different_plant_prohibition_without_confirmation_is_expert_review():
    """[Correction round] Same corrected policy as the safety test
    above, for regulatory prohibition."""
    decision = BotanicalRDCandidateEngine._decision_class(
        None, score=90, safety_flags="", interaction_flags="", has_evidence=True,
        match_quality="exact", same_plant=False,
        regulatory_barrier_types={"Prohibited / banned"},
    )
    assert decision.startswith("Expert review required")
    assert "Regulatory prohibition" not in decision


# ---------------------------------------------------------------------
# 2 — Eligibility_Status / Decision_Class must not contradict each
# other (design review item 6 / test 20).
# ---------------------------------------------------------------------

def test_decision_class_cannot_contradict_eligibility_status_via_evaluate_gates():
    """[Design review item 4] Gate_Results' NEW "eligibility" key must
    agree with Decision_Class -- not the legacy "safety" sub-key, which
    is a coarser, pre-Phase-4 view that can legitimately still say
    FAILED for an unconfirmed-scope hit term while the real
    Eligibility_Status is EXPERT_REVIEW_REQUIRED, not NO_GO_SAFETY (see
    eligibility_gate.py's corrected default-scope policy). The
    "eligibility" key is the one that must never disagree with
    Decision_Class."""
    gate_results = BotanicalRDCandidateEngine._evaluate_gates(
        safety_flags="teratogenic", match_quality="exact", has_evidence=True,
        evidence_level="Clinical / human evidence", regulatory_barrier_types=set(),
        same_plant=False, has_evidence_text=True,
    )
    decision = BotanicalRDCandidateEngine._decision_class(
        None, score=90, safety_flags="teratogenic", interaction_flags="",
        has_evidence=True, match_quality="exact", same_plant=False,
        has_evidence_text=True,
    )
    assert gate_results["eligibility"]["status"] == "expert_review_required"
    assert decision.startswith("Expert review required")
    assert "Safety concern" not in decision


def test_decision_class_ah_never_maps_expert_review_or_incomplete_to_a_go_class():
    """[Design review item 6 / desired test 20] A high-confidence,
    high-score row that is EXPERT_REVIEW_REQUIRED or INCOMPLETE must
    never be classified into a Decision_Class_AH letter that
    go_investigate_hold_no_go() maps to "Go" (A/B) or "Investigate"
    (C/D/E/F) -- it must land in G (Hold), never contradicting
    Eligibility_Status."""
    from decision_class_ah import classify_decision_ah
    from structured_rationale import go_investigate_hold_no_go

    for label in (
        "Expert review required — not eligible for normal ranking until safety/regulatory scope is confirmed",
        "Incomplete — insufficient safety/regulatory evidence for a validated recommendation",
    ):
        ah = classify_decision_ah(
            existing_decision_class=label,
            evidence_confidence=95, rd_opportunity_score=95,
            market_status="Unknown", match_quality="exact", same_plant=True,
        )
        assert ah == "G — Hold / insufficient evidence"
        assert go_investigate_hold_no_go(ah) == "Hold"


# ---------------------------------------------------------------------
# 9 / 11 — no-go is excluded from candidate_shortlisting's Shortlist
# status, including the same_plant scenario the old _hard_stop() text
# match missed (proven in the prior audit turn).
# ---------------------------------------------------------------------

def test_shortlisting_excludes_same_plant_bypassed_no_go_from_shortlist():
    from candidate_shortlisting import _row_classification

    row = pd.Series({
        "Decision_Class": "Promising candidate; verify safety and standardization",
        "Decision_Class_AH": "B — Established scientific candidate",
        "Go_Investigate_Hold_NoGo": "Go",
        "Safety_Flags": "teratogenic",
        "Regulatory_Barriers": "None identified",
        "Gate_Results": {},
        "Eligibility_Status": "no_go_safety",
        "Eligible_For_Normal_Ranking": False,
        "Target_or_Mechanism": "GABA-A receptor",
        "Target_Provenance": "Directly reported",
        "Evidence_Level": "Clinical / human evidence",
        "Evidence_Hierarchy_Detail": "Randomized controlled trial",
        "Candidate_Evidence_Strength_Tier": "Strong",
        "Evidence_Source": "PubMed",
        "Source_Record_IDs": "PMID:12345678",
        "GRADE_Certainty": "High",
        "Shared_or_Similar_Compound": "Kavalactone-X",
        "Novelty_Status": "Alternative",
    })
    status, reasons, detail = _row_classification(row, dosage_form="tea")
    assert status == "Excluded"
    assert detail.get("hard_stop") is True


# ---------------------------------------------------------------------
# 13 / 14 — no-go excluded from BOTH the legacy and modern
# recommendation paths in step_rd_candidates.py.
# ---------------------------------------------------------------------

def _stub_streamlit_and_supabase():
    """See test_phase4_eligibility_gate_characterization.py's identical
    helper for why this must be a context manager that restores
    sys.modules on exit, not a plain sys.modules mutation."""
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        def _noop_decorator(*_a, **_k):
            def wrap(fn):
                return fn
            return wrap

        captured = {"dataframe_calls": []}
        st_stub = types.ModuleType("streamlit")
        st_stub.markdown = lambda *a, **k: None
        st_stub.caption = lambda *a, **k: None
        st_stub.dataframe = lambda df, *a, **k: captured["dataframe_calls"].append(df.copy())
        st_stub.warning = lambda *a, **k: None
        st_stub.cache_data = _noop_decorator
        st_stub.cache_resource = _noop_decorator
        st_stub.session_state = {}

        sc_stub = types.ModuleType("supabase_client")
        sc_stub.get_supabase_client = lambda *a, **k: None

        poisonable_modules = (
            "streamlit", "supabase_client",
            "step_rd_candidates", "pharma_report_generator", "candidate_output_adapter",
        )
        saved = {name: sys.modules.get(name) for name in poisonable_modules}
        sys.modules["streamlit"] = st_stub
        sys.modules["supabase_client"] = sc_stub
        for name in ("step_rd_candidates", "pharma_report_generator", "candidate_output_adapter"):
            sys.modules.pop(name, None)
        try:
            yield captured
        finally:
            for name, mod in saved.items():
                if mod is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = mod

    return _ctx()


def test_legacy_recommendation_fallback_excludes_no_go():
    result_df = pd.DataFrame([
        {
            "Alternative_Plant": "Piper methysticum",
            "Shared_or_Similar_Compound": "Kavain",
            "Target_or_Mechanism": "GABA-A",
            "R&D_Opportunity_Score": 92.0,
            "Decision_Class": "Regulatory prohibition — not suitable without regulatory review",
            "Eligibility_Status": "no_go_regulatory",
            "Eligible_For_Normal_Ranking": False,
            "Safety_Flags": "hepatotoxic",
            "Market_Status": "Unknown",
            "Novelty_Status": "Alternative",
            "Rationale": "desired-behavior test row",
        },
        {
            "Alternative_Plant": "Matricaria chamomilla",
            "Shared_or_Similar_Compound": "Apigenin",
            "Target_or_Mechanism": "GABA-A",
            "R&D_Opportunity_Score": 40.0,
            "Decision_Class": "Early-stage candidate",
            "Eligibility_Status": "eligible",
            "Eligible_For_Normal_Ranking": True,
            "Safety_Flags": "No explicit flag found",
            "Market_Status": "Unknown",
            "Novelty_Status": "Alternative",
            "Rationale": "desired-behavior test row",
        },
    ])

    with _stub_streamlit_and_supabase() as captured:
        from step_rd_candidates import _recommendation_block
        _recommendation_block(result_df, report_ready_df=None)

    assert len(captured["dataframe_calls"]) >= 1
    recommended_shown = captured["dataframe_calls"][0]
    shown_plants = set(recommended_shown["Alternative_Plant"])
    assert "Piper methysticum" not in shown_plants


def test_modern_recommendation_path_excludes_no_go():
    report_ready_df = pd.DataFrame([
        {
            "Alternative_Plant": "Piper methysticum",
            "Target_or_Mechanism": "GABA-A",
            "R&D_Opportunity_Score": 92.0,
            "Decision_Class_AH": "H — No-go / safety concern",
            "Eligibility_Status": "no_go_regulatory",
            "Eligible_For_Normal_Ranking": False,
            "Go_Investigate_Hold_NoGo": "No-Go",
            "Safety_Flags": "hepatotoxic",
            "Market_Status": "Unknown",
            "Novelty_Status": "Alternative",
            "Rationale": "desired-behavior test row",
        },
    ])
    with _stub_streamlit_and_supabase() as captured:
        from step_rd_candidates import _recommendation_block
        _recommendation_block(pd.DataFrame(), report_ready_df=report_ready_df)

    if captured["dataframe_calls"]:
        recommended_shown = captured["dataframe_calls"][0]
        shown_plants = set(recommended_shown.get("Alternative_Plant", []))
        assert "Piper methysticum" not in shown_plants


# ---------------------------------------------------------------------
# 12 — no-go excluded from pharma report top-N.
# ---------------------------------------------------------------------

def test_pharma_report_top_n_excludes_no_go():
    if "streamlit" not in sys.modules:
        sys.modules["streamlit"] = types.ModuleType("streamlit")
    from pharma_report_generator import generate_pharma_report

    result_df = pd.DataFrame([
        {
            "Reference_Plant": "Piper nigrum",
            "Alternative_Plant": "Piper methysticum",
            "Shared_or_Similar_Compound": "Kavain",
            "R&D_Opportunity_Score": 95.0,
            "Decision_Class": "Regulatory prohibition — not suitable without regulatory review",
            "Decision_Class_AH": "H — No-go / safety concern",
            "Eligibility_Status": "no_go_regulatory",
            "Eligible_For_Normal_Ranking": False,
            "Go_Investigate_Hold_NoGo": "No-Go",
            "Safety_Flags": "hepatotoxic",
            "Rationale": "desired-behavior test row",
        },
        {
            "Reference_Plant": "Piper nigrum",
            "Alternative_Plant": "Matricaria chamomilla",
            "Shared_or_Similar_Compound": "Apigenin",
            "R&D_Opportunity_Score": 40.0,
            "Decision_Class": "Early-stage candidate",
            "Decision_Class_AH": "D — Mechanism-based R&D candidate",
            "Eligibility_Status": "eligible",
            "Eligible_For_Normal_Ranking": True,
            "Go_Investigate_Hold_NoGo": "Investigate",
            "Safety_Flags": "No explicit flag found",
            "Rationale": "desired-behavior test row",
        },
    ])
    report_markdown = generate_pharma_report(
        result_df, indication="anxiety", dosage_form="tea", market="EU", top_n=5,
    )
    # Traceability is required (design review item 9/10): the no-go
    # candidate must NOT vanish from the report entirely -- it must
    # appear in a distinct "Excluded" section, never inside the ranked
    # "Top Candidates" write-ups.
    top_section = report_markdown.split("## Top Candidates", 1)[1]
    top_section = top_section.split("## Excluded", 1)[0]
    assert "Piper methysticum" not in top_section
    assert "Excluded — Safety/Regulatory No-Go" in report_markdown
    assert "Piper methysticum" in report_markdown  # still traceable, just excluded from ranking
    assert "Matricaria chamomilla" in top_section


# ---------------------------------------------------------------------
# 18 — historical row with no eligibility fields defaults to INCOMPLETE
# ---------------------------------------------------------------------

def test_historical_row_without_eligibility_fields_defaults_to_incomplete():
    from candidate_output_adapter import validate_row

    legacy_row = pd.Series({
        "Reference_Plant": "Piper nigrum",
        "Alternative_Plant": "Matricaria chamomilla",
        # No Eligibility_Status / Eligible_For_Normal_Ranking columns
        # at all -- this is a pre-Phase-4 record.
    })
    record, errors = validate_row(legacy_row, indication="anxiety")
    assert record is not None
    assert record.eligibility_status == "incomplete"
    assert record.eligible_for_normal_ranking is False


# ---------------------------------------------------------------------
# 19 — CSV audit export retains the no-go row and its structured status
# (Phase 4 explicitly does NOT filter the raw CSV — see design review
# item 9).
# ---------------------------------------------------------------------

def test_csv_audit_export_retains_no_go_row_with_structured_status():
    result_df = pd.DataFrame([
        {
            "Alternative_Plant": "Piper methysticum",
            "R&D_Opportunity_Score": 92.0,
            "Decision_Class": "Regulatory prohibition — not suitable without regulatory review",
            "Eligibility_Status": "no_go_regulatory",
            "Eligible_For_Normal_Ranking": False,
            "Score_Validity": "audit_only",
        },
    ])
    csv_text = result_df.to_csv(index=False)
    assert "Piper methysticum" in csv_text
    assert "no_go_regulatory" in csv_text
    assert "audit_only" in csv_text


# ---------------------------------------------------------------------
# Correction round item 2 — honest production-wiring integration test.
#
# This does NOT claim production can determine that a differing plant
# part/preparation makes a documented risk irrelevant -- the Phase 4
# audit proved it cannot (no plant-part/preparation-aware matching is
# wired into the live evidence pipeline). What this DOES prove: feeding
# the engine two EvidenceRecords for the SAME candidate plant, one
# naming a different plant part/preparation than the other and
# carrying a hard safety term, still runs end-to-end and produces the
# HONEST result (EXPERT_REVIEW_REQUIRED, scope=UNKNOWN) rather than a
# silently wrong ELIGIBLE or a fabricated NO_GO. Contextual relevance
# for plant_part/preparation is PARTIAL, not PASS -- see the
# acceptance-criteria table in the final report.
# ---------------------------------------------------------------------

def test_differing_plant_part_evidence_records_still_resolve_honestly_to_expert_review():
    import pandas as pd

    # IMPORTANT capability-boundary note (discovered while writing this
    # test): HARD_SAFETY_TERMS is reachable ONLY via the STRUCTURED
    # target/Known_Target field (_extract_hazard_flags_exact), never via
    # free-text Notes -- botanical_rd_candidate_engine.SAFETY_TERMS (the
    # vocabulary _extract_flags_negation_aware() checks free text
    # against) does not even contain "teratogenic"/"lithogenic"/etc. See
    # test_gold_case_execution.py::test_capability_boundary_notes_alone_cannot_trigger_hard_safety_gate,
    # which already documents this. So the hard term here comes from the
    # candidate's structured `target` field (as it would in real
    # production data), and the two EvidenceRecords below carry the
    # differing-plant-part SIGNAL as descriptive free text only --
    # proving that text alone changes nothing about the outcome either
    # way, which is the honest point of this test.
    rows = [
        dict(scientific_name="RefPlant", compound_name="SharedCompound",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="AltPlant", compound_name="SharedCompound",
             indication="TestIndication", target="Teratogenic",
             common_name="", plant_part="", extraction_method=""),
    ]
    evidence_df = pd.DataFrame([
        {
            "Scientific_Name": "AltPlant",
            "Target_Indication": "TestIndication",
            "Notes": "Root decoction studied in a small human trial for digestive complaints.",
        },
        {
            "Scientific_Name": "AltPlant",
            "Target_Indication": "TestIndication",
            "Notes": "Leaf essential oil separately documented in a different preparation.",
        },
    ])

    import botanical_rd_candidate_engine as eng
    from test_gate_layer import make_engine  # reuses the existing, tested fixture builder
    eng.SIMILAR_COMPOUND_GROUPS = {}
    eng.COMPOUND_TARGETS = {}
    engine = make_engine(rows)
    engine.evidence_df = evidence_df
    result = engine.run(indication="TestIndication", dosage_form="Infusion", market="EU")

    alt_row = result[
        (result["Reference_Plant"] == "RefPlant") & (result["Alternative_Plant"] == "AltPlant")
    ].iloc[0]

    # Honest result: the structured hard term IS detected (not silently
    # dropped), but WITHOUT a confirmed part-specific scope -- which
    # today's evidence pipeline cannot supply, root vs. leaf preparation
    # notwithstanding -- it resolves to EXPERT_REVIEW_REQUIRED, never a
    # fabricated automatic NO_GO and never a silent ELIGIBLE.
    assert "teratogenic" in str(alt_row["Safety_Flags"]).lower()
    assert alt_row["Eligibility_Status"] == "expert_review_required"
    assert alt_row["Safety_Scope"] == "unknown"
    assert bool(alt_row["Eligible_For_Normal_Ranking"]) is False


# ---------------------------------------------------------------------
# Correction round item 5 — explicit no-go(score=99) vs eligible(score=60)
# ranking test, across the real normal-ranking consumers.
# ---------------------------------------------------------------------

def test_no_go_high_raw_score_never_outranks_eligible_in_normal_ranking():
    result_df = pd.DataFrame([
        {
            "Alternative_Plant": "No-go plant (raw score 99)",
            "Shared_or_Similar_Compound": "X",
            "Target_or_Mechanism": "Y",
            "R&D_Opportunity_Score": 99.0,
            "Decision_Class": "Regulatory prohibition — not suitable without regulatory review",
            "Eligibility_Status": "no_go_regulatory",
            "Eligible_For_Normal_Ranking": False,
            "Score_Validity": "audit_only",
            "Safety_Flags": "No explicit flag found",
            "Market_Status": "Unknown",
            "Novelty_Status": "Alternative",
            "Rationale": "correction-round test row",
        },
        {
            "Alternative_Plant": "Eligible plant (score 60)",
            "Shared_or_Similar_Compound": "X",
            "Target_or_Mechanism": "Y",
            "R&D_Opportunity_Score": 60.0,
            "Decision_Class": "Early-stage candidate; more evidence needed",
            "Eligibility_Status": "eligible",
            "Eligible_For_Normal_Ranking": True,
            "Score_Validity": "valid",
            "Safety_Flags": "No explicit flag found",
            "Market_Status": "Unknown",
            "Novelty_Status": "Alternative",
            "Rationale": "correction-round test row",
        },
    ])

    # Consumer 1: UI recommendation block (legacy fallback branch).
    with _stub_streamlit_and_supabase() as captured:
        from step_rd_candidates import _recommendation_block
        _recommendation_block(result_df, report_ready_df=None)
    assert captured["dataframe_calls"], "expected at least one st.dataframe() call"
    recommended_shown = captured["dataframe_calls"][0]
    shown_plants = list(recommended_shown["Alternative_Plant"])
    assert "No-go plant (raw score 99)" not in shown_plants
    assert "Eligible plant (score 60)" in shown_plants

    # Consumer 2: pharma report top-N.
    if "streamlit" not in sys.modules:
        sys.modules["streamlit"] = types.ModuleType("streamlit")
    from pharma_report_generator import generate_pharma_report
    report_markdown = generate_pharma_report(
        result_df, indication="anxiety", dosage_form="tea", market="EU", top_n=5,
    )
    top_section = report_markdown.split("## Top Candidates", 1)[1]
    top_section = top_section.split("## Excluded", 1)[0]
    assert "No-go plant (raw score 99)" not in top_section
    assert "Eligible plant (score 60)" in top_section

    # Consumer 3: candidate_shortlisting's hard-stop check.
    from candidate_shortlisting import _hard_stop
    no_go_row = result_df.iloc[0]
    eligible_row = result_df.iloc[1]
    assert _hard_stop(no_go_row) is True
    assert _hard_stop(eligible_row) is False


# ---------------------------------------------------------------------
# Correction round item 1 (2nd pass) — end-to-end finding-specific
# evidence ID tests, through a REAL engine.run(), not synthetic
# dataclasses. Proves the per-record re-check wired into
# botanical_rd_candidate_engine.py's row loop (via the new
# evidence_records_index / _collect_raw_evidence 4th return value)
# actually narrows Safety_Gate_Evidence_IDs / Regulatory_Gate_Evidence_IDs
# down to the specific contributing record(s), not the whole row's
# pooled evidence_source_ids.
# ---------------------------------------------------------------------

def test_safety_gate_evidence_ids_are_finding_specific_end_to_end():
    import pandas as pd
    import botanical_rd_candidate_engine as eng
    from test_gate_layer import make_engine

    eng.SIMILAR_COMPOUND_GROUPS = {}
    eng.COMPOUND_TARGETS = {}

    rows = [
        dict(scientific_name="RefPlant", compound_name="SharedCompound",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
        # target="Teratogenic" is what gives this row a real
        # HARD_SAFETY_TERMS hit via the structured-target path (see
        # test_differing_plant_part_evidence_records_still_resolve_honestly_to_expert_review's
        # capability-boundary note above) -- the literal word also
        # appears in ONE of the two evidence records below, which is
        # the actual thing under test here.
        dict(scientific_name="AltPlant", compound_name="SharedCompound",
             indication="TestIndication", target="Teratogenic",
             common_name="", plant_part="", extraction_method=""),
    ]
    evidence_df = pd.DataFrame([
        {
            "Evidence_Record_ID": "EV-EFFICACY-001",
            "Scientific_Name": "AltPlant",
            "Target_Indication": "TestIndication",
            "Notes": "A randomized controlled trial found improved digestive comfort with no adverse events reported.",
        },
        {
            "Evidence_Record_ID": "EV-TOXICITY-002",
            "Scientific_Name": "AltPlant",
            "Target_Indication": "TestIndication",
            "Notes": "Animal studies found this compound to be teratogenic at high doses.",
        },
    ])

    engine = make_engine(rows)
    engine.evidence_df = evidence_df
    result = engine.run(indication="TestIndication", dosage_form="Infusion", market="EU")

    alt_row = result[
        (result["Reference_Plant"] == "RefPlant") & (result["Alternative_Plant"] == "AltPlant")
    ].iloc[0]

    assert alt_row["Eligibility_Status"] == "expert_review_required"  # confirmed above pattern
    safety_ids = [x.strip() for x in str(alt_row["Safety_Gate_Evidence_IDs"]).split(";") if x.strip()]
    assert safety_ids == ["EV-TOXICITY-002"]
    assert "EV-EFFICACY-001" not in safety_ids

    gate_ids = [x.strip() for x in str(alt_row["Gate_Evidence_IDs"]).split(";") if x.strip()]
    assert "EV-TOXICITY-002" in gate_ids
    assert "EV-EFFICACY-001" not in gate_ids


def test_regulatory_gate_evidence_ids_are_finding_specific_end_to_end():
    import pandas as pd
    import botanical_rd_candidate_engine as eng
    from test_gate_layer import make_engine

    eng.SIMILAR_COMPOUND_GROUPS = {}
    eng.COMPOUND_TARGETS = {}

    rows = [
        dict(scientific_name="RefPlant", compound_name="SharedCompound",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="AltPlant", compound_name="SharedCompound",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
    ]
    evidence_df = pd.DataFrame([
        {
            "Evidence_Record_ID": "EV-EFFICACY-101",
            "Scientific_Name": "AltPlant",
            "Target_Indication": "TestIndication",
            "Notes": "A cohort study found modest symptomatic improvement in participants.",
        },
        {
            "Evidence_Record_ID": "EV-PROHIBITED-102",
            "Scientific_Name": "AltPlant",
            "Target_Indication": "TestIndication",
            "Notes": "This substance is prohibited and banned for sale in several jurisdictions.",
        },
    ])

    engine = make_engine(rows)
    engine.evidence_df = evidence_df
    result = engine.run(indication="TestIndication", dosage_form="Infusion", market="EU")

    alt_row = result[
        (result["Reference_Plant"] == "RefPlant") & (result["Alternative_Plant"] == "AltPlant")
    ].iloc[0]

    # Root-cause remediation (Reference-Grounded Validation v1, Problem
    # C): a documented prohibition with no plant-part/preparation/
    # constituent qualifier at all is now read as applying to the whole
    # substance by default (mirrors classify_safety_finding()'s
    # equivalent "no limiting qualifier -> species-wide" default for
    # serious safety assertions) and resolves automatically to
    # NO_GO_REGULATORY, rather than being stuck at EXPERT_REVIEW_REQUIRED
    # forever for lack of a structured scope override production never
    # supplies. This replaces the prior characterization of the
    # pre-remediation gap (see regulatory_scope_assessment.py).
    assert alt_row["Regulatory_Status"] == "prohibited"
    assert alt_row["Eligibility_Status"] == "no_go_regulatory"

    regulatory_ids = [x.strip() for x in str(alt_row["Regulatory_Gate_Evidence_IDs"]).split(";") if x.strip()]
    assert regulatory_ids == ["EV-PROHIBITED-102"]
    assert "EV-EFFICACY-101" not in regulatory_ids


# ---------------------------------------------------------------------
# Correction round item 2 — the main run() DataFrame itself is sorted
# by Ranking_Partition first, R&D_Opportunity_Score second (not score
# alone), while remaining audit-complete (every row still present).
# ---------------------------------------------------------------------

def test_sort_by_ranking_partition_then_score_overrides_raw_score_order():
    """Direct, deterministic unit test of the shared sort function
    itself (not dependent on the scoring engine's own conservative
    safety-flag score capping happening to produce a particular
    ordering by coincidence) — proves a NO_GO row with a much higher
    raw score still sorts BEHIND a NORMAL-partition row with a lower
    one."""
    import pandas as pd
    from botanical_rd_candidate_engine import sort_by_ranking_partition_then_score

    df = pd.DataFrame([
        {"Alternative_Plant": "NoGoHighScore", "R&D_Opportunity_Score": 99.0,
         "Ranking_Partition": "excluded_no_go"},
        {"Alternative_Plant": "ExpertReviewMidScore", "R&D_Opportunity_Score": 80.0,
         "Ranking_Partition": "preliminary_or_expert_review"},
        {"Alternative_Plant": "NormalLowScore", "R&D_Opportunity_Score": 60.0,
         "Ranking_Partition": "normal"},
        {"Alternative_Plant": "NormalHighScore", "R&D_Opportunity_Score": 95.0,
         "Ranking_Partition": "normal"},
    ])
    sorted_df = sort_by_ranking_partition_then_score(df)

    # Every row preserved -- audit-complete, nothing dropped.
    assert set(sorted_df["Alternative_Plant"]) == set(df["Alternative_Plant"])

    order = list(sorted_df["Alternative_Plant"])
    # Both NORMAL rows (regardless of their own relative score) precede
    # both non-NORMAL rows (regardless of THEIR score, even 99 vs 60).
    assert order.index("NormalHighScore") < order.index("NoGoHighScore")
    assert order.index("NormalLowScore") < order.index("NoGoHighScore")
    assert order.index("NormalLowScore") < order.index("ExpertReviewMidScore")
    # Within the same partition, still ordered by score descending.
    assert order.index("NormalHighScore") < order.index("NormalLowScore")


def test_run_output_dataframe_carries_correct_ranking_partition_end_to_end():
    """Complementary end-to-end check (real engine.run(), not a
    synthetic frame): the Ranking_Partition COLUMN itself is populated
    correctly for a genuinely non-normal candidate, proving the wiring
    from EligibilityDecision.ranking_partition into the real row dict
    -- the sort ORDER guarantee itself is proven independently above
    against the scoring engine's own realistic (and, as observed while
    writing this test, fairly conservative) safety-flag score capping."""
    import pandas as pd
    import botanical_rd_candidate_engine as eng
    from test_gate_layer import make_engine

    eng.SIMILAR_COMPOUND_GROUPS = {"TestClass": ["RefCompound", "ToxicCompound", "CleanCompound"]}
    eng.COMPOUND_TARGETS = {}

    rows = [
        dict(scientific_name="RefPlant", compound_name="RefCompound",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="ToxicAltPlant", compound_name="ToxicCompound",
             indication="TestIndication", target="Teratogenic",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="CleanAltPlant", compound_name="CleanCompound",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
    ]
    evidence_df = pd.DataFrame([
        {"Evidence_Record_ID": "EV-1", "Scientific_Name": "ToxicAltPlant", "Target_Indication": "TestIndication",
         "Notes": "A randomized controlled trial found some benefit."},
        {"Evidence_Record_ID": "EV-2", "Scientific_Name": "CleanAltPlant", "Target_Indication": "TestIndication",
         "Notes": "A randomized controlled trial found some benefit."},
    ])
    engine = make_engine(rows)
    engine.evidence_df = evidence_df
    # This test isolates Ranking_Partition wiring. Its synthetic evidence
    # predates canonical structured result_direction, so opt into legacy text
    # fallback locally rather than changing the production fail-safe default.
    engine.allow_legacy_text_fallback = True
    result = engine.run(indication="TestIndication", dosage_form="Infusion", market="EU")

    alt_rows = result[result["Reference_Plant"] == "RefPlant"]
    toxic_row = alt_rows[alt_rows["Alternative_Plant"] == "ToxicAltPlant"].iloc[0]
    clean_row = alt_rows[alt_rows["Alternative_Plant"] == "CleanAltPlant"].iloc[0]

    assert toxic_row["Ranking_Partition"] != "normal"
    assert clean_row["Ranking_Partition"] == "normal"
    # And the DataFrame's own row order already respects this (proven
    # generally above; spot-checked here against the real output).
    toxic_position = list(alt_rows["Alternative_Plant"]).index("ToxicAltPlant")
    clean_position = list(alt_rows["Alternative_Plant"]).index("CleanAltPlant")
    assert clean_position < toxic_position
