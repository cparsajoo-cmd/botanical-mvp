import unittest

from applicability_check import ReferenceDomain
from assertion_vocabulary import (
    AssertionState,
    AssertionType,
    ExtractionConfidenceLevel,
    SeverityLevel,
    TransformationType,
)
from gold_case import RiskStratum
from reference_precedence import ResolutionStatus
from gold_case_reference_grounded_014_ginkgo_biloba_safety_interaction import (
    build_gold_case_refgrounded_014_ginkgo_biloba_safety_interaction,
)


class TestCase014GinkgoSafetyInteraction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = build_gold_case_refgrounded_014_ginkgo_biloba_safety_interaction()
        cls.gref = cls.case.references[0]
        cls.claim = cls.gref.claims[0]
        cls.outcome = cls.case.resolved_outcomes[0]

    def test_safety_interaction_identity(self):
        self.assertEqual(self.claim.domain, ReferenceDomain.SAFETY)
        self.assertEqual(self.claim.assertion_type, AssertionType.INTERACTION)
        self.assertEqual(self.claim.assertion_state, AssertionState.PRESENT)

    def test_moderate_severity_is_explicit(self):
        self.assertEqual(self.claim.severity, SeverityLevel.MODERATE)
        self.assertEqual(self.outcome.severity, SeverityLevel.MODERATE)
        self.assertIn(RiskStratum.SAFETY_MODERATE, self.case.risk_strata)
        self.assertIn(RiskStratum.INTERACTION, self.case.risk_strata)

    def test_claim_is_narrowly_scoped_to_dabigatran(self):
        self.assertEqual(
            self.claim.subject,
            "concomitant use with dabigatran etexilate",
        )
        self.assertNotIn("all anticoagulants", self.claim.evidence_text.normalized_text.lower())

    def test_ema_hmpc_reference_and_exact_locator(self):
        self.assertEqual(self.gref.reference.source_type, "EMA_HMPC")
        self.assertIn("EMA/HMPC/321097/2012", self.gref.reference.version)
        self.assertIn("section 4.5", self.claim.source_locator)
        self.assertIn("page 4/8", self.claim.source_locator)

    def test_preparation_and_route_match_monograph_scope(self):
        prep = self.case.validation_unit.preparation
        self.assertEqual(prep.dosage_form, "Dry extract")
        self.assertEqual(prep.solvent, "acetone 60% m/m")
        self.assertEqual((prep.der_min, prep.der_max), (35.0, 67.0))
        self.assertEqual(self.case.validation_unit.route_of_administration, "Oral")

    def test_applicability_and_safety_precedence_select_reference(self):
        applicability = self.gref.applicability_by_domain[ReferenceDomain.SAFETY]
        self.assertTrue(applicability.applicable)
        self.assertEqual(applicability.failed_dimensions, [])
        self.assertEqual(self.outcome.resolution_status, ResolutionStatus.SELECTED)
        self.assertEqual(self.outcome.selected_reference_id, self.gref.reference.reference_id)

    def test_evidence_is_traceable_and_not_overstated(self):
        self.assertEqual(
            self.claim.evidence_text.original_text,
            "Caution is advised if combining G. biloba and dabigatran.",
        )
        self.assertEqual(
            self.claim.evidence_text.transformation_type,
            TransformationType.NORMALIZED_TERMINOLOGY,
        )
        self.assertEqual(
            self.claim.extraction_confidence.level,
            ExtractionConfidenceLevel.HIGH,
        )

    def test_no_engine_evidence_leakage(self):
        self.assertEqual(self.case.engine_evidence, [])
        self.assertIsNone(self.case.engine_evidence_origin)


if __name__ == "__main__":
    unittest.main()
