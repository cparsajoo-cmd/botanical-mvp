"""Backfill missing canonical scientific assertions in Supabase.

Usage:
  python backfill_canonical_assertions.py              # dry-run
  python backfill_canonical_assertions.py --apply      # write missing fields

Requirements for --apply:
- SUPABASE_URL / SUPABASE_KEY
- OPENAI_API_KEY
- migrations/0008_add_regulatory_authorization_status.sql applied if the
  authorization field will be populated by a regulatory connector later.

This script never overwrites an existing Result_Direction or Safety_Signal.
It exists because pre-canonical evidence rows otherwise remain permanently
unstructured and force the engine to abstain.
"""
from __future__ import annotations

import argparse
from database import get_supabase_client
from llm_extractor import extract_evidence_with_llm


def _blank(v):
    return v is None or not str(v).strip()


def backfill(*, apply=False, limit=None):
    supabase=get_supabase_client()
    q=supabase.table("evidence_records").select(
        "id,target_indication,dosage_form,notes,evidence_type,evidence_level,"
        "study_type,result_direction,safety_signal,plants(scientific_name)"
    )
    if limit:
        q=q.limit(int(limit))
    rows=q.execute().data or []

    stats={"scanned":0,"needs_direction":0,"extracted":0,"failed":0,"updated":0}
    failures=[]
    for item in rows:
        stats["scanned"]+=1
        if not _blank(item.get("result_direction")):
            continue
        stats["needs_direction"]+=1
        plant=item.get("plants") or {}
        record={
            "Scientific_Name":plant.get("scientific_name",""),
            "Target_Indication":item.get("target_indication",""),
            "Dosage_Form":item.get("dosage_form",""),
            "Notes":item.get("notes",""),
            "Evidence_Type":item.get("evidence_type",""),
            "Evidence_Level":item.get("evidence_level",""),
            "Study_Type":item.get("study_type",""),
        }
        try:
            out=extract_evidence_with_llm(
                record,
                selected_dosage_form=record["Dosage_Form"],
                selected_indication=record["Target_Indication"],
            )
            direction=str(out.get("result_direction") or "Unknown").strip() or "Unknown"
            safety=str(out.get("safety_signal") or "").strip()
            stats["extracted"]+=1
            if apply:
                payload={"result_direction":direction}
                if _blank(item.get("safety_signal")) and safety:
                    payload["safety_signal"]=safety
                supabase.table("evidence_records").update(payload).eq("id",item["id"]).execute()
                stats["updated"]+=1
        except Exception as exc:
            stats["failed"]+=1
            failures.append({"id":item.get("id"),"error":str(exc)})

    return stats,failures


if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--apply",action="store_true")
    ap.add_argument("--limit",type=int)
    args=ap.parse_args()
    stats,failures=backfill(apply=args.apply,limit=args.limit)
    print(stats)
    if failures:
        print("Failures:")
        for row in failures[:20]:
            print(row)
