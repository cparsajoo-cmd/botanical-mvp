"""
Global Plant Discovery Engine

Step 2 of the Botanical AI Discovery Platform

This engine receives the interpreted research question,
searches global botanical sources,
and returns candidate medicinal plants.

Current source:
- Kew Plants of the World Online (POWO)

Later sources:
- GBIF
- Dr Duke
- Chinese Pharmacopoeia
- African Medicinal Plants
- Iranian Medicinal Plants
- Ayurvedic Database
- Japanese Kampo
"""

from ai_discovery_engine import understand_question
from kew_connector import search_kew_plants


class GlobalPlantDiscoveryEngine:

    def __init__(self):
        pass

    def discover(
        self,
        therapeutic_area,
        dosage_form,
        target_market,
    ):

        # -----------------------------
        # Understand user question
        # -----------------------------

        question = understand_question(
            therapeutic_area=therapeutic_area,
            dosage_form=dosage_form,
            target_market=target_market,
        )

        if question is None:
            return {
                "question": None,
                "candidate_plants": [],
                "sources": [],
            }

        # -----------------------------
        # Search candidate plants
        # -----------------------------

        candidate_plants = []

        for keyword in question["keywords"]:

            try:

                plants = search_kew_plants(
                    keyword=keyword,
                    limit=30,
                )

                candidate_plants.extend(plants)

            except Exception:
                pass

        # -----------------------------
        # Remove duplicates
        # -----------------------------

        unique = {}

        for plant in candidate_plants:

            name = plant.get("Scientific_Name")

            if not name:
                continue

            if name not in unique:
                unique[name] = plant

        candidate_plants = list(unique.values())

        # -----------------------------
        # Sort alphabetically
        # -----------------------------

        candidate_plants.sort(
            key=lambda x: x.get("Scientific_Name", "")
        )

        # -----------------------------
        # Return
        # -----------------------------

        return {

            "question": question,

            "candidate_plants": candidate_plants,

            "sources": [

                "Kew Plants of the World Online"

            ]

        }


if __name__ == "__main__":

    engine = GlobalPlantDiscoveryEngine()

    result = engine.discover(

        therapeutic_area="Sleep and relaxation",

        dosage_form="Infusion",

        target_market="European Union",

    )

    print(result["question"])

    print()

    print(f"Plants found: {len(result['candidate_plants'])}")

    for plant in result["candidate_plants"][:10]:
        print(plant)
