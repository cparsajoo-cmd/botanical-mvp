"""Regression tests for expert_sign_off.py (Task 8 — Structured Expert
Sign-Off). See that module's docstring for the full documented method
and its declared limitations.
"""

from datetime import datetime, timedelta

from expert_sign_off import (
    ExpertSignOff, SignOffDisposition, MINIMUM_MEANINGFUL_REVIEW_SECONDS,
    is_meaningful_sign_off, require_meaningful_sign_off,
    IncompleteSignOffError, review_duration_seconds, sign_off_summary,
    sign_off_to_dict,
)


def _base_kwargs():
    return dict(analysis_id="a1", reference_plant="RefPlant", alternative_plant="AltPlant")


def _meaningful_sign_off(**overrides):
    start = datetime(2026, 1, 1, 10, 0, 0)
    defaults = dict(
        reviewer_role="Pharmacognosist",
        reviewer_credentials="PhD, 15y botanical R&D",
        evidence_access_confirmed=True,
        review_started_at=start,
        review_completed_at=start + timedelta(minutes=10),
        disposition=SignOffDisposition.APPROVED,
        disposition_notes="Evidence base is solid and directly applicable.",
    )
    defaults.update(overrides)
    return ExpertSignOff(**_base_kwargs(), **defaults)


# ---------------------------------------------------------------------
# review_duration_seconds
# ---------------------------------------------------------------------

def test_review_duration_none_when_timestamps_missing():
    s = ExpertSignOff(**_base_kwargs())
    assert review_duration_seconds(s) is None


def test_review_duration_none_when_completed_before_started():
    start = datetime(2026, 1, 1, 10, 0, 0)
    s = ExpertSignOff(
        **_base_kwargs(),
        review_started_at=start, review_completed_at=start - timedelta(seconds=5),
    )
    assert review_duration_seconds(s) is None


def test_review_duration_none_when_zero():
    start = datetime(2026, 1, 1, 10, 0, 0)
    s = ExpertSignOff(**_base_kwargs(), review_started_at=start, review_completed_at=start)
    assert review_duration_seconds(s) is None


def test_review_duration_positive_case():
    start = datetime(2026, 1, 1, 10, 0, 0)
    s = ExpertSignOff(
        **_base_kwargs(),
        review_started_at=start, review_completed_at=start + timedelta(minutes=5),
    )
    assert review_duration_seconds(s) == 300.0


# ---------------------------------------------------------------------
# is_meaningful_sign_off — each of the four Chapter-11 elements
# ---------------------------------------------------------------------

def test_completely_empty_sign_off_fails_all_checks():
    s = ExpertSignOff(**_base_kwargs())
    ok, reasons = is_meaningful_sign_off(s)
    assert ok is False
    assert len(reasons) >= 4


def test_missing_reviewer_role_fails():
    s = _meaningful_sign_off(reviewer_role=None)
    ok, reasons = is_meaningful_sign_off(s)
    assert ok is False
    assert any("reviewer_role" in r for r in reasons)


def test_whitespace_only_reviewer_role_fails():
    s = _meaningful_sign_off(reviewer_role="   ")
    ok, _ = is_meaningful_sign_off(s)
    assert ok is False


def test_evidence_access_not_confirmed_fails():
    s = _meaningful_sign_off(evidence_access_confirmed=False)
    ok, reasons = is_meaningful_sign_off(s)
    assert ok is False
    assert any("evidence_access_confirmed" in r for r in reasons)


def test_review_too_fast_fails():
    start = datetime(2026, 1, 1, 10, 0, 0)
    s = _meaningful_sign_off(
        review_started_at=start,
        review_completed_at=start + timedelta(seconds=MINIMUM_MEANINGFUL_REVIEW_SECONDS - 1),
    )
    ok, reasons = is_meaningful_sign_off(s)
    assert ok is False
    assert any("below the" in r for r in reasons)


def test_review_exactly_at_floor_passes_duration_check():
    start = datetime(2026, 1, 1, 10, 0, 0)
    s = _meaningful_sign_off(
        review_started_at=start,
        review_completed_at=start + timedelta(seconds=MINIMUM_MEANINGFUL_REVIEW_SECONDS),
    )
    ok, reasons = is_meaningful_sign_off(s)
    assert not any("below the" in r for r in reasons)


def test_missing_disposition_fails():
    s = _meaningful_sign_off(disposition=None)
    ok, reasons = is_meaningful_sign_off(s)
    assert ok is False
    assert any("disposition is not set" in r for r in reasons)


def test_empty_disposition_notes_fails():
    s = _meaningful_sign_off(disposition_notes="")
    ok, reasons = is_meaningful_sign_off(s)
    assert ok is False
    assert any("disposition_notes" in r for r in reasons)


def test_whitespace_only_disposition_notes_fails():
    s = _meaningful_sign_off(disposition_notes="   ")
    ok, _ = is_meaningful_sign_off(s)
    assert ok is False


def test_approved_with_modifications_requires_modifications_made():
    s = _meaningful_sign_off(
        disposition=SignOffDisposition.APPROVED_WITH_MODIFICATIONS,
        modifications_made=None,
    )
    ok, reasons = is_meaningful_sign_off(s)
    assert ok is False
    assert any("modifications_made" in r for r in reasons)


def test_approved_with_modifications_and_modifications_stated_passes():
    s = _meaningful_sign_off(
        disposition=SignOffDisposition.APPROVED_WITH_MODIFICATIONS,
        modifications_made="Downgraded tier pending standardization check.",
    )
    ok, reasons = is_meaningful_sign_off(s)
    assert ok is True
    assert reasons == []


def test_rejected_disposition_does_not_require_modifications_made():
    s = _meaningful_sign_off(disposition=SignOffDisposition.REJECTED)
    ok, _ = is_meaningful_sign_off(s)
    assert ok is True


def test_fully_meaningful_sign_off_passes():
    s = _meaningful_sign_off()
    ok, reasons = is_meaningful_sign_off(s)
    assert ok is True
    assert reasons == []


# ---------------------------------------------------------------------
# require_meaningful_sign_off — the hard-refusal gate
# ---------------------------------------------------------------------

def test_require_meaningful_raises_on_incomplete():
    s = ExpertSignOff(**_base_kwargs())
    try:
        require_meaningful_sign_off(s)
        assert False, "should have raised"
    except IncompleteSignOffError as e:
        assert len(e.reasons) > 0


def test_require_meaningful_returns_same_object_when_meaningful():
    s = _meaningful_sign_off()
    result = require_meaningful_sign_off(s)
    assert result is s


# ---------------------------------------------------------------------
# sign_off_summary
# ---------------------------------------------------------------------

def test_sign_off_summary_shape():
    s = _meaningful_sign_off(platform_recommendation="Go")
    summary = sign_off_summary(s)
    assert summary["is_meaningful"] is True
    assert summary["disposition"] == "Approved"
    assert summary["review_duration_seconds"] == 600.0
    assert summary["agrees_with_platform"] is True


def test_sign_off_summary_never_raises_on_incomplete():
    s = ExpertSignOff(**_base_kwargs())
    summary = sign_off_summary(s)
    assert summary["is_meaningful"] is False
    assert len(summary["incomplete_reasons"]) > 0


def test_agreement_none_when_no_platform_recommendation():
    s = _meaningful_sign_off(platform_recommendation=None)
    summary = sign_off_summary(s)
    assert summary["agrees_with_platform"] is None


def test_agreement_true_when_both_negative():
    s = _meaningful_sign_off(
        disposition=SignOffDisposition.REJECTED,
        platform_recommendation="Hold",
    )
    summary = sign_off_summary(s)
    assert summary["agrees_with_platform"] is True


def test_agreement_false_when_platform_go_but_reviewer_rejects():
    s = _meaningful_sign_off(
        disposition=SignOffDisposition.REJECTED,
        platform_recommendation="Go",
    )
    summary = sign_off_summary(s)
    assert summary["agrees_with_platform"] is False


def test_agreement_false_when_platform_hold_but_reviewer_approves():
    s = _meaningful_sign_off(
        disposition=SignOffDisposition.APPROVED,
        platform_recommendation="Hold",
    )
    summary = sign_off_summary(s)
    assert summary["agrees_with_platform"] is False


# ---------------------------------------------------------------------
# sign_off_to_dict — serialization
# ---------------------------------------------------------------------

def test_sign_off_to_dict_normalizes_enum_and_datetimes():
    s = _meaningful_sign_off()
    as_dict = sign_off_to_dict(s)
    assert as_dict["disposition"] == "Approved"
    assert isinstance(as_dict["review_started_at"], str)
    assert isinstance(as_dict["review_completed_at"], str)


def test_sign_off_to_dict_handles_none_disposition_and_timestamps():
    s = ExpertSignOff(**_base_kwargs())
    as_dict = sign_off_to_dict(s)
    assert as_dict["disposition"] is None
    assert as_dict["review_started_at"] is None
    assert as_dict["review_completed_at"] is None


def test_sign_off_to_dict_includes_identification_fields():
    s = _meaningful_sign_off()
    as_dict = sign_off_to_dict(s)
    assert as_dict["analysis_id"] == "a1"
    assert as_dict["reference_plant"] == "RefPlant"
    assert as_dict["alternative_plant"] == "AltPlant"


# ---------------------------------------------------------------------
# Task 9 — role-authorization additions (is_meaningful_and_authorized,
# require_authorized_sign_off, UnauthorizedReviewerError). These are
# purely additive to the module — none of the tests above should be
# affected by anything in this section.
# ---------------------------------------------------------------------

from user_roles import ReviewDomain
from expert_sign_off import (
    is_meaningful_and_authorized, require_authorized_sign_off,
    UnauthorizedReviewerError,
)


def test_unauthorized_reviewer_error_is_a_subclass_of_incomplete_sign_off_error():
    assert issubclass(UnauthorizedReviewerError, IncompleteSignOffError)


def test_meaningful_and_authorized_true_for_valid_matching_sign_off():
    s = _meaningful_sign_off(reviewer_role="Pharmacognosist")
    ok, reasons = is_meaningful_and_authorized(s, {ReviewDomain.SCIENTIFIC_EVIDENCE})
    assert ok is True
    assert reasons == []


def test_meaningful_and_authorized_false_when_role_wrong_for_domain():
    s = _meaningful_sign_off(reviewer_role="Market / investment analyst")
    ok, reasons = is_meaningful_and_authorized(
        s, {ReviewDomain.SCIENTIFIC_EVIDENCE, ReviewDomain.SAFETY},
    )
    assert ok is False
    assert any("Market / investment analyst" in r for r in reasons)


def test_meaningful_and_authorized_false_when_sign_off_incomplete_even_if_role_would_be_ok():
    s = ExpertSignOff(**_base_kwargs(), reviewer_role="Pharmacognosist")
    ok, reasons = is_meaningful_and_authorized(s, {ReviewDomain.SCIENTIFIC_EVIDENCE})
    assert ok is False
    # Both an incompleteness reason and no false-positive authorization.
    assert any("disposition" in r for r in reasons)


def test_meaningful_and_authorized_combines_both_failure_reasons():
    s = ExpertSignOff(**_base_kwargs(), reviewer_role="Market / investment analyst")
    ok, reasons = is_meaningful_and_authorized(s, {ReviewDomain.SAFETY})
    assert ok is False
    assert any("disposition" in r for r in reasons)
    assert any("Market / investment analyst" in r for r in reasons)


def test_require_authorized_raises_unauthorized_when_only_role_is_wrong():
    s = _meaningful_sign_off(reviewer_role="Market / investment analyst")
    try:
        require_authorized_sign_off(s, {ReviewDomain.SAFETY})
        assert False, "should have raised"
    except UnauthorizedReviewerError as e:
        assert len(e.reasons) >= 1


def test_require_authorized_raises_base_incomplete_error_when_role_would_be_fine():
    # Sign-off itself is incomplete (no disposition), but the asserted
    # role WOULD have been authorized — should raise the base
    # IncompleteSignOffError, not UnauthorizedReviewerError, since role
    # is not the (or a) failing element here.
    s = ExpertSignOff(
        **_base_kwargs(), reviewer_role="Pharmacognosist",
        evidence_access_confirmed=True,
    )
    try:
        require_authorized_sign_off(s, {ReviewDomain.SCIENTIFIC_EVIDENCE})
        assert False, "should have raised"
    except UnauthorizedReviewerError:
        assert False, "should not be the Unauthorized subclass here"
    except IncompleteSignOffError:
        pass


def test_require_authorized_returns_same_object_when_fully_valid():
    s = _meaningful_sign_off(reviewer_role="Pharmacognosist")
    result = require_authorized_sign_off(s, {ReviewDomain.SCIENTIFIC_EVIDENCE})
    assert result is s


def test_require_authorized_toxicologist_on_safety_flagged_candidate_succeeds():
    s = _meaningful_sign_off(reviewer_role="Pharmacologist / Toxicologist")
    result = require_authorized_sign_off(
        s, {ReviewDomain.SCIENTIFIC_EVIDENCE, ReviewDomain.SAFETY},
    )
    assert result is s
