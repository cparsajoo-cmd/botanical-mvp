from ai_discovery_engine import understand_question
from global_discovery_connectors import discover_records


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
            therapeutic_area=therapeutic_area,
            dosage_form=dosage_form,
            target_market=target_market,
        )

        if question is None:
            return {
                "question": None,
                "records": [],
                "candidate_plants": [],
                "compounds": [],
                "papers": [],
                "clinical_trials": [],
                "sources": [],
            }

        all_records = []

        search_terms = []

        search_terms.extend(question.get("keywords", []))
        search_terms.extend(question.get("targets", []))
        search_terms.extend(question.get("compound_classes", []))

        for term in search_terms:
            records = discover_records(term)
            all_records.extend(records)

        all_records = self._deduplicate(all_records)

        candidate_plants = [
            r for r in all_records
            if r.get("record_type") == "plant"
        ]

        compounds = [
            r for r in all_records
            if r.get("record_type") == "compound"
        ]

        papers = [
            r for r in all_records
            if r.get("record_type") == "paper"
        ]

        clinical_trials = [
            r for r in all_records
            if r.get("record_type") == "clinical_trial"
        ]

        sources = sorted(set([
            r.get("source", "")
            for r in all_records
            if r.get("source", "")
        ]))

        return {
            "question": question,
            "records": all_records,
            "candidate_plants": candidate_plants,
            "compounds": compounds,
            "papers": papers,
            "clinical_trials": clinical_trials,
            "sources": sources,
        }

    def _deduplicate(self, records):
        unique = {}

        for r in records:
            key = "|".join([
                r.get("record_type", ""),
                r.get("scientific_name", "").lower(),
                r.get("compound", "").lower(),
                r.get("title", "").lower(),
                r.get("source", ""),
            ])

            if key not in unique:
                unique[key] = r

        return list(unique.values())


if __name__ == "__main__":
    engine = GlobalPlantDiscoveryEngine()

    result = engine.discover(
        therapeutic_area="Sleep and relaxation",
        dosage_form="Infusion",
        target_market="European Union",
    )

    print("Sources:", result["sources"])
    print("Plants:", len(result["candidate_plants"]))
    print("Compounds:", len(result["compounds"]))
    print("Papers:", len(result["papers"]))
    print("Clinical trials:", len(result["clinical_trials"]))
