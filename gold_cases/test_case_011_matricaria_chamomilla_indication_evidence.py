import unittest
from applicability_check import ReferenceDomain
from assertion_vocabulary import AssertionState, AssertionType
from reference_precedence import ResolutionStatus
from gold_case_reference_grounded_011_matricaria_chamomilla_indication_evidence import (
    build_gold_case_refgrounded_011_matricaria_chamomilla_indication_evidence,
)

class TestCorrectedCase011(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = build_gold_case_refgrounded_011_matricaria_chamomilla_indication_evidence()
        cls.claim = cls.case.references[0].claims[0]
        cls.outcome = cls.case.resolved_outcomes[0]

    def test_domain_is_indication_not_safety(self):
        self.assertEqual(self.claim.domain, ReferenceDomain.INDICATION_EVIDENCE)
        self.assertNotEqual(self.claim.domain, ReferenceDomain.SAFETY)

    def test_assertion_is_ontology_compatible(self):
        self.assertEqual(self.claim.assertion_type, AssertionType.SUPPORTS_INDICATION)
        self.assertEqual(self.claim.assertion_state, AssertionState.PRESENT)

    def test_governing_source_is_systematic_review(self):
        self.assertEqual(self.case.references[0].reference.source_type, "SYSTEMATIC_REVIEW")
        self.assertIn("10.1002/ptr.6349", self.case.references[0].reference.version)

    def test_resolves_selected(self):
        self.assertEqual(self.outcome.resolution_status, ResolutionStatus.SELECTED)
        self.assertEqual(self.outcome.selected_reference_id, self.case.references[0].reference.reference_id)

    def test_no_engine_evidence_leakage(self):
        self.assertEqual(self.case.engine_evidence, [])
        self.assertIsNone(self.case.engine_evidence_origin)

if __name__ == "__main__":
    unittest.main()
