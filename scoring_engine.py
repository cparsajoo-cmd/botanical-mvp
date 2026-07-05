from schema import get_connection

RELEVANCE_WEIGHT = {"established": 1.0, "probable": 0.6, "theoretical": 0.3}

SAFETY_MAP = {"none": 90, "mild": 70, "moderate": 50, "severe": 20}
COMMERCIAL_MAP = {"very high": 95, "high": 80, "medium-high": 65, "medium": 50, "low": 30}
PRODUCTION_MAP = {"commercially produced": 80, "r&d candidate": 40, "not produced": 10}

WEIGHTS = {
    "clinical_score": 0.25,
    "chemistry_score": 0.20,
    "compound_score": 0.15,
    "target_score": 0.10,
    "extraction_score": 0.10,
    "safety_score": 0.05,
    "regulatory_score": 0.10,
    "novelty_score": 0.03,
    "commercial_score": 0.01,
    "market_score": 0.01,
}


def _decision_class(score):
    if score >= 90:
        return "Product Ready"
    if score >= 80:
        return "Strategic Development"
    if score >= 70:
        return "Advanced R&D"
    if score >= 60:
        return "Research Candidate"
    if score >= 50:
        return "Early Research"
    return "Not Recommended"


def list_diseases():
    conn = get_connection()
    rows = conn.execute("SELECT disease_name FROM diseases ORDER BY disease_name").fetchall()
    conn.close()
    return [r["disease_name"] for r in rows]


def rank_plants(disease_name, dosage_form="Infusion"):
    conn = get_connection()
    cur = conn.cursor()

    disease_row = cur.execute(
        "SELECT disease_id FROM diseases WHERE disease_name = ?", (disease_name,)
    ).fetchone()
    if not disease_row:
        conn.close()
        return []
    disease_id = disease_row["disease_id"]

    target_rows = cur.execute(
        """SELECT t.target_id, td.relevance_level
           FROM target_diseases td JOIN targets t ON t.target_id = td.target_id
           WHERE td.disease_id = ?""",
        (disease_id,),
    ).fetchall()
    relevant_targets = {r["target_id"]: RELEVANCE_WEIGHT.get(r["relevance_level"], 0.3) for r in target_rows}

    plants = cur.execute("SELECT * FROM plants ORDER BY scientific_name").fetchall()

    results = []
    for p in plants:
        pid = p["plant_id"]

        compounds = cur.execute(
            """SELECT c.compound_id, c.compound_name, pc.extraction_method
               FROM plant_compounds pc JOIN compounds c ON c.compound_id = pc.compound_id
               WHERE pc.plant_id = ?""",
            (pid,),
        ).fetchall()

        compound_count = len(compounds)
        compound_score = min(100, 15 + compound_count * 12) if compound_count else 0

        target_hit_score = 0.0
        hit_target_names = set()
        for c in compounds:
            c_targets = cur.execute(
                """SELECT t.target_id, t.target_name
                   FROM compound_targets ct JOIN targets t ON t.target_id = ct.target_id
                   WHERE ct.compound_id = ?""",
                (c["compound_id"],),
            ).fetchall()
            for t in c_targets:
                if t["target_id"] in relevant_targets:
                    target_hit_score += relevant_targets[t["target_id"]]
                    hit_target_names.add(t["target_name"])

        target_score = min(100, round(target_hit_score * 30, 1))

        extraction_methods = " ".join((c["extraction_method"] or "").lower() for c in compounds)
        if dosage_form.lower() == "infusion":
            extraction_score = 80 if ("infusion" in extraction_methods or "aqueous" in extraction_methods) else 20
        else:
            extraction_score = 80 if ("extract" in extraction_methods or "oil" in extraction_methods) else 40

        chemistry_score = round(
            compound_score * 0.5 + extraction_score * 0.3 + target_score * 0.2, 1
        )

        evidences = cur.execute(
            "SELECT * FROM clinical_evidence WHERE plant_id = ? AND disease_id = ?",
            (pid, disease_id),
        ).fetchall()

        clinical_score = 0
        evidence_notes = []
        for e in evidences:
            st = (e["study_type"] or "").lower()
            if "rct" in st and "not" not in st:
                base = 70
            elif "traditional" in st:
                base = 35
            elif "preclinical" in st:
                base = 15
            else:
                base = 20

            if dosage_form.lower() == "infusion":
                base += 20 if e["preparation_form"] == "infusion" else -15
            base = max(0, min(100, base))
            clinical_score = max(clinical_score, base)
            evidence_notes.append(e["outcome"])

        regs = cur.execute("SELECT * FROM regulatory_status WHERE plant_id = ?", (pid,)).fetchall()
        regulatory_score = 0
        reg_notes = []
        for r in regs:
            status = (r["status"] or "").lower()
            if "well-established" in status:
                regulatory_score = max(regulatory_score, 90)
            elif "traditional use" in status:
                regulatory_score = max(regulatory_score, 60)
            elif "listed" in status:
                regulatory_score = max(regulatory_score, 40)
            if r["status"]:
                reg_notes.append(f"{r['agency']}: {r['status']}")

        safety_row = cur.execute("SELECT * FROM safety_profile WHERE plant_id = ?", (pid,)).fetchone()
        safety_score = SAFETY_MAP.get((safety_row["severity"] if safety_row else "mild"), 70)

        market_row = cur.execute("SELECT * FROM market_information WHERE plant_id = ?", (pid,)).fetchone()
        commercial_score = COMMERCIAL_MAP.get(
            (market_row["commercial_attractiveness"].lower() if market_row and market_row["commercial_attractiveness"] else ""), 40
        )
        market_score = PRODUCTION_MAP.get(
            (market_row["production_status"].lower() if market_row and market_row["production_status"] else ""), 20
        )

        novelty_score = 70 if compound_count and regulatory_score < 60 else 40

        scores = {
            "clinical_score": clinical_score,
            "chemistry_score": chemistry_score,
            "compound_score": compound_score,
            "target_score": target_score,
            "extraction_score": extraction_score,
            "safety_score": safety_score,
            "regulatory_score": regulatory_score,
            "novelty_score": novelty_score,
            "commercial_score": commercial_score,
            "market_score": market_score,
        }

        final_score = round(sum(scores[k] * WEIGHTS[k] for k in WEIGHTS), 1)

        results.append({
            "Scientific_Name": p["scientific_name"],
            "Common_Name": p["common_name"],
            "Region": p["region"],
            "Final_Score": final_score,
            "Decision_Class": _decision_class(final_score),
            **{"_".join(w.capitalize() for w in k.split("_")): v for k, v in scores.items()},
            "Compound_Count": compound_count,
            "Relevant_Targets_Hit": ", ".join(sorted(hit_target_names)) or "None",
            "Clinical_Evidence_Notes": " | ".join(evidence_notes) or "No disease-specific clinical evidence on file",
            "Regulatory_Notes": " | ".join(reg_notes) or "Not evaluated by any listed agency",
        })

    conn.close()
    results.sort(key=lambda r: r["Final_Score"], reverse=True)
    return results


if __name__ == "__main__":
    for row in rank_plants("Insomnia / sleep disturbance", "Infusion"):
        print(row["Scientific_Name"], row["Final_Score"], row["Decision_Class"])
