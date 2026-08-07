1. Final Verification Audit
Audit date: 2026-08-07
Active Gold Cases: 22 (Case 002 abandoned; active IDs are 001 and 003–023)
Decision: FREEZE BLOCKED
The project was audited beyond gold_corpus, including Gold Cases, validation, benchmark/calibration, E2E validation, retrieval tests, Evidence Direction, source registry, scientific/regulatory corpora, synthetic fixtures, evidence interpretation, scoring, and safety/regulatory/eligibility gates.
Key findings:
All 22 active cases remain ground_truth_status=REFERENCE_CURATED_DEVELOPMENT, locked=false, and internal_scientific_curation_pending_external_expert_review in the authoritative manifest. Therefore none can honestly be promoted to VERIFIED/LOCKED by this audit alone.
Source-existence/identifier checks succeeded for the declared critical references reviewed in this pass. One real metadata error was corrected: Case 003 Kazemi et al. had document_date=2024-08-01; the article is Epub 2024-08-04 (PMID 39106912; DOI 10.1016/j.ctim.2024.103071). No claim/direction/score/production rule was changed.
Seven E2E retrieval snapshots exist (006, 016, 018, 019, 020, 021, 022); 15 active cases have no frozen E2E retrieval snapshot.
The seven existing snapshot files freeze question, candidate_pool, and records, but do not encode an explicit expected_gate_outcome or expected_final_decision. Therefore gate/decision baselines are not frozen even for the pilot seven.
The existing E2E pilot itself reports 9/9 critical-source retrieval recall, but evidence-direction accuracy 1/9 and a serious-safety false negative in Case 006. These are valid blockers/diagnostics and were not tuned away.
Synthetic validation fixtures are physically separated under synthetic_validation_fixtures/ and have their own pipeline test. No synthetic record was added to the Gold Corpus in this phase.
Repeated source URLs exist in corpus extensions, but inspection shows many are item-level records from the same authoritative monograph/table. URL reuse alone is therefore not treated as duplicate evidence. Aggregate/per-item files must nevertheless continue to be excluded from additive performance counting.
Regression after the only metadata correction: 203 passed on the targeted Gold/manifest/E2E/calibration/benchmark/synthetic validation suite.
2. Freeze Readiness Matrix for all 22 Cases
The machine-readable matrix is provided as FREEZE_READINESS_MATRIX.csv. Summary: 0/22 Freeze Ready under the requested v1.0 rules, because external review/locking is pending for all cases and complete frozen E2E gate/decision baselines do not exist.
Case
Source
Ground Truth
Direction
Retrieval
Gate
Decision
External Review
Lock
Freeze Ready
001
Verified source/ID
Development
INTERNAL CURATED (positive)
MISSING
NOT FROZEN
NOT FROZEN
PENDING
UNLOCKED
NO
003
Verified source/ID
Development
INTERNAL CURATED (mixed)
MISSING
NOT FROZEN
NOT FROZEN
PENDING
UNLOCKED
NO
004
Verified source/ID
Development
INTERNAL CURATED (negative)
MISSING
NOT FROZEN
NOT FROZEN
PENDING
UNLOCKED
NO
005
Verified source/ID
Development
INTERNAL CURATED (unclear)
MISSING
NOT FROZEN
NOT FROZEN
PENDING
UNLOCKED
NO
006
Verified source/ID
Development
INTERNAL CURATED (positive)
FROZEN
NOT FROZEN
NOT FROZEN
PENDING
UNLOCKED
NO
007
Verified source/ID
Development
INTERNAL CURATED (positive)
MISSING
NOT FROZEN
NOT FROZEN
PENDING
UNLOCKED
NO
008
Verified source/ID
Development
INTERNAL CURATED (positive)
MISSING
NOT FROZEN
NOT FROZEN
PENDING
UNLOCKED
NO
009
Verified source/ID
Development
INTERNAL CURATED (positive)
MISSING
NOT FROZEN
NOT FROZEN
PENDING
UNLOCKED
NO
010
Verified source/ID
Development
INTERNAL CURATED (positive)
MISSING
NOT FROZEN
NOT FROZEN
PENDING
UNLOCKED
NO
011
Verified source/ID
Development
INTERNAL CURATED (positive)
MISSING
NOT FROZEN
NOT FROZEN
PENDING
UNLOCKED
NO
012
Verified source/ID
Development
INTERNAL CURATED (positive)
MISSING
NOT FROZEN
NOT FROZEN
PENDING
UNLOCKED
NO
013
Verified source/ID
Development
INTERNAL CURATED (positive)
MISSING
NOT FROZEN
NOT FROZEN
PENDING
UNLOCKED
NO
014
Verified source/ID
Development
INTERNAL CURATED (positive)
MISSING
NOT FROZEN
NOT FROZEN
PENDING
UNLOCKED
NO
015
Verified source/ID
Development
INTERNAL CURATED (positive)
MISSING
NOT FROZEN
NOT FROZEN
PENDING
UNLOCKED
NO
016
Verified source/ID
Development
INTERNAL CURATED (positive)
FROZEN
NOT FROZEN
NOT FROZEN
PENDING
UNLOCKED
NO
017
Verified source/ID
Development
INTERNAL CURATED (positive)
MISSING
NOT FROZEN
NOT FROZEN
PENDING
UNLOCKED
NO
018
Verified source/ID
Development
INTERNAL CURATED (positive)
FROZEN
NOT FROZEN
NOT FROZEN
PENDING
UNLOCKED
NO
019
Verified source/ID
Development
INTERNAL CURATED (positive)
FROZEN
NOT FROZEN
NOT FROZEN
PENDING
UNLOCKED
NO
020
Verified source/ID
Development
INTERNAL CURATED (positive)
FROZEN
NOT FROZEN
NOT FROZEN
PENDING
UNLOCKED
NO
021
Verified source/ID
Development
INTERNAL CURATED (conflicting)
FROZEN
NOT FROZEN
NOT FROZEN
PENDING
UNLOCKED
NO
022
Verified source/ID
Development
INTERNAL CURATED (mixed)
FROZEN
NOT FROZEN
NOT FROZEN
PENDING
UNLOCKED
NO
023
Verified source/ID
Development
INTERNAL CURATED (null)
MISSING
NOT FROZEN
NOT FROZEN
PENDING
UNLOCKED
NO
3. UNVERIFIED / PENDING / DEVELOPMENT items
All 22 active cases: REFERENCE_CURATED_DEVELOPMENT.
All 22 active cases: reviewer state is internal_scientific_curation_pending_external_expert_review.
All 22 active cases: locked=false.
Cases 001, 003, 004, 005, 006: case provenance contains explicit VerificationStatus.UNVERIFIED fields; these must not be silently converted to VERIFIED.
Case 005: its own case documentation explicitly labels trial-level direct taxonomy comparability, preparation equivalence, and population equivalence as UNVERIFIED.
Case 006: its case documentation explicitly states lower-confidence/unverified source elements remain; the E2E pilot also reports a serious-safety false negative.
Case 023 quality record: explicit freeze_blocker = external expert review and lock still pending.
UNKNOWN values appearing in production applicability/market code are not by themselves Gold Case verification states; they were not bulk-rewritten.
4. E2E Baseline Coverage
Frozen retrieval snapshots: 7/22 = 31.8% (006, 016, 018, 019, 020, 021, 022).
Missing frozen retrieval snapshots: 15/22 = 68.2% (001, 003, 004, 005, 007–015, 017, 023).
Explicit frozen expected gate outcome inside snapshot files: 0/22.
Explicit frozen expected final decision inside snapshot files: 0/22.
The manifest does contain expected safety/regulatory/direction fields, but several final-decision entries explicitly say they are derivable/not frozen or not applicable under protocol v0.3; this is not equivalent to a frozen E2E decision baseline.
5. Calibration vs Holdout Leakage Audit
BLOCKER CONFIRMED.
human_evidence_direction_calibration_v1.json and human_evidence_direction_benchmark.json overlap on 12 PMIDs:
11308434, 11744467, 11939866, 17940604, 18482867, 19017911, 19593179, 19609225, 20347389, 21173411, 21775910, 27912875
The repository report explains why: Calibration V1 was built as a combined 24-record set containing the original 12-record benchmark plus a disjoint 12-record extension. That may be valid as a calibration history, but it means the named benchmark is not a holdout from calibration. Under the requested Freeze rule (“calibration dataset completely separate from holdout benchmark”), v1.0 cannot be frozen with these roles unchanged.
External Validation V2 is disjoint from both in the identifier audit, but the project currently does not redefine the original benchmark as calibration-only and a separate frozen holdout as the authoritative holdout. No dataset labels were silently reassigned in this phase.
6. Freeze Blockers
External expert review is pending for all 22 active cases.
All 22 cases remain development ground truth and unlocked.
Frozen E2E retrieval baseline exists for only 7/22 cases.
Frozen gate and final-decision baselines are not explicitly encoded for any active case snapshot.
Calibration V1 and the named benchmark overlap on 12 PMIDs, violating the required calibration-vs-holdout separation.
Existing E2E pilot exposes unresolved production behavior: evidence-direction baseline 1/9 across the mixed pilot vocabulary and a serious-safety false negative for Case 006. These findings must not be tuned against holdout cases.
Explicit UNVERIFIED provenance/equivalence items remain in Cases 001/003/004/005/006, with especially material scope-equivalence caveats in Case 005.
What was not done: no new Gold Case, no new corpus extension, no synthetic Gold data, no benchmark-specific rule, no scoring/gate production change, no forced VERIFIED status, no lock/changelog v1.0 entry.
7. Final Decision
FREEZE BLOCKED
The corpus is not ready to be declared Gold Corpus v1.0 under the requested rules. The blockers are governance/external review, incomplete E2E frozen baselines, missing explicit gate/decision baselines, and calibration/holdout role leakage. Because these cannot be scientifically resolved by a metadata-only patch, the project was not falsely locked or frozen.
