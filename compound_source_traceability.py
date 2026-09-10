"""Compound provenance for Stage 6.

Presentation/provenance only. Two DIFFERENT claims, kept in separate maps
per spec (never laundered into one another):

  * Plant -> Compound: "this plant contains compound X" -- sourced from
    candidate_shortlisting.py's ``Compound_Reference_Map`` (plant-level,
    aggregated from each matched row's Mechanistic_Compound_Reference_Map,
    itself read directly off the plant_compounds database row's own
    reference_title/reference_url -- see plant_compound_database.py and
    indication_candidate_discovery.py's _score_mechanistic_links()).
  * Compound -> Target/Mechanism: "compound X affects target Y" -- sourced
    from ``Compound_Target_Source_Map`` (same underlying rows, but keyed by
    compound+target so a compound with several activities does not have an
    unrelated target's reference attributed to it).

When a compound has NEITHER a real plant-compound reference nor real
compound-target references, it falls back to INTERNAL_CURATED_PROVENANCE
(the plant-compound relational database itself, with no citable external
URL) -- never a fabricated PubChem/ChEMBL/DOI link.

A caller with independently-resolved external identifiers (PubChem CID /
ChEMBL ID) not already carried on the row can still supply them via the
optional ``compound_metadata`` override, but this module invents nothing.
"""
from __future__ import annotations

import json
import re

import pandas as pd

from evidence_source_resolver import _clean, _valid_http_url


def _compound_names(value) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    text = _clean(value)
    if not text:
        return []
    return [c.strip() for c in re.split(r"[;|\n]+", text) if c.strip()]


def _as_dict(value) -> dict:
    if isinstance(value, dict):
        return value
    text = _clean(value)
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def build_compound_source_map(
    compound_names: list[str],
    *,
    plant_compound_refs: dict | None = None,
    compound_target_refs: dict | None = None,
    compound_metadata: dict | None = None,
) -> dict:
    """Build the Compound_Source_Map for one candidate's linked compounds.

    ``plant_compound_refs``: {compound_name: {"title": ..., "url": ...}} --
    the plant->compound source, already resolved this session.
    ``compound_target_refs``: {compound_name: {target_name: [{"title","url"}]}}
    -- the compound->target/mechanism sources, kept distinct.
    ``compound_metadata`` (optional, legacy override): {compound_name:
    {"reference_url"/"reference_title"/"pubchem_cid"/"chembl_id"}} -- ONLY
    used for a compound neither of the two real maps above already covers.
    """
    plant_refs = plant_compound_refs or {}
    target_refs = compound_target_refs or {}
    metadata = compound_metadata or {}

    result: dict[str, dict] = {}
    for name in compound_names:
        plant_ref = plant_refs.get(name) or plant_refs.get(name.lower()) or {}
        plant_title = _clean(plant_ref.get("title"))
        plant_url = _valid_http_url(plant_ref.get("url"))

        raw_target_sources = target_refs.get(name) or target_refs.get(name.lower()) or {}
        target_sources = {}
        for target_name, refs in raw_target_sources.items():
            cleaned = []
            for ref in refs or []:
                url = _valid_http_url(ref.get("url"))
                title = _clean(ref.get("title"))
                if url or title:
                    cleaned.append({"title": title, "url": url})
            if cleaned:
                target_sources[target_name] = cleaned

        pubchem_cid = chembl_id = None
        if not plant_url and not plant_title:
            meta = metadata.get(name) or metadata.get(name.lower()) or {}
            plant_url = _valid_http_url(meta.get("reference_url"))
            plant_title = _clean(meta.get("reference_title"))
            pubchem_cid = _clean(meta.get("pubchem_cid"))
            chembl_id = _clean(meta.get("chembl_id"))

        has_any_real_source = bool(plant_url or plant_title or target_sources or pubchem_cid or chembl_id)
        entry: dict = {
            "provenance_type": "EXTERNALLY_LINKED" if has_any_real_source else "INTERNAL_CURATED_PROVENANCE",
        }
        if plant_title or plant_url:
            entry["plant_compound_source"] = {"title": plant_title, "url": plant_url}
        elif not has_any_real_source:
            entry["plant_compound_source"] = {
                "title": "internal curated plant-compound relational database", "url": None,
            }
        if target_sources:
            entry["target_sources"] = target_sources
        if pubchem_cid:
            entry["pubchem_cid"] = pubchem_cid
        if chembl_id:
            entry["chembl_id"] = chembl_id
        result[name] = entry
    return result


def attach_compound_source_traceability(report_df: pd.DataFrame, compound_metadata: dict | None = None) -> pd.DataFrame:
    """Append Compound_* source fields to a Stage-6 frame.

    Reads Discovery_Linked_Compounds (which compounds), Compound_Reference_Map
    (plant->compound source) and Compound_Target_Source_Map (compound->target
    source) if present -- all already computed by candidate_shortlisting.py,
    no new lookup performed here. A row with no linked compounds gets zero
    counts rather than a fabricated entry.
    """
    if not isinstance(report_df, pd.DataFrame) or report_df.empty:
        return report_df

    out = report_df.copy()
    has_col = "Discovery_Linked_Compounds" in out.columns
    payloads = []
    for _, row in out.iterrows():
        names = _compound_names(row.get("Discovery_Linked_Compounds")) if has_col else []
        plant_refs = _as_dict(row.get("Compound_Reference_Map"))
        target_refs = _as_dict(row.get("Compound_Target_Source_Map"))
        source_map = build_compound_source_map(
            names,
            plant_compound_refs=plant_refs,
            compound_target_refs=target_refs,
            compound_metadata=compound_metadata,
        )

        external = [n for n, e in source_map.items() if e["provenance_type"] == "EXTERNALLY_LINKED"]
        flat_sources = []
        for entry in source_map.values():
            pcs = entry.get("plant_compound_source")
            if pcs and pcs.get("url"):
                flat_sources.append(pcs)
            for refs in (entry.get("target_sources") or {}).values():
                for ref in refs:
                    if ref.get("url"):
                        flat_sources.append(ref)
        urls = [s["url"] for s in flat_sources if s.get("url")]
        titles = [s["title"] for s in flat_sources if s.get("title")]
        primary_title = titles[0] if titles else None
        primary_url = urls[0] if urls else None

        payloads.append({
            "Compound_Source_Map": json.dumps(source_map, ensure_ascii=False),
            "Compound_Source_Count": len(source_map),
            "Compound_Resolved_Source_Count": len(external),
            "Compound_Unresolved_Source_Count": len(source_map) - len(external),
            "Compound_Primary_Source_Title": primary_title,
            "Compound_Primary_Source_URL": primary_url,
            "Compound_Source_URLs": json.dumps(sorted(set(urls)), ensure_ascii=False),
            "Compound_Sources_JSON": json.dumps(flat_sources, ensure_ascii=False),
        })

    payload_df = pd.DataFrame(payloads, index=out.index)
    for column in payload_df.columns:
        out[column] = payload_df[column]
    return out


def parse_compound_source_map(value) -> dict:
    return _as_dict(value)
