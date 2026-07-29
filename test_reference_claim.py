"""Tests for reference_claim.py (ReferenceClaim, NormalizedEvidenceText, ExtractionConfidence)."""

from applicability_check import ReferenceDomain
from assertion_vocabulary import (
    AssertionState, AssertionType, SeverityLevel, TransformationType, ExtractionConfidenceLevel,
)
from reference_claim import ReferenceClaim, NormalizedEvidenceText, ExtractionConfidence


def test_minimal_claim_construction():
    claim = ReferenceClaim(
        domain=ReferenceDomain.SAFETY, assertion_type=AssertionType.CONTRAINDICATION,
        subject="pregnancy", assertion_state=AssertionState.PRESENT,
    )
    assert claim.severity is None
    assert claim.evidence_text is None
    assert claim.extraction_confidence is None


def test_full_claim_construction():
    text = NormalizedEvidenceText(
        original_text="Contraindicated in pregnancy.", normalized_text="Contraindicated in pregnancy.",
        transformation_type=TransformationType.VERBATIM, transformation_version="1.0",
        source_locator="section 4.3",
    )
    confidence = ExtractionConfidence(
        level=ExtractionConfidenceLevel.HIGH, basis="Verbatim match to source text",
        extractor_type="human_curator", extractor_version="1.0",
    )
    claim = ReferenceClaim(
        domain=ReferenceDomain.SAFETY, assertion_type=AssertionType.CONTRAINDICATION,
        subject="pregnancy", assertion_state=AssertionState.PRESENT, severity=SeverityLevel.SERIOUS,
        source_reference_id="ref1", source_locator="section 4.3",
        evidence_text=text, extraction_confidence=confidence,
    )
    assert claim.evidence_text.transformation_type == TransformationType.VERBATIM
    assert claim.extraction_confidence.level == ExtractionConfidenceLevel.HIGH


def test_normalized_evidence_text_preserves_both_original_and_normalized():
    text = NormalizedEvidenceText(
        original_text="Kontraindiziert in der Schwangerschaft.",
        normalized_text="Contraindicated in pregnancy.",
        transformation_type=TransformationType.TRANSLATED,
        transformation_version="1.0", source_locator="section 4.3",
    )
    assert text.original_text != text.normalized_text


def test_extraction_confidence_uses_categorical_level_not_a_probability():
    confidence = ExtractionConfidence(
        level=ExtractionConfidenceLevel.MEDIUM, basis="Automated pattern match",
        extractor_type="automated_nlp", extractor_version="2.1",
    )
    assert confidence.level in (
        ExtractionConfidenceLevel.HIGH, ExtractionConfidenceLevel.MEDIUM, ExtractionConfidenceLevel.LOW,
    )
    assert not hasattr(confidence, "probability")
    assert not hasattr(confidence, "score")


def test_summarized_by_curator_is_a_real_transformation_type():
    text = NormalizedEvidenceText(
        original_text="x", normalized_text="y",
        transformation_type=TransformationType.SUMMARIZED_BY_CURATOR,
        transformation_version="1.0", source_locator="loc",
    )
    assert text.transformation_type == TransformationType.SUMMARIZED_BY_CURATOR
