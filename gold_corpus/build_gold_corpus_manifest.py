from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

from agreement_eligibility import map_assertion_state_to_direction
from applicability_check import ReferenceDomain

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "gold_cases" / "gold_case_registry_corrected_2026-08-01.json"
OUT = Path(__file__).resolve().parent / "gold_corpus_manifest.json"

# Human-curated question/rationale layer. These are benchmark questions, not
# production rules and are deliberately kept outside the engine.
CURATION: dict[int, dict[str, Any]] = {
    1: {"question": "What reference-grounded evidence supports Melissa officinalis leaf for sleep and relaxation?", "rationale": "Positive indication benchmark from an EMA/HMPC monograph."},
    3: {"question": "What does the clinical evidence show for Matricaria chamomilla and sleep outcomes?", "rationale": "Mixed/conditional human evidence from a systematic review and meta-analysis.", "supporting_sources": [{"citation": "Hieu TH et al. 2019. Phytother Res 33:1604-1615. DOI 10.1002/ptr.6349.", "role": "supporting_competing_review", "verification": "documented_in_case_file"}]},
    4: {"question": "Does Ginkgo biloba improve cognitive impairment outcomes in adults and older people?", "rationale": "Negative human-evidence benchmark governed by a current Cochrane systematic review.", "supporting_sources": [{"citation": "Chan E et al. earlier EGb761 systematic review/meta-analysis (documented in Case 004 source-precedence audit).", "role": "supporting_older_review", "verification": "documented_in_case_file"}]},
    5: {"question": "Is there sufficient evidence to support Cimicifuga racemosa for menopausal symptoms?", "rationale": "Insufficient-evidence benchmark with a documented conflicting later review.", "supporting_sources": [{"citation": "Sadahiro R et al. 2023. Menopause 30(7):766-773. DOI 10.1097/GME.0000000000002196.", "role": "conflicting_review_scope_caveat", "verification": "public_abstract_documented_in_case_file"}]},
    6: {"question": "What serious medicine interactions or contraindications apply to Hypericum perforatum herb?", "rationale": "Serious safety/contraindication benchmark from EMA/HMPC."},
    7: {"question": "What preparation specification is defined for Valeriana officinalis radix dry extract?", "rationale": "Preparation-specific benchmark with DER and extraction solvent."},
    8: {"question": "What preparation specification is defined for Ginkgo biloba folium quantified dry extract?", "rationale": "Preparation-specific benchmark with DER and acetone extraction solvent."},
    9: {"question": "Does the EMA/HMPC reference support Melissa officinalis leaf for relief of mild mental stress?", "rationale": "Positive EMA/HMPC indication benchmark."},
    10: {"question": "Does the EMA/HMPC reference support Passiflora incarnata herb for relief of mild mental stress?", "rationale": "Positive EMA/HMPC indication benchmark."},
    11: {"question": "What does the systematic-review evidence show for Matricaria chamomilla in generalized anxiety disorder?", "rationale": "Positive human-evidence benchmark from a systematic review/meta-analysis."},
    12: {"question": "Does the EMA/HMPC reference support Lavandula angustifolia essential oil as an aid to sleep?", "rationale": "Positive EMA/HMPC indication benchmark."},
    13: {"question": "What is the accepted botanical identity of Echinacea purpurea?", "rationale": "Botanical identity benchmark from Kew Plants of the World Online."},
    14: {"question": "What interaction warning applies to concomitant Ginkgo biloba and dabigatran etexilate?", "rationale": "Drug-interaction safety benchmark from EMA/HMPC."},
    15: {"question": "What well-established preparation specification is defined for Hypericum perforatum dry extract?", "rationale": "Preparation-specific benchmark with DER and methanol extraction solvent."},
    16: {"question": "What UK medicinal-product prohibition applies to Piper methysticum (kava-kava)?", "rationale": "National regulatory prohibition benchmark with an external-use exception."},
    17: {"question": "What is the accepted botanical identity of Matricaria chamomilla and its Chamomilla recutita synonym?", "rationale": "Botanical identity/synonym benchmark from Kew POWO."},
    18: {"question": "What UK supply restriction applies to internal-use herbal medicines containing Ephedra sinica at specified dose thresholds?", "rationale": "Dose-specific national regulatory restriction benchmark."},
    19: {"question": "What clinically supported use does the WHO monograph recognize for Panax ginseng root?", "rationale": "First WHO_MONOGRAPH governing source in the corpus; closes the WHO source-coverage gap."},
    20: {"question": "What therapeutic indication does the ESCOP monograph recognize for Echinacea purpurea flowering aerial parts?", "rationale": "First ESCOP_MONOGRAPH governing source in the corpus; closes the ESCOP source-coverage gap using only claims visible on the official public ESCOP summary."},
    21: {"question": "Do equally ranked systematic reviews agree on whether Serenoa repens improves lower urinary tract symptoms due to benign prostatic enlargement?", "rationale": "First real multi-reference GoldCase in which two applicable SYSTEMATIC_REVIEW sources carry opposing verdicts and must resolve to REFERENCE_CONFLICT rather than being silently ranked by recency."},
    22: {
        "question": "When a systematic review and an EMA/HMPC monograph disagree on Valeriana officinalis for insomnia, which reference governs under the existing INDICATION_EVIDENCE hierarchy?",
        "rationale": "First cross-rank precedence benchmark: a SYSTEMATIC_REVIEW with an inconclusive verdict must outrank a newer EMA_HMPC monograph without creating a same-rank conflict.",
        "critical_reference_ids": [
            "PUBMED_10767649_STEVINSON_ERNST_2000_VALERIAN_INSOMNIA_SR",
            "EMA_HMPC_150848_2015_VALERIANA_RADIX_SLEEP",
        ],
    },
}

STUDY_DESIGN_BY_SOURCE = {
    "SYSTEMATIC_REVIEW": "systematic_review",
    "EMA_HMPC": "regulatory_monograph",
    "TAXONOMIC_AUTHORITY": "taxonomic_database",
    "NATIONAL_REGULATORY": "national_regulatory_instrument_or_guidance",
    "WHO_MONOGRAPH": "who_monograph_with_clinical_data_supported_use",
    "ESCOP_MONOGRAPH": "escop_monograph",
}


def _load_builder(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    builders = [v for k, v in vars(module).items() if k.startswith("build_gold_case") and callable(v)]
    if len(builders) != 1:
        raise RuntimeError(f"Expected exactly one builder in {path}, found {len(builders)}")
    return builders[0], module


def _prep_dict(prep):
    if prep is None:
        return None
    return {
        "dosage_form": prep.dosage_form,
        "solvent": prep.solvent,
        "der_min": prep.der_min,
        "der_max": prep.der_max,
        "source_status": prep.source_status,
    }


def _decision_direction(outcome):
    if outcome.domain != ReferenceDomain.INDICATION_EVIDENCE:
        return {"value": None, "status": "NOT_APPLICABLE_TO_WHOLE_CASE_DECISION_UNDER_PROTOCOL_V0_3"}
    if outcome.resolution_status.value in {"Reference conflict", "Human review required"}:
        return {"value": None, "status": "NOT_ELIGIBLE_DUE_TO_UNRESOLVED_REFERENCE_CONFLICT"}
    direction = map_assertion_state_to_direction(outcome.assertion_state) if outcome.assertion_state else None
    if direction is None:
        return {"value": None, "status": "NOT_ELIGIBLE_UNDER_CURRENT_ASSERTION_STATE_MAPPING"}
    return {"value": direction.value, "status": "DERIVABLE_FROM_GROUND_TRUTH_BUT_NOT_FROZEN_IN_GOLDCASE_EXPECTED_OUTPUT"}


def build_manifest() -> dict:
    registry = json.loads(REGISTRY.read_text())
    entries = []
    for item in registry["active_cases"]:
        n = item["case_number"]
        path = ROOT / "gold_cases" / item["file"]
        builder, module = _load_builder(path)
        case = builder()
        if len(case.resolved_outcomes) != 1:
            raise RuntimeError(f"{case.case_id}: expected one resolved outcome")
        outcome = case.resolved_outcomes[0]
        cur = CURATION[n]
        # Critical Ground Truth references are either the single selected
        # reference or, for an unresolved same-rank conflict, every reference
        # explicitly named by the precedence resolution. This keeps the corpus
        # generic and avoids case-specific benchmark rules.
        curated_critical_ids = cur.get("critical_reference_ids")
        if curated_critical_ids:
            critical_ids = list(curated_critical_ids)
        elif outcome.selected_reference_id:
            critical_ids = [outcome.selected_reference_id]
        elif outcome.conflicting_reference_ids:
            critical_ids = list(outcome.conflicting_reference_ids)
        else:
            critical_ids = []

        refs_by_id = {g.reference.reference_id: g for g in case.references}
        critical_sources = []
        for critical_id in critical_ids:
            gref = refs_by_id[critical_id]
            ref = gref.reference
            matching_claims = [
                c for c in gref.claims
                if c.domain == outcome.domain and c.assertion_type == outcome.assertion_type
            ]
            if len(matching_claims) != 1:
                raise RuntimeError(
                    f"{case.case_id}: expected exactly one claim for critical reference {critical_id}"
                )
            claim = matching_claims[0]
            state = claim.assertion_state.value if claim.assertion_state else None
            direction = (
                "positive" if state == "Present"
                else "negative" if state == "Absent"
                else "mixed" if state == "Conditional"
                else "unclear" if state == "Insufficient"
                else None
            )
            critical_sources.append({
                "reference_id": ref.reference_id,
                "source_type": ref.source_type,
                "document_date": str(ref.document_date) if ref.document_date else None,
                "source_locator": claim.source_locator,
                "expected_study_design": STUDY_DESIGN_BY_SOURCE.get(ref.source_type, "unspecified"),
                "expected_evidence_direction": direction,
                "expected_applicability": "applicable_for_resolved_domain",
                "critical_retrieval_requirement": True,
                "safety_critical": bool(
                    outcome.domain == ReferenceDomain.SAFETY
                    and claim.severity
                    and claim.severity.value == "SERIOUS"
                ),
                "regulatory_critical": bool(
                    outcome.domain == ReferenceDomain.REGULATORY_STATUS
                    and outcome.assertion_type.value == "Prohibition"
                ),
            })

        if not critical_sources:
            raise RuntimeError(f"{case.case_id}: active corpus case has no critical Ground Truth reference")

        if outcome.resolution_status.value == "Reference conflict":
            aggregate_direction = "conflicting"
        else:
            dirs = {x["expected_evidence_direction"] for x in critical_sources}
            aggregate_direction = next(iter(dirs)) if len(dirs) == 1 else "mixed"

        designs = {x["expected_study_design"] for x in critical_sources}
        aggregate_design = next(iter(designs)) if len(designs) == 1 else "mixed"
        expected_safety = "NOT_APPLICABLE"
        if outcome.domain == ReferenceDomain.SAFETY:
            expected_safety = f"{outcome.assertion_type.value}:{outcome.assertion_state.value}:{outcome.severity.value if outcome.severity else 'UNSPECIFIED'}"
        expected_reg = "NOT_APPLICABLE"
        if outcome.domain == ReferenceDomain.REGULATORY_STATUS:
            expected_reg = f"{outcome.assertion_type.value}:{outcome.assertion_state.value}"
        prohibited = []
        if any(src["safety_critical"] for src in critical_sources):
            prohibited = ["positive_or_clear_decision_when_serious_safety_source_is_retrieved", "serious_safety_candidate_in_top5"]
        elif any(src["regulatory_critical"] for src in critical_sources):
            prohibited = ["positive_or_clear_decision_when_prohibition_source_is_retrieved", "prohibited_candidate_in_top5"]
        entry = {
            "case_number": n,
            "case_id": case.case_id,
            "question": cur["question"],
            "indication": case.validation_unit.indication,
            "botanical_identity": case.validation_unit.taxon,
            "scientific_name": case.validation_unit.taxon,
            "plant_part": case.validation_unit.plant_part,
            "preparation": _prep_dict(case.validation_unit.preparation),
            "dose": None,
            "population": case.validation_unit.population,
            "route": case.validation_unit.route_of_administration,
            "jurisdiction": case.validation_unit.jurisdiction,
            "domain": outcome.domain.value,
            "assertion_type": outcome.assertion_type.value,
            "assertion_state": outcome.assertion_state.value if outcome.assertion_state else None,
            "critical_sources": critical_sources,
            "supporting_sources": cur.get("supporting_sources", []),
            "known_irrelevant_sources": [],
            "known_duplicate_sources": [],
            "expected_evidence_direction": aggregate_direction,
            "expected_study_design": aggregate_design,
                        "expected_applicability": (
                "APPLICABLE"
                if all(
                    refs_by_id[src["reference_id"]].applicability_by_domain[outcome.domain].applicable
                    for src in critical_sources
                )
                else "NOT_APPLICABLE"
            ),
            "expected_safety_status": expected_safety,
            "expected_regulatory_status": expected_reg,
            "expected_decision_direction": _decision_direction(outcome),
            "expected_prohibited_decisions": prohibited,
            "reference_rationale": cur["rationale"],
            "resolution_status": outcome.resolution_status.value,
            "reviewer": "internal_scientific_curation_pending_external_expert_review",
            "review_date": "2026-08-07",
            "ground_truth_status": "REFERENCE_CURATED_DEVELOPMENT",
            "engine_evidence_attached": bool(case.engine_evidence),
            "locked": bool(case.locked),
            "e2e_snapshot_status": "NOT_CAPTURED",
        }
        if n == 18:
            entry["dose"] = {"single_dose_threshold_mg": 600, "daily_dose_threshold_mg": 1800, "meaning": "supply-channel thresholds, not absolute lawful maxima"}
        entries.append(entry)
    return {
        "gold_corpus_version": "0.3.0",
        "generated_date": "2026-08-07",
        "protocol_version": "VALIDATION_PROTOCOL.md v0.3",
        "active_case_count": len(entries),
        "abandoned_case_numbers": registry.get("abandoned_cases", []),
        "corpus_status": "CURATED_GROUND_TRUTH_WITH_CRITICAL_SOURCE_EXPECTATIONS; FROZEN_RETRIEVAL_SNAPSHOTS_NOT_YET_CAPTURED",
        "cases": entries,
    }


if __name__ == "__main__":
    OUT.write_text(json.dumps(build_manifest(), indent=2, ensure_ascii=False) + "\n")
    print(OUT)
