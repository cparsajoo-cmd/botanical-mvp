"""Cross-stage regression lock for the platform's closed reliability pillars.

This is deliberately an integration contract rather than another scientific
benchmark.  It protects three already-validated layers from future refactors:

1. Scientific Decision Reliability
2. Preparation / Evidence Transferability
3. Retrieval Completeness / Source Coverage

The cases are generic synthetic invariants: no botanical-specific rule, PMID,
Gold Case, or holdout wording is used.  A change in one stage must not weaken
or bypass the protections established by another stage.
"""
from __future__ import annotations

import pandas as pd

import botanical_rd_candidate_engine as eng
from retrieval_coverage import assess_retrieval_coverage
from standard_evidence_builder import build_transferability_target_context


EMPTY_SEMANTIC_GATE = {"safety_assertions": [], "regulatory_assertions": []}


def _make_engine(plant: str):
    # Keep global lookup state deterministic and avoid any live retrieval.
    eng.SIMILAR_COMPOUND_GROUPS = {}
    eng.COMPOUND_TARGETS = {}
    rows = [
        dict(
            scientific_name=plant,
            compound_name="CoreCompound",
            indication="pain",
            target="Analgesic",
            common_name="",
            plant_part="",
            extraction_method="",
        )
    ]
    rows += [
        dict(
            scientific_name=f"CoreBg{i}",
            compound_name=f"CoreBgCompound{i}",
            indication="background",
            target="Antioxidant",
            common_name="",
            plant_part="",
            extraction_method="",
        )
        for i in range(25)
    ]
    return eng.BotanicalRDCandidateEngine(
        plant_compounds_df=pd.DataFrame(rows),
        compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(),
        use_live_search=False,
    )


def _self_row(result: pd.DataFrame, plant: str):
    rows = result[
        (result["Reference_Plant"] == plant)
        & (result["Alternative_Plant"] == plant)
    ]
    assert not rows.empty
    return rows.iloc[0]


def _target_context(preparation: str, *, indication: str = "pain"):
    return build_transferability_target_context(
        indication,
        preparation,
        {
            "target_indication": indication,
            "dosage_form": preparation,
            "route": "oral",
            "target_plant_part": "leaf",
            "target_dose": "240 mg/day",
        },
    )


def _coverage(plant: str, *, complete: bool):
    checked = [
        "PubMed",
        "Europe PMC",
        "LiverTox",
        "EMA/WHO/ESCOP Regulatory",
    ]
    result = {
        "saved_records": [],
        "sources_checked": checked,
        "errors": [] if complete else [
            {"source": "EMA/WHO/ESCOP Regulatory", "error": "simulated timeout"}
        ],
    }
    coverage = assess_retrieval_coverage(result, market="European Union")
    return {plant: coverage}


def _positive_evidence(plant: str, *, indication: str = "pain"):
    return {
        "Scientific_Name": plant,
        "Target_Indication": indication,
        "Preparation": "standardized dry extract",
        "Preparation_Category": "dry_extract",
        "Plant_Part": "leaf",
        "Administration_Route": "oral",
        "Dose": "240 mg/day",
        "Notes": "A randomized controlled trial found significantly improved pain versus placebo.",
        "Result_Direction": "Positive",
        "Study_Type": "Randomized Controlled Trial",
        "Evidence_Record_ID": "core-reliability-positive",
        "LLM_Gate_Assertions": EMPTY_SEMANTIC_GATE,
    }


def _run(engine, plant: str, evidence: dict, *, preparation: str, coverage, indication="pain"):
    engine.evidence_df = pd.DataFrame([evidence])
    return _self_row(
        engine.run(
            indication=indication,
            dosage_form=preparation,
            market="European Union",
            target_context=_target_context(preparation, indication=indication),
            retrieval_coverage_by_plant=coverage,
        ),
        plant,
    )


def test_closed_pillars_cross_stage_contract():
    """One metamorphic contract locks the three closed reliability pillars."""
    plant = "CoreReliabilityPlant"
    engine = _make_engine(plant)
    complete = _coverage(plant, complete=True)
    incomplete = _coverage(plant, complete=False)
    positive = _positive_evidence(plant)

    # Baseline: same-indication evidence + matching product + sufficient
    # retrieval coverage remains usable. COMPLETE_WITH_LIMITATIONS is expected
    # for EU because the coverage assessor exposes documented scope limits;
    # it is deliberately non-blocking.
    baseline = _run(
        engine,
        plant,
        positive,
        preparation="standardized dry extract",
        coverage=complete,
    )
    assert baseline["Evidence_Direction"] == "positive"
    assert baseline["Final_Decision_Status"] in {"GO", "GO WITH CAUTION"}
    assert baseline["Retrieval_Coverage_Status"] in {
        "COMPLETE", "COMPLETE_WITH_LIMITATIONS"
    }
    assert bool(baseline["Eligible_For_Normal_Ranking"]) is True

    # Change ONLY the target preparation: efficacy must no longer transfer.
    preparation_mismatch = _run(
        engine,
        plant,
        positive,
        preparation="Infusion",
        coverage=complete,
    )
    assert preparation_mismatch["Evidence_Direction"] == "unclear"
    assert preparation_mismatch["Final_Decision_Status"] == "INSUFFICIENT EVIDENCE"
    assert bool(preparation_mismatch["Eligible_For_Normal_Ranking"]) is False

    # Restore preparation but make retrieval incomplete: a previously valid GO
    # must be capped to expert review, never silently preserved.
    retrieval_incomplete = _run(
        engine,
        plant,
        positive,
        preparation="standardized dry extract",
        coverage=incomplete,
    )
    assert retrieval_incomplete["Evidence_Direction"] == "positive"
    assert retrieval_incomplete["Retrieval_Coverage_Status"] == "INCOMPLETE"
    assert retrieval_incomplete["Final_Decision_Status"] == "EXPERT REVIEW REQUIRED"
    assert bool(retrieval_incomplete["Eligible_For_Normal_Ranking"]) is False

    # Change ONLY the scientific indication: complete retrieval and a matching
    # preparation cannot resurrect off-indication efficacy.
    off_indication = _run(
        engine,
        plant,
        _positive_evidence(plant, indication="insomnia"),
        preparation="standardized dry extract",
        coverage=complete,
    )
    assert off_indication["Evidence_Direction"] == "unclear"
    assert off_indication["Final_Decision_Status"] == "INSUFFICIENT EVIDENCE"


def test_hard_stops_survive_preparation_mismatch_and_incomplete_retrieval():
    """Later-stage uncertainty must never weaken safety/regulatory hard stops."""
    plant = "CoreHardStopPlant"
    engine = _make_engine(plant)
    incomplete = _coverage(plant, complete=False)

    safety_sentence = "Use caused a life-threatening event requiring hospitalization."
    safety = {
        **_positive_evidence(plant),
        "Notes": safety_sentence,
        "Result_Direction": "Unknown",
        "Evidence_Record_ID": "core-reliability-safety",
        "LLM_Gate_Assertions": {
            "safety_assertions": [{
                "hazard_type": "serious_adverse_event",
                "seriousness": "serious",
                "seriousness_criterion": "life_threatening",
                "polarity": "risk_present",
                "affected_population": ["general"],
                "preparation": "standardized dry extract",
                "dose_dependency": "unknown",
                "route": "oral",
                "reported_outcome": "life-threatening event requiring hospitalization",
                "context_applicability": "relevant",
                "supporting_text": safety_sentence,
                "extraction_confidence": 0.99,
            }],
            "regulatory_assertions": [],
        },
    }
    safety_row = _run(
        engine,
        plant,
        safety,
        preparation="Infusion",  # deliberate transferability mismatch
        coverage=incomplete,
    )
    assert safety_row["Retrieval_Coverage_Status"] == "INCOMPLETE"
    assert safety_row["Final_Decision_Status"] == "NO GO SAFETY"
    assert bool(safety_row["Eligible_For_Normal_Ranking"]) is False

    regulatory_sentence = (
        "The competent authority determined that this ingredient may not legally "
        "be placed on the market."
    )
    regulatory = {
        **_positive_evidence(plant),
        "Notes": regulatory_sentence,
        "Result_Direction": "Unknown",
        "Evidence_Record_ID": "core-reliability-regulatory",
        "LLM_Gate_Assertions": {
            "safety_assertions": [],
            "regulatory_assertions": [{
                "action": "prohibited",
                "market_access_effect": "blocks_market_access",
                "jurisdiction": "EU",
                "authority": "competent authority",
                "ingredient": "this ingredient",
                "plant_part": "",
                "preparation": "",
                "route": "",
                "product_category": "",
                "conditions": "",
                "effective_date": "",
                "context_applicability": "relevant",
                "supporting_text": regulatory_sentence,
                "extraction_confidence": 0.99,
            }],
        },
    }
    regulatory_row = _run(
        engine,
        plant,
        regulatory,
        preparation="Infusion",  # deliberate transferability mismatch
        coverage=incomplete,
    )
    assert regulatory_row["Retrieval_Coverage_Status"] == "INCOMPLETE"
    assert regulatory_row["Final_Decision_Status"] == "NO GO REGULATORY"
    assert bool(regulatory_row["Eligible_For_Normal_Ranking"]) is False
