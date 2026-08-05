"""Phase 3 — tests for evidence_authority.py.

Every test here is a pure unit test: no pandas, no DataFrame, no
database. Per the Phase 3 brief's requirement that "classification
functions باید بدون DataFrame نیز قابل unit test باشند."
"""
import evidence_authority as ea


# ---------------------------------------------------------------------
# 1-14: one deterministic test per taxonomy category (brief's required
# minimum list).
# ---------------------------------------------------------------------

def test_ema_hmpc_monograph_authority():
    result = ea.classify_source_authority(
        source_organization="European Medicines Agency",
        supporting_text="HMPC monograph on Melissa officinalis",
    )
    assert result.label == ea.AUTHORITY_EMA_HMPC_MONOGRAPH
    assert result.score == ea.AUTHORITY_FACTORS[ea.AUTHORITY_EMA_HMPC_MONOGRAPH]
    assert result.score == 1.00


def test_who_monograph_authority():
    result = ea.classify_source_authority(
        supporting_text="WHO monograph on selected medicinal plants, Chamomilla recutita",
    )
    assert result.label == ea.AUTHORITY_WHO_MONOGRAPH
    assert result.score == 0.97


def test_escop_monograph_authority():
    result = ea.classify_source_authority(
        source_organization="ESCOP",
        supporting_text="ESCOP monograph on Valeriana officinalis",
    )
    assert result.label == ea.AUTHORITY_ESCOP_MONOGRAPH
    assert result.score == 0.93


def test_cochrane_review_authority():
    result = ea.classify_source_authority(
        supporting_text="Cochrane systematic review of valerian for insomnia",
    )
    assert result.label == ea.AUTHORITY_COCHRANE_REVIEW
    assert result.score == 0.93


def test_systematic_review_meta_analysis_authority_fallback():
    result = ea.classify_source_authority(
        connector_name="PubMed",
        supporting_text="A systematic review and meta-analysis of chamomile for anxiety",
    )
    assert result.label == ea.AUTHORITY_SYSTEMATIC_REVIEW
    assert result.score == 0.85


def test_randomized_controlled_trial_authority_fallback():
    result = ea.classify_source_authority(
        connector_name="PubMed",
        supporting_text="A randomized controlled trial of Melissa officinalis extract",
    )
    assert result.label == ea.AUTHORITY_RCT
    assert result.score == 0.80


def test_controlled_clinical_trial_authority_fallback():
    result = ea.classify_source_authority(
        connector_name="PubMed",
        supporting_text="A controlled clinical trial evaluating chamomile tea",
    )
    assert result.label == ea.AUTHORITY_CONTROLLED_CLINICAL_TRIAL
    assert result.score == 0.72


def test_observational_study_authority_fallback():
    result = ea.classify_source_authority(
        connector_name="PubMed",
        supporting_text="A prospective cohort study of herbal tea consumption",
    )
    assert result.label == ea.AUTHORITY_OBSERVATIONAL_STUDY
    assert result.score == 0.60


def test_case_report_authority_fallback():
    result = ea.classify_source_authority(
        connector_name="PubMed",
        supporting_text="A case report of adverse reaction to kava extract",
    )
    assert result.label == ea.AUTHORITY_CASE_REPORT
    assert result.score == 0.45


def test_animal_study_authority_fallback():
    result = ea.classify_source_authority(
        connector_name="PubMed",
        supporting_text="An animal study in a rat model of anxiety",
    )
    assert result.label == ea.AUTHORITY_ANIMAL_STUDY
    assert result.score == 0.40


def test_in_vitro_study_authority_fallback():
    result = ea.classify_source_authority(
        connector_name="PubMed",
        supporting_text="An in vitro cell line assay of anti-inflammatory activity",
    )
    assert result.label == ea.AUTHORITY_IN_VITRO_STUDY
    assert result.score == 0.35


def test_commercial_website_authority():
    result = ea.classify_source_authority(
        source_url="https://herbalshop.example.com/buy/chamomile-tea",
        source_type="Commercial Website",
    )
    assert result.label == ea.AUTHORITY_COMMERCIAL_WEBSITE
    assert result.score == 0.20


def test_blog_authority():
    result = ea.classify_source_authority(
        source_url="https://myherbsjournal.wordpress.com/2024/chamomile-benefits",
    )
    assert result.label == ea.AUTHORITY_BLOG
    assert result.score == 0.15


def test_unknown_source_authority_conservative_fallback():
    result = ea.classify_source_authority()
    assert result.label == ea.AUTHORITY_UNKNOWN
    assert result.score == 0.50
    # Explicitly not zero and not the maximum.
    assert 0.0 < result.score < 1.0


# ---------------------------------------------------------------------
# Precedence / false-positive protection
# ---------------------------------------------------------------------

def test_generic_combined_regulatory_bucket_does_not_falsely_resolve_to_any_specific_org():
    """source_registry.py's own connector entry is literally named
    "EMA/WHO/ESCOP Regulatory" — this string alone must not resolve to
    EMA, WHO, or ESCOP without more specific supporting metadata (see
    PHASE3_SOURCE_AUTHORITY_AUDIT.md §1.1)."""
    result = ea.classify_source_authority(
        source_organization="EMA/WHO/ESCOP Regulatory",
        connector_name="EMA/WHO/ESCOP Regulatory",
    )
    assert result.label == ea.AUTHORITY_UNKNOWN


def test_ema_precedence_over_who_and_escop_when_all_mentioned():
    result = ea.classify_source_authority(
        supporting_text=(
            "HMPC monograph referencing WHO monographs on selected "
            "medicinal plants and ESCOP monograph guidance"
        ),
    )
    assert result.label == ea.AUTHORITY_EMA_HMPC_MONOGRAPH


def test_who_precedence_over_escop_when_ema_absent():
    result = ea.classify_source_authority(
        supporting_text="WHO monograph also referencing ESCOP monograph guidance",
    )
    assert result.label == ea.AUTHORITY_WHO_MONOGRAPH


def test_commercial_and_blog_precedence_over_literature_fallback():
    """A commercial page that happens to mention "clinical trial" in
    marketing copy must not be classified as literature."""
    result = ea.classify_source_authority(
        source_url="https://herbalshop.example.com/buy/chamomile",
        source_type="Commercial Website",
        supporting_text="Backed by a randomized controlled trial",
    )
    assert result.label == ea.AUTHORITY_COMMERCIAL_WEBSITE


# ---------------------------------------------------------------------
# Ordering sanity: EMA/WHO/ESCOP/Cochrane > literature > Unknown >
# commercial/blog (Phase 3 brief: "EMA/WHO/ESCOP monograph باید از یک
# blog معتبرتر باشد").
# ---------------------------------------------------------------------

def test_authority_factor_ordering_regulatory_above_literature_above_unknown_above_blog():
    ema = ea.AUTHORITY_FACTORS[ea.AUTHORITY_EMA_HMPC_MONOGRAPH]
    who = ea.AUTHORITY_FACTORS[ea.AUTHORITY_WHO_MONOGRAPH]
    escop = ea.AUTHORITY_FACTORS[ea.AUTHORITY_ESCOP_MONOGRAPH]
    cochrane = ea.AUTHORITY_FACTORS[ea.AUTHORITY_COCHRANE_REVIEW]
    rct = ea.AUTHORITY_FACTORS[ea.AUTHORITY_RCT]
    unknown = ea.AUTHORITY_FACTORS[ea.AUTHORITY_UNKNOWN]
    blog = ea.AUTHORITY_FACTORS[ea.AUTHORITY_BLOG]
    commercial = ea.AUTHORITY_FACTORS[ea.AUTHORITY_COMMERCIAL_WEBSITE]

    assert min(ema, who, escop, cochrane) > rct
    assert rct > unknown
    assert unknown > blog
    assert unknown > commercial
    assert blog != 0.0 and commercial != 0.0


# ---------------------------------------------------------------------
# classify_source_authority_from_row — dict/pandas-Series-shaped rows.
# ---------------------------------------------------------------------

def test_classify_from_row_ingestion_shape():
    row = {
        "Source_Organization": "World Health Organization",
        "Source_Title": "WHO monograph on Matricaria chamomilla",
    }
    result = ea.classify_source_authority_from_row(row)
    assert result.label == ea.AUTHORITY_WHO_MONOGRAPH


def test_classify_from_row_candidate_shortlisting_shape():
    row = {
        "Evidence_Source": "PubMed",
        "Evidence_Hierarchy_Detail": "Randomized controlled trial evidence",
    }
    result = ea.classify_source_authority_from_row(row)
    assert result.label == ea.AUTHORITY_RCT


def test_classify_from_row_never_raises_on_missing_keys():
    result = ea.classify_source_authority_from_row({})
    assert result.label == ea.AUTHORITY_UNKNOWN


# ---------------------------------------------------------------------
# Combination formulas: evidence_strength / signed_evidence_contribution
# ---------------------------------------------------------------------

def test_weighted_evidence_strength_formula():
    strength = ea.weighted_evidence_strength(
        quality_factor=1.0, authority_factor=0.8, applicability_factor_value=1.0,
    )
    assert strength == 0.8


def test_signed_evidence_contribution_positive_direction():
    strength = ea.weighted_evidence_strength(1.0, 1.0, 1.0)
    contribution = ea.signed_evidence_contribution(strength, ea.DIRECTION_POSITIVE)
    assert contribution == 1.0


def test_signed_evidence_contribution_negative_direction_is_negative_not_positive():
    """The brief's core rule: a negative RCT must be a strong NEGATIVE
    contribution, never a positive one, regardless of how high its
    authority/quality factors are."""
    strength = ea.weighted_evidence_strength(
        quality_factor=1.0, authority_factor=1.0, applicability_factor_value=1.0,
    )
    contribution = ea.signed_evidence_contribution(strength, ea.DIRECTION_NEGATIVE)
    assert contribution < 0
    assert contribution == -1.0


def test_authority_never_changes_direction_sign_by_itself():
    """Varying authority_factor alone must never flip the sign of the
    final signed contribution for a fixed direction."""
    for authority in (ea.AUTHORITY_FACTORS[label] for label in ea.AUTHORITY_LABELS):
        strength = ea.weighted_evidence_strength(1.0, authority, 1.0)
        contribution = ea.signed_evidence_contribution(strength, ea.DIRECTION_NEGATIVE)
        assert contribution <= 0
        contribution_pos = ea.signed_evidence_contribution(strength, ea.DIRECTION_POSITIVE)
        assert contribution_pos >= 0


def test_null_direction_yields_zero_contribution_regardless_of_authority():
    strength = ea.weighted_evidence_strength(1.0, 1.0, 1.0)
    assert ea.signed_evidence_contribution(strength, ea.DIRECTION_NULL) == 0.0


def test_applicability_factor_zero_forces_zero_strength():
    strength = ea.weighted_evidence_strength(
        quality_factor=1.0, authority_factor=1.0, applicability_factor_value=0.0,
    )
    assert strength == 0.0


def test_study_quality_factor_reuses_evidence_interpretation_table_not_redefined():
    """Phase 3 brief: 'دو classifier مستقل نساز' — this module must not
    invent its own quality-factor table."""
    from evidence_interpretation import QUALITY_FACTOR
    assert ea.study_quality_factor(ea.QUALITY_LOW) == QUALITY_FACTOR[ea.QUALITY_LOW]
    assert ea.study_quality_factor(ea.QUALITY_HIGH) == QUALITY_FACTOR[ea.QUALITY_HIGH]


def test_summarize_authority_distribution():
    labels = [ea.AUTHORITY_RCT, ea.AUTHORITY_RCT, None, ea.AUTHORITY_BLOG]
    dist = ea.summarize_authority_distribution(labels)
    assert dist[ea.AUTHORITY_RCT] == 2
    assert dist[ea.AUTHORITY_UNKNOWN] == 1
    assert dist[ea.AUTHORITY_BLOG] == 1


def test_authority_factors_mapping_is_immutable():
    import types
    assert isinstance(ea.AUTHORITY_FACTORS, types.MappingProxyType)
