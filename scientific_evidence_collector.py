import os
from datetime import datetime, timedelta, timezone

import pandas as pd
from supabase import create_client

from scientific_evidence_engine import collect_scientific_evidence


CACHE_DAYS = 30


def get_supabase_client():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")

    if not url or not key:
        raise ValueError("SUPABASE_URL or SUPABASE_KEY is missing.")

    return create_client(url, key)


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _is_fresh(created_at, cache_days=CACHE_DAYS):
    if not created_at:
        return False

    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        return created >= datetime.now(timezone.utc) - timedelta(days=cache_days)
    except Exception:
        return False


def load_cached_evidence(plant, indication, market="European Union"):
    supabase = get_supabase_client()

    response = (
        supabase
        .table("scientific_evidence")
        .select("*")
        .eq("plant", plant)
        .eq("indication", indication)
        .eq("market", market)
        .execute()
    )

    rows = response.data or []

    fresh_rows = [
        r for r in rows
        if _is_fresh(r.get("created_at"))
    ]

    return fresh_rows


def save_evidence_records(plant, indication, market, evidence_output):
    supabase = get_supabase_client()

    records = evidence_output.get("records", [])
    decision = evidence_output.get("decision", {})

    saved = 0

    for r in records:
        row = {
            "plant": plant,
            "indication": indication,
            "market": market,

            "source": r.get("source", ""),
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "abstract": r.get("abstract", ""),
            "year": str(r.get("year", "")),

            "trust_score": float(r.get("trust_score", 0) or 0),
            "evidence_score": float(r.get("evidence_score", 0) or 0),
            "final_source_score": float(r.get("final_source_score", 0) or 0),
            "evidence_flags": r.get("evidence_flags", ""),

            "decision_class": decision.get("decision_class", ""),
            "overall_evidence_score": float(decision.get("overall_evidence_score", 0) or 0),
            "clinical_score": float(decision.get("clinical_score", 0) or 0),
            "chemistry_score": float(decision.get("chemistry_score", 0) or 0),
            "regulatory_score": float(decision.get("regulatory_score", 0) or 0),
            "final_scientific_score": float(decision.get("final_scientific_score", 0) or 0),
            "decision_reason": decision.get("decision_reason", ""),

            "extra": r.get("extra", {}),
            "created_at": _now_iso(),
        }

        try:
            supabase.table("scientific_evidence").insert(row).execute()
            saved += 1
        except Exception:
            pass

    return saved


def collect_or_load_evidence(
    plant,
    indication,
    compounds=None,
    market="European Union",
    max_results=8,
    force_refresh=False,
):
    if not force_refresh:
        cached = load_cached_evidence(
            plant=plant,
            indication=indication,
            market=market,
        )

        if cached:
            return {
                "plant": plant,
                "indication": indication,
                "market": market,
                "from_cache": True,
                "record_count": len(cached),
                "records": cached,
                "decision": summarize_cached_decision(cached),
            }

    evidence_output = collect_scientific_evidence(
        plant=plant,
        indication=indication,
        compounds=compounds or [],
        market=market,
        max_results=max_results,
    )

    saved_count = save_evidence_records(
        plant=plant,
        indication=indication,
        market=market,
        evidence_output=evidence_output,
    )

    evidence_output["from_cache"] = False
    evidence_output["saved_count"] = saved_count

    return evidence_output


def summarize_cached_decision(rows):
    if not rows:
        return {
            "overall_evidence_score": 0,
            "clinical_score": 0,
            "chemistry_score": 0,
            "regulatory_score": 0,
            "final_scientific_score": 0,
            "decision_class": "No cached evidence",
            "decision_reason": "No cached evidence records found.",
        }

    df = pd.DataFrame(rows)

    def mean_col(col):
        if col not in df.columns:
            return 0
        return round(pd.to_numeric(df[col], errors="coerce").fillna(0).mean(), 1)

    decision_classes = [
        x for x in df.get("decision_class", pd.Series(dtype=str)).dropna().astype(str).tolist()
        if x
    ]

    decision_class = decision_classes[0] if decision_classes else "Cached evidence available"

    return {
        "overall_evidence_score": mean_col("overall_evidence_score"),
        "clinical_score": mean_col("clinical_score"),
        "chemistry_score": mean_col("chemistry_score"),
        "regulatory_score": mean_col("regulatory_score"),
        "final_scientific_score": mean_col("final_scientific_score"),
        "decision_class": decision_class,
        "decision_reason": "Loaded from cached scientific evidence database.",
    }


def evidence_records_to_dataframe(records):
    if not records:
        return pd.DataFrame()

    return pd.DataFrame(records)
