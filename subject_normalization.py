"""
Reference-Grounded Validation — Subject Normalization.

WHY THIS EXISTS
Claims about "pregnancy," "pregnant women," and "use in pregnancy" are
the SAME subject and must be grouped together before precedence
resolution — otherwise three references making the same claim in
slightly different words would each become an isolated, single-source
"resolved outcome" instead of being compared against each other (v4
correction #5). This module is the one place that mapping lives.

VERSIONING
SUBJECT_NORMALIZATION_RULE_VERSION is stored on every
ResolvedExpectedOutcome that used this module (see
resolved_expected_outcome.py) — a future change to the mapping table
below MUST bump this version, so a locked outcome's provenance always
names the exact rule version that grouped its claims, not just "some
version of normalization."

DETERMINISM
normalize_subject() is a pure function: same input string always
produces the same output, no randomness, no external lookup.
Unrecognized subjects normalize to their own lowercased, whitespace-
collapsed form rather than raising — an unrecognized subject is not an
error, it just doesn't get grouped with any known synonym set.
"""

from __future__ import annotations

import re

SUBJECT_NORMALIZATION_RULE_VERSION = "1.0.0"

# Each canonical subject maps to every known surface-form variant,
# lowercased. Extend this table (and bump the version above) as new
# variants are found during real Gold Set curation — never silently
# add a synonym without bumping the version, since a resolved outcome
# from before the change would otherwise be indistinguishable from one
# computed after it.
_SYNONYM_GROUPS = {
    "pregnancy": {
        "pregnancy", "pregnant women", "use in pregnancy",
        "during pregnancy", "pregnant", "gestation",
    },
    "lactation": {
        "lactation", "breastfeeding", "breast-feeding",
        "nursing mothers", "use during lactation",
    },
    "pediatric": {
        "pediatric", "paediatric", "children", "use in children",
        "pediatric population", "under 12 years", "minors",
    },
    "hepatic impairment": {
        "hepatic impairment", "liver impairment", "liver disease",
        "hepatic dysfunction",
    },
    "renal impairment": {
        "renal impairment", "kidney impairment", "renal dysfunction",
    },
    "elderly": {
        "elderly", "geriatric", "older adults", "advanced age",
    },
}

_CANONICAL_BY_VARIANT = {
    variant: canonical
    for canonical, variants in _SYNONYM_GROUPS.items()
    for variant in variants
}


def _collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def normalize_subject(subject: str) -> str:
    """Deterministic normalization used to group ReferenceClaims by
    (domain, assertion_type, normalized_subject) before precedence
    resolution — see resolved_expected_outcome.py's
    group_claims_by_assertion_identity(). Never raises; an
    unrecognized subject normalizes to its own collapsed-whitespace,
    lowercased form."""
    collapsed = _collapse_whitespace(subject or "")
    return _CANONICAL_BY_VARIANT.get(collapsed, collapsed)
