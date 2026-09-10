"""Cross-category source-linkage consistency checks (source-traceability pass, spec §22).

Reads the *already computed* per-category resolution-status fields (Human_
Evidence_Source_Resolution_Status, Safety_Source_Resolution_Status,
Commercial_Source_Resolution_Status, Regulatory_Source_Status,
Patent_Source_Status) and rolls them into one row-level audit summary. This
module recomputes nothing scientific; it only flags when a claim's status
implies sourcing that isn't actually linked, so the disagreement is visible
in the UI/export instead of silently passing through.
"""
from __future__ import annotations

import pandas as pd

from evidence_source_resolver import _clean


def check_source_linkage_consistency(row) -> list[str]:
    """Return a list of human-readable source-linkage issues for one row."""
    issues: list[str] = []

    human_status = _clean(row.get("Human_Evidence_Source_Resolution_Status"))
    if human_status == "SOURCE_LINKAGE_INCOMPLETE":
        issues.append(
            "Human evidence count/IDs mismatch: human-evidence claim not fully source-linked."
        )

    safety_status = _clean(row.get("Safety_Source_Resolution_Status"))
    concern_level = _clean(row.get("Safety_Concern_Level"))
    if safety_status == "SOURCE_LINKAGE_INCOMPLETE":
        if concern_level and concern_level.strip().upper() == "SERIOUS":
            issues.append(
                "Safety_Concern_Level=SERIOUS but no Safety_Evidence_IDs resolve to a source."
            )
        else:
            issues.append("Safety assertion not fully source-linked.")

    commercial_status = _clean(row.get("Commercial_Source_Resolution_Status"))
    overall_commercial = _clean(row.get("Commercial_Status_Overall"))
    marketed_labels = {"VERIFIED_MARKETED", "VERIFIED_MARKETED_FOR_INDICATION",
                        "CROWDED_MARKET", "COMMERCIALLY_ESTABLISHED"}
    if commercial_status == "SOURCE_LINKAGE_INCOMPLETE" or (
        overall_commercial in marketed_labels
        and int(pd.to_numeric(row.get("Commercial_Source_Count", 0), errors="coerce") or 0) == 0
    ):
        issues.append(
            f"Commercial status {overall_commercial!r} claimed but Commercial_Source_Count is 0."
        )

    regulatory_status = _clean(row.get("Regulatory_Source_Status"))
    if regulatory_status == "ASSESSED" and int(
        pd.to_numeric(row.get("Regulatory_Source_Count", 0), errors="coerce") or 0
    ) == 0:
        issues.append("Regulatory assessment claimed as ASSESSED but Regulatory_Source_Count is 0.")

    patent_status = _clean(row.get("Patent_Source_Status"))
    if patent_status == "ASSESSED" and int(
        pd.to_numeric(row.get("Patent_Source_Count", 0), errors="coerce") or 0
    ) == 0:
        issues.append("Patent activity claimed as ASSESSED but Patent_Source_Count is 0.")

    return issues


def attach_source_linkage_consistency(report_df: pd.DataFrame) -> pd.DataFrame:
    """Append Evidence_Source_Linkage_Status / _Issues to a Stage-6 frame.

    Must run after the per-category attach_* functions it reads from.
    """
    if not isinstance(report_df, pd.DataFrame) or report_df.empty:
        return report_df

    out = report_df.copy()
    statuses = []
    issues_col = []
    for _, row in out.iterrows():
        issues = check_source_linkage_consistency(row)
        issues_col.append(" | ".join(issues) if issues else "")
        statuses.append("SOURCE_LINKAGE_INCOMPLETE" if issues else "SOURCE_LINKAGE_OK")
    out["Evidence_Source_Linkage_Status"] = statuses
    out["Evidence_Source_Linkage_Issues"] = issues_col
    return out
