import json

import pandas as pd

import botanical_rd_candidate_engine as eng
from assertion_vocabulary import SeverityLevel
from decision_explainability import build_candidate_explanation
from safety_assertion_engine import (
    AssertionPolarity,
    SafetyAssertionType,
    SafetyConfidence,
    classify_safety_assertions,
    summarize_safety_assertions,
)
from test_gate_layer import make_engine


def _engine_row(evidence_rows, *, alt="AltPlantPharmaSafety"):
    eng.SIMILAR_COMPOUND_GROUPS = {}
    eng.COMPOUND_TARGETS = {}
    rows = [
        dict(scientific_name="RefPlant", compound_name="SharedCompound", indication="TestIndication", target="Laxative", common_name="", plant_part="", extraction_method=""),
        dict(scientific_name=alt, compound_name="SharedCompound", indication="TestIndication", target="Laxative", common_name="", plant_part="", extraction_method=""),
    ]
    engine = make_engine(rows)
    engine.evidence_df = pd.DataFrame(evidence_rows)
    result = engine.run(indication="TestIndication", dosage_form="Infusion", market="EU")
    return result[(result["Reference_Plant"] == "RefPlant") & (result["Alternative_Plant"] == alt)].iloc[0]


def test_explicit_population_contraindication_is_serious_without_drug_class_whitelist():
    assertions = classify_safety_assertions(
        "Use is contraindicated during pregnancy.",
        evidence_record_id="ev-preg-1",
        authority="EMA HMPC Monograph",
        authority_score=1.0,
    )
    assert any(a.assertion_type == SafetyAssertionType.CONTRAINDICATION and a.severity == SeverityLevel.SERIOUS for a in assertions)
    assert any(a.assertion_type == SafetyAssertionType.PREGNANCY and a.severity == SeverityLevel.SERIOUS for a in assertions)
    assert all(a.evidence_record_id == "ev-preg-1" for a in assertions)


def test_explicit_pregnancy_contraindication_cannot_pass_live_engine():
    row = _engine_row([{
        "Scientific_Name": "AltPlantPharmaSafety",
        "Target_Indication": "TestIndication",
        "Notes": "Use is contraindicated during pregnancy.",
        "Evidence_Record_ID": "ev-preg-2",
        "Source_Organization": "European Medicines Agency",
        "Source_Type": "HMPC monograph",
        "Source_URL": "https://example.invalid/regulator-record",
    }])
    assert row["Eligibility_Status"] == "expert_review_required"
    assert bool(row["Eligible_For_Normal_Ranking"]) is False
    assert row["Safety_Severity"] == "severe"
    assert row["Safety_Decision_Confidence"] == "High"
    payload = json.loads(row["Safety_Assertions"])
    assert any(a["assertion_type"] == "pregnancy" and a["severity"] == "SERIOUS" for a in payload)
    assert any(a["evidence_record_id"] == "ev-preg-2" and "contraindicated" in a["source_sentence"].lower() for a in payload)


def test_conflicting_safety_evidence_is_retained_not_overwritten():
    row = _engine_row([
        {
            "Scientific_Name": "AltPlantPharmaSafety",
            "Target_Indication": "TestIndication",
            "Notes": "Use is contraindicated during pregnancy.",
            "Evidence_Record_ID": "ev-risk",
            "Source_Organization": "European Medicines Agency",
            "Source_Type": "HMPC monograph",
        },
        {
            "Scientific_Name": "AltPlantPharmaSafety",
            "Target_Indication": "TestIndication",
            "Notes": "The preparation is generally considered safe in routine use.",
            "Evidence_Record_ID": "ev-safe",
            "Source_Type": "Systematic review",
        },
    ])
    assert bool(row["Safety_Evidence_Conflict"]) is True
    assert row["Safety_Severity"] == "severe"
    assert row["Eligibility_Status"] != "eligible"
    payload = json.loads(row["Safety_Assertions"])
    assert {a["evidence_record_id"] for a in payload} >= {"ev-risk", "ev-safe"}
    assert any(a["polarity"] == AssertionPolarity.RISK_PRESENT.value for a in payload)
    assert any(a["polarity"] == AssertionPolarity.RISK_ABSENT.value for a in payload)


def test_authority_changes_confidence_not_asserted_severity():
    high = classify_safety_assertions("This medicine is contraindicated with the treatment.", authority="EMA HMPC Monograph", authority_score=1.0)
    low = classify_safety_assertions("This medicine is contraindicated with the treatment.", authority="Blog", authority_score=0.15)
    high_serious = next(a for a in high if a.assertion_type == SafetyAssertionType.CONTRAINDICATION)
    low_serious = next(a for a in low if a.assertion_type == SafetyAssertionType.CONTRAINDICATION)
    assert high_serious.severity == low_serious.severity == SeverityLevel.SERIOUS
    assert high_serious.evidence_strength == SafetyConfidence.HIGH
    assert low_serious.evidence_strength == SafetyConfidence.INSUFFICIENT


def test_protective_toxicity_context_does_not_create_serious_organ_toxicity():
    assertions = classify_safety_assertions("The flavonoid protects against drug-induced hepatotoxicity in mice.")
    assert not any(a.assertion_type == SafetyAssertionType.ORGAN_TOXICITY and a.severity == SeverityLevel.SERIOUS for a in assertions)


def test_mechanistic_cyp_signal_is_structured_but_non_blocking():
    assertions = classify_safety_assertions("The extract induces CYP3A4 expression in vitro.")
    assert any(a.assertion_type == SafetyAssertionType.CYP_INDUCTION and a.polarity == AssertionPolarity.MECHANISTIC_ONLY and a.severity == SeverityLevel.NONE for a in assertions)
    summary = summarize_safety_assertions(assertions)
    assert not summary["serious_assertions"]


def test_explainability_contains_sentence_assertion_severity_rule_and_evidence_id():
    row = _engine_row([{
        "Scientific_Name": "AltPlantPharmaSafety",
        "Target_Indication": "TestIndication",
        "Notes": "Use is contraindicated during pregnancy.",
        "Evidence_Record_ID": "ev-trace",
        "Source_Organization": "European Medicines Agency",
        "Source_Type": "HMPC monograph",
    }])
    explanation = build_candidate_explanation(row.to_dict(), [])
    eligibility_gates = [g for g in explanation["applied_gates"] if str(g.get("gate", "")).startswith("eligibility:")]
    assert eligibility_gates
    gate = eligibility_gates[0]
    assert gate["severity"] == "severe"
    assert gate["severity_rule"] == "pharma-safety-severity-v1"
    assert "ev-trace" in gate["evidence_ids"]
    assert any(a["evidence_record_id"] == "ev-trace" and a["source_sentence"] for a in gate["assertion_trace"])


def test_regulatory_and_guideline_authorities_are_not_collapsed_to_same_weight():
    import evidence_authority as ea
    fda = ea.classify_source_authority(source_organization="U.S. Food and Drug Administration")
    hc = ea.classify_source_authority(source_organization="Health Canada")
    tga = ea.classify_source_authority(source_organization="Therapeutic Goods Administration")
    guideline = ea.classify_source_authority(source_type="Clinical practice guideline")
    case_report = ea.classify_source_authority(source_type="Case report")
    assert fda.label == ea.AUTHORITY_FDA_REGULATORY
    assert hc.label == ea.AUTHORITY_HEALTH_CANADA_REGULATORY
    assert tga.label == ea.AUTHORITY_TGA_REGULATORY
    assert guideline.label == ea.AUTHORITY_CLINICAL_GUIDELINE
    assert fda.score > guideline.score > case_report.score


# ---------------------------------------------------------------------
# Root-cause regressions (2026-08-10, RGV v1 rerun): both real evidence
# texts below produced ZERO safety assertions before this fix --
# verified directly against classify_safety_assertions, not assumed --
# because of two separate vocabulary gaps in the same _ORGAN_TOXICITY
# regex family already fixed once for RGV v1's original remediation.
# rgv1_017_chaparral_oral/rgv1_018_germander_oral/etc. (the earlier fix's
# own cases) still pass -- these are two further gaps in the same
# family, not a re-break of the earlier fix.
# ---------------------------------------------------------------------
def test_organ_toxicity_recognizes_produce_as_a_causal_verb():
    # rgv2_020_belladonna_oral: the causal verb was "produce", which was
    # absent from the verb alternation even though the noun that follows
    # it ("neurotoxicity") was already recognized.
    text = "Belladonna poisoning can produce severe neurotoxicity including seizures, coma and anticholinergic toxicity."
    assertions = classify_safety_assertions(text)
    assert assertions
    assert assertions[0].assertion_type == SafetyAssertionType.ORGAN_TOXICITY
    assert assertions[0].severity == SeverityLevel.SERIOUS


def test_organ_toxicity_recognizes_anticholinergic_toxicity_as_a_serious_noun():
    # rgv2_018_datura_oral: the causal verb "result in" was already
    # recognized, but "anticholinergic toxicity" was not in the noun
    # list (only organ-specific hepato-/nephro-/cardio-/neuro- terms
    # were).
    text = "Ingestion of Datura species can result in severe anticholinergic toxicity with hallucinations, tachycardia, confusion and dangerous poisoning."
    assertions = classify_safety_assertions(text)
    assert assertions
    assert assertions[0].assertion_type == SafetyAssertionType.ORGAN_TOXICITY
    assert assertions[0].severity == SeverityLevel.SERIOUS


def test_organ_toxicity_still_recognizes_the_original_2026_08_08_fix_cases():
    # Non-regression: the standalone severe-outcome terms added for RGV
    # v1's original remediation (multiorgan failure, cardiovascular
    # collapse, etc.) must still match after this edit widened the same
    # tuple.
    for term in ("multiorgan failure", "cardiovascular collapse", "acute hepatic necrosis"):
        assertions = classify_safety_assertions(f"The case series reported {term} following high-dose use.")
        assert assertions, f"expected a SERIOUS assertion for {term!r}"
        assert assertions[0].severity == SeverityLevel.SERIOUS
