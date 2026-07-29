"""
Parity test — normalization.py vs BotanicalRDCandidateEngine's private
normalization methods.

WHY THIS TEST EXISTS
normalization.py is deliberately an independent reimplementation, not
an import of BotanicalRDCandidateEngine._norm/_norm_taxon (see
normalization.py's own module docstring for why: no production code in
this validation program may depend on the engine's private,
underscore-prefixed surface). This test is the ONLY place in the
repository allowed to import those private methods — and it imports
them purely to compare outputs, never to call or affect the engine's
actual behavior. If this test ever fails, normalization.py has drifted
from the engine's real behavior and must be updated to match; the
engine itself is never "fixed" to match this test.
"""

from botanical_rd_candidate_engine import BotanicalRDCandidateEngine
from normalization import normalize_taxon, normalize_text

# Fixed case list — deliberately covers the scenarios this validation
# program actually cares about (see execution_readiness.py's seed-data
# collision check): plain names, authority suffixes, infraspecific
# ranks, hybrid markers, irregular whitespace/case, and the documented
# missing-value tokens.
_CASES = [
    None,
    "",
    "   ",
    "nan",
    "NaN",
    "none",
    "null",
    "Melissa officinalis",
    "Melissa officinalis L.",
    "MELISSA OFFICINALIS L.",
    "  Melissa   officinalis   L.  ",
    "Melissa officinalis subsp. altissima",
    "Melissa officinalis var. altissima",
    "Melissa officinalis ssp. altissima",
    "Melissa officinalis f. altissima",
    "Melissa officinalis cv. altissima",
    "Tilia × vulgaris",
    "Tilia x vulgaris",
    "Valeriana officinalis",
    "Passiflora incarnata",
    "Curcuma longa",
]


def test_normalize_text_matches_engine_norm_for_fixed_cases():
    for case in _CASES:
        assert normalize_text(case) == BotanicalRDCandidateEngine._norm(case), (
            f"normalize_text({case!r}) diverged from BotanicalRDCandidateEngine._norm()"
        )


def test_normalize_taxon_matches_engine_norm_taxon_for_fixed_cases():
    for case in _CASES:
        assert normalize_taxon(case) == BotanicalRDCandidateEngine._norm_taxon(case), (
            f"normalize_taxon({case!r}) diverged from BotanicalRDCandidateEngine._norm_taxon()"
        )


def test_normalize_text_and_normalize_taxon_diverge_exactly_where_expected():
    """Documents, as an executable assertion, a real scenario where
    normalize_taxon() collapses two strings that normalize_text() does
    not: a trailing infraspecific-rank token with no epithet after it
    (e.g. "var." on its own). This is the mechanism
    SEED_DATA_COLLISION_RISK depends on in execution_readiness.py.

    IMPORTANT CORRECTION (found by this test, not assumed): an earlier
    round of this validation program incorrectly believed a taxonomic
    AUTHORITY CITATION suffix (e.g. "L." for Linnaeus) would also be
    stripped by normalize_taxon()/_norm_taxon(), making
    "Melissa officinalis L." collide with a seed key "Melissa
    officinalis" under taxon-normalization. It does not: "l" is not in
    _norm_taxon()'s stripped-token set (only x/subsp/ssp/nothosubsp/
    var/f/cv are). See test_authority_citation_suffix_is_not_stripped_
    by_either_normalization below for the corrected, verified fact."""
    suffixed = "Melissa officinalis var."
    bare = "Melissa officinalis"

    assert normalize_text(suffixed) != normalize_text(bare)
    assert normalize_taxon(suffixed) == normalize_taxon(bare)

    # And the engine's real private methods behave the same way —
    # this is the actual fact the whole contamination-guard design
    # depends on.
    assert BotanicalRDCandidateEngine._norm(suffixed) != BotanicalRDCandidateEngine._norm(bare)
    assert BotanicalRDCandidateEngine._norm_taxon(suffixed) == BotanicalRDCandidateEngine._norm_taxon(bare)


def test_authority_citation_suffix_is_not_stripped_by_either_normalization():
    """Corrected fact, verified against the engine's real private
    methods: an authority citation like "L." is NOT an infraspecific-
    rank/hybrid token, so it is stripped by NEITHER normalize_text()
    nor normalize_taxon() — "Melissa officinalis L." does not collide
    with seed key "Melissa officinalis" under either normalization as
    currently implemented. This is a real, disclosed coverage gap in
    the seed-data contamination guard, not a safe outcome to rely on
    going forward — see execution_readiness.py's module docstring."""
    suffixed = "Melissa officinalis L."
    bare = "Melissa officinalis"

    assert normalize_text(suffixed) != normalize_text(bare)
    assert normalize_taxon(suffixed) != normalize_taxon(bare)
    assert BotanicalRDCandidateEngine._norm(suffixed) != BotanicalRDCandidateEngine._norm(bare)
    assert BotanicalRDCandidateEngine._norm_taxon(suffixed) != BotanicalRDCandidateEngine._norm_taxon(bare)
