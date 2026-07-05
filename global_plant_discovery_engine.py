from ai_discovery_engine import understand_question


class GlobalPlantDiscoveryEngine:

    def __init__(self):
        pass

    def discover(
        self,
        therapeutic_area,
        dosage_form,
        target_market,
    ):

        question = understand_question(
            therapeutic_area,
            dosage_form,
            target_market,
        )

        return {
            "question": question,
            "candidate_plants": [],
            "sources": [],
      }
