import json
from pathlib import Path

import pytest

import freeze_internal_holdout_v4 as freeze
from check_internal_holdout_v4_leakage import evaluate_leakage
from internal_holdout_v4 import extract_publication_identifiers, validate_reference_cases_document, verify_manifest_hashes


def _case(**overrides):
    case = {
        "case_id": "rgv4_001_new_case",
        "botanical": "Testus botanica",
        "indication": "new indication",
        "jurisdiction": "EU",
        "dosage_form": "oral",
        "expected_decision": "GO WITH CAUTION",
        "reference_established_independently_of_platform_output": True,
        "expert_or_authoritative_reference_review_complete": True,
        "reference_rationale": "Independent reference rationale.",
        "reference_evidence": [{"pmid": "99999999", "source_title": "Independent source"}],
        "engine_input_snapshot": "snapshots/rgv4_001_new_case.json",
    }
    case.update(overrides)
    return case


def test_empty_template_is_not_freeze_ready():
    doc = {"cases": []}
    result = validate_reference_cases_document(doc, require_complete_labels=True)
    assert not result.ready


def test_six_class_vocabulary_is_reused_not_reinvented():
    doc = {"cases": [_case(expected_decision="NEW CLASS")]}
    result = validate_reference_cases_document(doc, require_complete_labels=True)
    assert not result.ready
    assert any("six-class vocabulary" in e for e in result.errors)


def test_reference_must_be_independent_before_freeze():
    doc = {"cases": [_case(reference_established_independently_of_platform_output=False)]}
    result = validate_reference_cases_document(doc, require_complete_labels=True)
    assert not result.ready


def test_identifier_extraction_normalizes_pmid_doi_nct():
    ids = extract_publication_identifiers({
        "reference": "PMID: 12345678; NCT01234567; doi:10.1000/ABC.1",
        "doi": "https://doi.org/10.2000/XYZ",
    })
    assert "12345678" in ids["pmids"]
    assert "NCT01234567" in ids["ncts"]
    assert "10.1000/abc.1" in ids["dois"]
    assert "10.2000/xyz" in ids["dois"]


def test_leakage_checker_detects_historical_pmid_overlap(tmp_path):
    (tmp_path / "gold_corpus").mkdir()
    (tmp_path / "gold_corpus" / "old_validation.json").write_text(
        json.dumps({"cases": [{"case_id": "old", "botanical": "Old plant", "indication": "old", "pmid": "99999999"}]})
    )
    report = evaluate_leakage({"cases": [_case()]}, repo_root=tmp_path)
    assert report["status"] == "fail"
    assert report["historical_identifier_overlap"]["pmids"] == ["99999999"]


def test_leakage_checker_detects_duplicate_nct_within_new_holdout(tmp_path):
    (tmp_path / "gold_corpus").mkdir()
    c1 = _case(case_id="rgv4_001", reference_evidence=[{"nct_id": "NCT01234567"}])
    c2 = _case(case_id="rgv4_002", botanical="Other plant", indication="other", reference_evidence=[{"nct_id": "NCT01234567"}])
    report = evaluate_leakage({"cases": [c1, c2]}, repo_root=tmp_path)
    assert report["status"] == "fail"
    assert "NCT01234567" in report["within_holdout_duplicate_identifiers"]["ncts"]


def test_freeze_refuses_without_manual_study_overlap_review(tmp_path, monkeypatch):
    base = tmp_path / "gold_corpus/scientific_validity/rgv_v4"
    (base / "snapshots").mkdir(parents=True)
    (base / "snapshots/rgv4_001_new_case.json").write_text("{}")
    doc = {
        "labels_visible_to_engine_before_first_execution": False,
        "used_for_engine_remediation": False,
        "reference_defining_evidence_excluded_from_engine_input": True,
        "manual_study_overlap_review_complete": False,
        "cases": [_case()],
    }
    cases = base / "reference_cases.json"
    cases.write_text(json.dumps(doc))
    monkeypatch.setattr(freeze, "BASE", base)
    with pytest.raises(ValueError, match="manual_study_overlap_review_complete"):
        freeze.build_freeze_manifest(cases, repo_root=tmp_path)



def test_freeze_refuses_reference_evidence_leaking_into_engine_input(tmp_path, monkeypatch):
    base = tmp_path / "gold_corpus/scientific_validity/rgv_v4"
    (base / "snapshots").mkdir(parents=True)
    (base / "snapshots/rgv4_001_new_case.json").write_text(json.dumps({
        "candidate_pool": ["Testus botanica"],
        "records": [{"pmid": "99999999"}],
    }))
    doc = {
        "labels_visible_to_engine_before_first_execution": False,
        "used_for_engine_remediation": False,
        "reference_defining_evidence_excluded_from_engine_input": True,
        "manual_study_overlap_review_complete": True,
        "cases": [_case()],
    }
    cases = base / "reference_cases.json"
    cases.write_text(json.dumps(doc))
    monkeypatch.setattr(freeze, "BASE", base)
    with pytest.raises(ValueError, match="also appears in engine input"):
        freeze.build_freeze_manifest(cases, repo_root=tmp_path)

def test_freeze_manifest_hashes_detect_post_freeze_change(tmp_path):
    p = tmp_path / "f.json"
    p.write_text('{"a":1}')
    import hashlib
    expected = hashlib.sha256(p.read_bytes()).hexdigest()
    manifest = {"file_hashes": {"f.json": expected}}
    assert verify_manifest_hashes(tmp_path, manifest).ready
    p.write_text('{"a":2}')
    result = verify_manifest_hashes(tmp_path, manifest)
    assert not result.ready
    assert any("Hash mismatch" in e for e in result.errors)
