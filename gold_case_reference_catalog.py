"""gold_case_reference_catalog.py

Repository-backed curated reference catalog for Gold Case candidate discovery.

Discovery strategy: PRIMARY (catalog-backed) → FALLBACK (live search)
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict
from pathlib import Path
import json


@dataclass
class CatalogEntry:
    """A curated candidate in the repository catalog"""
    catalog_id: str
    taxon: str
    plant_part: Optional[str]
    target_domain: str
    proposed_assertion_type: str
    proposed_assertion_state: str = "PRESENT"
    source_reference_id: str = ""
    source_type: str = ""
    source_title: str = ""
    source_urls: List[str] = field(default_factory=list)
    curator_comment: str = ""
    date_added: str = ""
    last_verified: str = ""
    verification_status: str = "CURATED"
    priority: int = 1
    
    def to_dict(self) -> Dict:
        return {
            "catalog_id": self.catalog_id,
            "taxon": self.taxon,
            "plant_part": self.plant_part,
            "target_domain": self.target_domain,
            "proposed_assertion_type": self.proposed_assertion_type,
            "proposed_assertion_state": self.proposed_assertion_state,
            "source_reference_id": self.source_reference_id,
            "source_type": self.source_type,
            "source_title": self.source_title,
            "source_urls": self.source_urls,
            "curator_comment": self.curator_comment,
            "date_added": self.date_added,
            "last_verified": self.last_verified,
            "verification_status": self.verification_status,
            "priority": self.priority,
        }


class GoldCaseReferenceCatalog:
    """Repository-backed curated catalog of candidates"""
    
    CATALOG: List[CatalogEntry] = [
        # INDICATION_EVIDENCE
        CatalogEntry(
            catalog_id="CATALOG_001_GINKGO_BILOBA_INDICATION",
            taxon="Ginkgo biloba L.",
            plant_part="leaf",
            target_domain="INDICATION_EVIDENCE",
            proposed_assertion_type="SUPPORTS_INDICATION",
            source_reference_id="COCHRANE_CD013661_2026",
            source_type="SYSTEMATIC_REVIEW",
            source_title="Cochrane Systematic Review on Ginkgo biloba for cognitive impairment",
            source_urls=["https://www.cochranelibrary.com/cd/CD013661"],
            curator_comment="First INDICATION_EVIDENCE case",
            date_added="2026-07-30",
            last_verified="2026-07-30",
            verification_status="CURATED",
            priority=1,
        ),
        CatalogEntry(
            catalog_id="CATALOG_002_HYPERICUM_PERFORATUM_INDICATION",
            taxon="Hypericum perforatum L.",
            plant_part="herb",
            target_domain="INDICATION_EVIDENCE",
            proposed_assertion_type="SUPPORTS_INDICATION",
            source_reference_id="COCHRANE_CD000448_2025",
            source_type="SYSTEMATIC_REVIEW",
            source_title="Cochrane Review: Hypericum for Depression",
            source_urls=["https://www.cochranelibrary.com/cd/CD000448"],
            curator_comment="Depression evidence with contradictions",
            date_added="2026-07-30",
            last_verified="2026-07-30",
            verification_status="CURATED",
            priority=2,
        ),
        
        # SAFETY
        CatalogEntry(
            catalog_id="CATALOG_003_KAVA_PIPER_SAFETY",
            taxon="Piper methysticum Forst. f.",
            plant_part="rhizome",
            target_domain="SAFETY",
            proposed_assertion_type="CONTRAINDICATION",
            source_reference_id="EMA_HMPC_KAVA_2015",
            source_type="EMA_HMPC",
            source_title="EMA Public Statement on Kava hepatotoxicity",
            source_urls=["https://www.ema.europa.eu"],
            curator_comment="Hepatotoxicity contraindication",
            date_added="2026-07-30",
            last_verified="2026-07-30",
            verification_status="CURATED",
            priority=1,
        ),
        
        # IDENTITY_QUALITY
        CatalogEntry(
            catalog_id="CATALOG_004_ECHINACEA_SPECIES_IDENTITY",
            taxon="Echinacea species",
            plant_part="root",
            target_domain="IDENTITY_QUALITY",
            proposed_assertion_type="IDENTITY_CONFIRMATION",
            source_reference_id="EMA_HMPC_ECHINACEA_2021",
            source_type="EMA_HMPC",
            source_title="EMA/HMPC Assessment: Echinacea species identity",
            source_urls=["https://www.ema.europa.eu/human"],
            curator_comment="Species confusion documented",
            date_added="2026-07-30",
            last_verified="2026-07-30",
            verification_status="CURATED",
            priority=1,
        ),
        CatalogEntry(
            catalog_id="CATALOG_005_PANAX_SPECIES_IDENTITY",
            taxon="Panax species",
            plant_part="root",
            target_domain="IDENTITY_QUALITY",
            proposed_assertion_type="IDENTITY_CONFIRMATION",
            source_reference_id="PH_EUR_PANAX_2026",
            source_type="PHARMACOPOEIA",
            source_title="European Pharmacopoeia: Panax species",
            source_urls=["https://pheur.edqm.eu"],
            curator_comment="Asian vs American ginseng differentiation",
            date_added="2026-07-30",
            last_verified="2026-07-30",
            verification_status="CURATED",
            priority=2,
        ),
        
        # PREPARATION_SPEC
        CatalogEntry(
            catalog_id="CATALOG_006_PASSIFLORA_INCARNATA_PREP",
            taxon="Passiflora incarnata L.",
            plant_part="herb",
            target_domain="PREPARATION_SPEC",
            proposed_assertion_type="PREPARATION_SPECIFICATION",
            source_reference_id="EMA_HMPC_PASSIFLORA_2019",
            source_type="EMA_HMPC",
            source_title="EMA/HMPC Assessment: Passiflora incarnata herba",
            source_urls=["https://www.ema.europa.eu/human"],
            curator_comment="Traditional use with defined preparation",
            date_added="2026-07-30",
            last_verified="2026-07-30",
            verification_status="CURATED",
            priority=1,
        ),
    ]
    
    @classmethod
    def query_by_domain(cls, domain: str, priority_limit: int = 3) -> List[CatalogEntry]:
        """Query catalog for candidates in a domain"""
        matching = [
            e for e in cls.CATALOG
            if e.target_domain == domain and e.priority <= priority_limit
        ]
        return sorted(matching, key=lambda e: e.priority)
    
    @classmethod
    def print_catalog(cls):
        """Print catalog overview"""
        print("\n" + "="*80)
        print("REPOSITORY-BACKED GOLD CASE REFERENCE CATALOG")
        print("="*80 + "\n")
        print(f"Total entries: {len(cls.CATALOG)}\n")
        
        by_domain = {}
        for entry in cls.CATALOG:
            if entry.target_domain not in by_domain:
                by_domain[entry.target_domain] = []
            by_domain[entry.target_domain].append(entry)
        
        for domain in sorted(by_domain.keys()):
            entries = by_domain[domain]
            print(f"{domain} ({len(entries)} candidates)")
            for entry in sorted(entries, key=lambda e: e.priority):
                print(f"  P{entry.priority}: {entry.taxon} ({entry.source_type})")
            print()


class CatalogFirstDiscovery:
    """
    Discovery strategy: PRIMARY (catalog) → FALLBACK (live search)
    
    Guarantees reproducibility and stability.
    """
    
    def __init__(self, live_search_fn=None):
        self.catalog = GoldCaseReferenceCatalog
        self.live_search = live_search_fn or self._stub_live_search
    
    def discover(self, domain: str, candidate_limit: int = 3) -> List[CatalogEntry]:
        """
        Discover candidates: Primary (catalog) → Fallback (live search)
        """
        print(f"\n[Discovery] PRIMARY: Querying repository-backed catalog...")
        print(f"[Discovery] Domain: {domain}\n")
        
        # STEP 1: Query catalog (PRIMARY)
        candidates = self.catalog.query_by_domain(domain, priority_limit=3)
        candidates = candidates[:candidate_limit]
        
        if candidates:
            print(f"[Discovery] ✓ Found {len(candidates)} candidate(s) in repository catalog")
            for i, c in enumerate(candidates, 1):
                print(f"  {i}. {c.taxon} (P{c.priority}, {c.source_type})")
            return candidates
        
        # STEP 2: Fallback to live search (only if catalog empty)
        print(f"[Discovery] ⚠ No candidates in repository catalog")
        print(f"[Discovery] FALLBACK: Attempting live web search...\n")
        
        live_candidates = self._live_search_fallback(domain)
        
        if live_candidates:
            print(f"[Discovery] ✓ Found {len(live_candidates)} via live search (not in repository)")
            print(f"[Discovery] ⚠ These should be curated and added to catalog\n")
            return live_candidates
        
        print(f"[Discovery] ✗ No candidates found\n")
        return []
    
    def _live_search_fallback(self, domain: str):
        """Fallback to live search only if catalog empty"""
        print(f"  [LiveSearch] Stub: no results")
        return []
    
    def _stub_live_search(self, query: str):
        """Stub live search"""
        return []


if __name__ == "__main__":
    print("\nRepository-Backed Gold Case Reference Catalog")
    print("=============================================\n")
    print("Discovery strategy:")
    print("  1. PRIMARY: Query repository-backed catalog")
    print("  2. FALLBACK: Live web search (only if catalog empty)")
    print()
    print("Guarantees:")
    print("  ✓ Reproducibility (same catalog version → same candidates)")
    print("  ✓ Determinism (no time-dependent behavior)")
    print("  ✓ Stability (results independent of web state)")
    print("  ✓ Auditability (every candidate tracked)\n")
    
    GoldCaseReferenceCatalog.print_catalog()
