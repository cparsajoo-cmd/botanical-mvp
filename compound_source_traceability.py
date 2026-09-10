"""Compound provenance for Stage 6.

Presentation/provenance only. ``Discovery_Linked_Compounds`` (already
computed by indication_candidate_discovery.py / candidate_shortlisting.py
and present on the report-ready frame) is the only per-candidate compound
list this pipeline currently carries. The underlying plant-compound
relationship comes from the internal plant_compounds relational database
(see plant_compound_database.py) -- a real, maintained dataset, but not a
per-compound external citation. Per spec: this is INTERNAL_CURATED_PROVENANCE,
not fabricated as an external publication.

If a caller has actually resolved per-compound external identifiers this
session (PubChem CID / ChEMBL ID / a real reference URL -- see
data_contracts.Compound and plant_compound_database.save_plant_compound_record's
reference_title/reference_url columns), it can pass them in via
``compound_metadata`` and this module will report those specific compounds as
genuinely externally linked instead. Never invents this metadata itself.
"""
from __future__ import annotations

import json

import pandas as pd

from evidence_source_resolver import _clean, _valid_http_url


def _compound_names(value) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    text = _clean(value)
    if not text:
        return []
    import re
    return [c.strip() for c in re.split(r"[;|\n]+", text) if c.strip()]


def build_compound_source_map(compound_names: list[str], compound_metadata: dict | None = None) -> dict:
    """Build the Compound_Source_Map for one candidate's linked compounds.

    ``compound_metadata`` (optional): {compound_name: {"reference_url": ...,
    "reference_title": ..., "pubchem_cid": ..., "chembl_id": ...}} -- ONLY
    real, already-resolved metadata the caller has; never fabricated here.
    """
    metadata = compound_metadata or {}
    result: dict[str, dict] = {}
    for name in compound_names:
        meta = metadata.get(name) or metadata.get(name.lower()) or {}
        url = _valid_http_url(meta.get("reference_url"))
        title = _clean(meta.get("reference_title"))
        pubchem_cid = _clean(meta.get("pubchem_cid"))
        chembl_id = _clean(meta.get("chembl_id"))
        if url or pubchem_cid or chembl_id:
            entry = {"provenance_type": "EXTERNALLY_LINKED"}
            if title:
                entry["source"] = title
            if url:
                entry["url"] = url
            if pubchem_cid:
                entry["pubchem_cid"] = pubchem_cid
            if chembl_id:
                entry["chembl_id"] = chembl_id
        else:
            entry = {
                "provenance_type": "INTERNAL_CURATED_PROVENANCE",
                "source": "internal curated plant-compound relational database",
                "url": None,
            }
        result[name] = entry
    return result


def attach_compound_source_traceability(report_df: pd.DataFrame, compound_metadata: dict | None = None) -> pd.DataFrame:
    """Append Compound_* source fields to a Stage-6 frame.

    Reads Discovery_Linked_Compounds if present; a row with no linked
    compounds gets zero counts rather than a fabricated entry.
    """
    if not isinstance(report_df, pd.DataFrame) or report_df.empty:
        return report_df

    out = report_df.copy()
    has_col = "Discovery_Linked_Compounds" in out.columns
    payloads = []
    for _, row in out.iterrows():
        names = _compound_names(row.get("Discovery_Linked_Compounds")) if has_col else []
        source_map = build_compound_source_map(names, compound_metadata)

        external = [n for n, e in source_map.items() if e["provenance_type"] == "EXTERNALLY_LINKED"]
        urls = [source_map[n]["url"] for n in external if source_map[n].get("url")]
        titles = [source_map[n]["source"] for n in external if source_map[n].get("source")]
        primary_title = titles[0] if titles else None
        primary_url = urls[0] if urls else None

        payloads.append({
            "Compound_Source_Map": json.dumps(source_map, ensure_ascii=False),
            "Compound_Source_Count": len(source_map),
            "Compound_Resolved_Source_Count": len(external),
            "Compound_Unresolved_Source_Count": len(source_map) - len(external),
            "Compound_Primary_Source_Title": primary_title,
            "Compound_Primary_Source_URL": primary_url,
            "Compound_Source_URLs": json.dumps(urls, ensure_ascii=False),
        })

    payload_df = pd.DataFrame(payloads, index=out.index)
    for column in payload_df.columns:
        out[column] = payload_df[column]
    return out


def parse_compound_source_map(value) -> dict:
    text = _clean(value)
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}
