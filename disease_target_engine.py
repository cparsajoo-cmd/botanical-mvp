from dataclasses import dataclass

@dataclass
class TargetCandidate:
    target: str
    pathway: str
    organ: str
    confidence: float


class DiseaseTargetEngine:

    def discover(self, indication, knowledge_df):

        indication = indication.lower()

        targets = []

        for _, row in knowledge_df.iterrows():

            ind = str(row.get("Indication","")).lower()
            target = str(row.get("Target",""))
            mechanism = str(row.get("Mechanism",""))

            if indication in ind:

                score = 60

                if mechanism:
                    score += 20

                if target:
                    score += 20

                targets.append(
                    TargetCandidate(
                        target=target,
                        pathway=mechanism,
                        organ="",
                        confidence=min(score,100)
                    )
                )

        unique = {}

        for t in targets:

            if t.target not in unique:
                unique[t.target]=t
            elif t.confidence>unique[t.target].confidence:
                unique[t.target]=t

        return sorted(
            unique.values(),
            key=lambda x:x.confidence,
            reverse=True
        )
