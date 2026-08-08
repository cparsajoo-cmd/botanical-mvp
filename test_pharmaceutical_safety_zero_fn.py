from assertion_vocabulary import SeverityLevel
from safety_assertion_engine import SafetyAssertionType, classify_safety_assertions
from eligibility_gate import classify_safety_finding, evaluate_eligibility, EligibilityStatus


def _types(text):
    return {a.assertion_type: a for a in classify_safety_assertions(text, evidence_record_id='ADV')}


def test_fatal_adverse_event_is_serious_and_cannot_enter_normal_ranking():
    a = _types('Fatal adverse events including death have been reported after use.')
    assert a[SafetyAssertionType.FATAL_ADVERSE_EVENT].severity == SeverityLevel.SERIOUS
    f = classify_safety_finding(hit_terms=frozenset(), flagged_terms=frozenset(), has_evidence_text=True, same_plant=False, assertions=tuple(a.values()))
    d = evaluate_eligibility(f, __import__('eligibility_gate').classify_regulatory_finding(barrier_types=frozenset(), has_evidence_text=True, same_plant=False))
    assert d.status in {EligibilityStatus.NO_GO_SAFETY, EligibilityStatus.EXPERT_REVIEW_REQUIRED}
    assert not d.eligible_for_normal_ranking


def test_serious_adverse_event_taxonomy():
    a = _types('Serious adverse events requiring hospitalization were associated with treatment.')
    assert a[SafetyAssertionType.SERIOUS_ADVERSE_EVENT].severity == SeverityLevel.SERIOUS


def test_carcinogenicity_genotoxicity_reproductive_toxicity_taxonomy():
    assert _types('The extract was shown to be carcinogenic in the study.')[SafetyAssertionType.CARCINOGENICITY].severity == SeverityLevel.SERIOUS
    assert _types('The preparation caused genotoxicity and DNA damage.')[SafetyAssertionType.GENOTOXICITY].severity == SeverityLevel.SERIOUS
    assert _types('The product caused reproductive toxicity in exposed animals.')[SafetyAssertionType.REPRODUCTIVE_TOXICITY].severity == SeverityLevel.SERIOUS


def test_serotonergic_cns_and_metabolic_cardiovascular_taxonomy():
    assert SafetyAssertionType.SEROTONERGIC_TOXICITY in _types('Concomitant use can cause serotonin syndrome.')
    assert SafetyAssertionType.CNS_DEPRESSION in _types('Concomitant sedatives may cause severe CNS depression.')
    assert SafetyAssertionType.HYPERTENSION in _types('Use can cause severe hypertension.')
    assert SafetyAssertionType.HYPOTENSION in _types('Use can cause severe hypotension.')
    assert SafetyAssertionType.DIABETES_INTERACTION in _types('May potentiate antidiabetic medicines and cause severe hypoglycemia.')


def test_geriatric_and_regulatory_warning_taxonomy():
    assert SafetyAssertionType.GERIATRIC_RESTRICTION in _types('Use is contraindicated in elderly patients.')
    assert _types('FDA boxed warning: risk of fatal liver injury.')[SafetyAssertionType.MAJOR_REGULATORY_SAFETY_WARNING].severity == SeverityLevel.SERIOUS


def test_population_metadata_is_not_discarded():
    assertions = classify_safety_assertions('Use is contraindicated.', affected_population=('pregnancy',), evidence_record_id='P1')
    assert any('pregnancy' in a.affected_population for a in assertions)
