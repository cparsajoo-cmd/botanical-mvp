"""Regression tests for user_roles.py (Task 9 — Formal User-Role
Permissions). See that module's docstring for the full documented
method and its declared limitations.
"""

from user_roles import (
    ReviewerRole, ReviewDomain, ROLE_AUTHORIZED_DOMAINS,
    parse_reviewer_role, authorized_domains_for_role,
    required_domains_for_candidate, is_role_authorized,
)


# ---------------------------------------------------------------------
# parse_reviewer_role
# ---------------------------------------------------------------------

def test_parse_exact_match():
    assert parse_reviewer_role("Pharmacognosist") == ReviewerRole.PHARMACOGNOSIST
    assert parse_reviewer_role("Market / investment analyst") == ReviewerRole.MARKET_INVESTMENT_ANALYST


def test_parse_case_and_whitespace_insensitive():
    assert parse_reviewer_role("  pharmacognosist  ") == ReviewerRole.PHARMACOGNOSIST
    assert parse_reviewer_role("REGULATORY PROFESSIONAL") == ReviewerRole.REGULATORY_PROFESSIONAL


def test_parse_does_not_fuzzy_match():
    assert parse_reviewer_role("Toxicology person") is None
    assert parse_reviewer_role("Pharmacognosis") is None


def test_parse_none_or_empty_returns_none():
    assert parse_reviewer_role(None) is None
    assert parse_reviewer_role("") is None
    assert parse_reviewer_role("   ") is None


# ---------------------------------------------------------------------
# authorized_domains_for_role
# ---------------------------------------------------------------------

def test_every_role_has_an_explicit_mapping_entry():
    for role in ReviewerRole:
        assert role in ROLE_AUTHORIZED_DOMAINS


def test_authorized_domains_for_none_role_is_empty():
    assert authorized_domains_for_role(None) == set()


def test_market_analyst_never_authorized_for_safety():
    domains = authorized_domains_for_role(ReviewerRole.MARKET_INVESTMENT_ANALYST)
    assert ReviewDomain.SAFETY not in domains


def test_market_analyst_never_authorized_for_scientific_evidence():
    # Chapter 11: "an investment professional [should not] treat a
    # platform score as a substitute for scientific due diligence."
    domains = authorized_domains_for_role(ReviewerRole.MARKET_INVESTMENT_ANALYST)
    assert ReviewDomain.SCIENTIFIC_EVIDENCE not in domains


def test_toxicologist_authorized_for_safety_and_scientific_evidence():
    domains = authorized_domains_for_role(ReviewerRole.PHARMACOLOGIST_TOXICOLOGIST)
    assert ReviewDomain.SAFETY in domains
    assert ReviewDomain.SCIENTIFIC_EVIDENCE in domains


def test_regulatory_professional_authorized_only_for_regulatory():
    domains = authorized_domains_for_role(ReviewerRole.REGULATORY_PROFESSIONAL)
    assert domains == {ReviewDomain.REGULATORY}


def test_platform_administrator_has_no_domain_authority():
    # No superuser bypass — an admin must assert an actual
    # competence-based role to sign off on anything.
    domains = authorized_domains_for_role(ReviewerRole.PLATFORM_ADMINISTRATOR)
    assert domains == set()


# ---------------------------------------------------------------------
# required_domains_for_candidate
# ---------------------------------------------------------------------

def test_scientific_evidence_always_required():
    domains = required_domains_for_candidate()
    assert ReviewDomain.SCIENTIFIC_EVIDENCE in domains


def test_no_safety_flag_placeholder_does_not_require_safety_domain():
    domains = required_domains_for_candidate(safety_flags="No explicit flag found")
    assert ReviewDomain.SAFETY not in domains


def test_real_safety_flag_requires_safety_domain():
    domains = required_domains_for_candidate(safety_flags="Lithogenic")
    assert ReviewDomain.SAFETY in domains


def test_no_regulatory_barrier_placeholder_does_not_require_regulatory_domain():
    domains = required_domains_for_candidate(regulatory_barriers="None identified")
    assert ReviewDomain.REGULATORY not in domains


def test_real_regulatory_barrier_requires_regulatory_domain():
    domains = required_domains_for_candidate(regulatory_barriers="Prohibited / banned")
    assert ReviewDomain.REGULATORY in domains


def test_no_commercial_signal_placeholders_do_not_require_commercial_domain():
    for placeholder in (
        "No verified product found", "Search not performed",
        "Source unavailable", "Unknown", "",
    ):
        domains = required_domains_for_candidate(market_status=placeholder)
        assert ReviewDomain.COMMERCIAL not in domains, placeholder


def test_real_commercial_signal_requires_commercial_domain():
    for real_signal in (
        "Verified marketed product",
        "Commercial evidence reported, not independently verified",
        "Regulatory monograph exists",
    ):
        domains = required_domains_for_candidate(market_status=real_signal)
        assert ReviewDomain.COMMERCIAL in domains, real_signal


def test_all_four_domains_required_when_all_signals_present():
    domains = required_domains_for_candidate(
        safety_flags="Lithogenic",
        regulatory_barriers="Prohibited / banned",
        market_status="Verified marketed product",
    )
    assert domains == {
        ReviewDomain.SCIENTIFIC_EVIDENCE, ReviewDomain.SAFETY,
        ReviewDomain.REGULATORY, ReviewDomain.COMMERCIAL,
    }


def test_only_scientific_evidence_required_when_no_other_signals():
    domains = required_domains_for_candidate(
        safety_flags="No explicit flag found",
        regulatory_barriers="None identified",
        market_status="No verified product found",
    )
    assert domains == {ReviewDomain.SCIENTIFIC_EVIDENCE}


# ---------------------------------------------------------------------
# is_role_authorized — the core Chapter-11 worked examples
# ---------------------------------------------------------------------

def test_market_analyst_not_authorized_for_safety_flagged_candidate():
    domains = required_domains_for_candidate(safety_flags="Lithogenic")
    ok, reasons = is_role_authorized(ReviewerRole.MARKET_INVESTMENT_ANALYST, domains)
    assert ok is False
    assert any("Market / investment analyst" in r for r in reasons)


def test_toxicologist_authorized_for_safety_only_candidate():
    domains = required_domains_for_candidate(safety_flags="Lithogenic")
    ok, reasons = is_role_authorized(ReviewerRole.PHARMACOLOGIST_TOXICOLOGIST, domains)
    assert ok is True
    assert reasons == []


def test_toxicologist_not_authorized_when_commercial_domain_also_required():
    domains = required_domains_for_candidate(
        safety_flags="Lithogenic", market_status="Verified marketed product",
    )
    ok, reasons = is_role_authorized(ReviewerRole.PHARMACOLOGIST_TOXICOLOGIST, domains)
    assert ok is False
    assert any("Commercial" in r for r in reasons)


def test_partial_coverage_is_not_sufficient_non_compensatory():
    # A role authorized for 3 of 4 required domains is still refused —
    # matches the platform's existing non-compensatory gate design.
    domains = {
        ReviewDomain.SCIENTIFIC_EVIDENCE, ReviewDomain.SAFETY,
        ReviewDomain.REGULATORY, ReviewDomain.COMMERCIAL,
    }
    ok, reasons = is_role_authorized(ReviewerRole.PHARMACOLOGIST_TOXICOLOGIST, domains)
    assert ok is False


def test_none_role_never_authorized_for_anything():
    ok, reasons = is_role_authorized(None, {ReviewDomain.SCIENTIFIC_EVIDENCE})
    assert ok is False
    assert len(reasons) == 1


def test_none_role_not_authorized_even_for_empty_required_domains():
    # An unrecognized/missing role is refused outright, even if (in
    # principle) no domain would need to be covered — never silently
    # "authorized by default".
    ok, reasons = is_role_authorized(None, set())
    assert ok is False


def test_regulatory_professional_alone_not_sufficient_since_scientific_evidence_always_required():
    # SCIENTIFIC_EVIDENCE is always in required_domains_for_candidate()'s
    # baseline (see that function's own docstring) — a role authorized
    # ONLY for Regulatory can never single-handedly cover a candidate,
    # even one whose only extra signal is regulatory. This is the same
    # non-compensatory, no-partial-coverage design as every other test
    # in this section, just applied to the baseline domain specifically.
    domains = required_domains_for_candidate(regulatory_barriers="Prohibited / banned")
    ok, reasons = is_role_authorized(ReviewerRole.REGULATORY_PROFESSIONAL, domains)
    assert ok is False
    assert any("Scientific evidence" in r for r in reasons)


def test_regulatory_professional_not_authorized_for_safety_flagged_candidate():
    domains = required_domains_for_candidate(safety_flags="Lithogenic")
    ok, reasons = is_role_authorized(ReviewerRole.REGULATORY_PROFESSIONAL, domains)
    assert ok is False


def test_platform_administrator_never_authorized_for_any_real_candidate():
    domains = required_domains_for_candidate()  # scientific evidence only
    ok, reasons = is_role_authorized(ReviewerRole.PLATFORM_ADMINISTRATOR, domains)
    assert ok is False
