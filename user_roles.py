"""
Task 9 — Formal User-Role Permissions.

WHAT THIS CLOSES
Chapter 11's explicit requirement: "The platform should never assume
one user is competent to evaluate every evidence domain: a market
analyst should not independently approve a safety conclusion, nor
should an investment professional treat a platform score as a
substitute for scientific due diligence," and the governance chapter's
own gap list: "Formal user-role permissions, structured approval
checkpoints... remain partial or require verification."

WHAT THIS IS NOT — READ BEFORE ASSUMING THIS IS AN AUTH SYSTEM
There is no login, session-identity, or user-account system anywhere
in this repository (confirmed: no auth module, no user table, no
password/token handling of any kind — the deployed app is a
single-session Streamlit workflow). This module does NOT add one, and
does not pretend to. It cannot verify that the person asserting
"I am a Toxicologist" actually is one — that is an identity-
verification problem, entirely outside this module's scope and this
repository's current architecture.

What this module DOES provide is the next honest thing available
without an identity layer: a controlled vocabulary of the competence-
based roles Chapter 11 names, an explicit mapping of which review
DOMAINS each role is authorized for, and a hard check that a sign-off
cannot be completed unless the reviewer's ASSERTED role covers every
domain the specific candidate requires. This is a real, structural
control — it stops a sign-off asserting the "Market / investment
analyst" role from being accepted for a candidate carrying safety
flags, regardless of what that reviewer privately believes their own
competence to be — but it is a control on ASSERTED role, not on
VERIFIED identity. A future identity/authentication layer, if one is
ever added, should plug into is_role_authorized() below rather than
requiring this module's logic to be rewritten.

REVIEW DOMAINS
    Scientific evidence   — always required (every candidate has some
                             evidence claim to check)
    Safety                — required when the candidate carries any
                             safety flag
    Regulatory             — required when the candidate carries any
                             regulatory barrier
    Commercial / market     — required when the candidate carries a
                             genuine commercial signal (not merely
                             "not searched"/"unknown")

ROLE -> AUTHORIZED-DOMAINS MAPPING
This is a documented FIRST DRAFT, matching Chapter 11's own worked
examples exactly (a market analyst is authorized for Commercial only,
never Safety; a toxicologist is authorized for Safety) and otherwise
using ordinary professional-scope judgment for the remaining roles —
not calibrated against any external competence framework. Revisit
freely; the point of naming ROLE_AUTHORIZED_DOMAINS as one place is
that revisiting it is a one-dict change, not a hunt through call sites.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional


class ReviewerRole(str, Enum):
    """Matches Chapter 11's "Intended users" list exactly:
    "pharmacognosists, pharmacologists, toxicologists, clinical-
    evidence specialists, regulatory professionals, and investment
    professionals." Pharmacologist and toxicologist are merged into
    one role here (both concern drug/substance safety and mechanism
    competence) since Chapter 11 lists them together without
    distinguishing their authorized domains from one another."""
    PHARMACOGNOSIST = "Pharmacognosist"
    PHARMACOLOGIST_TOXICOLOGIST = "Pharmacologist / Toxicologist"
    CLINICAL_EVIDENCE_SPECIALIST = "Clinical-evidence specialist"
    REGULATORY_PROFESSIONAL = "Regulatory professional"
    MARKET_INVESTMENT_ANALYST = "Market / investment analyst"
    PLATFORM_ADMINISTRATOR = "Platform administrator"


class ReviewDomain(str, Enum):
    SCIENTIFIC_EVIDENCE = "Scientific evidence"
    SAFETY = "Safety"
    REGULATORY = "Regulatory"
    COMMERCIAL = "Commercial / market"


# See module docstring's "ROLE -> AUTHORIZED-DOMAINS MAPPING" section.
# PLATFORM_ADMINISTRATOR is deliberately given NO domain authority by
# default — an admin role is an operational/infrastructure role, not
# a scientific-competence bypass; an administrator wanting to sign off
# on a candidate must assert one of the actual competence-based roles
# instead, same as anyone else. There is no superuser exemption here.
ROLE_AUTHORIZED_DOMAINS = {
    ReviewerRole.PHARMACOGNOSIST: {ReviewDomain.SCIENTIFIC_EVIDENCE},
    ReviewerRole.PHARMACOLOGIST_TOXICOLOGIST: {
        ReviewDomain.SCIENTIFIC_EVIDENCE, ReviewDomain.SAFETY,
    },
    ReviewerRole.CLINICAL_EVIDENCE_SPECIALIST: {ReviewDomain.SCIENTIFIC_EVIDENCE},
    ReviewerRole.REGULATORY_PROFESSIONAL: {ReviewDomain.REGULATORY},
    ReviewerRole.MARKET_INVESTMENT_ANALYST: {ReviewDomain.COMMERCIAL},
    ReviewerRole.PLATFORM_ADMINISTRATOR: set(),
}

# Market/regulatory/safety "no genuine signal present" values — matches
# data_contracts.MarketVerificationStatus and
# botanical_rd_candidate_engine.py's own placeholder strings exactly,
# so this module never invents a second vocabulary for "nothing to
# review here" alongside the ones those modules already use.
_NO_SAFETY_SIGNAL = {"", "No explicit flag found"}
_NO_REGULATORY_SIGNAL = {"", "None identified"}
_NO_COMMERCIAL_SIGNAL = {
    "", "No verified product found", "Search not performed",
    "Source unavailable", "Unknown",
}


def parse_reviewer_role(text: Optional[str]) -> Optional[ReviewerRole]:
    """Maps a reviewer-asserted role string onto ReviewerRole, exact
    value match only (case/whitespace-insensitive) — deliberately NOT
    a fuzzy or partial match, since silently accepting "Toxicology
    person" as ReviewerRole.PHARMACOLOGIST_TOXICOLOGIST would defeat
    the entire point of a controlled vocabulary. Returns None for
    anything that isn't an exact match to one of the defined roles,
    including empty/missing text — a caller checking is_role_authorized()
    with role=None will correctly find no domain authorized for it."""
    if not text:
        return None
    normalized = text.strip().lower()
    for role in ReviewerRole:
        if role.value.lower() == normalized:
            return role
    return None


def authorized_domains_for_role(role: Optional[ReviewerRole]) -> set:
    """Empty set for role=None or any role with no explicit mapping
    entry (defensive default; every real ReviewerRole value does have
    an entry above) — never a silent "authorized for everything"
    fallback."""
    if role is None:
        return set()
    return ROLE_AUTHORIZED_DOMAINS.get(role, set())


def required_domains_for_candidate(
    safety_flags: str = "",
    regulatory_barriers: str = "",
    market_status: str = "",
) -> set:
    """Which ReviewDomain values a sign-off on ONE candidate row must
    cover, derived from signals the engine already computes per row
    (Safety_Flags, Regulatory_Barriers via Gate_Results["regulatory"]
    ["evidence"], Market_Status) — no new classification, just reading
    already-computed fields against their own existing "nothing found"
    placeholder vocabulary.

    SCIENTIFIC_EVIDENCE is always included — every candidate has some
    evidence claim behind it that a scientifically competent reviewer
    should be able to check, regardless of whether safety/regulatory/
    commercial signals are present.
    """
    domains = {ReviewDomain.SCIENTIFIC_EVIDENCE}

    if (safety_flags or "").strip() not in _NO_SAFETY_SIGNAL:
        domains.add(ReviewDomain.SAFETY)

    if (regulatory_barriers or "").strip() not in _NO_REGULATORY_SIGNAL:
        domains.add(ReviewDomain.REGULATORY)

    if (market_status or "").strip() not in _NO_COMMERCIAL_SIGNAL:
        domains.add(ReviewDomain.COMMERCIAL)

    return domains


def is_role_authorized(role: Optional[ReviewerRole], required_domains: set) -> tuple:
    """Returns (is_authorized, reasons). is_authorized is True only if
    EVERY domain in `required_domains` is covered by `role`'s
    authorized domains — a role authorized for 3 of 4 required domains
    is still not authorized; partial coverage is not treated as
    sufficient, matching the non-compensatory-gate design already
    established elsewhere in this pipeline (a candidate cannot pass
    the safety gate by having a strong score, and a reviewer cannot
    sign off on a safety-flagged candidate by being competent in three
    other domains).
    """
    if role is None:
        return False, [
            "Reviewer role is missing or is not one of the platform's "
            "defined roles (see user_roles.ReviewerRole)."
        ]

    authorized = authorized_domains_for_role(role)
    missing = required_domains - authorized
    if missing:
        missing_labels = ", ".join(sorted(d.value for d in missing))
        return False, [
            f"Role '{role.value}' is not authorized for required "
            f"domain(s): {missing_labels}."
        ]
    return True, []
