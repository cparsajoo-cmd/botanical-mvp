"""Pure status rules for Bulk Evidence Collection progress rows."""
from __future__ import annotations


def progress_status(*, error_count: int = 0, failed_entirely: bool = False) -> str:
    if failed_entirely:
        return "failed"
    if int(error_count or 0) > 0:
        return "retry_required"
    return "done"


def is_complete_progress_row(row: dict) -> bool:
    return (
        str((row or {}).get("status") or "").strip().lower() == "done"
        and int((row or {}).get("error_count") or 0) == 0
    )
