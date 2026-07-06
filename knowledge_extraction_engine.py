import json
import re
import pandas as pd
from evidence_database import load_evidence_database


def _safe(x):
    if x is None:
        return ""
    return str(x).strip()


def _lower(x):
    return _safe(x).lower()


def _first_existing(row, cols):
    for c in cols:
        if c in row.index:
            v = _safe(row.get(c, ""))
            if v and v.lower() != "nan":
                return v
    return ""


class ScientificKnowledgeExtractionEngine:
    def __init__(self):
        try:
            self.evidence_df = load_evidence_database()
        except Exception:
            self.evidence_df = pd.DataFrame()

        self.targets = {
            "GABA-A receptor": ["gaba-a", "gabaa", "gaba receptor", "benzodiazepine receptor"],
            "GABA pathway": ["gaba", "gabaergic", "gaba transaminase"],
            "5-HT1A receptor": ["5-ht1a", "serotonin", "serotonergic"],
            "Melatonin pathway": ["melatonin", "circadian"],
            "Adenosine pathway": ["adenosine"],
            "Orexin pathway": ["orexin", "hypocretin"],
            "COX pathway": ["cox", "cyclooxygenase", "prostaglandin"],
            "NF-kB pathway": ["nf-kb", "nfκb", "nuclear factor kappa"],
            "TRPV1 channel": ["trpv1"],
            "Histamine H1 receptor": ["histamine", "h1 receptor"],
            "Acetylcholinesterase": ["acetylcholinesterase", "ache"],
        }

        self.mechanisms = {
            "sedative / hypnotic activity": ["sedative", "hypnotic", "sleep", "insomnia"],
            "anxiolytic activity": ["anxiolytic", "anxiety", "relaxation"],
            "anti-inflammatory activity": ["anti-inflammatory", "inflammation", "cox", "nf-kb"],
            "antioxidant activity": ["antioxidant", "oxidative stress"],
            "analgesic activity": ["analgesic", "pain"],
            "antimicrobial activity": ["antimicrobial", "antibacterial", "antifungal"],
            "spasmolytic activity": ["spasmolytic", "smooth muscle"],
            "enzyme inhibition": ["inhibition", "inhibitor", "enzyme"],
        }

        self.evidence_types = {
            "human clinical evidence": ["clinical trial", "randomized", "placebo", "human study", "patients"],
            "animal evidence": ["rat", "rats", "mouse", "mice", "animal model"],
            "in vitro evidence": ["in vitro", "cell line", "enzyme assay"],
            "review evidence": ["review", "systematic review", "meta-analysis"],
            "regulatory evidence": ["ema", "who", "escop", "monograph"],
            "patent evidence": ["patent"],
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
                "plant", "scientific_name", "common_name",
                "compound", "compound_name",
                "title", "abstract", "source", "source_title",
                "source_url", "url", "indication", "mechanism",
                "target", "major_target", "pmid", "doi"
            ]
        ]

        if not usable_cols:
            return pd.DataFrame()

        df["_full_text"] = (
            df[usable_cols]
            .fillna("")
            .astype(str)
            .apply(lambda x: " ".join(x.values.astype(str)), axis=1)
            .str.lower()
        )

        records = []

        for _, row in df.iterrows():
            text = row.get("_full_text", "")

            plant = _first_existing(
                row,
                ["plant", "Plant", "scientific_name", "Scientific_Name", "common_name", "Common_Name"],
            )

            compound = _first_existing(
                row,
                ["compound", "Compound", "compound_name", "Compound_Name"],
            )

            title = _first_existing(row, ["title", "Title", "source_title", "Source_Title"])
            source = _first_existing(row, ["source", "Source"])
            url = _first_existing(row, ["source_url", "Source_URL", "url", "URL"])
            pmid = _first_existing(row, ["pmid", "PMID"])
            doi = _first_existing(row, ["doi", "DOI"])

            target = self._detect_from_dict(text, self.targets)
            mechanism = self._detect_from_dict(text, self.mechanisms)
            evidence_type = self._detect_from_dict(text, self.evidence_types)

            indication = inputs.get("indication", "") or _first_existing(row, ["indication", "Indication"])

            if not target and not mechanism:
                continue

            confidence = self._score(
                plant=plant,
                compound=compound,
                target=target,
                mechanism=mechanism,
                evidence_type=evidence_type,
                title=title,
            )

            records.append(
                {
                    "Plant": plant,
                    "Compound": compound,
                    "Target": target,
                    "Mechanism": mechanism,
                    "Indication": indication,
                    "Evidence_Type": evidence_type or "literature signal",
                    "Title": title,
                    "Source": source,
                    "PMID": pmid,
                    "DOI": doi,
                    "URL": url,
                    "Confidence": confidence,
                    "Extracted_Text_Signal": self._short_signal(text, target, mechanism),
                }
            )

        out = pd.DataFrame(records)

        if out.empty:
            return out

        out = out.drop_duplicates(
            subset=["Plant", "Compound", "Target", "Mechanism", "Title"],
            keep="first",
        )

        out = out.sort_values("Confidence", ascending=False).reset_index(drop=True)
        out.insert(0, "Rank", range(1, len(out) + 1))

        return out

    def _detect_from_dict(self, text, dictionary):
        for label, keywords in dictionary.items():
            for kw in keywords:
                if kw in text:
                    return label
        return ""

    def _score(self, plant, compound, target, mechanism, evidence_type, title):
        score = 0

        if plant:
            score += 15
        if compound:
            score += 15
        if target:
            score += 25
        if mechanism:
            score += 25
        if evidence_type:
            score += 10
        if title:
            score += 10

        return min(100, score)

    def _short_signal(self, text, target, mechanism):
        terms = []
        if target:
            terms.extend(target.lower().split())
        if mechanism:
            terms.extend(mechanism.lower().split())

        for term in terms:
            if len(term) < 4:
                continue
            idx = text.find(term)
            if idx != -1:
                start = max(0, idx - 90)
                end = min(len(text), idx + 160)
                return text[start:end]

        return text[:250]
