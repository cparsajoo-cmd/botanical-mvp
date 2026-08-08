"""Structured causal trace for authoritative plant-level decisions.

Phase 6: additive only.  This module never changes scoring, gating, ranking,
or UI behaviour.  It converts already-computed authoritative fields and the
row audit into a machine-readable decision explanation.  No LLM/free-text
inference is used; human summaries are deterministic templates over observed
structured fields only.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from score_breakdown_schema import parse_score_breakdown

RULE_VERSION = "decision-explainability-v1"
EVIDENCE_SCHEMA_VERSION = "evidence-record-phase2"
COMPONENT_MAX = {
    "Indication Relevance": 35.0,
    "Scientific Evidence": 30.0,
    "Compound Support": 5.0,
    "Mechanism Support": 10.0,
    "Safety & Regulatory": 15.0,
    "Novelty & Market": 5.0,
}


def _ids(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(x).strip() for x in value if str(x).strip()]
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        return []
    return [p.strip() for p in text.split(";") if p.strip()]


def _canonical_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _rejection_reason(audit_row: dict) -> str:
    reasons = str(audit_row.get("Scientific_Triage_Reasons") or "").lower()
    dosage = str(audit_row.get("Dosage_Form_Compatibility") or "").lower()
    if "duplicate" in reasons:
        return "Duplicate"
    if dosage == "mismatch" or "preparation" in reasons and "mismatch" in reasons:
        return "Wrong preparation"
    if "indication" in reasons and ("no candidate-specific" in reasons or "no direct" in reasons or "irrelevant" in reasons):
        return "Wrong indication"
    if bool(audit_row.get("Hard_Stop_Present", False)):
        return "Safety/regulatory hard stop"
    if "protocol" in reasons:
        return "Protocol"
    if "review citation" in reasons:
        return "Review citation"
    status = str(audit_row.get("Scientific_Triage_Status") or "")
    if status == "Excluded":
        return str(audit_row.get("Scientific_Triage_Reasons") or "Excluded by scientific triage")
    return "Not used by an authoritative score component"


def _missing_data(row: dict) -> list[dict]:
    out: list[dict] = []
    safety_status = str(row.get("Safety_Data_Status") or "").strip().lower()
    if safety_status in {"not_assessed", "not assessed"}:
        out.append({"field": "safety", "state": "No Evidence", "detail": "Safety_Data_Status=not_assessed"})
    reg = str(row.get("Regulatory_Barriers") or "").strip().lower()
    if "search not performed" in reg:
        out.append({"field": "regulatory", "state": "Search Not Performed", "detail": "Regulatory_Barriers reports search not performed"})
    for field in ("Source_Failures", "Source_Failure", "Connector_Failures"):
        value = row.get(field)
        if value not in (None, "", [], (), {}):
            out.append({"field": field, "state": "Source Unavailable", "detail": value})
    return out




def _safety_assertions(row: dict) -> list[dict]:
    raw = row.get("Safety_Assertions")
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if not isinstance(raw, str) or not raw.strip():
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return [x for x in data if isinstance(x, dict)] if isinstance(data, list) else []

def _gate_attribution(row: dict) -> list[dict]:
    gates = []
    gate_results = row.get("Gate_Results")
    if isinstance(gate_results, dict):
        for name, value in gate_results.items():
            if not isinstance(value, dict):
                continue
            gates.append({
                "gate": name,
                "status": str(value.get("status") or ""),
                "reason": value.get("reason") or "",
                "evidence_ids": _ids(value.get("evidence")),
                "authority": value.get("authority"),
                "severity": value.get("severity"),
                "override": False,
                "expert_review_required": "expert" in str(value.get("reason") or "").lower(),
            })
    # Phase-4 structured eligibility attribution, if present on the merged row.
    gate_type = str(row.get("Gate_Type") or "").strip()
    if gate_type and gate_type != "none":
        ids = _ids(row.get("Gate_Evidence_IDs"))
        safety_assertions = _safety_assertions(row)
        gates.append({
            "gate": f"eligibility:{gate_type}",
            "status": str(row.get("Eligibility_Status") or ""),
            "reason": row.get("Gate_Reason") or "",
            "evidence_ids": ids,
            "authority": sorted({str(a.get("authority")) for a in safety_assertions if a.get("authority")}) or None,
            "severity": row.get("Safety_Severity"),
            "safety_confidence": row.get("Safety_Decision_Confidence"),
            "evidence_conflict": bool(row.get("Safety_Evidence_Conflict", False)),
            "severity_rule": row.get("Safety_Severity_Rule"),
            "assertion_trace": safety_assertions,
            "override": bool(row.get("Hard_No_Go", False)),
            "expert_review_required": "expert" in str(row.get("Eligibility_Status") or "").lower(),
        })
    return gates


def _rules(row: dict) -> list[dict]:
    rules = [
        {"rule_id": "score.authoritative_six_component_sum", "applied": True, "changed_decision": False, "override": False},
        {"rule_id": "ranking.overall_score_desc", "applied": True, "changed_decision": False, "override": False},
    ]
    status = str(row.get("Scientific_Triage_Status") or "")
    if status == "Excluded":
        rules.append({"rule_id": "triage.exclusion", "applied": True, "changed_decision": True, "override": True, "reason": row.get("Why_Selected_or_Rejected") or row.get("Triage_Gate_Reasons") or ""})
    elif status == "Exploratory":
        rules.append({"rule_id": "triage.exploratory_cap", "applied": True, "changed_decision": True, "override": False, "reason": row.get("Triage_Gate_Reasons") or ""})
    if row.get("Duplicate_Pruning_Note"):
        rules.append({"rule_id": "ranking.near_duplicate_congener_pruning", "applied": True, "changed_decision": True, "override": True, "reason": row.get("Duplicate_Pruning_Note")})
    if _safety_assertions(row):
        rules.append({
            "rule_id": str(row.get("Safety_Severity_Rule") or "safety.structured_assertion"),
            "applied": True,
            "changed_decision": str(row.get("Safety_Severity") or "").lower() == "severe",
            "override": bool(row.get("Hard_No_Go", False)),
            "reason": row.get("Gate_Reason") or "Structured safety assertion evaluation.",
        })
    return rules


def build_candidate_explanation(row: dict, audit_rows: list[dict] | None = None, *, generated_time: str | None = None, decision_metadata: dict | None = None) -> dict:
    """Build a structured explanation from observed fields only."""
    generated_time = generated_time or datetime.now(timezone.utc).isoformat()
    breakdown = parse_score_breakdown(row.get("Score_Breakdown"))
    component_ids = row.get("Component_Source_Record_IDs") or {}
    components = []
    for name, value in breakdown.items():
        maximum = COMPONENT_MAX.get(name)
        components.append({
            "component": name,
            "raw_value": float(value),
            "weight": (maximum / 100.0) if maximum is not None else None,
            "contribution": float(value),
            "maximum_possible_contribution": maximum,
            "evidence_ids": list(component_ids.get(name, []) or []),
            "penalties": [],
            "reason": "authoritative component value computed by candidate_shortlisting",
        })

    component_sum = round(sum(float(c["contribution"]) for c in components), 10)
    final_score = float(row.get("Overall_Score", row.get("R&D_Opportunity_Score", 0)) or 0)

    used_by_id: dict[str, list[str]] = {}
    for c in components:
        for evidence_id in c["evidence_ids"]:
            used_by_id.setdefault(str(evidence_id), []).append(c["component"])

    evidence_contributions = []
    seen = set()
    for audit in audit_rows or []:
        ids = _ids(audit.get("Source_Record_IDs")) or _ids(audit.get("Evidence_Record_ID"))
        for evidence_id in ids:
            if evidence_id in seen:
                continue
            seen.add(evidence_id)
            components_used = used_by_id.get(evidence_id, [])
            entry = {
                "evidence_id": evidence_id,
                "entered_score": bool(components_used),
                "components": components_used,
                # An additive per-record point allocation does not exist in the
                # current nonlinear model.  Never fabricate one.  Scientific
                # evidence marginal effects, when available, are attached below.
                "score_points": None,
                "score_effect_method": "not_uniquely_additive",
                "excluded_reason": None if components_used else _rejection_reason(audit),
            }
            evidence_contributions.append(entry)

    # Phase-5 scientific evidence trace may carry exact leave-one-out effects.
    for trace in row.get("Scientific_Evidence_Contributions", []) or []:
        eid = str(trace.get("evidence_id") or "")
        if not eid:
            continue
        match = next((x for x in evidence_contributions if x["evidence_id"] == eid), None)
        if match is None:
            match = {"evidence_id": eid, "entered_score": True, "components": ["Scientific Evidence"], "excluded_reason": None}
            evidence_contributions.append(match)
        match["score_points"] = trace.get("marginal_score_effect")
        match["score_effect_method"] = "leave_one_evidence_out"
        match["scientific_trace"] = trace

    gates = _gate_attribution(row)
    missing = _missing_data(row)
    rules = _rules(row)
    overrides = [r for r in rules if r.get("override")] + [g for g in gates if g.get("override")]
    all_evidence_ids = sorted(set(used_by_id) | {x["evidence_id"] for x in evidence_contributions})

    metadata = decision_metadata or {}
    config_material = {
        "scoring_model_version": row.get("Scoring_Model_Version") or metadata.get("scoring_model_version"),
        "scoring_config_version": row.get("Scoring_Config_Version"),
        "rule_version": RULE_VERSION,
        "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
        "breakdown_maxima": COMPONENT_MAX,
    }

    explanation = {
        "candidate_id": row.get("Candidate_ID") or row.get("Alternative_Plant"),
        "final_decision": row.get("Go_Investigate_Hold_NoGo") or row.get("Decision_Class_AH") or row.get("Scientific_Triage_Status"),
        "eligibility_status": row.get("Eligibility_Status") or row.get("Scientific_Triage_Status"),
        "raw_score": final_score,
        "final_score": final_score,
        "score_components": components,
        "score_reconciliation": {"component_sum": component_sum, "final_score": final_score, "exact": abs(component_sum - final_score) < 1e-9},
        "evidence_contributions": evidence_contributions,
        "applied_gates": gates,
        "overrides": overrides,
        "missing_data": missing,
        "source_failures": [x for x in missing if x["state"] == "Source Unavailable"],
        "evidence_ids": all_evidence_ids,
        "rules_applied": rules,
        "scoring_version": config_material["scoring_model_version"],
        "rule_version": RULE_VERSION,
        "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
        "data_snapshot": metadata.get("evidence_snapshot_id"),
        "generated_time": generated_time,
        "execution_time": metadata.get("decision_timestamp") or generated_time,
        "configuration_hash": _canonical_hash(config_material),
    }
    explanation["human_summary"] = build_human_summary(explanation)
    return explanation


def build_human_summary(explanation: dict) -> str:
    """Deterministic summary: every sentence is triggered by structured data."""
    sentences: list[str] = []
    score = explanation.get("final_score")
    if score is not None:
        sentences.append(f"Final score is {score} from {len(explanation.get('score_components', []))} recorded score components.")
    used = [e for e in explanation.get("evidence_contributions", []) if e.get("entered_score")]
    rejected = [e for e in explanation.get("evidence_contributions", []) if not e.get("entered_score")]
    if used:
        sentences.append(f"{len(used)} traceable evidence record(s) are linked to at least one score component.")
    if rejected:
        counts: dict[str, int] = {}
        for e in rejected:
            reason = e.get("excluded_reason") or "Unspecified structured reason"
            counts[reason] = counts.get(reason, 0) + 1
        detail = ", ".join(f"{n} {reason}" for reason, n in sorted(counts.items()))
        sentences.append(f"Excluded evidence: {detail}.")
    failed_gates = [g for g in explanation.get("applied_gates", []) if any(x in str(g.get("status", "")).lower() for x in ("fail", "no_go"))]
    if failed_gates:
        sentences.append(f"{len(failed_gates)} gate(s) recorded a blocking outcome.")
    if explanation.get("source_failures"):
        sentences.append("At least one source was unavailable in this execution; the affected assessment is incomplete.")
    if explanation.get("missing_data") and not explanation.get("source_failures"):
        sentences.append("The explanation records incomplete or unperformed data collection for at least one assessment area.")
    return " ".join(sentences)


def decision_diff(old: dict, new: dict) -> dict:
    """Compare two candidate explanations without recomputing either decision."""
    old_e = set(old.get("evidence_ids", [])); new_e = set(new.get("evidence_ids", []))
    old_rules = {r.get("rule_id") for r in old.get("rules_applied", [])}; new_rules = {r.get("rule_id") for r in new.get("rules_applied", [])}
    old_gates = {(g.get("gate"), str(g.get("status"))) for g in old.get("applied_gates", [])}; new_gates = {(g.get("gate"), str(g.get("status"))) for g in new.get("applied_gates", [])}
    old_components = {c.get("component"): c.get("contribution") for c in old.get("score_components", [])}
    new_components = {c.get("component"): c.get("contribution") for c in new.get("score_components", [])}
    return {
        "score_changed": old.get("final_score") != new.get("final_score"),
        "score_delta": round(float(new.get("final_score", 0)) - float(old.get("final_score", 0)), 10),
        "component_changes": {k: {"old": old_components.get(k), "new": new_components.get(k)} for k in sorted(set(old_components) | set(new_components)) if old_components.get(k) != new_components.get(k)},
        "evidence_added": sorted(new_e - old_e),
        "evidence_removed": sorted(old_e - new_e),
        "rule_added": sorted(x for x in new_rules - old_rules if x),
        "rule_removed": sorted(x for x in old_rules - new_rules if x),
        "weight_changed": old.get("configuration_hash") != new.get("configuration_hash"),
        "gate_changed": old_gates != new_gates,
        "decision_changed": old.get("final_decision") != new.get("final_decision"),
        "old_decision": old.get("final_decision"),
        "new_decision": new.get("final_decision"),
    }


def attach_decision_explanations(report_ready_df, triage_audit_df, *, decision_metadata: dict | None = None):
    """Return a copy with one Decision_Explanation dict per candidate."""
    if report_ready_df is None or getattr(report_ready_df, "empty", True):
        return report_ready_df
    out = report_ready_df.copy()
    generated = (decision_metadata or {}).get("decision_timestamp") or datetime.now(timezone.utc).isoformat()
    explanations = []
    for _, row in out.iterrows():
        plant = str(row.get("Alternative_Plant", ""))
        audit_rows = []
        if triage_audit_df is not None and not getattr(triage_audit_df, "empty", True) and "Alternative_Plant" in triage_audit_df.columns:
            audit_rows = triage_audit_df[triage_audit_df["Alternative_Plant"].astype(str) == plant].to_dict("records")
        explanations.append(build_candidate_explanation(row.to_dict(), audit_rows, generated_time=generated, decision_metadata=decision_metadata))
    out["Decision_Explanation"] = explanations
    return out
