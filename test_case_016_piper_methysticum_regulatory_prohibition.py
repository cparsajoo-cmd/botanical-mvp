import unittest

from applicability_check import ReferenceDomain
from assertion_vocabulary import AssertionState, AssertionType, ExtractionConfidenceLevel
from reference_precedence import ResolutionStatus
from gold_case_reference_grounded_016_piper_methysticum_regulatory_prohibition import (
    build_gold_case_refgrounded_016_piper_methysticum_regulatory_prohibition,
)


class TestCase016PiperMethysticumRegulatoryProhibition(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = build_gold_case_refgrounded_016_piper_methysticum_regulatory_prohibition()
        cls.gref = cls.case.references[0]
        cls.claim = cls.gref.claims[0]
        cls.outcome = cls.case.resolved_outcomes[0]

    def test_regulatory_status_domain(self):
        self.assertEqual(self.claim.domain, ReferenceDomain.REGULATORY_STATUS)

    def test_prohibition_is_present(self):
        self.assertEqual(self.claim.assertion_type, AssertionType.PROHIBITION)
        self.assertEqual(self.claim.assertion_state, AssertionState.PRESENT)

    def test_national_regulatory_source_is_recognized(self):
        self.assertEqual(self.gref.reference.source_type, "NATIONAL_REGULATORY")
        self.assertIn("SI 2002/3170", self.gref.reference.version)

    def test_scope_is_taxon_jurisdiction_and_route_specific(self):
        self.assertEqual(self.case.validation_unit.taxon, "Piper methysticum G.Forst.")
        self.assertEqual(self.case.validation_unit.jurisdiction, "UK")
        self.assertEqual(self.case.validation_unit.route_of_administration, "Oral")

    def test_external_use_exception_is_preserved(self):
        self.assertIn("external use", self.claim.evidence_text.original_text.lower())
        self.assertIn("excluded", self.claim.evidence_text.normalized_text.lower())

    def test_applicability_and_precedence_select_source(self):
        applicability = self.gref.applicability_by_domain[ReferenceDomain.REGULATORY_STATUS]
        self.assertTrue(applicability.applicable)
        self.assertEqual(self.outcome.resolution_status, ResolutionStatus.SELECTED)
        self.assertEqual(self.outcome.selected_reference_id, self.gref.reference.reference_id)

    def test_traceability_and_confidence(self):
        self.assertIn("Piper methysticum", self.claim.source_locator)
        self.assertEqual(self.claim.extraction_confidence.level, ExtractionConfidenceLevel.HIGH)

    def test_ground_truth_is_leakage_free(self):
        self.assertEqual(self.case.engine_evidence, [])
        self.assertIsNone(self.case.engine_evidence_origin)
        self.assertFalse(self.case.locked)


if __name__ == "__main__":
    unittest.main()
