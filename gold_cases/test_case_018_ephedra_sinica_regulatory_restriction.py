import unittest

from applicability_check import ReferenceDomain
from assertion_vocabulary import AssertionState, AssertionType, ExtractionConfidenceLevel
from reference_precedence import ResolutionStatus
from gold_case_reference_grounded_018_ephedra_sinica_regulatory_restriction import (
    build_gold_case_refgrounded_018_ephedra_sinica_regulatory_restriction,
)


class TestCase018EphedraSinicaRegulatoryRestriction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = build_gold_case_refgrounded_018_ephedra_sinica_regulatory_restriction()
        cls.gref = cls.case.references[0]
        cls.claim = cls.gref.claims[0]
        cls.outcome = cls.case.resolved_outcomes[0]

    def test_regulatory_status_domain(self):
        self.assertEqual(self.claim.domain, ReferenceDomain.REGULATORY_STATUS)

    def test_restriction_is_present(self):
        self.assertEqual(self.claim.assertion_type, AssertionType.RESTRICTION)
        self.assertEqual(self.claim.assertion_state, AssertionState.PRESENT)

    def test_national_regulatory_source_is_recognized(self):
        self.assertEqual(self.gref.reference.source_type, "NATIONAL_REGULATORY")
        self.assertIn("Schedule 20", self.gref.reference.version)

    def test_scope_is_species_jurisdiction_and_internal_use_mapping_specific(self):
        self.assertEqual(self.case.validation_unit.taxon, "Ephedra sinica Stapf")
        self.assertEqual(self.case.validation_unit.jurisdiction, "UK")
        self.assertEqual(self.case.validation_unit.route_of_administration, "Oral")
        self.assertIsNone(self.case.validation_unit.population)
        self.assertIsNone(self.gref.reference.population)
        self.assertEqual(self.gref.reference.route_scope, ["Oral"])

    def test_dose_thresholds_and_supply_channel_are_preserved(self):
        self.assertEqual(self.claim.evidence_text.original_text, "600 mg (MD), 1800 mg (MDD)")
        normalized = self.claim.evidence_text.normalized_text.lower()
        self.assertIn("600 mg", normalized)
        self.assertIn("1800 mg", normalized)
        self.assertIn("one-to-one practitioner consultation", normalized)
        self.assertIn("registered pharmacy premises", normalized)
        self.assertIn("pharmacist supervision", normalized)

    def test_claim_is_not_an_absolute_maximum_or_prohibition(self):
        normalized = self.claim.evidence_text.normalized_text.lower()
        self.assertNotIn("maximum permitted under all circumstances", normalized)
        self.assertNotIn("prohibited above", normalized)
        self.assertEqual(self.claim.assertion_type, AssertionType.RESTRICTION)

    def test_applicability_and_precedence_select_source(self):
        applicability = self.gref.applicability_by_domain[ReferenceDomain.REGULATORY_STATUS]
        self.assertTrue(applicability.applicable)
        self.assertEqual(self.outcome.resolution_status, ResolutionStatus.SELECTED)
        self.assertEqual(self.outcome.selected_reference_id, self.gref.reference.reference_id)

    def test_traceability_confidence_and_risk_strata(self):
        self.assertIn("Ephedra sinica", self.claim.source_locator)
        self.assertEqual(self.claim.extraction_confidence.level, ExtractionConfidenceLevel.HIGH)
        self.assertEqual(self.case.risk_strata, [])

    def test_ground_truth_is_leakage_free(self):
        self.assertEqual(self.case.engine_evidence, [])
        self.assertIsNone(self.case.engine_evidence_origin)
        self.assertFalse(self.case.locked)


if __name__ == "__main__":
    unittest.main()
