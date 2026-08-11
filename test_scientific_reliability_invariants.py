"""Architecture-level invariants for Scientific Decision Reliability.

These tests are intentionally generic.  They do not mention a Gold Case,
PMID, or botanical-specific exception.  They protect the decision contract:
indication-scoped efficacy, cross-indication safety/regulatory protection,
fail-closed semantic coverage, and strict source-vs-model provenance.
"""

import pandas as pd

import botanical_rd_candidate_engine as eng


VALID_EMPTY_SEMANTIC_GATE = {
    "safety_assertions": [],
    "regulatory_assertions": [],
}


def make_engine(rows):
    eng.SIMILAR_COMPOUND_GROUPS = {}
    eng.COMPOUND_TARGETS = {}
    background = [
        dict(
            scientific_name=f"Bg{i}",
            compound_name=f"BgCompound{i}",
            indication="background",
            target="Antioxidant",
            common_name="",
            plant_part="",
            extraction_method="",
        )
        for i in range(25)
    ]
    return eng.BotanicalRDCandidateEngine(
        plant_compounds_df=pd.DataFrame(list(rows) + background),
        compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(),
        use_live_search=False,
    )


def self_row(result, plant):
    rows = result[
        (result["Reference_Plant"] == plant)
        & (result["Alternative_Plant"] == plant)
    ]
    assert not rows.empty
    return rows.iloc[0]


def test_invariant_off_indication_positive_evidence_cannot_create_go():
    """Changing only the evidence indication must remove its efficacy vote."""
    plant = "ContextInvariantPlant"
    rows = [
        dict(
            scientific_name=plant,
            compound_name="SharedCompound",
            indication="pain",
            target="Analgesic",
            common_name="",
            plant_part="",
            extraction_method="",
        )
    ]
    evidence = {
        "Scientific_Name": plant,
        "Target_Indication": "insomnia",
        "Notes": "A randomized controlled trial found significantly improved sleep onset.",
        "Result_Direction": "Positive",
        "Study_Type": "Randomized Controlled Trial",
        "Evidence_Record_ID": "context-invariant-1",
        "LLM_Gate_Assertions": VALID_EMPTY_SEMANTIC_GATE,
    }
    engine = make_engine(rows)
    engine.evidence_df = pd.DataFrame([evidence])
    row = self_row(engine.run(indication="pain", dosage_form="Infusion", market="EU"), plant)

    assert row["Evidence_Direction"] == "unclear"
    assert row["Evidence_Level"] == "No direct evidence"
    assert row["Final_Decision_Status"] == "INSUFFICIENT EVIDENCE"
    assert "GO" not in str(row["Final_Decision_Status"]).replace("INSUFFICIENT EVIDENCE", "")


def test_invariant_same_record_becomes_efficacy_relevant_only_when_context_matches():
    """Metamorphic pair: only Target_Indication changes between the two runs."""
    plant = "ContextSwitchPlant"
    rows = [
        dict(
            scientific_name=plant,
            compound_name="SharedCompound",
            indication="pain",
            target="Analgesic",
            common_name="",
            plant_part="",
            extraction_method="",
        )
    ]
    base = {
        "Scientific_Name": plant,
        "Notes": "A randomized controlled trial found significantly improved symptoms versus placebo.",
        "Result_Direction": "Positive",
        "Study_Type": "Randomized Controlled Trial",
        "Evidence_Record_ID": "context-switch-1",
        "LLM_Gate_Assertions": VALID_EMPTY_SEMANTIC_GATE,
    }

    engine = make_engine(rows)
    engine.evidence_df = pd.DataFrame([{**base, "Target_Indication": "insomnia"}])
    off = self_row(engine.run(indication="pain", dosage_form="Infusion", market="EU"), plant)

    engine.evidence_df = pd.DataFrame([{**base, "Target_Indication": "pain"}])
    on = self_row(engine.run(indication="pain", dosage_form="Infusion", market="EU"), plant)

    assert off["Final_Decision_Status"] == "INSUFFICIENT EVIDENCE"
    assert on["Evidence_Direction"] == "positive"
    assert on["Final_Decision_Status"] in {"GO WITH CAUTION", "GO"}


def test_invariant_unassessed_semantic_gate_never_defaults_to_eligible():
    """High-consequence wording must not fail open when semantic payload is absent."""
    plant = "UnassessedRiskPlant"
    rows = [
        dict(
            scientific_name=plant,
            compound_name="NovelCompound",
            indication="pain",
            target="Analgesic",
            common_name="",
            plant_part="",
            extraction_method="",
        )
    ]
    engine = make_engine(rows)
    engine.evidence_df = pd.DataFrame([{
        "Scientific_Name": plant,
        "Target_Indication": "pain",
        "Notes": "A report described permanent blindness requiring emergency surgery after exposure.",
        "Result_Direction": "Unknown",
        "Evidence_Record_ID": "semantic-missing-1",
        # Intentionally no LLM_Gate_Assertions.
    }])
    row = self_row(engine.run(indication="pain", dosage_form="Infusion", market="EU"), plant)
    # The deterministic consequence-based safety layer may now resolve this
    # directly as NO_GO_SAFETY; EXPERT_REVIEW_REQUIRED would also be an
    # acceptable conservative outcome. The invariant is that it never passes.
    assert row["Eligibility_Status"] in {"expert_review_required", "no_go_safety"}
    assert row["Final_Decision_Status"] in {"EXPERT REVIEW REQUIRED", "NO GO SAFETY"}
    assert bool(row["Eligible_For_Normal_Ranking"]) is False



def test_invariant_missing_semantic_payload_alone_does_not_poison_clean_legacy_record():
    """Absence is not the same as a failed semantic assessment."""
    plant = "LegacyCleanPlant"
    rows = [
        dict(
            scientific_name=plant,
            compound_name="LegacyCompound",
            indication="pain",
            target="Analgesic",
            common_name="",
            plant_part="",
            extraction_method="",
        )
    ]
    engine = make_engine(rows)
    engine.evidence_df = pd.DataFrame([{
        "Scientific_Name": plant,
        "Target_Indication": "pain",
        "Notes": "A randomized controlled trial reported improved pain outcomes versus placebo.",
        "Result_Direction": "Positive",
        "Study_Type": "Randomized Controlled Trial",
        "Evidence_Record_ID": "legacy-clean-1",
        # Intentionally no LLM_Gate_Assertions: this represents an older
        # pre-backfill record, not a semantic extraction error.
    }])
    row = self_row(engine.run(indication="pain", dosage_form="Infusion", market="EU"), plant)
    assert row["Eligibility_Status"] == "eligible"
    assert row["Final_Decision_Status"] in {"GO WITH CAUTION", "GO"}


def test_invariant_malformed_semantic_payload_fails_closed():
    """An actual semantic-processing failure is not treated like legacy absence."""
    plant = "MalformedSemanticPlant"
    rows = [
        dict(
            scientific_name=plant,
            compound_name="MalformedCompound",
            indication="pain",
            target="Analgesic",
            common_name="",
            plant_part="",
            extraction_method="",
        )
    ]
    engine = make_engine(rows)
    engine.evidence_df = pd.DataFrame([{
        "Scientific_Name": plant,
        "Target_Indication": "pain",
        "Notes": "A randomized controlled trial reported improved pain outcomes versus placebo.",
        "Result_Direction": "Positive",
        "Study_Type": "Randomized Controlled Trial",
        "Evidence_Record_ID": "semantic-malformed-1",
        "LLM_Gate_Assertions": "{not-valid-json",
    }])
    row = self_row(engine.run(indication="pain", dosage_form="Infusion", market="EU"), plant)
    assert row["Eligibility_Status"] == "expert_review_required"
    assert row["Final_Decision_Status"] == "EXPERT REVIEW REQUIRED"
    assert bool(row["Eligible_For_Normal_Ranking"]) is False

def test_invariant_semantic_serious_harm_can_trigger_hard_safety_stop_without_keyword_whitelist():
    """A validated semantic assertion can close a novel-wording safety gap."""
    plant = "SemanticSafetyPlant"
    sentence = "Permanent blindness requiring emergency surgery was documented after exposure."
    rows = [
        dict(
            scientific_name=plant,
            compound_name="NovelCompound",
            indication="pain",
            target="Analgesic",
            common_name="",
            plant_part="",
            extraction_method="",
        )
    ]
    payload = {
        "safety_assertions": [{
            "hazard_type": "serious_adverse_event",
            "seriousness": "serious",
            "seriousness_criterion": "persistent_or_significant_disability",
            "polarity": "risk_present",
            "affected_population": [],
            "preparation": "",
            "dose_dependency": "unknown",
            "route": "",
            "reported_outcome": "permanent blindness",
            "context_applicability": "relevant",
            "supporting_text": sentence,
            "extraction_confidence": 0.95,
        }],
        "regulatory_assertions": [],
    }
    engine = make_engine(rows)
    engine.evidence_df = pd.DataFrame([{
        "Scientific_Name": plant,
        "Target_Indication": "pain",
        "Notes": sentence,
        "Result_Direction": "Unknown",
        "Evidence_Record_ID": "semantic-safety-1",
        "Source_Authority": "Regulatory / official source",
        "Source_Authority_Score": 0.95,
        "LLM_Gate_Assertions": payload,
    }])
    row = self_row(engine.run(indication="pain", dosage_form="Infusion", market="EU"), plant)
    assert row["Eligibility_Status"] == "no_go_safety"
    assert row["Final_Decision_Status"] == "NO GO SAFETY"


def test_invariant_semantic_market_access_block_can_trigger_regulatory_no_go():
    """Legal blocking semantics are evaluated independently of phrase lists."""
    plant = "SemanticRegulatoryPlant"
    sentence = "The competent authority determined that this ingredient may not legally be placed on the market."
    rows = [
        dict(
            scientific_name=plant,
            compound_name="NovelCompound",
            indication="pain",
            target="Analgesic",
            common_name="",
            plant_part="",
            extraction_method="",
        )
    ]
    payload = {
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
            "supporting_text": sentence,
            "extraction_confidence": 0.95,
        }],
    }
    engine = make_engine(rows)
    engine.evidence_df = pd.DataFrame([{
        "Scientific_Name": plant,
        "Target_Indication": "pain",
        "Notes": sentence,
        "Result_Direction": "Unknown",
        "Evidence_Record_ID": "semantic-reg-1",
        "LLM_Gate_Assertions": payload,
    }])
    row = self_row(engine.run(indication="pain", dosage_form="Infusion", market="EU"), plant)
    assert row["Eligibility_Status"] == "no_go_regulatory"
    assert row["Final_Decision_Status"] == "NO GO REGULATORY"


def test_invariant_positive_record_cannot_borrow_study_strength_from_non_supporting_record():
    """Methodological strength follows the records that support direction."""
    from evidence_interpretation import interpret_evidence

    positive = {
        "text": "A small clinical trial reported significant improvement in symptoms.",
        "source_result_direction": "Positive",
        "authority_factor": 0.55,
    }
    non_supporting_review = {
        "text": "A systematic review summarized the literature but reached no clear efficacy conclusion.",
        "source_result_direction": "Unknown",
        "authority_factor": 0.95,
    }
    pooled = positive["text"] + " " + non_supporting_review["text"]
    result = interpret_evidence(
        pooled,
        clinical_weight=24,
        source_authority_factor=0.95,
        contributing_records=[positive, non_supporting_review],
    )

    assert result.evidence_direction == "positive"
    assert result.study_design == "clinical_trial", (
        "the positive study must not borrow the systematic-review design of a "
        "record that did not support the positive direction"
    )
    assert result.contribution < 24, (
        "the positive record's weaker authority must remain visible in scoring"
    )
