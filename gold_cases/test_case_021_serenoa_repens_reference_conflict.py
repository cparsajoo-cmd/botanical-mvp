import unittest

from applicability_check import ReferenceDomain
from assertion_vocabulary import AssertionState, AssertionType, TransformationType
from reference_precedence import ResolutionStatus
from gold_case_reference_grounded_021_serenoa_repens_reference_conflict import (
    build_gold_case_refgrounded_021_serenoa_repens_reference_conflict,
)


class TestCase021SerenoaRepensReferenceConflict(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = build_gold_case_refgrounded_021_serenoa_repens_reference_conflict()
        cls.outcome = cls.case.resolved_outcomes[0]
        cls.refs = {g.reference.reference_id: g for g in cls.case.references}

    def test_two_real_same_rank_systematic_reviews(self):
        self.assertEqual(len(self.case.references), 2)
        self.assertEqual({g.reference.source_type for g in self.case.references}, {"SYSTEMATIC_REVIEW"})
        versions = " ".join(g.reference.version for g in self.case.references)
        self.assertIn("PMID:9820264", versions)
        self.assertIn("CD001423", versions)

    def test_same_assertion_identity_opposing_states(self):
        claims = [g.claims[0] for g in self.case.references]
        self.assertEqual({c.domain for c in claims}, {ReferenceDomain.INDICATION_EVIDENCE})
        self.assertEqual({c.assertion_type for c in claims}, {AssertionType.SUPPORTS_INDICATION})
        self.assertEqual(len({c.subject for c in claims}), 1)
        self.assertEqual({c.assertion_state for c in claims}, {AssertionState.PRESENT, AssertionState.ABSENT})

    def test_both_references_are_applicable(self):
        for gref in self.case.references:
            result = gref.applicability_by_domain[ReferenceDomain.INDICATION_EVIDENCE]
            self.assertTrue(result.applicable, result.detail)

    def test_resolves_to_real_reference_conflict(self):
        self.assertEqual(self.outcome.resolution_status, ResolutionStatus.REFERENCE_CONFLICT)
        self.assertIsNone(self.outcome.selected_reference_id)
        self.assertIsNone(self.outcome.assertion_state)
        self.assertEqual(
            set(self.outcome.conflicting_reference_ids),
            {g.reference.reference_id for g in self.case.references},
        )

    def test_short_source_excerpts_are_traceable(self):
        claims = [g.claims[0] for g in self.case.references]
        self.assertTrue(all(c.evidence_text.transformation_type == TransformationType.VERBATIM for c in claims))
        self.assertTrue(any("PMID 9820264" in c.source_locator for c in claims))
        self.assertTrue(any("cochrane.org" in c.source_locator for c in claims))

    def test_no_fabricated_preparation_dose_route_or_duration(self):
        unit = self.case.validation_unit
        self.assertIsNone(unit.preparation)
        self.assertIsNone(unit.dose)
        self.assertIsNone(unit.route_of_administration)
        self.assertIsNone(unit.duration)

    def test_no_engine_evidence_leakage(self):
        self.assertEqual(self.case.engine_evidence, [])
        self.assertIsNone(self.case.engine_evidence_origin)
        self.assertFalse(self.case.locked)

    def test_conflict_is_not_silently_resolved_by_recency(self):
        # This is the exact architecture behavior the case is intended to benchmark:
        # equal source rank + opposing verdicts => REFERENCE_CONFLICT, not "pick newest".
        self.assertEqual(self.outcome.resolution_status, ResolutionStatus.REFERENCE_CONFLICT)
        self.assertEqual(len(self.outcome.conflicting_reference_ids), 2)


if __name__ == "__main__":
    unittest.main()
