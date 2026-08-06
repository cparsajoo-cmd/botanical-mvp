import unittest

from applicability_check import ReferenceDomain
from assertion_vocabulary import AssertionState, AssertionType
from reference_precedence import ResolutionStatus
from gold_case_reference_grounded_019_panax_ginseng_who_monograph import (
    build_gold_case_refgrounded_019_panax_ginseng_who_monograph,
)


class TestCase019PanaxGinsengWHO(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = build_gold_case_refgrounded_019_panax_ginseng_who_monograph()
        cls.ref = cls.case.references[0].reference
        cls.claim = cls.case.references[0].claims[0]
        cls.outcome = cls.case.resolved_outcomes[0]

    def test_closes_who_source_gap(self):
        self.assertEqual(self.ref.source_type, "WHO_MONOGRAPH")
        self.assertIn("9241545178", self.ref.version)

    def test_botanical_identity_and_part_are_source_grounded(self):
        self.assertEqual(self.case.validation_unit.taxon, "Panax ginseng C.A. Meyer")
        self.assertEqual(self.case.validation_unit.plant_part, "root")
        self.assertEqual(self.ref.taxon, "Panax ginseng C.A. Meyer")
        self.assertEqual(self.ref.plant_part, "root")

    def test_indication_assertion(self):
        self.assertEqual(self.claim.domain, ReferenceDomain.INDICATION_EVIDENCE)
        self.assertEqual(self.claim.assertion_type, AssertionType.SUPPORTS_INDICATION)
        self.assertEqual(self.claim.assertion_state, AssertionState.PRESENT)

    def test_no_fabricated_preparation_dose_route_or_population(self):
        self.assertIsNone(self.case.validation_unit.preparation)
        self.assertIsNone(self.case.validation_unit.dose)
        self.assertIsNone(self.case.validation_unit.route_of_administration)
        self.assertIsNone(self.case.validation_unit.population)

    def test_applicability_passes(self):
        result = self.case.references[0].applicability_by_domain[ReferenceDomain.INDICATION_EVIDENCE]
        self.assertTrue(result.applicable)

    def test_resolves_selected(self):
        self.assertEqual(self.outcome.resolution_status, ResolutionStatus.SELECTED)
        self.assertEqual(self.outcome.selected_reference_id, self.ref.reference_id)
        self.assertEqual(self.outcome.assertion_state, AssertionState.PRESENT)

    def test_critical_source_locator_is_specific(self):
        self.assertIn("p.172", self.claim.source_locator)
        self.assertIn("p.168", self.claim.source_locator)

    def test_no_engine_evidence_leakage(self):
        self.assertEqual(self.case.engine_evidence, [])
        self.assertIsNone(self.case.engine_evidence_origin)
        self.assertFalse(self.case.locked)


if __name__ == "__main__":
    unittest.main()
