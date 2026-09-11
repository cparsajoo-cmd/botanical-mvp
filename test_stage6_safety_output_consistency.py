import ast
import json
from pathlib import Path

import pandas as pd

import candidate_shortlisting as cs
from safety_assertion_engine import (
    SAFETY_STATUS_CONCERN,
    SAFETY_STATUS_CONFLICTING,
    SAFETY_STATUS_INTERACTION,
    SAFETY_STATUS_NO_EVIDENCE,
)


def _group(status, level="SERIOUS", safety_flags=""):
    return pd.DataFrame([
        {
            "Safety_Flags": safety_flags,
            "Safety_Assertion_Status": status,
            "Safety_Concern_Level": level,
            "Safety_Evidence_IDs": "S1",
        }
    ])


def test_display_does_not_claim_no_adverse_event_when_structured_concern_exists():
    text = cs._safety_flags_display_for_plant(
        _group(SAFETY_STATUS_CONCERN), "Plantus testus"
    )
    assert "structured safety concern is present" in text.lower()
    assert "no explicit adverse event attributable" not in text.lower()


def test_display_surfaces_interaction_when_no_adverse_event_sentence_exists():
    text = cs._safety_flags_display_for_plant(
        _group(SAFETY_STATUS_INTERACTION, level="MODERATE"), "Plantus testus"
    )
    assert "interaction-type safety signal is present" in text.lower()


def test_display_surfaces_conflict_when_no_adverse_event_sentence_exists():
    text = cs._safety_flags_display_for_plant(
        _group(SAFETY_STATUS_CONFLICTING, level="MODERATE"), "Plantus testus"
    )
    assert "safety assertions are conflicting" in text.lower()


def test_display_remains_neutral_when_no_safety_evidence_exists():
    text = cs._safety_flags_display_for_plant(
        _group(SAFETY_STATUS_NO_EVIDENCE, level="UNKNOWN"), "Plantus testus"
    )
    assert "no safety-relevant evidence was retrieved" in text.lower()


def _load_reconcile_function_without_importing_streamlit():
    """Compile only the pure reconciliation function(s) from the Streamlit
    module, without importing streamlit itself.

    PROBLEM 2 FIX: _reconcile_final_decision_status() now delegates to
    _pre_gate_final_decision_status() and applies the hard evidence-
    sufficiency gate via _evidence_sufficiency_gate_triggered() (which in
    turn calls _verified_outcome_specific_human_evidence_count()) -- all
    four function defs must be present in the isolated exec namespace, not
    just the top-level one, or the extracted function raises NameError as
    soon as it tries to call them.

    PROBLEM 5 FIX: _reconcile_final_decision_status() also now applies the
    sequential formulation-compatibility gate via
    _formulation_compatibility_gate_triggered() (which in turn calls
    _verified_formulation_compatible_outcome_specific_human_evidence_
    count()) -- both new function defs must be present here too, for the
    exact same reason.
    """
    path = Path(__file__).with_name("step_rd_candidates.py")
    tree = ast.parse(path.read_text())
    needed = {
        "_pre_gate_final_decision_status",
        "_verified_outcome_specific_human_evidence_count",
        "_evidence_sufficiency_gate_triggered",
        "_verified_formulation_compatible_outcome_specific_human_evidence_count",
        "_formulation_compatibility_gate_triggered",
        "_reconcile_final_decision_status",
    }
    targets = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in needed
    ]
    assert {node.name for node in targets} == needed
    module = ast.Module(body=targets, type_ignores=[])
    ast.fix_missing_locations(module)
    ns = {"json": json}
    exec(compile(module, str(path), "exec"), ns)
    return ns["_reconcile_final_decision_status"]


def _actionable_row(**overrides):
    row = {
        "Final_Decision_Status": "GO WITH CAUTION",
        "Decision_Class_AH": "C — Alternative-source R&D candidate",
        "Relevance_Gate_Result": "passed_direct",
        "Preparation_Applicability_Class": "direct_match",
        "Evidence_Adjudication_Status": "AI_ADJUDICATION_OK",
        "Indication_Evidence_Direction": "CONSISTENT_POSITIVE",
        # PROBLEM 2 FIX: paired with Outcome_Specific_Human_Evidence_Count=1
        # below -- "NONE" would trigger a pre-existing (pre-Problem-2)
        # verified-record/strength-label contradiction check unrelated to
        # what this fixture is for.
        "Human_Evidence_Strength": "WEAK",
        "Evidence_Conflict_Level": "NONE",
        "Scientific_Evidence_Confidence": "LOW",
        "Indication_Evidence_Mode": "Direct human/clinical",
        "Direct_Indication_Evidence_Count": 5,
        # PROBLEM 2 FIX: this fixture models a plausibly-actionable
        # candidate for SAFETY-focused assertions below (serious/
        # conflicting/moderate interaction) -- it is not testing the
        # evidence-sufficiency gate at all, so it must carry a genuinely
        # verified outcome-specific human record. Left at 0 (its
        # pre-Problem-2 value), the new hard gate would itself force
        # EXPERT REVIEW REQUIRED on the moderate-interaction case for an
        # unrelated reason, masking exactly what that test checks.
        "Outcome_Specific_Human_Evidence_Count": 1,
        # PROBLEM 5 FIX: same reasoning as the Problem-2 comment above --
        # this fixture is for SAFETY-focused assertions, not formulation
        # compatibility, so its one verified record must be marked
        # formulation-compatible or the new sequential gate would itself
        # force EXPERT REVIEW REQUIRED on the moderate-interaction case
        # for an unrelated reason.
        "Verified_Formulation_Compatible_Outcome_Specific_Human_Evidence_Count": 1,
        "Outcome_Specific_Direct_Evidence_Count": 1,
        "Evidence_Adjudication_Evidence_Count": 25,
        "Safety_Flags": "No attributable adverse-event narrative was extracted.",
        "Safety_Assertion_Status": "NO_SAFETY_EVIDENCE_RETRIEVED",
        "Safety_Concern_Level": "UNKNOWN",
    }
    row.update(overrides)
    return row


def test_serious_structured_safety_cannot_remain_go_with_caution():
    reconcile = _load_reconcile_function_without_importing_streamlit()
    row = _actionable_row(
        Safety_Assertion_Status="SAFETY_CONCERN_RETRIEVED",
        Safety_Concern_Level="SERIOUS",
    )
    assert reconcile(row) == "EXPERT REVIEW REQUIRED"


def test_conflicting_safety_cannot_remain_go_with_caution_even_if_moderate():
    reconcile = _load_reconcile_function_without_importing_streamlit()
    row = _actionable_row(
        Safety_Assertion_Status="CONFLICTING_SAFETY_EVIDENCE",
        Safety_Concern_Level="MODERATE",
    )
    assert reconcile(row) == "EXPERT REVIEW REQUIRED"


def test_moderate_interaction_does_not_get_overblocked_by_new_rule():
    reconcile = _load_reconcile_function_without_importing_streamlit()
    row = _actionable_row(
        Safety_Assertion_Status="INTERACTION_SIGNAL_RETRIEVED",
        Safety_Concern_Level="MODERATE",
    )
    assert reconcile(row) == "GO WITH CAUTION"
