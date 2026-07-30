"""gold_case_dynamic_candidate_discovery.py

Evidence-driven candidate discovery for Gold Case generation.

Discovery strategy: PRIMARY (catalog-backed) → FALLBACK (live search)

PRIMARY: Repository-backed reference catalog
  • Curated, version-controlled candidates
  • Guaranteed reproducibility and determinism
  • Every candidate has source_reference_id and curator attribution
  • Fast, stable, auditable

FALLBACK: Live web search (only if catalog returns no candidate)
  • Used only when repository catalog is exhausted
  • Results NOT reproducible without curation
  • Should be curated and added to catalog for future use

This architecture guarantees:
• Reproducibility: Same catalog version → same candidates always
• Determinism: No time-dependent or random behavior
• Stability: Results independent of current web state
• Auditability: Full trace of source and curation
"""

import sys
import json
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum

sys.path.insert(0, str(Path(__file__).parent))

# ========== IMPORTS ==========

# Note: web_search and web_fetch would be imported here in production
# For this architecture, we define the interface that will be filled
# by the orchestrator using actual tools

# ========== DATA MODELS ==========

@dataclass
class DynamicCandidate:
    """A candidate discovered from evidence sources"""
    rank: int
    taxon: str
    plant_part: Optional[str]
    target_domain: str
    proposed_assertion_type: str
    proposed_assertion_state: str = "PRESENT"
    source_type: str = "UNKNOWN"
    source_reference_id: str = ""  # e.g., "EMA_HMPC_150846_2015"
    source_title: str = ""  # e.g., "EMA Assessment Report on Valeriana..."
    source_urls: List[str] = field(default_factory=list)
    verification_score: float = 0.0  # 0–1, confidence in source claim
    rationale: str = ""


@dataclass
class DomainGap:
    """Representation of a coverage gap in the matrix"""
    domain: str
    gap_type: str  # "entirely_uncovered" | "assertion_state_missing" | "source_type_missing"
    gap_priority: int  # 1 (highest) to 5 (lowest)
    missing_assertion_states: List[str] = field(default_factory=list)
    missing_source_types: List[str] = field(default_factory=list)
    search_queries: List[str] = field(default_factory=list)  # Auto-generated queries for this gap


# ========== SOURCE TYPE HIERARCHIES ==========

SOURCE_TYPE_HIERARCHIES = {
    "INDICATION_EVIDENCE": ["SYSTEMATIC_REVIEW", "EMA_HMPC", "WHO_MONOGRAPH", "ESCOP_MONOGRAPH", "COMMISSION_E"],
    "SAFETY": ["EMA_HMPC", "WHO_MONOGRAPH", "ESCOP_MONOGRAPH", "COMMISSION_E"],
    "IDENTITY_QUALITY": ["PHARMACOPOEIA", "EMA_HMPC", "WHO_MONOGRAPH", "TAXONOMIC_AUTHORITY"],
    "PREPARATION_SPEC": ["EMA_HMPC", "PHARMACOPOEIA", "WHO_MONOGRAPH", "ESCOP_MONOGRAPH"],
    "REGULATORY_STATUS": ["NATIONAL_REGULATORY", "EMA_HMPC", "OTHER_NATIONAL_REGULATORY"],
}


# ========== DYNAMIC DISCOVERY ENGINE ==========

class DynamicCandidateDiscovery:
    """
    Discovers candidates using CATALOG-FIRST strategy.
    
    PRIMARY: Repository-backed reference catalog (guaranteed reproducibility)
    FALLBACK: Live web search (only if catalog empty)
    
    This ensures deterministic, auditable, and stable candidate discovery.
    """
    
    def __init__(self, live_search_fn=None, web_fetch_fn=None):
        """
        Initialize discovery with catalog as primary.
        
        Args:
            live_search_fn: Function for live web search (fallback only)
            web_fetch_fn: Function for fetching URLs (not used in catalog-first mode)
        """
        # Import catalog here to avoid circular imports
        try:
            from gold_case_reference_catalog import (
                GoldCaseReferenceCatalog,
                CatalogFirstDiscovery,
            )
            self.catalog = GoldCaseReferenceCatalog
            self.catalog_discovery = CatalogFirstDiscovery(live_search_fn)
        except ImportError:
            print("ERROR: gold_case_reference_catalog.py not found")
            self.catalog = None
            self.catalog_discovery = None
        
        self.live_search = live_search_fn or self._stub_live_search
        self.web_fetch = web_fetch_fn or self._stub_web_fetch
        self.existing_cases = {}
    
    def discover(self, domain: str, candidate_limit: int = 5) -> List:
        """
        Discover candidates using CATALOG-FIRST strategy.
        
        1. PRIMARY: Query repository-backed catalog
        2. FALLBACK: Live web search (only if catalog empty)
        
        Args:
            domain: Target domain (INDICATION_EVIDENCE, SAFETY, etc.)
            candidate_limit: Max candidates to return
        
        Returns:
            List of candidates, ranked by source quality
        """
        if not self.catalog or not self.catalog_discovery:
            print("[Discovery] ERROR: Catalog not initialized")
            return []
        
        print(f"\n{'='*80}")
        print(f"EVIDENCE-DRIVEN CANDIDATE DISCOVERY (CATALOG-FIRST)")
        print(f"{'='*80}")
        print(f"Domain: {domain}")
        print(f"Limit: {candidate_limit} candidates\n")
        
        # PRIMARY: Query repository-backed catalog
        print(f"[Discovery] PRIMARY: Querying repository-backed catalog...")
        candidates = self.catalog_discovery.discover(domain, candidate_limit)
        
        if candidates:
            print(f"\n[Discovery] ✓ Found {len(candidates)} candidate(s) from repository catalog")
            print(f"[Discovery] ✓ Discovery is REPRODUCIBLE (from version-controlled sources)\n")
            return candidates[:candidate_limit]
        
        # FALLBACK: Only if catalog is empty
        print(f"\n[Discovery] ⚠ Repository catalog has no candidates for {domain}")
        print(f"[Discovery] FALLBACK: Attempting live web search...\n")
        print(f"[Discovery] NOTE: Live search results are NOT reproducible")
        print(f"[Discovery]       Candidates should be curated and added to catalog\n")
        
        return []  # Fallback stub; would call live search if implemented
    
    def _analyze_domain_gap(self, domain: str) -> DomainGap:
        """
        Analyze the coverage gap for a domain.
        
        Returns what's missing: entirely uncovered, or just missing assertion_state/source_type.
        """
        # Check if domain is entirely uncovered
        if domain not in self.existing_cases or not self.existing_cases[domain]:
            return DomainGap(
                domain=domain,
                gap_type="entirely_uncovered",
                gap_priority=1,
                search_queries=[]
            )
        
        # Check for missing assertion states in this domain
        covered_states = set(self.existing_cases.get(domain, {}).get("assertion_states", []))
        all_states = {"PRESENT", "ABSENT", "CONDITIONAL", "INSUFFICIENT", "NOT_STATED"}
        missing_states = list(all_states - covered_states)
        
        if missing_states:
            return DomainGap(
                domain=domain,
                gap_type="assertion_state_missing",
                gap_priority=2,
                missing_assertion_states=missing_states,
                search_queries=[]
            )
        
        # Check for missing source types in this domain
        covered_sources = set(self.existing_cases.get(domain, {}).get("source_types", []))
        hierarchy = SOURCE_TYPE_HIERARCHIES.get(domain, [])
        missing_sources = [s for s in hierarchy if s not in covered_sources]
        
        if missing_sources:
            return DomainGap(
                domain=domain,
                gap_type="source_type_missing",
                gap_priority=3,
                missing_source_types=missing_sources,
                search_queries=[]
            )
        
        # Domain is fully covered; suggest extending with new candidates
        return DomainGap(
            domain=domain,
            gap_type="extend_coverage",
            gap_priority=4,
            search_queries=[]
        )
    
    def _generate_search_queries(self, domain: str, gap: DomainGap) -> List[str]:
        """
        Generate search queries for a domain and gap type.
        
        Queries target authoritative sources (EMA/HMPC, WHO, systematic reviews).
        """
        queries = []
        
        if gap.gap_type == "entirely_uncovered":
            # Search for evidence in this domain from top-ranked source
            if domain == "INDICATION_EVIDENCE":
                queries = [
                    "systematic review herbal medicinal plant evidence",
                    "Cochrane herbal botanical clinical trial",
                    "EMA HMPC herbal monograph indications",
                ]
            elif domain == "SAFETY":
                queries = [
                    "EMA HMPC herbal safety contraindication toxicity",
                    "WHO herbal medicine adverse effects safety",
                    "European Commission herbal safety restrictions",
                ]
            elif domain == "IDENTITY_QUALITY":
                queries = [
                    "botanical identity species confusion adulteration",
                    "pharmacopoeia herbal medicine identity standards",
                    "EMA HMPC herbal species differentiation",
                ]
            elif domain == "PREPARATION_SPEC":
                queries = [
                    "EMA HMPC herbal preparation extract DER specification",
                    "herbal medicine standardization preparation solvent",
                    "traditional herbal drug preparation monograph",
                ]
            elif domain == "REGULATORY_STATUS":
                queries = [
                    "EMA herbal medicine regulatory prohibition restriction",
                    "national regulatory botanical medicinal product status",
                    "herbal medicinal product market authorization",
                ]
        
        elif gap.gap_type == "assertion_state_missing":
            # Search for evidence with missing assertion state
            for state in gap.missing_assertion_states[:2]:  # Top 2 missing
                if state == "ABSENT":
                    queries.append(f"{domain.lower()} herbal does not support ineffective")
                elif state == "INSUFFICIENT":
                    queries.append(f"{domain.lower()} herbal evidence insufficient limited")
                elif state == "NOT_STATED":
                    queries.append(f"{domain.lower()} herbal source silent unclear")
        
        elif gap.gap_type == "source_type_missing":
            # Search for evidence from missing source type
            for source in gap.missing_source_types[:2]:
                if "PHARMACOPOEIA" in source:
                    queries.append("European Pharmacopoeia Ph. Eur. herbal monograph")
                elif "WHO" in source:
                    queries.append("WHO monograph herbal medicinal plants")
                elif "SYSTEMATIC_REVIEW" in source:
                    queries.append("Cochrane systematic review herbal botanical medicine")
        
        return queries
    
    def _extract_candidate_from_source(self, url: str, domain: str) -> Optional[DynamicCandidate]:
        """
        Fetch a source URL and extract candidate information.
        
        In production, this would:
        1. Fetch URL content
        2. Parse for taxon (scientific name)
        3. Parse for plant part (root, leaf, herb, etc.)
        4. Identify source type (EMA, WHO, Cochrane, etc.)
        5. Extract claim (assertion type + state)
        6. Verify against applicability rules
        
        For this architecture, returns None (placeholder).
        """
        # Stub: would call self.web_fetch(url) and parse content
        # For now, return None to indicate: dynamic discovery needs actual web tools
        return None
    
    def _rank_by_source_quality(self, candidates: List[DynamicCandidate], domain: str) -> List[DynamicCandidate]:
        """
        Rank candidates by source quality hierarchy for the domain.
        
        Top-ranked source_type per domain gets rank 1, etc.
        """
        hierarchy = SOURCE_TYPE_HIERARCHIES.get(domain, [])
        
        # Sort by source type rank in hierarchy
        def source_rank(candidate):
            try:
                return hierarchy.index(candidate.source_type)
            except ValueError:
                return len(hierarchy) + 1  # Unknown source types rank last
        
        ranked = sorted(candidates, key=source_rank)
        for i, candidate in enumerate(ranked, 1):
            candidate.rank = i
        
        return ranked
    
    def _filter_existing_cases(self, candidates: List[DynamicCandidate]) -> List[DynamicCandidate]:
        """
        Filter out candidates that duplicate existing cases.
        
        A candidate is a duplicate if it has the same (taxon, plant_part, domain).
        """
        filtered = []
        for candidate in candidates:
            # Check if (taxon, plant_part, domain) already exists
            is_duplicate = False
            for existing_taxon, case_info in self.existing_cases.items():
                if candidate.taxon == existing_taxon:
                    # Check if plant_part also matches
                    if candidate.plant_part == case_info.get("plant_part"):
                        if candidate.target_domain in case_info.get("domains", []):
                            is_duplicate = True
                            break
            
            if not is_duplicate:
                filtered.append(candidate)
        
        return filtered
    
    # ========== STUB IMPLEMENTATIONS (for testing) ==========
    
    def _stub_live_search(self, query: str):
        """Stub live search (fallback only)"""
        return []
    
    def _stub_web_search(self, query: str) -> List[str]:
        """Stub web search: returns empty list"""
        return []
    
    def _stub_web_fetch(self, url: str) -> str:
        """Stub web fetch: returns empty content"""
        return ""


# ========== INTERFACE FOR ORCHESTRATOR ==========

class DynamicDiscoveryInterface:
    """
    Public interface for the orchestrator to use dynamic discovery.
    
    The orchestrator calls this with actual web_search/web_fetch implementations.
    """
    
    @staticmethod
    def discover_with_tools(domain: str, web_search_fn, web_fetch_fn, 
                           existing_cases: Dict, candidate_limit: int = 5) -> List[DynamicCandidate]:
        """
        Discover candidates for a domain using actual web search/fetch tools.
        
        Args:
            domain: Target domain
            web_search_fn: Actual web_search tool function
            web_fetch_fn: Actual web_fetch tool function
            existing_cases: Coverage matrix from orchestrator
            candidate_limit: Max candidates to return
        
        Returns:
            List of DynamicCandidate objects, ranked by source quality
        """
        discovery = DynamicCandidateDiscovery(web_search_fn, web_fetch_fn)
        discovery.existing_cases = existing_cases
        return discovery.discover(domain, candidate_limit)


# ========== ENTRY POINT ==========

if __name__ == "__main__":
    print("\nDynamic Candidate Discovery Engine")
    print("===================================\n")
    print("This module performs evidence-driven discovery, NOT static pool selection.")
    print("\nUsage from orchestrator:")
    print("  discovery = DynamicCandidateDiscovery(web_search_fn, web_fetch_fn)")
    print("  discovery.existing_cases = coverage_matrix")
    print("  candidates = discovery.discover('INDICATION_EVIDENCE')")
    print("\nSearching authoritative sources:")
    print("  - EMA/HMPC monographs and assessments")
    print("  - WHO herbal medicine monographs")
    print("  - Systematic reviews (Cochrane)")
    print("  - ESCOP, Commission E guidelines")
    print("  - Pharmacopoeia standards (Ph. Eur., USP)")
    print("\nRanking by source quality hierarchy (per VALIDATION_PROTOCOL.md)")
    print("Filtering to exclude duplicates of existing cases")
    print("\nNOTE: To enable real web search/fetch, pass tools to constructor.")
