"""Regression tests for evidence_coverage.py (architecture item 1, Evidence Coverage)."""

from evidence_coverage import classify_candidate_evidence_strength, _extract_source_count


def test_extract_source_count_parses_the_real_occurrence_corroboration_format():
    assert _extract_source_count("Corroborated by 5 independent sources") == 5
    assert _extract_source_count("Single-source claim — not independently corroborated") == 1
    assert _extract_source_count("No independent source identified — not corroborated") == 0
    assert _extract_source_count("") == 0


def test_single_source_low_confidence_is_preliminary():
    result = classify_candidate_evidence_strength(
        occurrence_corroboration="Single-source claim — not independently corroborated",
        evidence_confidence=10, evidence_hierarchy_detail=None,
    )
    assert result == "Preliminary"


def test_multi_source_but_low_confidence_is_partial():
    result = classify_candidate_evidence_strength(
        occurrence_corroboration="Corroborated by 2 independent sources",
        evidence_confidence=20, evidence_hierarchy_detail="Occurrence / analytical chemistry only",
    )
    assert result == "Partial Evidence"


def test_moderate_confidence_alone_no_corroboration_is_partial_not_preliminary():
    result = classify_candidate_evidence_strength(
        occurrence_corroboration="No independent source identified — not corroborated",
        evidence_confidence=55, evidence_hierarchy_detail="Observational human evidence",
    )
    assert result == "Partial Evidence"


def test_multi_source_and_moderate_confidence_is_broad():
    result = classify_candidate_evidence_strength(
        occurrence_corroboration="Corroborated by 3 independent sources",
        evidence_confidence=55, evidence_hierarchy_detail="Observational human evidence",
    )
    assert result == "Broad Evidence"


def test_multi_source_high_confidence_clinical_trial_is_decision_grade():
    result = classify_candidate_evidence_strength(
        occurrence_corroboration="Corroborated by 5 independent sources",
        evidence_confidence=85, evidence_hierarchy_detail="Clinical trial",
    )
    assert result == "High-priority evidence tier"


def test_multi_source_high_confidence_but_weak_hierarchy_is_not_decision_grade():
    # High confidence and many sources, but the hierarchy tier itself
    # isn't clinical/systematic-review level — must not be promoted to
    # Decision-grade just because the other two signals are strong.
    result = classify_candidate_evidence_strength(
        occurrence_corroboration="Corroborated by 8 independent sources",
        evidence_confidence=70, evidence_hierarchy_detail="In vitro / mechanistic",
    )
    assert result == "Broad Evidence"
    assert result != "High-priority evidence tier"


def test_systematic_review_also_qualifies_for_decision_grade():
    result = classify_candidate_evidence_strength(
        occurrence_corroboration="Corroborated by 4 independent sources",
        evidence_confidence=90, evidence_hierarchy_detail="Systematic review / meta-analysis",
    )
    assert result == "High-priority evidence tier"


def test_nothing_at_all_is_preliminary():
    result = classify_candidate_evidence_strength(
        occurrence_corroboration="No independent source identified — not corroborated",
        evidence_confidence=0, evidence_hierarchy_detail=None,
    )
    assert result == "Preliminary"


def test_tiers_are_ordered_consistently_as_signals_strengthen():
    tiers_seen = [
        classify_candidate_evidence_strength("No independent source identified — not corroborated", 0, None),
        classify_candidate_evidence_strength("Single-source claim — not independently corroborated", 20, None),
        classify_candidate_evidence_strength("Corroborated by 2 independent sources", 55, "Observational human evidence"),
        classify_candidate_evidence_strength("Corroborated by 5 independent sources", 90, "Clinical trial"),
    ]
    order = ["Preliminary", "Partial Evidence", "Broad Evidence", "High-priority evidence tier"]
    ranks = [order.index(t) for t in tiers_seen]
    assert ranks == sorted(ranks), f"coverage tiers did not strengthen monotonically: {tiers_seen}"


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
