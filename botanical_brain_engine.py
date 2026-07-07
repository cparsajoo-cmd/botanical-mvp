import re
import time
import pandas as pd

try:
    import requests
except Exception:
    requests = None


# Broad MVP natural-compound occurrence layer.
# This is NOT final evidence. It is a fallback botanical occurrence map.
COMPOUND_PLANT_MAP = {
    "huperzine a": ["Huperzia serrata"],
    "galantamine": ["Galanthus nivalis", "Leucojum aestivum", "Narcissus pseudonarcissus"],
    "berberine": ["Berberis vulgaris", "Coptis chinensis", "Hydrastis canadensis"],
    "rosmarinic acid": ["Melissa officinalis", "Rosmarinus officinalis", "Salvia officinalis", "Perilla frutescens", "Ocimum basilicum"],
    "apigenin": ["Matricaria chamomilla", "Passiflora incarnata", "Petroselinum crispum", "Apium graveolens"],
    "luteolin": ["Salvia officinalis", "Perilla frutescens", "Apium graveolens", "Thymus vulgaris"],
    "quercetin": ["Sophora japonica", "Allium cepa", "Camellia sinensis", "Ginkgo biloba"],
    "curcumin": ["Curcuma longa"],
    "boswellic acid": ["Boswellia serrata", "Boswellia sacra"],
    "boswellic acids": ["Boswellia serrata", "Boswellia sacra"],
    "withanolides": ["Withania somnifera"],
    "valerenic acid": ["Valeriana officinalis"],
    "linalool": ["Lavandula angustifolia", "Ocimum basilicum", "Coriandrum sativum"],
    "chrysin": ["Passiflora incarnata"],
    "honokiol": ["Magnolia officinalis"],
    "magnolol": ["Magnolia officinalis"],
    "capsaicin": ["Capsicum annuum", "Capsicum frutescens"],
    "gingerol": ["Zingiber officinale"],
    "gingerols": ["Zingiber officinale"],
    "resveratrol": ["Polygonum cuspidatum", "Vitis vinifera"],
    "caffeic acid": ["Coffea arabica", "Rosmarinus officinalis", "Salvia officinalis"],
    "chlorogenic acid": ["Coffea arabica", "Lonicera japonica", "Cynara scolymus"],
    "silymarin": ["Silybum marianum"],
    "silybin": ["Silybum marianum"],
    "rutin": ["Sophora japonica", "Fagopyrum esculentum"],
    "hyperforin": ["Hypericum perforatum"],
    "hypericin": ["Hypericum perforatum"],
    "ginkgolide": ["Ginkgo biloba"],
    "bilobalide": ["Ginkgo biloba"],
    "oleuropein": ["Olea europaea"],
    "carnosic acid": ["Rosmarinus officinalis", "Salvia officinalis"],
    "carnosol": ["Rosmarinus officinalis", "Salvia officinalis"],
    "thymol": ["Thymus vulgaris", "Origanum vulgare"],
    "carvacrol": ["Origanum vulgare", "Thymus vulgaris"],
    "menthol": ["Mentha piperita"],
    "eugenol": ["Syzygium aromaticum", "Ocimum gratissimum"],
    "allicin": ["Allium sativum"],
    "sennoside": ["Senna alexandrina"],
    "sennosides": ["Senna alexandrina"],
    "glycyrrhizin": ["Glycyrrhiza glabra"],
    "glycyrrhetinic acid": ["Glycyrrhiza glabra"],
    "baicalin": ["Scutellaria baicalensis"],
    "baicalein": ["Scutellaria baicalensis"],
    "wogonin": ["Scutellaria baicalensis"],
    "ellagic acid": ["Punica granatum", "Rubus idaeus"],
    "punicalagin": ["Punica granatum"],
    "catechin": ["Camellia sinensis"],
    "epigallocatechin gallate": ["Camellia sinensis"],
    "egcg": ["Camellia sinensis"],
}


# Broad fallback target-compound layer.
# Used only when online ChEMBL gives no usable botanical route.
TARGET_FALLBACK_MAP = {
    "acetylcholinesterase": ["huperzine a", "galantamine", "berberine", "rosmarinic acid", "apigenin", "luteolin"],
    "ache": ["huperzine a", "galantamine", "berberine", "rosmarinic acid", "apigenin", "luteolin"],
    "myeloperoxidase": ["curcumin", "quercetin", "resveratrol", "caffeic acid", "chlorogenic acid", "rosmarinic acid"],
    "mpo": ["curcumin", "quercetin", "resveratrol", "caffeic acid", "chlorogenic acid", "rosmarinic acid"],
    "gaba-a receptor": ["valerenic acid", "apigenin", "linalool", "chrysin", "honokiol", "magnolol"],
    "gaba": ["valerenic acid", "apigenin", "linalool", "chrysin", "honokiol", "magnolol"],
    "nf-kb": ["curcumin", "boswellic acids", "withanolides", "quercetin", "resveratrol", "rosmarinic acid"],
    "cox": ["curcumin", "boswellic acids", "quercetin", "apigenin", "luteolin", "rosmarinic acid"],
    "trpv1": ["capsaicin", "curcumin", "gingerols"],
    "5-ht1a": ["linalool", "apigenin", "rosmarinic acid", "hyperforin"],
}


def _clean(x):
    if x is None:
        return ""
    x = str(x).strip()
    if x.lower() in ["nan", "none", "null"]:
        return ""
    return x


def _norm(x):
    x = _clean(x).lower()
    x = re.sub(r"\s+", " ", x)
    return x


def _safe_get(row, cols):
    for c in cols:
        if c in row.index:
            v = _clean(row.get(c))
            if v:
                return v
    return ""


class UniversalBotanicalBrainEngine:
    def __init__(self, evidence_df=None, max_online_records=80):
        self.evidence_df = evidence_df if evidence_df is not None else pd.DataFrame()
        self.max_online_records = max_online_records
        self.session = None

        if requests is not None:
            self.session = requests.Session()
            self.session.headers.update({"User-Agent": "BotanicalBrainMVP/1.0"})

    def discover(self, query, mode="target"):
        query = _clean(query)
        mode = _norm(mode)

        if not query:
            return pd.DataFrame()

        if "compound" in mode:
            return self.discover_from_compound(query)

        return self.discover_from_target(query)

    def discover_from_target(self, target_query):
        target_query = _clean(target_query)
        rows = []

        online = self._chembl_target_to_compounds(target_query)

        if online.empty:
            online = self._fallback_target_to_compounds(target_query)

        if online.empty:
            return pd.DataFrame()

        for _, r in online.iterrows():
            compound = _clean(r.get("Compound"))
            target = _clean(r.get("Target")) or target_query
            mechanism = _clean(r.get("Mechanism")) or "target-associated activity"
            source = _clean(r.get("Source"))
            activity = _clean(r.get("Activity"))

            plants = self._find_plants_for_compound(compound)

            if not plants:
                rows.append(
                    self._make_row(
                        input_query=target_query,
                        input_type="Biological target",
                        target=target,
                        mechanism=mechanism,
                        compound=compound,
                        plant="Plant not found yet",
                        source=source,
                        activity=activity,
                        botanical_source="No plant occurrence found in MVP map/evidence database",
                    )
                )
            else:
                for plant, botanical_source in plants:
                    rows.append(
                        self._make_row(
                            input_query=target_query,
                            input_type="Biological target",
                            target=target,
                            mechanism=mechanism,
                            compound=compound,
                            plant=plant,
                            source=source,
                            activity=activity,
                            botanical_source=botanical_source,
                        )
                    )

        return self._finalize(rows)

    def discover_from_compound(self, compound_query):
        compound_query = _clean(compound_query)

        target_rows = self._chembl_compound_to_targets(compound_query)

        if target_rows.empty:
            target_rows = self._fallback_compound_to_targets(compound_query)

        if target_rows.empty:
            return pd.DataFrame()

        all_rows = []

        for _, tr in target_rows.iterrows():
            target = _clean(tr.get("Target"))
            related = self._chembl_target_to_compounds(target)

            if related.empty:
                related = self._fallback_target_to_compounds(target)

            if related.empty:
                related = pd.DataFrame(
                    [{
                        "Target": target,
                        "Compound": compound_query,
                        "Mechanism": _clean(tr.get("Mechanism")) or "target-associated activity",
                        "Activity": "",
                        "Source": _clean(tr.get("Source")) or "Input compound",
                    }]
                )

            for _, r in related.iterrows():
                compound = _clean(r.get("Compound"))
                plants = self._find_plants_for_compound(compound)

                if not plants:
                    all_rows.append(
                        self._make_row(
                            input_query=compound_query,
                            input_type="Active compound",
                            target=target,
                            mechanism=_clean(r.get("Mechanism")) or _clean(tr.get("Mechanism")),
                            compound=compound,
                            plant="Plant not found yet",
                            source=_clean(r.get("Source")),
                            activity=_clean(r.get("Activity")),
                            botanical_source="No plant occurrence found in MVP map/evidence database",
                            original_compound=compound_query,
                        )
                    )
                else:
                    for plant, botanical_source in plants:
                        all_rows.append(
                            self._make_row(
                                input_query=compound_query,
                                input_type="Active compound",
                                target=target,
                                mechanism=_clean(r.get("Mechanism")) or _clean(tr.get("Mechanism")),
                                compound=compound,
                                plant=plant,
                                source=_clean(r.get("Source")),
                                activity=_clean(r.get("Activity")),
                                botanical_source=botanical_source,
                                original_compound=compound_query,
                            )
                        )

        return self._finalize(all_rows)

    def _chembl_target_to_compounds(self, target_query):
        if self.session is None:
            return pd.DataFrame()

        try:
            target_url = "https://www.ebi.ac.uk/chembl/api/data/target/search.json"
            resp = self.session.get(target_url, params={"q": target_query}, timeout=12)
            if resp.status_code != 200:
                return pd.DataFrame()

            targets = resp.json().get("targets", [])[:3]
            records = []

            for t in targets:
                target_id = t.get("target_chembl_id")
                target_name = t.get("pref_name") or target_query

                if not target_id:
                    continue

                activity_url = "https://www.ebi.ac.uk/chembl/api/data/activity.json"
                params = {
                    "target_chembl_id": target_id,
                    "limit": self.max_online_records,
                    "standard_type__in": "IC50,Ki,Kd,EC50,Inhibition",
                }

                ar = self.session.get(activity_url, params=params, timeout=15)
                if ar.status_code != 200:
                    continue

                activities = ar.json().get("activities", [])

                for a in activities:
                    compound = a.get("molecule_pref_name") or ""
                    molecule_id = a.get("molecule_chembl_id") or ""
                    standard_type = a.get("standard_type") or ""
                    standard_value = a.get("standard_value") or ""
                    standard_units = a.get("standard_units") or ""

                    if not compound and molecule_id:
                        compound = self._chembl_molecule_name(molecule_id)

                    compound = _clean(compound)

                    if not compound:
                        continue

                    records.append(
                        {
                            "Target": target_name,
                            "Target_ID": target_id,
                            "Compound": compound,
                            "Mechanism": self._infer_mechanism_from_activity(standard_type),
                            "Activity": " ".join([standard_type, standard_value, standard_units]).strip(),
                            "Source": "ChEMBL activity data",
                        }
                    )

                time.sleep(0.15)

            df = pd.DataFrame(records)

            if df.empty:
                return df

            df = df.drop_duplicates(subset=["Target", "Compound"]).head(60)
            return df

        except Exception:
            return pd.DataFrame()

    def _chembl_compound_to_targets(self, compound_query):
        if self.session is None:
            return pd.DataFrame()

        try:
            search_url = "https://www.ebi.ac.uk/chembl/api/data/molecule/search.json"
            sr = self.session.get(search_url, params={"q": compound_query}, timeout=12)
            if sr.status_code != 200:
                return pd.DataFrame()

            molecules = sr.json().get("molecules", [])[:3]
            records = []

            for mol in molecules:
                mol_id = mol.get("molecule_chembl_id")
                mol_name = mol.get("pref_name") or compound_query

                if not mol_id:
                    continue

                activity_url = "https://www.ebi.ac.uk/chembl/api/data/activity.json"
                ar = self.session.get(
                    activity_url,
                    params={"molecule_chembl_id": mol_id, "limit": self.max_online_records},
                    timeout=15,
                )

                if ar.status_code != 200:
                    continue

                for a in ar.json().get("activities", []):
                    target = a.get("target_pref_name") or ""
                    target_id = a.get("target_chembl_id") or ""
                    standard_type = a.get("standard_type") or ""
                    standard_value = a.get("standard_value") or ""
                    standard_units = a.get("standard_units") or ""

                    if not target:
                        continue

                    records.append(
                        {
                            "Input_Compound": mol_name,
                            "Target": target,
                            "Target_ID": target_id,
                            "Mechanism": self._infer_mechanism_from_activity(standard_type),
                            "Activity": " ".join([standard_type, standard_value, standard_units]).strip(),
                            "Source": "ChEMBL compound-target activity data",
                        }
                    )

                time.sleep(0.15)

            df = pd.DataFrame(records)

            if df.empty:
                return df

            return df.drop_duplicates(subset=["Target"]).head(20)

        except Exception:
            return pd.DataFrame()

    def _chembl_molecule_name(self, molecule_chembl_id):
        try:
            url = f"https://www.ebi.ac.uk/chembl/api/data/molecule/{molecule_chembl_id}.json"
            r = self.session.get(url, timeout=10)
            if r.status_code != 200:
                return ""
            data = r.json()
            return data.get("pref_name") or molecule_chembl_id
        except Exception:
            return ""

    def _fallback_target_to_compounds(self, target_query):
        q = _norm(target_query)
        records = []

        for target_key, compounds in TARGET_FALLBACK_MAP.items():
            if q in target_key or target_key in q:
                for c in compounds:
                    records.append(
                        {
                            "Target": target_key,
                            "Compound": c.title(),
                            "Mechanism": self._fallback_mechanism(target_key),
                            "Activity": "Fallback curated MVP signal",
                            "Source": "Internal MVP target-compound fallback",
                        }
                    )

        return pd.DataFrame(records)

    def _fallback_compound_to_targets(self, compound_query):
        q = _norm(compound_query)
        records = []

        for target, compounds in TARGET_FALLBACK_MAP.items():
            for c in compounds:
                if q == _norm(c) or q in _norm(c) or _norm(c) in q:
                    records.append(
                        {
                            "Input_Compound": compound_query,
                            "Target": target,
                            "Mechanism": self._fallback_mechanism(target),
                            "Activity": "Fallback curated MVP signal",
                            "Source": "Internal MVP compound-target fallback",
                        }
                    )

        return pd.DataFrame(records)

    def _find_plants_for_compound(self, compound):
        compound_norm = _norm(compound)
        found = []

        for c, plants in COMPOUND_PLANT_MAP.items():
            c_norm = _norm(c)
            if compound_norm == c_norm or compound_norm in c_norm or c_norm in compound_norm:
                for p in plants:
                    found.append((p, "MVP compound-plant occurrence map"))

        evidence_plants = self._find_plants_in_evidence(compound)
        found.extend(evidence_plants)

        # Deduplicate
        seen = set()
        unique = []

        for plant, source in found:
            key = (_norm(plant), _norm(source))
            if key not in seen:
                seen.add(key)
                unique.append((plant, source))

        return unique[:20]

    def _find_plants_in_evidence(self, compound):
        if self.evidence_df is None or self.evidence_df.empty:
            return []

        df = self.evidence_df.copy()
        compound_norm = _norm(compound)
        results = []

        for _, row in df.iterrows():
            text = " ".join([_clean(v) for v in row.values]).lower()

            if compound_norm not in text:
                continue

            plant = _safe_get(
                row,
                [
                    "Plant",
                    "plant",
                    "Scientific_Name",
                    "scientific_name",
                    "common_name",
                    "Common_Name",
                ],
            )

            if plant:
                results.append((plant, "Local evidence database"))

        return results

    def _make_row(
        self,
        input_query,
        input_type,
        target,
        mechanism,
        compound,
        plant,
        source,
        activity,
        botanical_source,
        original_compound="",
    ):
        evidence_score = 40

        if "chembl" in _norm(source):
            evidence_score += 25
        if "fallback" in _norm(source):
            evidence_score += 10
        if plant and plant != "Plant not found yet":
            evidence_score += 20
        if "evidence database" in _norm(botanical_source):
            evidence_score += 10

        novelty_score = 20
        if original_compound and _norm(compound) == _norm(original_compound):
            novelty_score = 5

        final_score = min(100, evidence_score + novelty_score)

        return {
            "Input_Query": input_query,
            "Input_Type": input_type,
            "Target_or_Biomolecule": target,
            "Mechanism": mechanism,
            "Active_Compound": compound,
            "Candidate_Plant": plant,
            "Activity": activity,
            "Compound_Target_Source": source,
            "Plant_Compound_Source": botanical_source,
            "Evidence_Score": evidence_score,
            "Novelty_Score": novelty_score,
            "Botanical_Brain_Score": final_score,
            "Rationale": (
                f"{compound} is linked to {target}. "
                f"The system then searches for plants containing or reported with {compound}. "
                f"Candidate plant: {plant}."
            ),
        }

    def _finalize(self, rows):
        df = pd.DataFrame(rows)

        if df.empty:
            return df

        df = df.drop_duplicates(
            subset=["Target_or_Biomolecule", "Active_Compound", "Candidate_Plant"],
            keep="first",
        )

        df = df.sort_values(
            by="Botanical_Brain_Score",
            ascending=False,
        ).reset_index(drop=True)

        df.insert(0, "Rank", range(1, len(df) + 1))

        return df

    def _infer_mechanism_from_activity(self, standard_type):
        s = _norm(standard_type)

        if s in ["ic50", "ki", "kd", "inhibition"]:
            return "binding / inhibition signal"

        if s in ["ec50"]:
            return "functional activity signal"

        return "target-associated activity"

    def _fallback_mechanism(self, target):
        t = _norm(target)

        if "acetylcholinesterase" in t or "ache" in t:
            return "enzyme inhibition"

        if "myeloperoxidase" in t or "mpo" in t:
            return "oxidative / inflammatory pathway modulation"

        if "gaba" in t:
            return "GABAergic modulation"

        if "nf" in t:
            return "inflammatory transcription pathway modulation"

        if "cox" in t:
            return "cyclooxygenase pathway modulation"

        if "trpv1" in t:
            return "TRPV1 sensory channel modulation"

        return "target-associated activity"
