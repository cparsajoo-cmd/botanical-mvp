"""Stage 2 — dependency-aware study linkage regression tests.

These tests deliberately keep article identity, evidence-object identity and
underlying-study identity separate.  They protect against duplicate certainty
inflation without aggressively deleting legitimate evidence objects.
"""
from deduplication_engine import compute_article_identity, compute_study_identity
from evidence_body_assessment import assess_evidence_body, BodyCertainty


def _dir(_):
    return "positive"


def _lim(_):
    return "none"


def _trial_record(**extra):
    rec = {
        "source_type": "CLINICAL_TRIAL",
        "study_design": "Randomized Controlled Trial",
        "assertion_text": "The trial reported a clinically meaningful benefit.",
        "outcome": "symptom score",
        "comparator": "placebo",
        "risk_of_bias": "low",
        "applicability_classification": "directly applicable",
    }
    rec.update(extra)
    return rec


def test_registry_and_primary_publication_are_distinct_articles_but_same_study():
    registry = _trial_record(evidence_record_id="registry", nct_id="NCT01234567")
    publication = _trial_record(evidence_record_id="pub", pmid="12345678", nct_id="NCT01234567")

    assert compute_article_identity(registry) != compute_article_identity(publication)
    assert compute_study_identity(registry) == compute_study_identity(publication)


def test_primary_and_secondary_publications_can_share_underlying_trial_dependency():
    primary = _trial_record(pmid="11111111", nct_id="NCT01234567", outcome="primary endpoint")
    secondary = _trial_record(pmid="22222222", nct_id="NCT01234567", outcome="secondary endpoint")

    assert compute_article_identity(primary) != compute_article_identity(secondary)
    assert compute_study_identity(primary) == compute_study_identity(secondary)


def test_two_unrelated_rcts_are_separate_studies():
    a = _trial_record(pmid="11111111", nct_id="NCT00000001")
    b = _trial_record(pmid="22222222", nct_id="NCT00000002")
    assert compute_study_identity(a) != compute_study_identity(b)


def test_systematic_review_remains_distinct_even_if_trial_id_is_present():
    trial = _trial_record(pmid="11111111", nct_id="NCT01234567")
    review = {
        "source_type": "SYSTEMATIC_REVIEW",
        "study_design": "Systematic Review",
        "pmid": "99999999",
        # Deliberately present to prove a synthesis is not collapsed onto a
        # single included trial merely because a structured id is carried.
        "nct_id": "NCT01234567",
        "assertion_text": "Systematic review reported benefit.",
    }
    assert compute_study_identity(review) != compute_study_identity(trial)
    assert compute_study_identity(review)[0] == "synthesis"


def test_duplicate_trial_representation_does_not_increase_body_certainty():
    registry = _trial_record(evidence_record_id="registry", nct_id="NCT01234567")
    publication = _trial_record(evidence_record_id="publication", pmid="12345678", nct_id="NCT01234567")

    one = assess_evidence_body([registry], direction_fn=_dir, limitation_fn=_lim)
    duplicated = assess_evidence_body([registry, publication], direction_fn=_dir, limitation_fn=_lim)

    assert one.certainty == BodyCertainty.LOW
    assert duplicated.certainty == one.certainty
    assert duplicated.governing_source_count == 2  # both evidence objects remain visible
    assert duplicated.governing_study_count == 1   # but only one dependency unit
    assert duplicated.total_source_count == 2


def test_two_independent_trials_can_still_raise_rct_body_certainty():
    a = _trial_record(evidence_record_id="a", nct_id="NCT00000001")
    b = _trial_record(evidence_record_id="b", nct_id="NCT00000002")
    body = assess_evidence_body([a, b], direction_fn=_dir, limitation_fn=_lim)
    assert body.governing_source_count == 2
    assert body.governing_study_count == 2
    assert body.certainty == BodyCertainty.MODERATE
