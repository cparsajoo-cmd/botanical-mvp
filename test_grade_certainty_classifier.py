"""Regression tests for grade_certainty_classifier.py (Task 2 —
GRADE-style clinical-evidence certainty grading). See that module's
docstring for the full documented method and its declared limitations.
"""

from grade_certainty_classifier import (
    NOT_GRADE_APPLICABLE,
    classify_grade_certainty,
)


# ---------------------------------------------------------------------
# Tier applicability
# ---------------------------------------------------------------------

def test_non_clinical_tiers_are_not_grade_applicable():
    for tier in (
        "Validated ex vivo / in vivo",
        "In vitro / mechanistic",
        "Traditional-use / regulatory monograph",
        "Occurrence / analytical chemistry only",
        "Unclassified",
        None,
    ):
        result = classify_grade_certainty(tier, "some evidence text")
        assert result.certainty == NOT_GRADE_APPLICABLE
        assert result.domains == {}


def test_starting_certainty_by_tier_before_any_downgrade():
    # Systematic review / meta-analysis and Clinical trial both start
    # High; Observational human evidence starts Low. Verified here
    # with every downgrade domain explicitly satisfied (well-described
    # evidence, multiple sources, direct applicability, no negative
    # finding) so the result reflects the STARTING tier, not a
    # downgraded one — the minimal-detail case (few/no markers
    # present) is intentionally downgraded elsewhere in this file (see
    # test_poorly_supported_clinical_trial_floors_at_very_low and
    # test_risk_of_bias_serious_when_no_markers): a bare mention of a
    # tier with no supporting detail is honestly less certain than one
    # with detail, which is the whole point of this module.
    well_supported_kwargs = dict(
        evidence_text="A double-blind, placebo-controlled trial with n=250 patients.",
        has_negative_evidence=False,
        occurrence_corroboration="Corroborated by 3 independent sources",
        applicability_classification="Directly applicable",
    )

    result_sr = classify_grade_certainty(
        "Systematic review / meta-analysis", **well_supported_kwargs
    )
    assert result_sr.certainty == "High"

    result_ct = classify_grade_certainty("Clinical trial", **well_supported_kwargs)
    assert result_ct.certainty == "High"

    result_obs = classify_grade_certainty(
        "Observational human evidence", **well_supported_kwargs
    )
    assert result_obs.certainty == "Low"


# ---------------------------------------------------------------------
# Risk of bias domain — only assessed for "Clinical trial"
# ---------------------------------------------------------------------

def test_risk_of_bias_not_assessed_for_systematic_review():
    result = classify_grade_certainty(
        "Systematic review / meta-analysis", "no methodology markers here"
    )
    assert result.domains["risk_of_bias"].rating == "Not assessed"
    assert result.domains["risk_of_bias"].downgrade == 0


def test_risk_of_bias_not_assessed_for_observational():
    result = classify_grade_certainty(
        "Observational human evidence", "no methodology markers here"
    )
    assert result.domains["risk_of_bias"].rating == "Not assessed"


def test_risk_of_bias_not_serious_when_blinded():
    result = classify_grade_certainty(
        "Clinical trial", "A double-blind trial was conducted."
    )
    assert result.domains["risk_of_bias"].rating == "Not serious"


def test_risk_of_bias_not_serious_when_placebo_controlled():
    result = classify_grade_certainty(
        "Clinical trial", "A placebo-controlled trial was conducted."
    )
    assert result.domains["risk_of_bias"].rating == "Not serious"


def test_risk_of_bias_serious_when_no_markers():
    result = classify_grade_certainty("Clinical trial", "A trial was conducted.")
    assert result.domains["risk_of_bias"].rating == "Serious"
    assert result.domains["risk_of_bias"].downgrade == 1


# ---------------------------------------------------------------------
# Imprecision domain — assessed for Clinical trial + Observational
# ---------------------------------------------------------------------

def test_imprecision_not_assessed_for_systematic_review():
    result = classify_grade_certainty(
        "Systematic review / meta-analysis", "n=500 across all included trials"
    )
    assert result.domains["imprecision"].rating == "Not assessed"


def test_imprecision_not_serious_with_large_sample():
    result = classify_grade_certainty("Clinical trial", "n=200 patients enrolled.")
    assert result.domains["imprecision"].rating == "Not serious"


def test_imprecision_serious_with_small_or_no_sample_reported():
    result = classify_grade_certainty("Clinical trial", "A small pilot trial.")
    assert result.domains["imprecision"].rating == "Serious"

    result_obs = classify_grade_certainty(
        "Observational human evidence", "n=40 participants."
    )
    assert result_obs.domains["imprecision"].rating == "Serious"


# ---------------------------------------------------------------------
# Inconsistency domain
# ---------------------------------------------------------------------

def test_inconsistency_serious_when_negative_evidence_present():
    result = classify_grade_certainty(
        "Clinical trial", "A trial.", has_negative_evidence=True
    )
    assert result.domains["inconsistency"].rating == "Serious"


def test_inconsistency_not_serious_when_no_negative_evidence():
    result = classify_grade_certainty(
        "Clinical trial", "A trial.", has_negative_evidence=False
    )
    assert result.domains["inconsistency"].rating == "Not serious"


# ---------------------------------------------------------------------
# Indirectness domain
# ---------------------------------------------------------------------

def test_indirectness_not_serious_when_directly_applicable():
    result = classify_grade_certainty(
        "Clinical trial", "A trial.", applicability_classification="Directly applicable"
    )
    assert result.domains["indirectness"].rating == "Not serious"


def test_indirectness_serious_when_partially_applicable():
    result = classify_grade_certainty(
        "Clinical trial", "A trial.", applicability_classification="Partially applicable"
    )
    assert result.domains["indirectness"].rating == "Serious"
    assert result.domains["indirectness"].downgrade == 1


def test_indirectness_very_serious_when_indirectly_relevant_or_not_applicable():
    for classification in ("Indirectly relevant", "Not applicable"):
        result = classify_grade_certainty(
            "Clinical trial", "A trial.", applicability_classification=classification
        )
        assert result.domains["indirectness"].rating == "Very serious"
        assert result.domains["indirectness"].downgrade == 2


def test_indirectness_not_assessed_when_missing_or_not_assessable():
    for classification in (None, "", "Not assessable", "Some unrecognized value"):
        result = classify_grade_certainty(
            "Clinical trial", "A trial.", applicability_classification=classification
        )
        assert result.domains["indirectness"].rating == "Not assessed"
        assert result.domains["indirectness"].downgrade == 0


# ---------------------------------------------------------------------
# Publication bias domain
# ---------------------------------------------------------------------

def test_publication_bias_not_serious_with_multiple_sources():
    result = classify_grade_certainty(
        "Clinical trial", "A trial.",
        occurrence_corroboration="Corroborated by 2 independent sources",
    )
    assert result.domains["publication_bias"].rating == "Not serious"


def test_publication_bias_serious_with_single_or_no_source():
    result = classify_grade_certainty(
        "Clinical trial", "A trial.",
        occurrence_corroboration="Single-source claim — not independently corroborated",
    )
    assert result.domains["publication_bias"].rating == "Serious"

    result_none = classify_grade_certainty("Clinical trial", "A trial.")
    assert result_none.domains["publication_bias"].rating == "Serious"


# ---------------------------------------------------------------------
# End-to-end downgrade arithmetic and floor behavior
# ---------------------------------------------------------------------

def test_well_supported_clinical_trial_stays_high():
    result = classify_grade_certainty(
        evidence_hierarchy_detail="Clinical trial",
        evidence_text="A double-blind, placebo-controlled trial with n=250 patients.",
        has_negative_evidence=False,
        occurrence_corroboration="Corroborated by 3 independent sources",
        applicability_classification="Directly applicable",
    )
    assert result.certainty == "High"


def test_poorly_supported_clinical_trial_floors_at_very_low():
    result = classify_grade_certainty(
        evidence_hierarchy_detail="Clinical trial",
        evidence_text="A trial was conducted.",
        has_negative_evidence=True,
        occurrence_corroboration="Single-source claim — not independently corroborated",
        applicability_classification="Indirectly relevant",
    )
    # 5 downgrade points from a starting rank of 3 (High) floors at 0
    # (Very Low), never goes negative.
    assert result.certainty == "Very Low"


def test_moderate_downgrade_lands_between_high_and_very_low():
    result = classify_grade_certainty(
        evidence_hierarchy_detail="Clinical trial",
        evidence_text="A double-blind trial with n=200 patients.",
        has_negative_evidence=False,
        occurrence_corroboration="Single-source claim — not independently corroborated",
        applicability_classification="Partially applicable",
    )
    # risk_of_bias: not serious (blinded), imprecision: not serious
    # (large sample), inconsistency: not serious, indirectness: serious
    # (-1), publication_bias: serious (-1) => total downgrade 2,
    # High(3) - 2 = rank 1 = Low.
    assert result.certainty == "Low"


def test_certainty_never_reported_below_very_low_or_above_starting_tier():
    result = classify_grade_certainty(
        evidence_hierarchy_detail="Observational human evidence",
        evidence_text="",
        has_negative_evidence=True,
        occurrence_corroboration="",
        applicability_classification="Not applicable",
    )
    assert result.certainty in {"Very Low", "Low"}


def test_rationale_mentions_starting_tier_and_is_non_empty():
    result = classify_grade_certainty("Clinical trial", "A trial.")
    assert "Clinical trial" in result.rationale
    assert len(result.rationale) > 0


def test_never_raises_on_missing_optional_inputs():
    # Every optional argument omitted — must degrade gracefully, not crash.
    result = classify_grade_certainty("Clinical trial")
    assert result.certainty in {"High", "Moderate", "Low", "Very Low"}


def test_domains_as_text_returns_plain_dicts_for_every_domain():
    result = classify_grade_certainty("Clinical trial", "A trial.")
    flattened = result.domains_as_text()
    assert set(flattened.keys()) == {
        "risk_of_bias", "imprecision", "inconsistency",
        "indirectness", "publication_bias",
    }
    for entry in flattened.values():
        assert set(entry.keys()) == {"rating", "downgrade", "reason"}
