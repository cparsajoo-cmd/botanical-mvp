"""
Regression tests for data_contracts.py (Phase 3).

These are deliberately lightweight — this file has no external
dependencies (no network, no Supabase, no pydantic), so every test
just confirms the dataclasses actually construct with realistic data
and the shared helper functions behave the way their docstrings claim.
"""

import data_contracts as dc


def test_all_nine_entities_construct_with_minimal_required_fields():
    dc.Plant(scientific_name="Silybum marianum")
    dc.Compound(compound_name="Silymarin")
    dc.PlantCompoundOccurrence(
        plant_scientific_name="Silybum marianum",
        accepted_taxonomic_name=None,
        plant_synonym_used=None,
        compound_id="c1",
    )
    dc.TargetMechanism(target_name="Nrf2")
    dc.ScientificEvidence()
    dc.CommercialProduct(product_name="Test product")
    dc.RegulatoryRecord(status=dc.MarketVerificationStatus.UNKNOWN)
    dc.SafetyInteraction(compound_or_whole_plant="Silymarin")
    dc.CandidateAssessment(
        project_id="p1", indication="Liver support", product_type="Infusion",
        dosage_form="Infusion", target_market="EU",
        reference_plant="Silybum marianum", reference_plant_part=None,
        reference_compound="Silymarin", reference_compound_id=None,
        alternative_plant="Allium cepa", alternative_plant_part=None,
        alternative_compound="Quercetin", alternative_compound_id=None,
    )


def test_candidate_assessment_keeps_confidence_and_opportunity_separate():
    # Phase 1 audit 4.16: a candidate can have high opportunity and low
    # confidence at the same time — the schema must allow that, not
    # collapse them into one number.
    cand = dc.CandidateAssessment(
        project_id="p1", indication="Liver support", product_type="Infusion",
        dosage_form="Infusion", target_market="EU",
        reference_plant="Silybum marianum", reference_plant_part=None,
        reference_compound="Silymarin", reference_compound_id=None,
        alternative_plant="Allium cepa", alternative_plant_part=None,
        alternative_compound="Quercetin", alternative_compound_id=None,
        evidence_confidence=20.0,
        rd_opportunity_score=90.0,
    )
    assert cand.evidence_confidence != cand.rd_opportunity_score
    assert cand.evidence_confidence == 20.0
    assert cand.rd_opportunity_score == 90.0


def test_completeness_report_flags_missing_fields_correctly():
    sparse = dc.Plant(scientific_name="Silybum marianum")
    report = dc.completeness_report(sparse)
    assert report["populated_fields"] == 2  # scientific_name + verification_status default
    assert "family" in report["missing_fields"]
    assert "scientific_name" not in report["missing_fields"]
    assert 0 <= report["completeness_score"] <= 100

    full = dc.Plant(
        scientific_name="Silybum marianum",
        accepted_taxonomic_name="Silybum marianum (L.) Gaertn.",
        synonyms=["Carduus marianus"],
        common_names=["Milk thistle"],
        family="Asteraceae",
        native_region="Mediterranean",
        plant_parts_known=["Seed"],
        traditional_system="European herbal medicine",
        source_record_ids=["src-1"],
    )
    full_report = dc.completeness_report(full)
    assert full_report["completeness_score"] > report["completeness_score"]


def test_evidence_hierarchy_rank_orders_strongest_first():
    strong = dc.evidence_hierarchy_rank(dc.EvidenceHierarchyLevel.SYSTEMATIC_REVIEW_META_ANALYSIS)
    weak = dc.evidence_hierarchy_rank(dc.EvidenceHierarchyLevel.COMPUTATIONAL_HYPOTHESIS)
    unknown = dc.evidence_hierarchy_rank(None)

    assert strong < weak, "systematic review should rank stronger (lower number) than a hypothesis"
    assert weak < unknown, "an unscored/unknown record should rank weaker than even the weakest named tier"


def test_is_evidence_at_least_respects_hierarchy_direction():
    assert dc.is_evidence_at_least(
        dc.EvidenceHierarchyLevel.CLINICAL_TRIAL,
        dc.EvidenceHierarchyLevel.OBSERVATIONAL_HUMAN,
    ), "a clinical trial should count as at least as strong as observational evidence"

    assert not dc.is_evidence_at_least(
        dc.EvidenceHierarchyLevel.OBSERVATIONAL_HUMAN,
        dc.EvidenceHierarchyLevel.CLINICAL_TRIAL,
    ), "observational evidence should NOT count as at least as strong as a clinical trial"


def test_dataclass_field_names_matches_actual_fields():
    names = dc.dataclass_field_names(dc.SafetyInteraction)
    assert "compound_or_whole_plant" in names
    assert "adverse_event" in names
    assert "source_record_id" in names


if __name__ == "__main__":
    import sys

    try:
        import pytest
        sys.exit(pytest.main([__file__, "-v"]))
    except ImportError:
        this_module = sys.modules[__name__]
        test_fns = [
            getattr(this_module, name)
            for name in dir(this_module)
            if name.startswith("test_") and callable(getattr(this_module, name))
        ]
        passed, failed = [], []
        for fn in test_fns:
            try:
                fn()
            except AssertionError as exc:
                failed.append((fn.__name__, str(exc) or "assertion failed"))
            except Exception as exc:  # noqa: BLE001
                failed.append((fn.__name__, f"{type(exc).__name__}: {exc}"))
            else:
                passed.append(fn.__name__)
        print(f"\n{len(passed) + len(failed)} test(s) run.\n")
        for name in passed:
            print(f"  \u2705 {name}")
        if failed:
            print()
            for name, reason in failed:
                print(f"  \u274c {name}\n     -> {reason}")
            print(f"\n{len(failed)} FAILED, {len(passed)} passed.\n")
            sys.exit(1)
        print(f"\nALL TESTS PASSED ({len(passed)}/{len(passed)}).\n")
        sys.exit(0)
