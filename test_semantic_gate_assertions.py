from semantic_gate_assertions import (
    MarketAccessEffect,
    RegulatoryAction,
    SemanticRegulatoryAssertion,
    parse_semantic_gate_payload,
    safety_assertion_from_semantic,
)
from safety_assertion_engine import SafetyAssertionType, SafetyConfidence
from eligibility_gate import (
    classify_safety_finding,
    classify_regulatory_finding,
    evaluate_eligibility,
    EligibilityStatus,
)


def _safety_payload(
    span, seriousness="serious", hazard="other", confidence=0.99,
    seriousness_criterion="hospitalization",
):
    return {
        "hazard_present": True,
        "hazard_type": hazard,
        "reported_outcome": "anticholinergic toxicity",
        "seriousness": seriousness,
        "seriousness_criterion": seriousness_criterion,
        "polarity": "risk_present",
        "causal_relationship": "causal",
        "preparation": "",
        "route": "",
        "dose_dependency": "unknown",
        "affected_population": [],
        "context_applicability": "unknown",
        "supporting_text": span,
        "extraction_confidence": confidence,
    }


def test_unknown_safety_vocabulary_still_preserves_serious_semantics():
    text = "The preparation caused severe anticholinergic toxicity requiring hospitalization."
    a = safety_assertion_from_semantic(
        _safety_payload(text),
        source_text=text,
        evidence_record_id="E1",
        authority="Case report",
        authority_score=0.4,
    )
    assert a is not None
    assert a.assertion_type == SafetyAssertionType.SERIOUS_ADVERSE_EVENT
    assert a.evidence_strength == SafetyConfidence.LOW
    assert a.semantic_extraction_confidence == 0.99
    assert a.provenance == "llm_semantic_gate"


def test_nonverbatim_supporting_span_is_rejected():
    text = "No clinically important toxicity was observed."
    a = safety_assertion_from_semantic(
        _safety_payload("Severe liver failure occurred."),
        source_text=text,
    )
    assert a is None


def test_semantic_serious_species_wide_can_hard_stop_without_regex_synonym():
    text = "Exposure caused severe anticholinergic toxicity requiring hospitalization."
    payload = _safety_payload(text)
    payload["context_applicability"] = "relevant"
    a = safety_assertion_from_semantic(payload, source_text=text)
    safety = classify_safety_finding(
        hit_terms=frozenset(), flagged_terms=frozenset(),
        has_evidence_text=True, same_plant=True, assertions=(a,),
    )
    regulatory = classify_regulatory_finding(
        barrier_types=frozenset(), has_evidence_text=True, same_plant=True,
    )
    decision = evaluate_eligibility(safety, regulatory)
    assert decision.status == EligibilityStatus.NO_GO_SAFETY
    assert decision.hard_no_go


def test_semantic_serious_preparation_specific_routes_to_expert_review():
    text = "Unprocessed root preparations caused severe liver injury requiring hospitalization."
    payload = _safety_payload(text)
    payload["preparation"] = "unprocessed root preparation"
    payload["context_applicability"] = "unknown"
    a = safety_assertion_from_semantic(payload, source_text=text)
    safety = classify_safety_finding(
        hit_terms=frozenset(), flagged_terms=frozenset(),
        has_evidence_text=True, same_plant=True, assertions=(a,),
    )
    regulatory = classify_regulatory_finding(
        barrier_types=frozenset(), has_evidence_text=True, same_plant=True,
    )
    decision = evaluate_eligibility(safety, regulatory)
    assert decision.status == EligibilityStatus.EXPERT_REVIEW_REQUIRED
    assert not decision.hard_no_go

def test_deterministic_plus_semantic_serious_can_hard_stop():
    text = "Fatal liver failure was reported."
    a = safety_assertion_from_semantic(_safety_payload(text), source_text=text)
    safety = classify_safety_finding(
        hit_terms=frozenset({"fatal"}), flagged_terms=frozenset({"fatal"}),
        has_evidence_text=True, same_plant=True, assertions=(a,),
    )
    regulatory = classify_regulatory_finding(
        barrier_types=frozenset(), has_evidence_text=True, same_plant=True,
    )
    decision = evaluate_eligibility(safety, regulatory)
    assert decision.status == EligibilityStatus.NO_GO_SAFETY
    assert decision.hard_no_go


def test_semantic_relevant_regulatory_block_can_hard_stop_without_regex_phrase():
    a = SemanticRegulatoryAssertion(
        action=RegulatoryAction.TERMINATED,
        market_access_effect=MarketAccessEffect.BLOCKS_MARKET_ACCESS,
        supporting_text="The procedure was terminated without authorization.",
        evidence_record_id="R1",
        extraction_confidence=0.95,
        context_applicability="relevant",
    )
    reg = classify_regulatory_finding(
        barrier_types=frozenset(), has_evidence_text=True, same_plant=True,
        finding_text=a.supporting_text, semantic_assertions=(a,),
    )
    safety = classify_safety_finding(
        hit_terms=frozenset(), flagged_terms=frozenset(),
        has_evidence_text=True, same_plant=True,
    )
    decision = evaluate_eligibility(safety, reg)
    assert decision.status == EligibilityStatus.NO_GO_REGULATORY
    assert decision.hard_no_go


def test_semantic_unknown_applicability_regulatory_block_still_routes_to_review():
    a = SemanticRegulatoryAssertion(
        action=RegulatoryAction.TERMINATED,
        market_access_effect=MarketAccessEffect.BLOCKS_MARKET_ACCESS,
        supporting_text="The procedure was terminated without authorization.",
        evidence_record_id="R1u",
        extraction_confidence=0.95,
        context_applicability="unknown",
    )
    reg = classify_regulatory_finding(
        barrier_types=frozenset(), has_evidence_text=True, same_plant=True,
        finding_text=a.supporting_text, semantic_assertions=(a,),
    )
    safety = classify_safety_finding(
        hit_terms=frozenset(), flagged_terms=frozenset(),
        has_evidence_text=True, same_plant=True,
    )
    decision = evaluate_eligibility(safety, reg)
    assert decision.status == EligibilityStatus.EXPERT_REVIEW_REQUIRED
    assert not decision.hard_no_go

def test_authorization_required_is_review_not_prohibition():
    a = SemanticRegulatoryAssertion(
        action=RegulatoryAction.AUTHORIZATION_REQUIRED,
        market_access_effect=MarketAccessEffect.CONDITIONAL_ACCESS,
        supporting_text="A pre-market authorization is required.",
        evidence_record_id="R2",
        extraction_confidence=0.95,
        context_applicability="relevant",
    )
    reg = classify_regulatory_finding(
        barrier_types=frozenset(), has_evidence_text=True, same_plant=True,
        finding_text=a.supporting_text, semantic_assertions=(a,),
    )
    safety = classify_safety_finding(
        hit_terms=frozenset(), flagged_terms=frozenset(),
        has_evidence_text=True, same_plant=True,
    )
    decision = evaluate_eligibility(safety, reg)
    assert decision.status == EligibilityStatus.EXPERT_REVIEW_REQUIRED
    assert reg.status.value == "restricted"


def test_semantic_parser_keeps_record_provenance_and_warns_on_bad_span():
    source = "Severe liver injury was reported. The ingredient is authorized."
    payload = {
        "safety_assertions": [_safety_payload("Severe liver injury was reported.")],
        "regulatory_assertions": [{
            "action": "authorized",
            "market_access_effect": "no_block",
            "jurisdiction": "EU",
            "authority": "EU authority",
            "ingredient": "Example",
            "plant_part": "",
            "preparation": "",
            "route": "",
            "product_category": "food",
            "conditions": "",
            "effective_date": "",
            "context_applicability": "relevant",
            "supporting_text": "NOT A REAL SPAN",
            "extraction_confidence": 0.9,
        }],
    }
    safety, regulatory, warnings = parse_semantic_gate_payload(
        payload, source_text=source, evidence_record_id="E9"
    )
    assert safety[0].evidence_record_id == "E9"
    assert not regulatory
    assert "invalid_or_nonverbatim_regulatory_supporting_span" in warnings


def test_serious_label_without_seriousness_basis_is_downgraded():
    text = "Burning, itching, headache and dizziness were reported after topical use."
    a = safety_assertion_from_semantic(
        _safety_payload(
            text,
            seriousness="serious",
            hazard="serious_adverse_event",
            seriousness_criterion="none",
        ),
        source_text=text,
    )
    assert a is not None
    assert a.severity.value == "MODERATE"


def test_real_world_id59_tolerability_list_cannot_become_serious_without_basis():
    text = (
        "Topical agents and synthetic drugs used for dandruff treatment have "
        "specific side effects including burning at the application site, "
        "depression, dizziness, headache, itching or skin irritation."
    )
    a = safety_assertion_from_semantic(
        _safety_payload(
            text,
            seriousness="serious",
            hazard="serious_adverse_event",
            seriousness_criterion="none",
        ),
        source_text=text,
        evidence_record_id="59",
    )
    assert a is not None
    assert a.severity.value != "SERIOUS"


def test_uncertainty_statement_is_not_a_supported_serious_hazard():
    text = "However, more toxicity tests should be carried out to confirm its safety."
    a = safety_assertion_from_semantic(
        _safety_payload(
            text,
            seriousness="serious",
            hazard="warning",
            seriousness_criterion="unknown",
        ),
        source_text=text,
        evidence_record_id="60",
    )
    assert a is not None
    assert a.severity.value != "SERIOUS"


def test_semantic_relevant_serious_route_specific_hazard_hard_stops():
    text = "Oral exposure caused life-threatening poisoning requiring hospitalization."
    payload = _safety_payload(text, seriousness_criterion="life_threatening")
    payload["route"] = "oral"
    payload["affected_population"] = ["general"]
    payload["context_applicability"] = "relevant"
    a = safety_assertion_from_semantic(payload, source_text=text)
    safety = classify_safety_finding(
        hit_terms=frozenset(), flagged_terms=frozenset(),
        has_evidence_text=True, same_plant=True, assertions=(a,),
    )
    regulatory = classify_regulatory_finding(
        barrier_types=frozenset(), has_evidence_text=True, same_plant=True,
    )
    decision = evaluate_eligibility(safety, regulatory)
    assert safety.context_relevance.value == "relevant"
    assert decision.status == EligibilityStatus.NO_GO_SAFETY


def test_semantic_unknown_serious_route_specific_hazard_still_requires_review():
    text = "Oral exposure caused life-threatening poisoning requiring hospitalization."
    payload = _safety_payload(text, seriousness_criterion="life_threatening")
    payload["route"] = "oral"
    payload["context_applicability"] = "unknown"
    a = safety_assertion_from_semantic(payload, source_text=text)
    safety = classify_safety_finding(
        hit_terms=frozenset(), flagged_terms=frozenset(),
        has_evidence_text=True, same_plant=True, assertions=(a,),
    )
    regulatory = classify_regulatory_finding(
        barrier_types=frozenset(), has_evidence_text=True, same_plant=True,
    )
    decision = evaluate_eligibility(safety, regulatory)
    assert decision.status == EligibilityStatus.EXPERT_REVIEW_REQUIRED
