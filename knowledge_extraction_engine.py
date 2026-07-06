import pandas as pd
from evidence_database import load_evidence_database


def _txt(x):
    if x is None:
        return ""
    return str(x).lower().strip()


def _first_existing(row, cols):
    for c in cols:
        if c in row.index:
            val = row.get(c, "")
            if str(val).strip() and str(val).lower() != "nan":
                return str(val).strip()
    return ""


class KnowledgeExtractionEngine:
    def __init__(self):
        try:
            self.evidence_df = load_evidence_database()
        except Exception:
            self.evidence_df = pd.DataFrame()

        self.target_keywords = {
            "GABA-A receptor": ["gaba", "gaba-a", "gabaa", "benzodiazepine"],
            "5-HT1A receptor": ["5-ht1a", "serotonin", "serotonergic"],
            "Melatonin pathway": ["melatonin", "circadian"],
            "Adenosine pathway": ["adenosine"],
            "Orexin pathway": ["orexin", "hypocretin"],
            "COX pathway": ["cox", "cyclooxygenase", "prostaglandin"],
            "NF-kB pathway": ["nf-kb", "nfκb", "inflammation"],
            "TRPV1 channel": ["trpv1"],
            "Histamine pathway": ["histamine", "h1 receptor"],
        }

        self.mechanism_keywords = {
            "sedative / anxiolytic activity": ["sedative", "anxiolytic", "sleep", "insomnia", "relaxation"],
            "anti-inflammatory activity": ["anti-inflammatory", "inflammation", "cox", "nf-kb"],
            "antioxidant activity": ["antioxidant", "oxidative stress"],
            "spasmolytic activity": ["spasmolytic", "smooth muscle"],
            "antimicrobial activity": ["antimicrobial", "antibacterial", "antifungal"],
            "analgesic activity": ["analgesic", "pain"],
        }

        self.evidence_keywords = {
            "clinical": ["clinical trial", "randomized", "placebo", "human study"],
            "animal": ["rat", "mouse", "mice", "animal model"],
            "in vitro": ["in vitro", "cell line", "enzyme assay"],
            "review": ["review", "systematic review", "meta-analysis"],
            "regulatory": ["ema", "who", "escop", "monograph"],
            "patent": ["patent"],
        }

    def extract(self, inputs=None):
        if inputs is None:
            inputs = {}

        if self.evidence_df is None or self.evidence_df.empty:
            return pd.DataFrame()

        df = self.evidence_df.copy()

        usable_cols = [
            c for c in df.columns
            if c.lower() in [
                "plant",
                "scientific_name",
                "common_name",
                "compound",
                "compound_name",
                "title",
                "abstract",
                "source",
                "source_title",
                "source_url",
                "url",
                "indication",
                "mechanism",
                "target",
                "major_target",
            ]
        ]

        if not usable_cols:
            return pd.DataFrame()

        df["_text"] = (
            df[usable_cols]
            .fillna("")
            .astype(str)
            .apply(lambda x: " ".join(x.values.astype(str)), axis=1)
            .str.lower()
        )

        records = []

        for _, row in df.iterrows():
            text = row.get("_text", "")

            plant = _first_existing(
                row,
                ["plant", "Plant", "scientific_name", "Scientific_Name", "common_name", "Common_Name"],
            )

            compound = _first_existing(
                row,
                ["compound", "Compound", "compound_name", "Compound_Name"],
            )

            source = _first_existing(row, ["source", "Source", "source_title", "Source_Title", "title", "Title"])
            source_url = _first_existing(row, ["source_url", "Source_URL", "url", "URL"])

            target = self._detect_target(text)
            mechanism = self._detect_mechanism(text)
            evidence_type = self._detect_evidence_type(text)

            indication = inputs.get("indication", "")
            if not indication:
                indication = _first_existing(row, ["indication", "Indication"])

            confidence = self._confidence(
                plant=plant,
                compound=compound,
                target=target,
                mechanism=mechanism,
                evidence_type=evidence_type,
            )

            if confidence <= 0:
                continue

            records.append(
                {
                    "Plant": plant,
                    "Compound": compound,
                    "Target": target,
                    "Mechanism": mechanism,
                    "Indication": indication,
                    "Evidence_Type": evidence_type,
                    "Source": source,
                    "Source_URL": source_url,
                    "Confidence": confidence,
                }
            )

        result = pd.DataFrame(records)

        if result.empty:
            return result

        result = result.drop_duplicates(
            subset=["Plant", "Compound", "Target", "Mechanism", "Source"],
            keep="first",
        )

        result = result.sort_values(
            by="Confidence",
            ascending=False,
        ).reset_index(drop=True)

        result.insert(0, "Rank", range(1, len(result) + 1))

        return result

    def _detect_target(self, text):
        for target, keywords in self.target_keywords.items():
            for kw in keywords:
                if kw in text:
                    return target
        return ""

    def _detect_mechanism(self, text):
        for mechanism, keywords in self.mechanism_keywords.items():
            for kw in keywords:
                if kw in text:
                    return mechanism
        return ""

    def _detect_evidence_type(self, text):
        for evidence_type, keywords in self.evidence_keywords.items():
            for kw in keywords:
                if kw in text:
                    return evidence_type
        return "literature signal"

    def _confidence(self, plant, compound, target, mechanism, evidence_type):
        score = 0

        if plant:
            score += 20
        if compound:
            score += 20
        if target:
            score += 25
        if mechanism:
            score += 25
        if evidence_type:
            score += 10

        return min(100, score)
