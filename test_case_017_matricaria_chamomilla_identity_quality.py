import unittest

from applicability_check import ReferenceDomain
from assertion_vocabulary import AssertionState, AssertionType, ExtractionConfidenceLevel
from reference_precedence import ResolutionStatus
from gold_case_reference_grounded_017_matricaria_chamomilla_identity_quality import (
    build_gold_case_refgrounded_017_matricaria_chamomilla_identity_quality,
)


class TestCase017MatricariaIdentityQuality(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = build_gold_case_refgrounded_017_matricaria_chamomilla_identity_quality()
        cls.gref = cls.case.references[0]
        cls.claim = cls.gref.claims[0]
        cls.outcome = cls.case.resolved_outcomes[0]

    def test_identity_quality_domain(self):
        self.assertEqual(self.claim.domain, ReferenceDomain.IDENTITY_QUALITY)

    def test_identity_confirmation_present(self):
        self.assertEqual(self.claim.assertion_type, AssertionType.IDENTITY_CONFIRMATION)
        self.assertEqual(self.claim.assertion_state, AssertionState.PRESENT)

    def test_taxonomic_authority_source(self):
        self.assertEqual(self.gref.reference.source_type, "TAXONOMIC_AUTHORITY")
        self.assertIn("154715-2", self.gref.reference.version)

    def test_accepted_taxon_and_synonyms(self):
        self.assertEqual(self.case.validation_unit.taxon, "Matricaria chamomilla L.")
        self.assertIn(
            "Chamomilla recutita (L.) Rauschert",
            self.case.validation_unit.taxon_synonyms,
        )
        self.assertIn("Matricaria recutita L.", self.case.validation_unit.taxon_synonyms)

    def test_applicability_and_precedence(self):
        applicability = self.gref.applicability_by_domain[ReferenceDomain.IDENTITY_QUALITY]
        self.assertTrue(applicability.applicable)
        self.assertEqual(self.outcome.resolution_status, ResolutionStatus.SELECTED)
        self.assertEqual(self.outcome.selected_reference_id, self.gref.reference.reference_id)

    def test_evidence_traceability(self):
        self.assertIn("POWO", self.claim.source_locator)
        self.assertIn("accepted", self.claim.evidence_text.original_text.lower())
        self.assertEqual(
            self.claim.extraction_confidence.level,
            ExtractionConfidenceLevel.HIGH,
        )

    def test_case_scope_is_identity_only(self):
        self.assertIsNone(self.case.validation_unit.indication)
        self.assertIsNone(self.case.validation_unit.preparation)
        self.assertIsNone(self.case.validation_unit.route_of_administration)

    def test_no_ground_truth_leakage(self):
        self.assertEqual(self.case.engine_evidence, [])
        self.assertIsNone(self.case.engine_evidence_origin)


if __name__ == "__main__":
    unittest.main()
