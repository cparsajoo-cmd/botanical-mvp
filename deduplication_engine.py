import re
import pandas as pd


def _clean_text(x):
    if x is None:
        return ""
    x = str(x).lower().strip()
    x = re.sub(r"<.*?>", " ", x)
    x = re.sub(r"[^a-z0-9\s]", " ", x)
    x = re.sub(r"\s+", " ", x)
    return x


def _make_dedup_key(row):
    url = _clean_text(row.get("Source_URL", ""))
    title = _clean_text(row.get("Source_Title", ""))
    plant = _clean_text(row.get("Scientific_Name", ""))
    indication = _clean_text(row.get("Target_Indication", ""))
    dosage = _clean_text(row.get("Dosage_Form", ""))

    if url:
        return f"url::{url}|{plant}|{indication}|{dosage}"

    if title:
        title_short = " ".join(title.split()[:18])
        return f"title::{title_short}|{plant}|{indication}|{dosage}"

    notes = _clean_text(row.get("Notes", ""))
    notes_short = " ".join(notes.split()[:25])
    return f"notes::{notes_short}|{plant}|{indication}|{dosage}"


def deduplicate_evidence(df):
    if df is None or df.empty:
        return df

    data = df.copy()
    data["_dedup_key"] = data.apply(_make_dedup_key, axis=1)

    if "Evidence_Score" not in data.columns:
        data["Evidence_Score"] = 0

    if "Evidence_Quality_Score" not in data.columns:
        data["Evidence_Quality_Score"] = 0

    data["_sort_score"] = (
        pd.to_numeric(data["Evidence_Score"], errors="coerce").fillna(0)
        + pd.to_numeric(data["Evidence_Quality_Score"], errors="coerce").fillna(0)
    )

    data = (
        data.sort_values("_sort_score", ascending=False)
        .drop_duplicates(subset=["_dedup_key"], keep="first")
        .drop(columns=["_dedup_key", "_sort_score"], errors="ignore")
        .reset_index(drop=True)
    )

    return data
