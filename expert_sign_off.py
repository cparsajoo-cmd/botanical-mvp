"""
Task 8 — Structured Expert Sign-Off.

WHAT THIS CLOSES
Risk register item R18 ("Expert review becomes nominal rather than
meaningful — Human review is a platform principle; structured
sign-off requires further implementation") and Chapter 11's explicit
requirement: "the platform operationalizes meaningful review by
requiring a competent reviewer with evidence access, authority to
modify or reject outputs, sufficient review time and responsibility
for documenting the final disposition." Nothing in the repository
previously gave a reviewer a structured way to record any of this —
"human review" existed only as a stated principle, never as a
recordable, checkable act.

WHAT A "MEANINGFUL" SIGN-OFF REQUIRES (see is_meaningful_sign_off())
Every one of Chapter 11's four elements is checked explicitly:
  1. "a competent reviewer"       -> reviewer_role must be stated
  2. "evidence access"            -> evidence_access_confirmed must be True
  3. "sufficient review time"     -> review_started_at/review_completed_at
                                      must both be set, completed after
                                      started, and the elapsed time must
                                      clear a named, disclosed floor
                                      (MINIMUM_MEANINGFUL_REVIEW_SECONDS)
  4. "documenting the final       -> disposition must be set AND
      disposition"                   disposition_notes must be non-empty

reviewer_role/credentials are stored by ROLE, not personal name — same
reasoning as validation_case_protocol.py's ExpertPanelMember.

WHAT THE TIME FLOOR IS AND IS NOT
MINIMUM_MEANINGFUL_REVIEW_SECONDS is a DISCLOSED, NAMED heuristic — it
can only ever catch the most obvious nominal-review failure mode (a
reviewer approving in near-zero elapsed time). Clearing it is NECESSARY
for a sign-off to count as meaningful by this module's own criteria,
but it is NOT SUFFICIENT evidence that the review itself was
scientifically rigorous — a reviewer could still spend the minimum
time without engaging seriously with the evidence. This module can only
check for the presence of the four required elements and a floor on
elapsed time; it cannot verify review QUALITY, exactly like
evidence_confidence.py's own methodological-quality modifiers can only
detect textual markers, not verify a study was actually well-conducted.

WHY THIS NEVER FORCES A DISPOSITION OR REJECTS A CANDIDATE ITSELF
This module has no opinion on what disposition is correct — it only
enforces that SOME disposition, with SOME documented reasoning, was
recorded by SOMEONE with SOME stated role and SOME confirmed evidence
access, over SOME non-trivial span of time. The actual scientific
judgment remains entirely the reviewer's; see Chapter 11: "the final
decision belongs to the accountable human."

PERSISTENCE IS A SEPARATE MODULE
See sign_off_persistence.py for the append-only, best-effort Supabase
write path — same architectural separation
decision_record_persistence.py already keeps from
botanical_rd_candidate_engine.py (data contract and validation logic
here; I/O there).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class SignOffDisposition(str, Enum):
    """The reviewer's authority to modify or reject outputs (Chapter
    11) is represented as a controlled vocabulary, not free text —
    exactly like DecisionClass/GateStatus elsewhere in this pipeline,
    so downstream code can reason about dispositions without string-
    matching free text."""
    APPROVED = "Approved"
    APPROVED_WITH_MODIFICATIONS = "Approved with modifications"
    REJECTED = "Rejected"
    RETURNED_FOR_MORE_EVIDENCE = "Returned for more evidence"
    ESCALATED = "Escalated to specialist review"


# Named, disclosed floor — see module docstring's "WHAT THE TIME FLOOR
# IS AND IS NOT". 30 seconds is a deliberately low bar (enough to rule
# out an instant, reflexive approval; nowhere near a claim that 30
# seconds constitutes a rigorous review) — same "first, documented,
# reversible starting point, not a validated model" status as every
# other heuristic constant in this pipeline (evidence_confidence.py's
# own docstring uses this exact phrase for its modifiers).
MINIMUM_MEANINGFUL_REVIEW_SECONDS = 30


@dataclass
class ExpertSignOff:
    """One reviewer's structured sign-off on one candidate assessment.

    analysis_id/reference_plant/alternative_plant identify WHICH
    candidate row this sign-off applies to — the same identification
    triple decision_record_persistence.py's persisted records already
    use (analysis_id groups a completed run; reference_plant +
    alternative_plant identify one candidate row within it).

    platform_recommendation/platform_decision_class are OPTIONAL
    snapshots of what the platform itself said about this candidate at
    the time of review — filled by the caller from the candidate row
    being reviewed, never recomputed here. Recording them lets a later
    reader see whether the reviewer agreed or disagreed with the
    platform, which is itself a meaningful signal (see
    sign_off_persistence.py's load functions for how this is read
    back) — but their absence never invalidates a sign-off; only the
    four Chapter-11 elements listed in the module docstring do.
    """
    analysis_id: str
    reference_plant: str
    alternative_plant: str

    reviewer_role: Optional[str] = None
    reviewer_credentials: Optional[str] = None
    evidence_access_confirmed: bool = False

    review_started_at: Optional[datetime] = None
    review_completed_at: Optional[datetime] = None

    disposition: Optional[SignOffDisposition] = None
    disposition_notes: Optional[str] = None
    modifications_made: Optional[str] = None

    platform_recommendation: Optional[str] = None
    platform_decision_class: Optional[str] = None


def _non_empty(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and value.strip() == "":
        return False
    return True


def review_duration_seconds(sign_off: ExpertSignOff) -> Optional[float]:
    """Elapsed review time, or None if either timestamp is missing or
    completed is not after started (a negative/zero duration is
    treated as missing, not as a valid near-zero review — the same
    "an implausible value is a data gap, not a real data point"
    principle applied elsewhere in this pipeline, e.g.
    evidence_hierarchy_classifier.py's negation handling)."""
    if sign_off.review_started_at is None or sign_off.review_completed_at is None:
        return None
    delta = (sign_off.review_completed_at - sign_off.review_started_at).total_seconds()
    if delta <= 0:
        return None
    return delta


def is_meaningful_sign_off(sign_off: ExpertSignOff) -> tuple:
    """Checks all four Chapter-11 elements. Returns (is_meaningful,
    reasons) where reasons is a list of human-readable strings
    naming every failed check — empty only when is_meaningful is True.
    Never raises; a malformed/incomplete sign_off simply fails checks
    rather than crashing, matching this pipeline's "degrade to an
    explicit, disclosed state" convention.
    """
    reasons = []

    if not _non_empty(sign_off.reviewer_role):
        reasons.append("reviewer_role is not stated")

    if sign_off.evidence_access_confirmed is not True:
        reasons.append("evidence_access_confirmed is not True")

    duration = review_duration_seconds(sign_off)
    if duration is None:
        reasons.append(
            "review_started_at/review_completed_at are missing or "
            "completed is not after started"
        )
    elif duration < MINIMUM_MEANINGFUL_REVIEW_SECONDS:
        reasons.append(
            f"review duration ({duration:.0f}s) is below the "
            f"{MINIMUM_MEANINGFUL_REVIEW_SECONDS}s meaningful-review floor"
        )

    if sign_off.disposition is None:
        reasons.append("disposition is not set")

    if not _non_empty(sign_off.disposition_notes):
        reasons.append("disposition_notes is empty — the final disposition must be documented")

    if (
        sign_off.disposition == SignOffDisposition.APPROVED_WITH_MODIFICATIONS
        and not _non_empty(sign_off.modifications_made)
    ):
        reasons.append(
            "disposition is 'Approved with modifications' but modifications_made is empty"
        )

    return (len(reasons) == 0, reasons)


class IncompleteSignOffError(Exception):
    """Raised when code attempts to treat an incomplete sign-off as
    final — e.g. sign_off_persistence.persist_sign_off() refuses to
    write one. Carries the same (is_meaningful, reasons) detail
    is_meaningful_sign_off() produced, attached as .reasons, so a
    caller can show exactly what is still missing rather than a bare
    failure."""


class UnauthorizedReviewerError(IncompleteSignOffError):
    """Task 9 — raised when a reviewer's asserted role does not cover
    every domain a candidate's sign-off requires (see user_roles.py)
    — e.g. a market/investment analyst attempting to sign off on a
    candidate with safety flags present, which Chapter 11 explicitly
    names as prohibited: "a market analyst should not independently
    approve a safety conclusion." Subclasses IncompleteSignOffError so
    existing code that catches IncompleteSignOffError still catches
    this too, while callers that specifically need to distinguish
    "incomplete" from "wrong reviewer for this candidate" can catch
    this subclass instead."""


def is_meaningful_and_authorized(sign_off: ExpertSignOff, required_domains: set) -> tuple:
    """Task 9 — combines is_meaningful_sign_off() with a role-
    authorization check against `required_domains` (a set of
    user_roles.ReviewDomain values — see
    user_roles.required_domains_for_candidate()). Returns
    (is_valid, reasons).

    Deliberately takes required_domains as an explicit argument rather
    than deriving it internally: this function has no opinion on WHICH
    domains a given candidate requires — that judgment stays entirely
    in user_roles.py, independently callable and independently
    testable, exactly like is_meaningful_sign_off() above has no
    opinion on what a correct disposition would be, only on whether
    one was documented.
    """
    from user_roles import parse_reviewer_role, is_role_authorized

    is_meaningful, reasons = is_meaningful_sign_off(sign_off)
    role = parse_reviewer_role(sign_off.reviewer_role)
    is_authorized, auth_reasons = is_role_authorized(role, required_domains)
    return (is_meaningful and is_authorized, reasons + auth_reasons)


def require_authorized_sign_off(sign_off: ExpertSignOff, required_domains: set) -> ExpertSignOff:
    """Task 9 — hard-refusal gate combining require_meaningful_sign_off()'s
    check with role-authorization. Raises UnauthorizedReviewerError
    when the reviewer's role is the (or a) failing element, and the
    base IncompleteSignOffError when the sign-off is simply incomplete
    with no role-authorization problem — letting a caller react
    differently to the two cases (e.g. "please finish documenting
    your review" versus "please route this candidate to a reviewer
    with regulatory competence") without string-matching the error
    message.
    """
    from user_roles import parse_reviewer_role, is_role_authorized

    is_meaningful, reasons = is_meaningful_sign_off(sign_off)
    role = parse_reviewer_role(sign_off.reviewer_role)
    is_authorized, auth_reasons = is_role_authorized(role, required_domains)

    if not is_meaningful or not is_authorized:
        all_reasons = reasons + auth_reasons
        error_cls = UnauthorizedReviewerError if auth_reasons else IncompleteSignOffError
        error = error_cls(
            f"Sign-off for {sign_off.reference_plant} vs "
            f"{sign_off.alternative_plant} is not valid: {'; '.join(all_reasons)}"
        )
        error.reasons = all_reasons
        raise error
    return sign_off


def require_meaningful_sign_off(sign_off: ExpertSignOff) -> ExpertSignOff:
    """Returns `sign_off` unchanged if it is meaningful; raises
    IncompleteSignOffError otherwise. This is the hard-refusal gate —
    mirrors validation_case_protocol.lock_protocol()'s "never silently
    accept a partial record as final" guarantee, applied here to a
    single reviewer's sign-off instead of a whole validation case
    protocol."""
    is_meaningful, reasons = is_meaningful_sign_off(sign_off)
    if not is_meaningful:
        error = IncompleteSignOffError(
            f"Sign-off for {sign_off.reference_plant} vs "
            f"{sign_off.alternative_plant} is not meaningful: {'; '.join(reasons)}"
        )
        error.reasons = reasons
        raise error
    return sign_off


def sign_off_summary(sign_off: ExpertSignOff) -> dict:
    """A compact, display-ready summary — e.g. for a Streamlit page or
    report section showing a candidate's sign-off status. Never raises
    on an incomplete sign-off (unlike require_meaningful_sign_off()) —
    this is a read-only reporting view, not a gate."""
    is_meaningful, reasons = is_meaningful_sign_off(sign_off)
    duration = review_duration_seconds(sign_off)
    return {
        "reference_plant": sign_off.reference_plant,
        "alternative_plant": sign_off.alternative_plant,
        "reviewer_role": sign_off.reviewer_role,
        "disposition": sign_off.disposition.value if sign_off.disposition else None,
        "review_duration_seconds": duration,
        "is_meaningful": is_meaningful,
        "incomplete_reasons": reasons,
        "platform_recommendation": sign_off.platform_recommendation,
        "agrees_with_platform": (
            _agreement(sign_off) if sign_off.disposition is not None else None
        ),
    }


def _agreement(sign_off: ExpertSignOff) -> Optional[bool]:
    """Whether the reviewer's disposition points the same direction as
    the platform's own recommendation, where both are known. This is
    informational only — a disagreement is not an error, it is
    exactly the kind of signal a human-in-the-loop review process
    exists to surface (Chapter 11: "the final decision belongs to the
    accountable human")."""
    if not sign_off.platform_recommendation or sign_off.disposition is None:
        return None
    platform_positive = sign_off.platform_recommendation in {"Go", "Investigate"}
    reviewer_positive = sign_off.disposition in {
        SignOffDisposition.APPROVED, SignOffDisposition.APPROVED_WITH_MODIFICATIONS,
    }
    return platform_positive == reviewer_positive


def sign_off_to_dict(sign_off: ExpertSignOff) -> dict:
    """asdict() with Enum/datetime fields normalized to persistence-
    and JSON-friendly values — used by sign_off_persistence.py, kept
    here (not duplicated there) so both the dataclass and its
    serialization stay in one file."""
    as_dict = asdict(sign_off)
    if sign_off.disposition is not None:
        as_dict["disposition"] = sign_off.disposition.value
    if sign_off.review_started_at is not None:
        as_dict["review_started_at"] = sign_off.review_started_at.isoformat()
    if sign_off.review_completed_at is not None:
        as_dict["review_completed_at"] = sign_off.review_completed_at.isoformat()
    return as_dict
