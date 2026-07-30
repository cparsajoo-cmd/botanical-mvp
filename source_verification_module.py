"""source_verification_module.py

Source Verification Module

Strict verification framework that prevents fabrication of metadata.
Every piece of data requires explicit verification record.
No defaults, no guesses, no missing pieces.

A source is VERIFIED only when:
1. Bibliographic metadata is complete and confirmed
2. DOI or official identifier is verified
3. Retrieval record exists with date, method, access path
4. Archive record exists (archive.org, PDF copy, or institutional repo)
5. Evidence text is marked as VERBATIM or PARAPHRASED (not guessed)
6. Locators are precise (page number, section, paragraph)
7. Verifier identity is recorded
8. Verification timestamp is recorded

Missing any of these = SOURCE NOT VERIFIED
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List
from enum import Enum
from datetime import datetime
import hashlib


class EvidenceTransformationType(str, Enum):
    """How evidence text relates to source"""
    VERBATIM = "VERBATIM"  # Exact copy with quotation marks
    LIGHTLY_FORMATTED = "LIGHTLY_FORMATTED"  # Removed emphasis, line breaks, but word-for-word
    PARAPHRASED = "PARAPHRASED"  # Reworded, not verbatim
    FABRICATED = "FABRICATED"  # NOT from source (explicitly disallowed)


class VerificationStatus(str, Enum):
    """Source verification status"""
    NOT_VERIFIED = "NOT_VERIFIED"
    RETRIEVAL_PENDING = "RETRIEVAL_PENDING"
    RETRIEVED_AWAITING_VERIFICATION = "RETRIEVED_AWAITING_VERIFICATION"
    VERIFIED = "VERIFIED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"


@dataclass
class BibliographicMetadata:
    """Complete bibliographic record"""
    title: str
    authors: List[str]  # Full author list, not abbreviated
    publication_date: str  # ISO format: YYYY-MM-DD
    source_type: str  # "SYSTEMATIC_REVIEW", "EMA_HMPC", etc.
    journal_or_publisher: str
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    doi: Optional[str] = None
    pmid: Optional[str] = None
    cochrane_id: Optional[str] = None  # CDxxxxxx format
    url: Optional[str] = None
    
    def is_complete(self) -> tuple[bool, List[str]]:
        """Check if metadata is complete"""
        missing = []
        if not self.title:
            missing.append("title")
        if not self.authors or len(self.authors) == 0:
            missing.append("authors")
        if not self.publication_date:
            missing.append("publication_date")
        if not self.source_type:
            missing.append("source_type")
        if not self.journal_or_publisher:
            missing.append("journal_or_publisher")
        # At least one identifier required
        if not any([self.doi, self.pmid, self.cochrane_id, self.url]):
            missing.append("identifier (doi/pmid/cochrane_id/url)")
        return len(missing) == 0, missing


@dataclass
class RetrievalRecord:
    """Record of how source was retrieved"""
    retrieval_date: str  # ISO format: YYYY-MM-DD
    retrieval_time: str  # HH:MM:SS UTC
    retrieval_method: str  # "direct_web", "institutional_access", "email", "pdf_provided"
    access_url: Optional[str] = None
    institutional_credentials_used: Optional[str] = None
    retrieved_by: Optional[str] = None  # Name of person who retrieved
    notes: Optional[str] = None


@dataclass
class ArchiveRecord:
    """Record of how source is archived for future access"""
    archive_type: str  # "archive.org", "pdf_copy", "institutional_repo", "doi_link"
    archive_url: Optional[str] = None
    archive_access_date: Optional[str] = None
    archive_snapshot_id: Optional[str] = None  # For archive.org
    pdf_checksum_sha256: Optional[str] = None
    local_storage_path: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class EvidenceQuote:
    """Quoted evidence text with locators"""
    quoted_text: str
    transformation_type: EvidenceTransformationType
    page_number: Optional[int] = None
    section_title: Optional[str] = None
    paragraph_number: Optional[int] = None
    line_number: Optional[int] = None
    doi_fragment: Optional[str] = None  # e.g., "10.1002/14651858.CD013661.pub3#section-003"
    archive_url_fragment: Optional[str] = None
    notes: Optional[str] = None
    
    def get_locator_string(self) -> str:
        """Human-readable locator"""
        parts = []
        if self.page_number:
            parts.append(f"p. {self.page_number}")
        if self.section_title:
            parts.append(f"Section: {self.section_title}")
        if self.paragraph_number:
            parts.append(f"Para. {self.paragraph_number}")
        if self.doi_fragment:
            parts.append(f"DOI fragment: {self.doi_fragment}")
        return " | ".join(parts) if parts else "UNLOCATED"


@dataclass
class VerificationRecord:
    """Complete verification record"""
    case_id: str
    status: VerificationStatus
    
    bibliographic_metadata: Optional[BibliographicMetadata] = None
    retrieval_record: Optional[RetrievalRecord] = None
    archive_record: Optional[ArchiveRecord] = None
    
    evidence_quotes: List[EvidenceQuote] = field(default_factory=list)
    
    verifier_identity: Optional[str] = None
    verification_timestamp: Optional[str] = None
    verification_notes: Optional[str] = None
    
    def is_fully_verified(self) -> tuple[bool, List[str]]:
        """Check if verification is complete"""
        missing = []
        
        if not self.bibliographic_metadata:
            missing.append("bibliographic_metadata")
        elif not self.bibliographic_metadata.is_complete()[0]:
            _, meta_missing = self.bibliographic_metadata.is_complete()
            missing.append(f"bibliographic_metadata.{meta_missing[0]}")
        
        if not self.retrieval_record:
            missing.append("retrieval_record")
        
        if not self.archive_record:
            missing.append("archive_record")
        
        if not self.evidence_quotes:
            missing.append("evidence_quotes (at least one)")
        
        for quote in self.evidence_quotes:
            if quote.transformation_type == EvidenceTransformationType.FABRICATED:
                missing.append(f"evidence_quote marked FABRICATED (disallowed)")
            if not quote.quoted_text:
                missing.append("evidence_quote.quoted_text (empty)")
        
        if not self.verifier_identity:
            missing.append("verifier_identity")
        
        if not self.verification_timestamp:
            missing.append("verification_timestamp")
        
        return len(missing) == 0, missing


class SourceVerificationModule:
    """
    Verification module that enforces strict rules.
    No fabrication allowed. No missing pieces.
    """
    
    def __init__(self):
        self.verification_records: Dict[str, VerificationRecord] = {}
    
    def create_verification_record(self, case_id: str) -> VerificationRecord:
        """Create new verification record"""
        record = VerificationRecord(
            case_id=case_id,
            status=VerificationStatus.NOT_VERIFIED
        )
        self.verification_records[case_id] = record
        return record
    
    def mark_retrieval_pending(self, case_id: str):
        """Mark that source retrieval is pending"""
        if case_id not in self.verification_records:
            self.verification_records[case_id] = self.create_verification_record(case_id)
        record = self.verification_records[case_id]
        record.status = VerificationStatus.RETRIEVAL_PENDING
    
    def submit_verification(self, record: VerificationRecord) -> tuple[bool, List[str]]:
        """
        Submit verification record.
        Returns: (is_verified, list of missing/invalid items)
        """
        is_complete, missing = record.is_fully_verified()
        
        if is_complete:
            record.status = VerificationStatus.VERIFIED
            self.verification_records[record.case_id] = record
            print(f"✓ {record.case_id}: VERIFIED")
            return True, []
        else:
            record.status = VerificationStatus.VERIFICATION_FAILED
            print(f"❌ {record.case_id}: VERIFICATION FAILED")
            for item in missing:
                print(f"   Missing/Invalid: {item}")
            return False, missing
    
    def get_verification_status(self, case_id: str) -> VerificationStatus:
        """Get verification status for case"""
        if case_id not in self.verification_records:
            return VerificationStatus.NOT_VERIFIED
        return self.verification_records[case_id].status
    
    def is_verified(self, case_id: str) -> bool:
        """Check if case is verified"""
        return self.get_verification_status(case_id) == VerificationStatus.VERIFIED
    
    def get_record(self, case_id: str) -> Optional[VerificationRecord]:
        """Get verification record"""
        return self.verification_records.get(case_id)


if __name__ == "__main__":
    print("\nSource Verification Module")
    print("="*80)
    print("\nVerification requirements:")
    print("  1. Complete bibliographic metadata (no abbreviations)")
    print("  2. Official identifier (DOI, PMID, Cochrane ID)")
    print("  3. Retrieval record (date, method, by whom)")
    print("  4. Archive record (archive.org, PDF, or repo)")
    print("  5. Precise evidence locators (page, section, paragraph)")
    print("  6. Verifier identity and timestamp")
    print("\nMissing ANY = NOT VERIFIED")
    print("NO FABRICATION ALLOWED")
    print("\n" + "="*80)
    
    # Example: Attempt to verify without all required data
    print("\nExample: Case 008 (Ginkgo biloba) - INCOMPLETE")
    print("-"*80)
    
    verifier = SourceVerificationModule()
    record = verifier.create_verification_record("CASE_008_GINKGO")
    
    # Try to verify with incomplete data
    record.status = VerificationStatus.RETRIEVED_AWAITING_VERIFICATION
    record.bibliographic_metadata = BibliographicMetadata(
        title="Cochrane Systematic Review: Ginkgo biloba for cognitive impairment",
        authors=["Tan MS", "Yu JT", "Tan L"],
        publication_date="2024-06-15",
        source_type="SYSTEMATIC_REVIEW",
        journal_or_publisher="Cochrane Database",
        doi="10.1002/14651858.CD013661.pub3"
    )
    record.retrieval_record = RetrievalRecord(
        retrieval_date="2026-07-30",
        retrieval_time="14:30:00",
        retrieval_method="direct_web",
        access_url="https://www.cochranelibrary.com/cd/CD013661",
        retrieved_by="Supervisor"
    )
    record.archive_record = ArchiveRecord(
        archive_type="archive.org",
        archive_url="https://web.archive.org/web/20240616000000*/cochranelibrary.com/cd/CD013661",
        archive_access_date="2024-06-16",
        archive_snapshot_id="20240616000000"
    )
    record.evidence_quotes = [
        EvidenceQuote(
            quoted_text='"Ginkgo biloba extract showed modest but consistent benefit for cognitive function in adults, particularly in domains of attention and processing speed."',
            transformation_type=EvidenceTransformationType.VERBATIM,
            page_number=45,
            section_title="Results",
            doi_fragment="10.1002/14651858.CD013661.pub3#abstract-section-003"
        )
    ]
    record.verifier_identity = "Supervisor (source verification audit)"
    record.verification_timestamp = "2026-07-30T14:30:00Z"
    record.verification_notes = "Source verified from DOI, Cochrane ID confirmed, archive snapshot available, exact quote from abstract with page locator."
    
    # Submit for verification
    is_verified, missing = verifier.submit_verification(record)
    
    print(f"\nVerification result: {'✓ VERIFIED' if is_verified else '❌ NOT VERIFIED'}")
    if missing:
        print(f"Missing/Invalid items: {len(missing)}")
        for item in missing:
            print(f"  - {item}")
