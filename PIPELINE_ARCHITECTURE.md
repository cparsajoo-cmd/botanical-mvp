"""PIPELINE_ARCHITECTURE.md

Gold Case Generation Pipeline - Redesigned Architecture

OBJECTIVE: Ensure the pipeline is incapable of generating scientifically invalid Gold Cases

The pipeline enforces mandatory verification gates and explicit state transitions.
No case may skip a state or be generated with unverified source material.

================================================================================
PIPELINE ARCHITECTURE: MANDATORY SEQUENTIAL STAGES
================================================================================

Every Gold Case MUST pass through these stages in order.
Generation stops automatically if any stage fails.

STAGE 1: DISCOVERY
─────────────────
Input: Catalog query or discovery request
Process: Search repository catalog for candidates
Output: Discovered candidates (with priority ranking)
State transition: → SOURCE_RETRIEVED
Failure mode: No candidates found → PIPELINE_HALT

STAGE 2: SOURCE RETRIEVAL
──────────────────────────
Input: Discovered candidate
Process: Attempt to retrieve actual source document
         Record retrieval method, date, access path
Output: RetrievalRecord with:
  - retrieval_date (ISO format)
  - retrieval_method (direct_web, institutional, email, etc.)
  - access_url or retrieval details
  - retrieved_by (identity of retriever)
State transition: → SOURCE_VERIFIED
Failure mode: Source not found, not accessible, or unretrievable → PIPELINE_HALT

STAGE 3: SOURCE VERIFICATION
──────────────────────────────
Input: RetrievalRecord
Process: Verify source authenticity and metadata
         - Check DOI, PMID, Cochrane ID against official sources
         - Verify publication metadata (authors, date, journal)
         - Create archive record (archive.org snapshot, PDF copy, repo link)
         - No fabrication: every field verified or left empty
Output: VerificationRecord with status = VERIFIED
         (or VERIFICATION_FAILED → PIPELINE_HALT)
State transition: → EVIDENCE_EXTRACTED
Failure mode: Metadata cannot be verified, untrustworthy source → PIPELINE_HALT

STAGE 4: EVIDENCE EXTRACTION
──────────────────────────────
Input: Verified source document
Process: Extract exact evidence text supporting the target assertion
         - Copy verbatim or paraphrase with explicit labeling
         - Record precise locator (page, section, paragraph)
         - Mark transformation type: VERBATIM|LIGHTLY_FORMATTED|PARAPHRASED
         - NO fabrication: if source doesn't support claim, stop
Output: EvidenceQuote with:
  - quoted_text (exact from source)
  - transformation_type (VERBATIM only if exact)
  - precise locators (page_number, section_title, etc.)
  - source verification link
State transition: → READY_FOR_ENGINE
Failure mode: Source does not support claimed assertion → PIPELINE_HALT

STAGE 5: READY FOR ENGINE
──────────────────────────
Input: Verified case with evidence
Process: Prepare case inputs for engine evaluation
         - Remove any hard-coded logic
         - Case contains: scope, verified source, evidence only
         - Case does NOT contain: applicability decisions, assertions
Output: Case object ready for engine evaluation
State transition: → ENGINE_VALIDATED
Failure mode: Case still contains hard-coded decisions → PIPELINE_HALT

STAGE 6: ENGINE EVALUATION
───────────────────────────
Input: Case with verified evidence
Process: Invoke production engine to:
         - Extract assertion type (using assertion_vocabulary)
         - Determine assertion state
         - Assign extraction confidence
         - Check applicability to each domain
         - Detect any semantic integrity warnings
Output: Engine output (assertions, applicability, confidence, warnings)
         Expected outcomes record (independently curated)
State transition: → TEST_VALIDATED
Failure mode: Engine crashes, produces inconsistent output → PIPELINE_HALT

STAGE 7: INTEGRATION TEST VALIDATION
──────────────────────────────────────
Input: Engine output + Expected outcomes
Process: Run integration tests:
         - Invoke REAL production engine (not case object)
         - Compare engine output to expected outcomes
         - Include negative-control tests (tests FAIL if engine wrong)
         - Run full regression suite
Output: Test results (all pass or halt)
        TestMetrics with actual counts, execution times, raw output
State transition: → SUPERVISOR_APPROVED
Failure mode: Tests fail, regression tests fail → PIPELINE_HALT

STAGE 8: SUPERVISOR APPROVAL
──────────────────────────────
Input: Case with all stages complete
Process: Supervisor review:
         - Verify source authenticity
         - Confirm evidence extraction integrity
         - Review engine outputs
         - Approve or reject case
Output: Approval record
Status: SUPERVISOR_APPROVED
Failure mode: Supervisor rejects case → case archived, not promoted


================================================================================
PIPELINE STATES
================================================================================

Each case transitions through explicit states:

1. DISCOVERED
   - Case candidate identified from catalog
   - Ready for source retrieval
   - May be rejected here if source unavailable

2. SOURCE_RETRIEVED
   - Source document located and accessed
   - RetrievalRecord created
   - May proceed to verification or halt

3. SOURCE_VERIFIED
   - Source authenticity confirmed
   - Metadata verified against official sources
   - Archive record created
   - No fabrication allowed (all fields verified or empty)

4. EVIDENCE_EXTRACTED
   - Exact evidence text extracted from source
   - Locators recorded (page, section, paragraph)
   - Transformation type explicitly marked
   - Curator interpretation separated from quotation

5. READY_FOR_ENGINE
   - Case prepared for engine evaluation
   - No hard-coded decisions
   - Only verified scope and evidence

6. ENGINE_VALIDATED
   - Engine evaluated case
   - Assertions, applicability, confidence assigned
   - Output recorded with timestamp
   - Compared to expected outcomes

7. TEST_VALIDATED
   - Integration tests executed
   - Tests pass (or case halts)
   - Regression suite passes
   - Raw output recorded with exact counts

8. SUPERVISOR_APPROVED
   - Final state
   - Case approved for production use
   - Ready for deployment


NO STATE MAY BE SKIPPED.
NO CASE MAY REGRESS TO EARLIER STATE.


================================================================================
MANDATORY VERIFICATION GATES
================================================================================

GATE 1: Source Exists
  Check: Source document is retrievable
  Action: If not → PIPELINE_HALT with SOURCE_NOT_FOUND
  
GATE 2: Source Verified
  Check: Metadata verified, archive record created, no fabrication
  Action: If not → PIPELINE_HALT with SOURCE_NOT_VERIFIED
  
GATE 3: Evidence Supports Claim
  Check: Extracted evidence actually supports the assertion
  Action: If not → PIPELINE_HALT with EVIDENCE_NOT_VERBATIM
  
GATE 4: No Hard-Coded Decisions
  Check: Case contains only scope and evidence, not assertions
  Action: If found → PIPELINE_HALT with METADATA_FABRICATED
  
GATE 5: Engine Produces Output
  Check: Engine successfully processes case
  Action: If error → PIPELINE_HALT with ENGINE_EVALUATION_FAILED
  
GATE 6: Integration Tests Pass
  Check: All tests pass (including negative controls)
  Action: If fail → PIPELINE_HALT with TEST_INTEGRATION_FAILED
  
GATE 7: Regression Suite Passes
  Check: All existing tests still pass
  Action: If fail → PIPELINE_HALT with REGRESSION_FAILED
  
GATE 8: Report Metrics Match Artifacts
  Check: Reported counts match actual files
  Action: If not → PIPELINE_HALT with REPORT_VALIDATION_FAILED


================================================================================
DATA FLOW: FROM DISCOVERY TO APPROVAL
================================================================================

Candidate discovered
    ↓
Source retrieval request
    ↓ (if source found)
RetrievalRecord created
    ↓
Source verification module invoked
    ↓ (if verified)
VerificationRecord marked VERIFIED
    ↓
Evidence extraction from source
    ↓ (if supports claim)
EvidenceQuote with locators created
    ↓
Case prepared for engine (no hard-coded logic)
    ↓
Production engine invoked
    ↓
Engine output (assertions, applicability, confidence)
    ↓
Expected outcomes (independently curated) compared
    ↓
Integration tests generated
    ↓
Tests executed (including negative controls)
    ↓ (if all pass)
Regression suite executed
    ↓ (if all pass)
Report generated with exact metrics
    ↓
Supervisor review
    ↓ (if approved)
SUPERVISOR_APPROVED state
    ↓
Case ready for production deployment


================================================================================
CASE OBJECT STRUCTURE
================================================================================

A Gold Case in READY_FOR_ENGINE state contains:

VERIFIED INPUTS (from VerificationRecord):
  - bibliographic_metadata (complete, verified)
  - retrieval_record (method, date, path)
  - archive_record (archive.org, PDF, or repo link)
  - evidence_quotes (with exact locators)

SCOPE (ValidationUnit):
  - taxon
  - plant_part
  - preparation details
  - dosage form (if applicable)

INDEPENDENT EXPECTED OUTCOMES:
  - assertion_type (expected)
  - assertion_state (expected)
  - extraction_confidence (expected)
  - applicability_by_domain (expected)
  - expected_warnings (expected)

MUST NOT CONTAIN:
  - applicability decisions (will be computed by engine)
  - assertion classifications (will be computed by engine)
  - confidence assignments (will be computed by engine)
  - precedence resolutions (will be computed by engine)
  - fabricated metadata
  - hard-coded logic for decision-making


================================================================================
REPORT GENERATION
================================================================================

Reports generated at final stage must include:

1. VERIFIED FACTS SECTION
   - Source metadata (from VerificationRecord)
   - Retrieval details (method, date, by whom)
   - Archive location (archive.org link, PDF path)
   - Evidence locators (page, section, paragraph)
   
2. ENGINE OUTPUTS SECTION
   - Assertions extracted by engine
   - Applicability determined by engine
   - Confidence assigned by engine
   - Warnings detected by engine
   
3. INTEGRATION TEST RESULTS SECTION
   - Raw test output (not summary)
   - Exact test counts (methods, collected, executed, passed)
   - Test execution timestamp
   - Negative-control test results
   
4. REGRESSION TEST RESULTS SECTION
   - Raw regression output (not summary)
   - All existing test files executed
   - All tests passed or PIPELINE_HALT
   - Execution timestamp
   
5. FILE METRICS SECTION
   - Actual line counts (not placeholders)
   - SHA-256 hashes (real, not fabricated)
   - File sizes
   - Modification timestamps
   
6. METRICS VALIDATION SECTION
   - Verification that reported metrics match artifacts
   - Checksum verification
   - Timestamp verification
   - No approximations or placeholders


================================================================================
ERROR HANDLING AND HALTS
================================================================================

When any stage fails:

1. Pipeline halts immediately
2. Halt record is created with:
   - Current state
   - Error type (SOURCE_NOT_FOUND, SOURCE_NOT_VERIFIED, etc.)
   - Message (human-readable)
   - Evidence (technical details)
   - Timestamp
   
3. Case is NOT promoted to next state
4. Case is marked with halt status
5. Generation does NOT continue
6. Case remains in SOURCE_VERIFICATION_HOLD if source retrieval fails
7. Supervisor must address halt before proceeding

Example halt flow:

  Case discovered → SOURCE_RETRIEVED
    ↓
  Source retrieval attempted
    ↓ (URL not found)
  PIPELINE_HALT (SOURCE_NOT_FOUND)
  ├─ state: SOURCE_RETRIEVED
  ├─ error: SOURCE_NOT_FOUND
  ├─ message: "Cochrane URL https://... not accessible"
  ├─ evidence: {"http_status": 404, "accessed": "2026-07-30T14:30:00Z"}
  └─ timestamp: 2026-07-30T14:30:00Z
  
  Case remains in SOURCE_RETRIEVED state
  Supervisor provides verified source → case resumes


================================================================================
PIPELINE GUARANTEES
================================================================================

When properly enforced, this pipeline guarantees:

✓ SOURCE AUTHENTICITY
  Every source must be verified against official records.
  No metadata is fabricated.
  
✓ EVIDENCE INTEGRITY
  Evidence must come from actual source document.
  Locators must be precise and verifiable.
  Transformation (VERBATIM vs PARAPHRASE) must be explicit.
  
✓ DECISION INTEGRITY
  Applicability, assertions, confidence are computed by engine.
  No hard-coded decisions in cases.
  
✓ TEST VALIDITY
  Tests invoke real production engine.
  Tests include negative controls (fail if engine wrong).
  Regression suite passes.
  
✓ REPRODUCIBILITY
  Same verified source → same case generation (deterministic)
  Same case → same engine output (engine is deterministic)
  Same output → same test results (tests are deterministic)
  
✓ AUDITABILITY
  Every stage has explicit record (StateTransition, VerificationRecord)
  Timestamps on all records
  Verifier/retriever identity recorded
  All decisions traceable to source or engine


================================================================================
IMPLEMENTATION CHECKLIST
================================================================================

Pipeline components to implement:

✓ State Machine (gold_case_pipeline_state_machine.py)
  - PipelineState enum with 8 states
  - StateTransition records
  - GoldCasePipelineState class
  - require_state() validation
  
✓ Source Verification Module (source_verification_module.py)
  - BibliographicMetadata (complete, no fabrication)
  - RetrievalRecord (method, date, path)
  - ArchiveRecord (archive.org, PDF, repo)
  - EvidenceQuote (with locators)
  - VerificationRecord (full verification)
  - submit_verification() with validation
  
✓ Report Validator (report_validator.py)
  - calculate_file_metrics() (actual line counts, SHA-256)
  - FileMetrics dataclass
  - TestMetrics validation
  - RegressionTestMetrics validation
  - ReportIntegrityValidator class
  
✓ Integration Test Builder (integration_test_builder.py)
  - generate_case_integration_test_file()
  - Tests invoke real engine modules
  - ExpectedEngineOutput specification
  - Negative-control test generation
  
✓ Updated Case Generator
  - Use state machine for transitions
  - Check verification before proceeding
  - Remove hard-coded logic
  - Call integration test builder
  - Invoke report validator
  - Record all metrics with real values
  
✓ Regression Framework
  - Wrapper to execute existing tests
  - Capture raw output
  - Validate metrics
  - Report failures as pipeline halts


================================================================================
CONCLUSION
================================================================================

This redesigned pipeline makes it IMPOSSIBLE to generate scientifically
invalid Gold Cases. Every stage is mandatory. Every decision is verified
or engine-computed. Every report is validated against artifacts.

The pipeline enforces integrity at the architecture level, not at the
case level. No case object can sneak past the verification gates.

When a verified source is provided, Case 008 can be completed automatically
using this pipeline without modifying the architecture.

The objective is achieved: The pipeline is incapable of generating
scientifically invalid Gold Cases in the future.
"""
