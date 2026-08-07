from gold_corpus.e2e_pilot_diagnostics import build_diagnostics


def test_raw_mixed_domain_direction_metric_is_reproduced_but_not_relabelled_as_scientific_accuracy():
    d = build_diagnostics()["direction_diagnostics"]
    assert d["raw_mixed_domain_accuracy"]["numerator"] == 1
    assert d["raw_mixed_domain_accuracy"]["denominator"] == 9
    assert "mixed-domain metric is descriptive only" in d["interpretation"]


def test_indication_only_direction_diagnostic_excludes_safety_and_regulatory_cases():
    d = build_diagnostics()["direction_diagnostics"]
    assert d["indication_domain_accuracy"]["numerator"] == 1
    assert d["indication_domain_accuracy"]["denominator"] == 6
    assert all(r["domain"] == "Indication/Evidence" for r in d["rows"] if r["indication_domain"])


def test_study_result_direction_diagnostic_is_limited_to_systematic_reviews_in_current_pilot():
    d = build_diagnostics()["direction_diagnostics"]
    assert d["study_result_eligible_accuracy"]["numerator"] == 1
    assert d["study_result_eligible_accuracy"]["denominator"] == 3
    eligible = [r for r in d["rows"] if r["study_result_eligible"]]
    assert eligible
    assert {r["source_type"] for r in eligible} == {"SYSTEMATIC_REVIEW"}


def test_safety_false_negative_is_localized_downstream_of_successful_retrieval():
    s = build_diagnostics()["safety_diagnostics"]
    assert s["critical_source_recall"]["numerator"] == 1
    assert s["critical_source_recall"]["denominator"] == 1
    assert s["serious_safety_false_negative_rate"]["numerator"] == 1
    assert s["serious_safety_false_negative_rate"]["denominator"] == 1
    row = s["cases"][0]
    assert row["safety_critical_retrieved"] == 1
    assert row["safety_gate_failed"] is False
    assert row["failure_code"] == "SERIOUS_SAFETY_EVIDENCE_IGNORED"


def test_diagnostics_do_not_rewrite_gold_truth_or_production_output():
    data = build_diagnostics()
    assert data["diagnostic_version"] == "gold-corpus-e2e-diagnostics/1"
    assert data["source_pilot_run"].endswith("pilot_evaluation_run.json")
