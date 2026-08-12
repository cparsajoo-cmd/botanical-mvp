"""Retrieval coverage assessment for scientific decision runs.

This module answers a deliberately narrow question: did the current retrieval
run cover the minimum source domains needed to support a downstream decision?
It does NOT infer that "no result" means "no evidence exists", and it does not
score efficacy, safety, or regulatory findings.

Coverage is session/run scoped.  A COMPLETE result means the required source
lanes were actually attempted successfully in this run; it is not a claim that
all literature in existence was found.
"""
from __future__ import annotations

from enum import Enum
from typing import Iterable, Mapping


EMA_SOURCE = "EMA/WHO/ESCOP Regulatory"  # legacy internal connector key; EMA/HMPC only in production.


class RetrievalCoverageStatus(str, Enum):
    COMPLETE = "COMPLETE"
    COMPLETE_WITH_LIMITATIONS = "COMPLETE_WITH_LIMITATIONS"
    INCOMPLETE = "INCOMPLETE"
    NOT_ASSESSABLE = "NOT_ASSESSABLE"


# Minimum literature redundancy: either primary literature index can keep the
# scientific domain assessable, but a failure of one lane is a limitation.
_LITERATURE_PRIMARY = ("PubMed", "Europe PMC")
_SAFETY_DEDICATED = ("LiverTox", "DailyMed", "OpenFDA FAERS")

# Market-specific regulatory source coverage.  ``implemented_source`` is the
# actual connector that exists in this repository.  ``missing_authority`` is
# intentionally explicit: the framework may know the authority name while no
# connector exists yet.  In that situation the honest status is INCOMPLETE,
# not "clear" by absence of findings.
_MARKET_REGULATORY_REQUIREMENTS = {
    "european union": {"implemented_source": EMA_SOURCE, "limitation": "EMA/HMPC inventory coverage only; WHO/ESCOP and product-specific national/Novel Food checks are not independently queried."},
    "united states": {"implemented_source": "FDA Labels", "limitation": "FDA label search is not a complete NDI/dietary-supplement market-access assessment."},
    "germany": {"implemented_source": EMA_SOURCE, "missing_authority": "BfArM"},
    "france": {"implemented_source": EMA_SOURCE, "missing_authority": "ANSM/DGCCRF national botanical rules"},
    "italy": {"implemented_source": EMA_SOURCE, "missing_authority": "AIFA/Ministero della Salute"},
    "spain": {"implemented_source": EMA_SOURCE, "missing_authority": "AEMPS"},
    "netherlands": {"implemented_source": EMA_SOURCE, "missing_authority": "CBG-MEB/NVWA"},
    "poland": {"implemented_source": EMA_SOURCE, "missing_authority": "URPL/GIS"},
    "united kingdom": {"missing_authority": "MHRA"},
    "switzerland": {"missing_authority": "Swissmedic"},
    "nordic countries (sweden, norway, denmark, finland)": {"implemented_source": EMA_SOURCE, "missing_authority": "national medicines/food authority"},
    "iran": {"missing_authority": "Iran FDA"},
    "middle east / gcc": {"missing_authority": "target-country authority (e.g. SFDA)"},
    "turkey": {"missing_authority": "TITCK"},
    "canada": {"missing_authority": "Health Canada NNHPD"},
    "brazil / latin america": {"missing_authority": "target-country authority (e.g. ANVISA)"},
    "china": {"missing_authority": "NMPA"},
    "japan": {"missing_authority": "MHLW/PMDA"},
    "south korea": {"missing_authority": "MFDS"},
    "india": {"missing_authority": "AYUSH/CDSCO/FSSAI"},
    "southeast asia (vietnam / thailand / indonesia)": {"missing_authority": "target-country authority"},
    "australia": {"missing_authority": "TGA"},
    "new zealand": {"missing_authority": "New Zealand Ministry of Health"},
    "south africa": {"missing_authority": "SAHPRA"},
    "global / multi-market": {"not_assessable": True, "missing_authority": "market-by-market regulatory assessment"},
}

_MARKET_ALIASES = {
    "eu": "european union",
    "europe": "european union",
    "us": "united states",
    "usa": "united states",
    "u.s.": "united states",
    "uk": "united kingdom",
    "u.k.": "united kingdom",
    "global": "global / multi-market",
}


def _norm(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _record_source(record: Mapping) -> str:
    """Return source name from either collector summary or standardized row."""
    return str(
        record.get("source")
        or record.get("Source_Type")
        or (record.get("record") or {}).get("Source_Type")
        or ""
    ).strip()


def _source_outcome(collection_result: Mapping, source: str) -> str:
    """Return completed / completed_with_errors / failed / not_attempted.

    A source that completed with zero records is still a successful retrieval
    attempt.  Absence of records is never turned into a finding of absence.
    """
    checked = set(collection_result.get("sources_checked") or [])
    if source not in checked:
        return "not_attempted"

    errors = [
        e for e in (collection_result.get("errors") or [])
        if str(e.get("source") or "").strip() == source
    ]
    records = [
        r for r in (collection_result.get("saved_records") or [])
        if _record_source(r) == source
    ]
    if errors and records:
        return "completed_with_errors"
    if errors:
        return "failed"
    return "completed"


def _any_usable(collection_result: Mapping, sources: Iterable[str]) -> bool:
    return any(_source_outcome(collection_result, s) in {"completed", "completed_with_errors"} for s in sources)


def assess_retrieval_coverage(
    collection_result: Mapping | None,
    *,
    market: str,
    collection_finished: bool = True,
    collection_attempted: bool = True,
) -> dict:
    """Assess one plant's current retrieval coverage.

    The result is deterministic and contains no I/O.  It distinguishes a
    completed search with zero hits from a search that never ran or failed.
    """
    result = dict(collection_result or {})
    market_key = _norm(market)
    market_key = _MARKET_ALIASES.get(market_key, market_key)

    if not collection_attempted or not result:
        return {
            "status": RetrievalCoverageStatus.NOT_ASSESSABLE.value,
            "reason": "No current retrieval run is available for this plant.",
            "missing_required_sources": [],
            "limitations": ["Retrieval coverage was not assessed in the current run."],
        }

    if not collection_finished:
        return {
            "status": RetrievalCoverageStatus.INCOMPLETE.value,
            "reason": "Plant collection did not finish within the current retrieval run.",
            "missing_required_sources": ["unfinished plant collection"],
            "limitations": [],
        }

    missing = []
    limitations = []

    # Scientific literature domain.
    lit_outcomes = {s: _source_outcome(result, s) for s in _LITERATURE_PRIMARY}
    usable_lit = [s for s, outcome in lit_outcomes.items() if outcome in {"completed", "completed_with_errors"}]
    if not usable_lit:
        missing.append("PubMed/Europe PMC scientific literature")
    elif len(usable_lit) < len(_LITERATURE_PRIMARY) or any(v == "completed_with_errors" for v in lit_outcomes.values()):
        limitations.append("Only partial primary-literature connector coverage completed successfully.")

    # Dedicated safety lane.  PubMed may also contain safety evidence, but a
    # decision run should not silently claim safety coverage when every
    # dedicated safety connector failed or was never attempted.
    if not _any_usable(result, _SAFETY_DEDICATED):
        missing.append("dedicated safety source (LiverTox/DailyMed/OpenFDA FAERS)")
    elif any(_source_outcome(result, s) in {"failed", "not_attempted"} for s in _SAFETY_DEDICATED):
        limitations.append("One or more dedicated safety connectors were unavailable or not completed.")

    req = _MARKET_REGULATORY_REQUIREMENTS.get(market_key)
    if not market_key or req is None:
        missing.append(f"primary regulatory authority for target market '{market or 'unspecified'}'")
    elif req.get("not_assessable"):
        return {
            "status": RetrievalCoverageStatus.NOT_ASSESSABLE.value,
            "reason": "The selected market requires a market-by-market regulatory assessment; no single primary authority can establish coverage.",
            "missing_required_sources": [req.get("missing_authority", "market-specific authority")],
            "limitations": limitations,
        }
    else:
        implemented = req.get("implemented_source")
        missing_authority = req.get("missing_authority")
        if implemented:
            reg_outcome = _source_outcome(result, implemented)
            if reg_outcome not in {"completed", "completed_with_errors"}:
                missing.append(f"{implemented} ({reg_outcome})")
            elif reg_outcome == "completed_with_errors":
                limitations.append(f"{implemented} completed with errors.")
        if missing_authority:
            missing.append(str(missing_authority))
        if req.get("limitation"):
            limitations.append(str(req["limitation"]))

    if missing:
        return {
            "status": RetrievalCoverageStatus.INCOMPLETE.value,
            "reason": "Required retrieval coverage is incomplete: " + "; ".join(missing) + ".",
            "missing_required_sources": missing,
            "limitations": limitations,
        }

    # Any connector errors outside mandatory domains are still useful to expose,
    # but they do not make the whole decision unassessable when all mandatory
    # domains completed.
    if result.get("errors"):
        limitations.append("One or more secondary connectors reported errors in this run.")

    if limitations:
        return {
            "status": RetrievalCoverageStatus.COMPLETE_WITH_LIMITATIONS.value,
            "reason": "Required retrieval domains completed, with documented limitations.",
            "missing_required_sources": [],
            "limitations": list(dict.fromkeys(limitations)),
        }

    return {
        "status": RetrievalCoverageStatus.COMPLETE.value,
        "reason": "Required retrieval domains completed in the current run.",
        "missing_required_sources": [],
        "limitations": [],
    }


def aggregate_coverage_status(coverage_by_plant: Mapping[str, Mapping] | None) -> str:
    values = [str((v or {}).get("status") or "") for v in (coverage_by_plant or {}).values()]
    if not values:
        return RetrievalCoverageStatus.NOT_ASSESSABLE.value
    if RetrievalCoverageStatus.NOT_ASSESSABLE.value in values:
        return RetrievalCoverageStatus.NOT_ASSESSABLE.value
    if RetrievalCoverageStatus.INCOMPLETE.value in values:
        return RetrievalCoverageStatus.INCOMPLETE.value
    if RetrievalCoverageStatus.COMPLETE_WITH_LIMITATIONS.value in values:
        return RetrievalCoverageStatus.COMPLETE_WITH_LIMITATIONS.value
    return RetrievalCoverageStatus.COMPLETE.value


def coverage_for_plant(coverage_by_plant: Mapping[str, Mapping] | None, plant: object) -> dict:
    key = _norm(plant)
    for name, payload in (coverage_by_plant or {}).items():
        if _norm(name) == key:
            return dict(payload or {})
    return {
        "status": RetrievalCoverageStatus.NOT_ASSESSABLE.value,
        "reason": "No current retrieval coverage record exists for this candidate plant.",
        "missing_required_sources": [],
        "limitations": ["Candidate was not covered by the current Step 2 retrieval run."],
    }
