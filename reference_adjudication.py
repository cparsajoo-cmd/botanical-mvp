"""External-reference adjudication overlay for validation only.

Preserves immutable source-grounded GoldCases while allowing a later, dated
scientific adjudication to supersede the *final benchmark label* when newer,
independent evidence creates a genuine conflict.  This module is not imported
by production decision logic.
"""
from __future__ import annotations
from final_decision_policy import FinalDecisionStatus

ADJUDICATION_VERSION = "reference-adjudication/1.0.0"

_ADJUDICATED = {
    "refgrounded_005_cimicifuga_racemosa_menopausal": {
        "decision": FinalDecisionStatus.EXPERT_REVIEW_REQUIRED,
        "reason": (
            "The original 2012 Cochrane review concluded evidence was insufficient, while a 2023 updated "
            "pairwise meta-analysis reported potentially beneficial effects and a 2026 systematic review found "
            "widely variable trial-reporting quality. The current evidence base is therefore not represented by a "
            "single unqualified INSUFFICIENT label."
        ),
        "adjudicated_on": "2026-08-08",
        "sources": [
            "PMID:22972105", "PMID:37192826", "PMID:41401209"
        ],
    },
    "refgrounded_023_momordica_charantia_null_fbg": {
        "decision": FinalDecisionStatus.EXPERT_REVIEW_REQUIRED,
        "reason": (
            "The 2024 systematic review/meta-analysis reported a null fasting-blood-glucose estimate, while a "
            "2025 systematic review/meta-analysis reported improved glycaemic control. Same-domain higher-level "
            "evidence is now discordant, so a frozen NULL label is no longer scientifically adequate."
        ),
        "adjudicated_on": "2026-08-08",
        "sources": ["PMID:38274207", "PMID:41280283"],
    },
}


def adjudicated_final_decision(case_id: str):
    row = _ADJUDICATED.get(case_id)
    return None if row is None else row["decision"]


def adjudication_record(case_id: str):
    return _ADJUDICATED.get(case_id)
