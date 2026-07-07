import re
import requests
import pandas as pd


def clean(x):
    if x is None:
        return ""
    x = str(x).strip()
    if x.lower() in ["nan", "none", "null"]:
        return ""
    return x


def norm(x):
    return re.sub(r"\s+", " ", clean(x).lower()).strip()


class BotanicalSubstitutionEngine:
    """
    Finds alternative plants containing the same active compound
    and ranks them as commercial or R&D candidates.
    """

    def __init__(self, evidence_df=None, max_results=30):
        self.evidence_df = evidence_df if evidence_df is not None else pd.DataFrame()
        self.max_results = max_results

    def discover(self, compound, reference_plant="", indication="", dosage_form="", market=""):
        compound = clean(compound)
        reference_plant = clean(reference_plant)

        records = []

        records.extend(
            self._search_local_evidence(
                compound=compound,
                reference_plant=reference_plant,
                indication=indication,
            )
        )

        records.extend(
            self._search_europepmc(
                compound=compound,
                indication=indication,
            )
        )

        if not records:
            return pd.DataFrame()

        df = pd.DataFrame(records)
        df = self._normalize(df, compound, reference_plant)
        df = self._score(df, reference_plant, dosage_form, market)

        df = df.drop_duplicates(
            subset=["Alternative_Plant", "Active_Compound", "Source_Title"],
            keep="first",
        )

        df = df.sort_values(
            by=["R&D_Opportunity_Score", "Concentration_Score", "Extraction_Score"],
            ascending=False,
        ).reset_index(drop=True)

        df.insert(0, "Rank", range(1, len(df) + 1))

        return df

    def _search_local_evidence(self, compound, reference_plant="", indication=""):
        if self.evidence_df is None or self.evidence_df.empty:
            return []

        rows = []

        for _, row in self.evidence_df.iterrows():
            text = " ".join([clean(v) for v in row.values])
            text_l = text.lower()

            if norm(compound) not in text_l:
                continue

            plant = self._get_first(
                row,
                ["Scientific_Name", "Plant", "plant", "scientific_name", "Common_Name"],
            )

            if not plant:
                plant = self._extract_plant_name(text)

            rows.append({
                "Active_Compound": compound,
                "Reference_Plant": reference_plant,
                "Alternative_Plant": plant,
                "Raw_Text": text,
                "Source_Title": self._get_first(row, ["Source_Title", "Title", "title"]),
                "Source_URL": self._get_first(row, ["Source_URL", "URL", "url"]),
                "Source_Type": "Local evidence database",
                "Indication": indication,
            })

        return rows

    def _search_europepmc(self, compound, indication=""):
        query = f'"{compound}" medicinal plant phytochemical extraction concentration'
        if indication:
            query += f' "{indication}"'

        url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

        try:
            r = requests.get(
                url,
                params={
                    "query": query,
                    "format": "json",
                    "pageSize": self.max_results,
                },
                timeout=20,
            )
            r.raise_for_status()
            items = r.json().get("resultList", {}).get("result", [])
        except Exception:
            return []

        rows = []

        for item in items:
            title = clean(item.get("title", ""))
            abstract = clean(item.get("abstractText", ""))
            year = clean(item.get("pubYear", ""))
            pmid = clean(item.get("pmid", ""))
            doi = clean(item.get("doi", ""))

            url_out = ""
            if pmid:
                url_out = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            elif doi:
                url_out = f"https://doi.org/{doi}"

            raw = f"{title}. {abstract}"

            plant = self._extract_plant_name(raw)

            rows.append({
                "Active_Compound": compound,
                "Reference_Plant": "",
                "Alternative_Plant": plant,
                "Raw_Text": raw,
                "Source_Title": title,
                "Source_URL": url_out,
                "Source_Year": year,
                "Source_Type": "Europe PMC",
                "Indication": indication,
            })

        return rows

    def _normalize(self, df, compound, reference_plant):
        out = df.copy()

        out["Active_Compound"] = compound
        out["Reference_Plant"] = reference_plant

        out["Alternative_Plant"] = out["Alternative_Plant"].apply(clean)
        out["Alternative_Plant"] = out["Alternative_Plant"].replace("", "Plant not clearly extracted")

        out["Concentration_Info"] = out["Raw_Text"].apply(self._extract_concentration)
        out["Extraction_Method"] = out["Raw_Text"].apply(self._extract_extraction)
        out["Co_Compounds"] = out["Raw_Text"].apply(self._extract_co_compounds)
        out["Safety_Flags"] = out["Raw_Text"].apply(self._extract_safety)
        out["Interaction_Flags"] = out["Raw_Text"].apply(self._extract_interactions)

        out["Is_Reference_Plant"] = out["Alternative_Plant"].apply(
            lambda x: norm(x) == norm(reference_plant) if reference_plant else False
        )

        return out

    def _score(self, df, reference_plant, dosage_form, market):
        result = df.copy()

        result["Concentration_Score"] = result["Concentration_Info"].apply(
            lambda x: 25 if x else 5
        )

        result["Extraction_Score"] = result["Extraction_Method"].apply(
            lambda x: self._score_extraction(x, dosage_form)
        )

        result["Co_Compound_Score"] = result["Co_Compounds"].apply(
            lambda x: min(25, 5 * len([i for i in str(x).split(";") if i.strip()]))
        )

        result["Safety_Risk_Score"] = result["Safety_Flags"].apply(
            lambda x: 25 if x else 5
        )

        result["Interaction_Risk_Score"] = result["Interaction_Flags"].apply(
            lambda x: 25 if x else 5
        )

        result["Novelty_Score"] = result["Is_Reference_Plant"].apply(
            lambda x: 0 if x else 25
        )

        result["Market_Status"] = result.apply(
            lambda r: self._classify_market_status(r, reference_plant),
            axis=1,
        )

        result["Commercial_Status_Score"] = result["Market_Status"].apply(
            lambda x: {
                "Reference / known commercial plant": 10,
                "Potential alternative / R&D candidate": 30,
                "Unclear market status": 20,
            }.get(x, 15)
        )

        result["R&D_Opportunity_Score"] = (
            result["Concentration_Score"]
            + result["Extraction_Score"]
            + result["Co_Compound_Score"]
            + result["Novelty_Score"]
            + result["Commercial_Status_Score"]
            - result["Safety_Risk_Score"] * 0.3
            - result["Interaction_Risk_Score"] * 0.3
        ).round(1)

        result["Decision_Class"] = result["R&D_Opportunity_Score"].apply(
            self._decision_class
        )

        result["Rationale"] = result.apply(
            lambda r: (
                f"{r['Alternative_Plant']} is a potential alternative source of "
                f"{r['Active_Compound']}. "
                f"Extraction: {r['Extraction_Method'] or 'not clearly reported'}. "
                f"Concentration: {r['Concentration_Info'] or 'not clearly reported'}. "
                f"Co-compounds: {r['Co_Compounds'] or 'not clearly extracted'}."
            ),
            axis=1,
        )

        return result

    def _score_extraction(self, extraction, dosage_form):
        e = norm(extraction)
        d = norm(dosage_form)

        if not e:
            return 5

        score = 15

        if "water" in e or "aqueous" in e or "infusion" in e:
            score += 15
            if "tea" in d or "infusion" in d or "herbal" in d:
                score += 15

        if "ethanol" in e or "hydroalcoholic" in e or "methanol" in e:
            score += 15
            if "extract" in d or "capsule" in d or "tablet" in d:
                score += 10

        if "essential oil" in e or "distillation" in e:
            score += 10
            if "essential oil" in d:
                score += 15

        return min(score, 40)

    def _classify_market_status(self, row, reference_plant):
        plant = clean(row.get("Alternative_Plant", ""))

        if reference_plant and norm(plant) == norm(reference_plant):
            return "Reference / known commercial plant"

        if plant and plant != "Plant not clearly extracted":
            return "Potential alternative / R&D candidate"

        return "Unclear market status"

    def _decision_class(self, score):
        if score >= 75:
            return "Strong R&D alternative"
        if score >= 55:
            return "Promising R&D candidate"
        if score >= 35:
            return "Early-stage candidate"
        return "Low priority / insufficient data"

    def _extract_concentration(self, text):
        text = clean(text)

        patterns = [
            r"\b\d+(\.\d+)?\s?%",
            r"\b\d+(\.\d+)?\s?mg/g\b",
            r"\b\d+(\.\d+)?\s?mg/kg\b",
            r"\b\d+(\.\d+)?\s?mg/100g\b",
            r"\b\d+(\.\d+)?\s?µg/g\b",
            r"\b\d+(\.\d+)?\s?ug/g\b",
            r"\b\d+(\.\d+)?\s?mg/ml\b",
        ]

        found = []

        for p in patterns:
            found.extend(re.findall(p, text, flags=re.IGNORECASE))

        matches = []
        for p in patterns:
            matches.extend(re.finditer(p, text, flags=re.IGNORECASE))

        vals = [m.group(0) for m in matches]

        return "; ".join(sorted(set(vals)))[:300]

    def _extract_extraction(self, text):
        t = norm(text)

        methods = []

        keywords = {
            "aqueous extraction": ["aqueous", "water extract", "hot water", "infusion", "decoction"],
            "ethanolic extraction": ["ethanol", "ethanolic"],
            "hydroalcoholic extraction": ["hydroalcoholic", "ethanol-water"],
            "methanolic extraction": ["methanol", "methanolic"],
            "ultrasound-assisted extraction": ["ultrasound"],
            "microwave-assisted extraction": ["microwave"],
            "supercritical CO2 extraction": ["supercritical", "co2"],
            "steam distillation": ["steam distillation", "distillation"],
            "essential oil extraction": ["essential oil", "volatile oil"],
        }

        for label, keys in keywords.items():
            if any(k in t for k in keys):
                methods.append(label)

        return "; ".join(sorted(set(methods)))

    def _extract_co_compounds(self, text):
        t = norm(text)

        known = [
            "apigenin", "luteolin", "quercetin", "kaempferol", "rutin",
            "rosmarinic acid", "caffeic acid", "chlorogenic acid",
            "curcumin", "berberine", "resveratrol", "catechin",
            "egcg", "gallic acid", "ellagic acid", "hypericin",
            "hyperforin", "linalool", "valerenic acid", "thymol",
            "carvacrol", "menthol", "eugenol", "silymarin",
            "withanolides", "boswellic acids",
        ]

        found = [c for c in known if c in t]

        return "; ".join(sorted(set(found)))

    def _extract_safety(self, text):
        t = norm(text)

        flags = []

        safety_words = [
            "toxicity", "toxic", "hepatotoxic", "cytotoxic",
            "adverse", "contraindication", "contraindicated",
            "pregnancy", "breastfeeding", "allergy",
            "warning", "caution",
        ]

        for w in safety_words:
            if w in t:
                flags.append(w)

        return "; ".join(sorted(set(flags)))

    def _extract_interactions(self, text):
        t = norm(text)

        flags = []

        interaction_words = [
            "drug interaction", "interaction", "cyp", "cytochrome",
            "warfarin", "anticoagulant", "antiplatelet",
            "ssri", "maoi", "benzodiazepine", "sedative",
            "hypoglycemic", "antidiabetic", "antihypertensive",
        ]

        for w in interaction_words:
            if w in t:
                flags.append(w)

        return "; ".join(sorted(set(flags)))

    def _extract_plant_name(self, text):
        text = clean(text)

        candidates = re.findall(r"\b[A-Z][a-z]+ [a-z]+(?:\s[a-z]+)?\b", text)

        bad = {
            "The aim", "The study", "The results", "This study",
            "United States", "European Union", "Clinical Trial",
        }

        for c in candidates:
            if c not in bad:
                return c

        return ""

    def _get_first(self, row, cols):
        for c in cols:
            if c in row.index:
                v = clean(row.get(c))
                if v:
                    return v
        return ""
