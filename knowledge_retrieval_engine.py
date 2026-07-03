# knowledge_retrieval_engine.py

from typing import Dict, List, Any


def create_evidence_object(
    source: str,
    plant: str,
    botanical_name: str,
    dosage_form: str,
    route: str,
    indication: str,
    evidence_type: str,
    evidence_level: str,
    regulatory_relevance: str,
    safety_relevance: str,
    confidence: float,
    notes: str
) -> Dict[str, Any]:

    return {
        "source": source,
        "plant": plant,
        "botanical_name": botanical_name,
        "dosage_form": dosage_form,
        "route": route,
        "indication": indication,
        "evidence_type": evidence_type,
        "evidence_level": evidence_level,
        "regulatory_relevance": regulatory_relevance,
        "safety_relevance": safety_relevance,
        "confidence": confidence,
        "notes": notes
    }


def retrieve_evidence(standardized_project: Dict[str, Any]) -> List[Dict[str, Any]]:

    indication = standardized_project.get("target_indication", "")
    dosage_form = standardized_project.get("dosage_form", "")
    route = standardized_project.get("route", "")
    market = standardized_project.get("target_market", "")

    evidence_objects = []

    # Placeholder evidence objects
    # Later, these will be replaced by real connectors:
    # EMA connector
    # WHO connector
    # ESCOP connector
    # PubMed connector
    # ClinicalTrials connector
    # Internal curated database connector

    if "Sleep" in indication or "Insomnia" in indication:

        evidence_objects.append(
            create_evidence_object(
                source="EMA-HMPC",
                plant="Valerian",
                botanical_name="Valeriana officinalis",
                dosage_form=dosage_form,
                route=route,
                indication=indication,
                evidence_type="Regulatory Monograph",
                evidence_level="Traditional Use",
                regulatory_relevance="High for EU herbal medicinal product assessment",
                safety_relevance="Requires review of CNS depression and sedative interactions",
                confidence=0.90,
                notes="Placeholder object for Module 3 architecture. Replace with real EMA retrieval later."
            )
        )

        evidence_objects.append(
            create_evidence_object(
                source="EMA-HMPC",
                plant="Passionflower",
                botanical_name="Passiflora incarnata",
                dosage_form=dosage_form,
                route=route,
                indication=indication,
                evidence_type="Regulatory Monograph",
                evidence_level="Traditional Use",
                regulatory_relevance="Relevant for sleep and mild stress positioning in EU",
                safety_relevance="Safety profile requires review before product decision",
                confidence=0.85,
                notes="Placeholder object for Module 3 architecture. Replace with real EMA retrieval later."
            )
        )

    elif "Stress" in indication or "Anxiety" in indication:

        evidence_objects.append(
            create_evidence_object(
                source="EMA-HMPC",
                plant="Passionflower",
                botanical_name="Passiflora incarnata",
                dosage_form=dosage_form,
                route=route,
                indication=indication,
                evidence_type="Regulatory Monograph",
                evidence_level="Traditional Use",
                regulatory_relevance="Relevant for mild symptoms of mental stress",
                safety_relevance="Requires review of sedative effects and interactions",
                confidence=0.85,
                notes="Placeholder object for Module 3 architecture. Replace with real EMA retrieval later."
            )
        )

    elif "Allergic Rhinitis" in indication or "Rhinitis" in indication:

        evidence_objects.append(
            create_evidence_object(
                source="Scientific Literature",
                plant="Butterbur",
                botanical_name="Petasites hybridus",
                dosage_form=dosage_form,
                route=route,
                indication=indication,
                evidence_type="Clinical Evidence",
                evidence_level="Indirect / Requires verification",
                regulatory_relevance="Requires strong regulatory screening due to safety concerns",
                safety_relevance="High safety concern; pyrrolizidine alkaloids must be assessed",
                confidence=0.60,
                notes="Placeholder object. Must be verified against real literature and regulatory sources."
            )
        )

    else:

        evidence_objects.append(
            create_evidence_object(
                source="System",
                plant="No candidate identified",
                botanical_name="Not available",
                dosage_form=dosage_form,
                route=route,
                indication=indication,
                evidence_type="No retrieval result",
                evidence_level="Evidence not found",
                regulatory_relevance="Not assessed",
                safety_relevance="Not assessed",
                confidence=0.0,
                notes="No placeholder candidate available for this indication."
            )
        )

    return evidence_objects
