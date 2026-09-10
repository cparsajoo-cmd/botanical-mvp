"""Static/pure-function tests for pipeline_fingerprint.py (Section 6).
Avoids importing step_rd_candidates directly where possible for the parts
that don't need it, matching test_step5_pipeline_fingerprint_static.py's
existing no-Streamlit-required convention.
"""

from pathlib import Path

import pipeline_fingerprint as pf


def test_step_rd_candidates_is_not_in_the_scientific_file_list():
    assert "step_rd_candidates.py" not in pf.SCIENTIFIC_FINGERPRINT_FILES


def test_step_rd_candidates_is_in_the_commercial_file_list():
    assert "step_rd_candidates.py" in pf.COMMERCIAL_FINGERPRINT_FILES


def test_new_commercial_modules_are_in_the_commercial_file_list():
    for expected in (
        "commercial_evidence_provider.py",
        "commercial_evidence_import.py",
        "commercial_opportunity_classification.py",
    ):
        assert expected in pf.COMMERCIAL_FINGERPRINT_FILES


def test_source_traceability_presentation_modules_are_in_the_commercial_file_list():
    """Corrective pass (2026-09-10, gap 4): the new presentation/provenance
    modules Stage 6 now calls must invalidate the commercial/presentation
    fingerprint on change, never the scientific one."""
    for expected in (
        "commercial_source_traceability.py",
        "compound_source_traceability.py",
        "claim_source_map.py",
        "source_linkage_consistency.py",
    ):
        assert expected in pf.COMMERCIAL_FINGERPRINT_FILES
        assert expected not in pf.SCIENTIFIC_FINGERPRINT_FILES


def test_scientific_and_commercial_file_lists_do_not_overlap():
    assert set(pf.SCIENTIFIC_FINGERPRINT_FILES).isdisjoint(set(pf.COMMERCIAL_FINGERPRINT_FILES))


def test_scientific_fingerprint_is_deterministic_for_the_same_tree():
    root = Path(__file__).resolve().parent
    assert pf.scientific_implementation_fingerprint(root) == pf.scientific_implementation_fingerprint(root)


def test_commercial_fingerprint_is_deterministic_for_the_same_tree():
    root = Path(__file__).resolve().parent
    assert pf.commercial_implementation_fingerprint(root) == pf.commercial_implementation_fingerprint(root)


def test_scientific_and_commercial_fingerprints_differ():
    root = Path(__file__).resolve().parent
    assert (
        pf.scientific_implementation_fingerprint(root)
        != pf.commercial_implementation_fingerprint(root)
    )


def test_editing_a_commercial_only_file_changes_only_commercial_fingerprint(tmp_path):
    """The core Section 6 guarantee, proven directly against real file
    content rather than mocked: changing a file that is ONLY in the
    commercial list must leave the scientific fingerprint untouched.
    """
    root = Path(__file__).resolve().parent
    scientific_before = pf.scientific_implementation_fingerprint(root)
    commercial_before = pf.commercial_implementation_fingerprint(root)

    # Build an isolated copy of the tree so this test never touches the
    # real repository files on disk.
    for filename in set(pf.SCIENTIFIC_FINGERPRINT_FILES) | set(pf.COMMERCIAL_FINGERPRINT_FILES):
        source = root / filename
        if not source.exists():
            continue  # stay genuinely absent, matching the real tree, so the
            # <missing> sentinel path is exercised identically in both places
        target = tmp_path / filename
        target.write_bytes(source.read_bytes())

    scientific_copy = pf.scientific_implementation_fingerprint(tmp_path)
    commercial_copy = pf.commercial_implementation_fingerprint(tmp_path)
    assert scientific_copy == scientific_before
    assert commercial_copy == commercial_before

    # Mutate ONLY a commercial-only file (step_rd_candidates.py is not in
    # the scientific list).
    target = tmp_path / "step_rd_candidates.py"
    target.write_bytes(target.read_bytes() + b"\n# a commercial/investor-view-only edit\n")

    assert pf.scientific_implementation_fingerprint(tmp_path) == scientific_copy
    assert pf.commercial_implementation_fingerprint(tmp_path) != commercial_copy


def test_editing_a_scientific_only_file_changes_only_scientific_fingerprint(tmp_path):
    root = Path(__file__).resolve().parent
    for filename in set(pf.SCIENTIFIC_FINGERPRINT_FILES) | set(pf.COMMERCIAL_FINGERPRINT_FILES):
        source = root / filename
        if not source.exists():
            continue
        target = tmp_path / filename
        target.write_bytes(source.read_bytes())

    scientific_copy = pf.scientific_implementation_fingerprint(tmp_path)
    commercial_copy = pf.commercial_implementation_fingerprint(tmp_path)

    target = tmp_path / "candidate_shortlisting.py"
    target.write_bytes(target.read_bytes() + b"\n# a scientific-scoring-only edit\n")

    assert pf.scientific_implementation_fingerprint(tmp_path) != scientific_copy
    assert pf.commercial_implementation_fingerprint(tmp_path) == commercial_copy


def test_missing_file_is_hashed_as_explicit_sentinel_not_silently_skipped(tmp_path):
    fp_with_file = pf._hash_files(("candidate_shortlisting.py",), root=Path(__file__).resolve().parent)
    fp_missing = pf._hash_files(("candidate_shortlisting.py",), root=tmp_path)
    assert fp_with_file != fp_missing
