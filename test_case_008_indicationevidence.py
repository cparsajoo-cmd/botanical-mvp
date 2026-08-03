"""test_case_008_indicationevidence.py

⚠️ SUPERSEDED / NON-CANONICAL (flagged 2026-08-03) ⚠️
This tests the superseded, non-canonical draft of Case 008
(gold_case_reference_grounded_008_ginkgo_biloba_indicationevidence.py).
The canonical Case 008 is gold_case_reference_grounded_008_ginkgo_biloba_preparation_spec.py
(domain PREPARATION_SPEC). See NEXT_ACTIONS.md NA-010 for the pending
archival decision. This test still runs under pytest and is not
currently broken, but its subject file is not part of the canonical
16-case Gold Case set.

Test suite for Gold Case 008: Ginkgo biloba L. (INDICATION_EVIDENCE)

Tests validate:
1. Gold Case Ground Truth instantiation
2. Correct extraction of assertion type and state
3. Proper domain classification
4. Confidence level assignment
5. Applicability checks
6. Agreement eligibility rules

Minimum tests required: 6 (VALIDATION_PROTOCOL.md §6)
Total tests: 8
"""

import sys
import unittest
from pathlib import Path

# Add repo to path
sys.path.insert(0, str(Path(__file__).parent))

# Import the Gold Case
try:
    from gold_case_reference_grounded_008_ginkgo_biloba_indicationevidence import (
        GoldCaseReference,
        ValidationUnit,
        ReferenceDescriptor,
        ReferenceClaim,
        NormalizedEvidenceText,
    )
except ImportError as e:
    print(f"ERROR: Failed to import Gold Case 008: {e}")
    sys.exit(1)


class TestCase008GroundTruth(unittest.TestCase):
    """Test 1-2: Ground Truth instantiation and structure"""
    
    def setUp(self):
        """Initialize case for each test"""
        self.case = GoldCaseReference()
    
    def test_001_case_instantiation(self):
        """Test 1: Case instantiates without errors"""
        self.assertIsNotNone(self.case)
        self.assertEqual(self.case.case_number, 8)
        self.assertEqual(self.case.case_id, "CASE_008_GINKGO_BILOBA_INDICATION")
    
    def test_002_scope_definition(self):
        """Test 2: Validation unit (scope) is properly defined"""
        unit = self.case.validation_unit
        self.assertEqual(unit.taxon, "Ginkgo biloba L.")
        self.assertEqual(unit.plant_part, "leaf")
        self.assertIsNotNone(unit.preparation)
        self.assertEqual(unit.plant_part, "leaf")


class TestCase008Assertion(unittest.TestCase):
    """Test 3-4: Assertion type and state"""
    
    def setUp(self):
        self.case = GoldCaseReference()
    
    def test_003_assertion_type_correct(self):
        """Test 3: Assertion type is SUPPORTS_INDICATION"""
        self.assertEqual(self.case.assertion_type, "SUPPORTS_INDICATION")
    
    def test_004_assertion_state_present(self):
        """Test 4: Assertion state is PRESENT (claim exists in source)"""
        self.assertEqual(self.case.assertion_state, "PRESENT")


class TestCase008DomainAndConfidence(unittest.TestCase):
    """Test 5-6: Domain classification and confidence"""
    
    def setUp(self):
        self.case = GoldCaseReference()
    
    def test_005_domain_indication_evidence(self):
        """Test 5: Domain is correctly set to INDICATION_EVIDENCE"""
        self.assertEqual(self.case.domain, "INDICATION_EVIDENCE")
    
    def test_006_extraction_confidence_high(self):
        """Test 6: Extraction confidence is HIGH (claim directly stated)"""
        self.assertEqual(self.case.extraction_confidence, "HIGH")


class TestCase008ApplicabilityAndSource(unittest.TestCase):
    """Test 7-8: Applicability checks and source integrity"""
    
    def setUp(self):
        self.case = GoldCaseReference()
    
    def test_007_applicability_indication_evidence(self):
        """Test 7: Case is applicable to INDICATION_EVIDENCE domain"""
        applicability = self.case.check_applicability()
        self.assertTrue(applicability["INDICATION_EVIDENCE"])
    
    def test_008_source_is_authoritative(self):
        """Test 8: Source is from authoritative high-quality source (Cochrane)"""
        descriptor = self.case.reference_descriptor
        self.assertEqual(descriptor.source_type, "SYSTEMATIC_REVIEW")
        self.assertIn("COCHRANE", descriptor.source_reference_id)
        self.assertIn("Cochrane", descriptor.source_title)


class TestCase008ExpectedOutcomes(unittest.TestCase):
    """Validation: Expected outcomes can be resolved"""
    
    def setUp(self):
        self.case = GoldCaseReference()
    
    def test_resolve_outcomes(self):
        """Resolve expected outcomes for test generation"""
        outcomes = self.case.resolve_expected_outcomes()
        
        # Verify structure
        self.assertIn("case_id", outcomes)
        self.assertIn("assertion_type", outcomes)
        self.assertIn("assertion_state", outcomes)
        self.assertIn("extraction_confidence", outcomes)
        self.assertIn("applicability", outcomes)
        
        # Verify values
        self.assertEqual(outcomes["assertion_type"], "SUPPORTS_INDICATION")
        self.assertEqual(outcomes["assertion_state"], "PRESENT")
        self.assertEqual(outcomes["extraction_confidence"], "HIGH")
        self.assertTrue(outcomes["applicability"]["INDICATION_EVIDENCE"])


# ========== REGRESSION SUITE ==========

class TestCase008Regression(unittest.TestCase):
    """Regression checks: case does not break existing behavior"""
    
    def test_no_safety_claim_assertion(self):
        """Regression: Case 008 does not introduce safety claims"""
        case = GoldCaseReference()
        self.assertFalse(case.applicability_by_domain["SAFETY"])
    
    def test_no_identity_claim_assertion(self):
        """Regression: Case 008 does not introduce identity claims"""
        case = GoldCaseReference()
        self.assertFalse(case.applicability_by_domain["IDENTITY_QUALITY"])
    
    def test_no_preparation_primary_claim(self):
        """Regression: Preparation is scope, not primary claim"""
        case = GoldCaseReference()
        # PREPARATION_SPEC should be False because the primary claim is indication, not preparation
        self.assertFalse(case.applicability_by_domain["PREPARATION_SPEC"])


# ========== TEST RUNNER ==========

def run_tests():
    """Run all tests and report results"""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestCase008GroundTruth))
    suite.addTests(loader.loadTestsFromTestCase(TestCase008Assertion))
    suite.addTests(loader.loadTestsFromTestCase(TestCase008DomainAndConfidence))
    suite.addTests(loader.loadTestsFromTestCase(TestCase008ApplicabilityAndSource))
    suite.addTests(loader.loadTestsFromTestCase(TestCase008ExpectedOutcomes))
    suite.addTests(loader.loadTestsFromTestCase(TestCase008Regression))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Report
    print("\n" + "="*80)
    print("TEST SUMMARY: Case 008")
    print("="*80)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Success: {result.wasSuccessful()}")
    print("="*80 + "\n")
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
