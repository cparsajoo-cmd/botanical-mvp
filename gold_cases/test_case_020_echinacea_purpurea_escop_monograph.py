import unittest

from applicability_check import ReferenceDomain
from assertion_vocabulary import AssertionState, AssertionType, TransformationType
from reference_precedence import ResolutionStatus
from gold_case_reference_grounded_020_echinacea_purpurea_escop_monograph import (
    build_gold_case_refgrounded_020_echinacea_purpurea_escop_monograph,
)


class TestCase020EchinaceaPurpureaESCOP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = build_gold_case_refgrounded_020_echinacea_purpurea_escop_monograph()
        cls.ref = cls.case.references[0].reference
        cls.claim = cls.case.references[0].claims[0]
        cls.outcome = cls.case.resolved_outcomes[0]

    def test_closes_escop_source_gap(self):
        self.assertEqual(self.ref.source_type, "ESCOP_MONOGRAPH")
        self.assertIn("ESCOP", self.ref.version)
        self.assertIn("2021", self.ref.version)

    def test_botanical_identity_and_part_are_source_grounded(self):
        self.assertEqual(self.case.validation_unit.taxon, "Echinacea purpurea (L.) Moench")
        self.assertEqual(self.case.validation_unit.plant_part, "flowering aerial parts")
        self.assertEqual(self.ref.taxon, self.case.validation_unit.taxon)
        self.assertEqual(self.ref.plant_part, self.case.validation_unit.plant_part)

    def test_indication_assertion_is_exactly_scoped(self):
        self.assertEqual(self.claim.domain, ReferenceDomain.INDICATION_EVIDENCE)
        self.assertEqual(self.claim.assertion_type, AssertionType.SUPPORTS_INDICATION)
        self.assertEqual(self.claim.assertion_state, AssertionState.PRESENT)
        self.assertEqual(
            self.claim.subject,
            "recurrent infections of the upper respiratory tract (common colds)",
        )

    def test_public_source_quote_is_verbatim_and_traceable(self):
        self.assertEqual(self.claim.evidence_text.transformation_type, TransformationType.VERBATIM)
        self.assertIn("therapeutic indications", self.claim.evidence_text.original_text)
        self.assertIn("escop.com", self.claim.source_locator)

    def test_no_fabricated_preparation_dose_route_population_or_duration(self):
        self.assertIsNone(self.case.validation_unit.preparation)
        self.assertIsNone(self.case.validation_unit.dose)
        self.assertIsNone(self.case.validation_unit.route_of_administration)
        self.assertIsNone(self.case.validation_unit.population)
        self.assertIsNone(self.case.validation_unit.duration)

    def test_applicability_passes(self):
        result = self.case.references[0].applicability_by_domain[ReferenceDomain.INDICATION_EVIDENCE]
        self.assertTrue(result.applicable)

    def test_resolves_selected(self):
        self.assertEqual(self.outcome.resolution_status, ResolutionStatus.SELECTED)
        self.assertEqual(self.outcome.selected_reference_id, self.ref.reference_id)
        self.assertEqual(self.outcome.assertion_state, AssertionState.PRESENT)

    def test_no_engine_evidence_leakage(self):
        self.assertEqual(self.case.engine_evidence, [])
        self.assertIsNone(self.case.engine_evidence_origin)
        self.assertFalse(self.case.locked)


if __name__ == "__main__":
    unittest.main()
