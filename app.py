import streamlit as st
import pandas as pd
from pathlib import Path

from schema import DB_PATH
from seed_data import seed_all
from scoring_engine import rank_plants, list_diseases

st.set_page_config(
    page_title="Botanical Product Intelligence Platform",
    page_icon="🌿",
    layout="wide",
)

st.title("🌿 Botanical Product Intelligence Platform")
st.caption("Plant-first decision support — every plant in the database is ranked, not just plants with existing evidence")

if not Path(DB_PATH).exists():
    with st.spinner("First run: building the local database..."):
        seed_all()

with st.sidebar:
    st.header("Product question")
    disease = st.selectbox("Health indication (disease/target)", list_diseases())
    dosage_form = st.selectbox("Dosage form", ["Infusion", "Extract", "Capsule"])
    market = st.selectbox("Target market", ["European Union", "France", "Global"])

    st.markdown("---")
    st.caption(
        "This demo runs on a local SQLite database seeded from the plant / compound / "
        "target / disease graph."
    )

    if st.button("Rebuild seed database"):
        seed_all()
        st.success("Database rebuilt.")

st.markdown(
    f"**Decision question:** Which medicinal plants are the best candidates for a "
    f"**{dosage_form}** targeting **{disease}** in **{market}**?"
)

results = rank_plants(disease, dosage_form)
df = pd.DataFrame(results)

if df.empty:
    st.warning("No plants found. Try rebuilding the database from the sidebar.")
else:
    st.success(f"{len(df)} plants ranked out of {len(df)} in the global plant database (plant-first: no plant is excluded for lack of evidence).")

    st.markdown("## Final Global Botanical Ranking")
    overview_cols = [
        "Scientific_Name", "Common_Name", "Region", "Decision_Class", "Final_Score",
        "Clinical_Score", "Chemistry_Score", "Regulatory_Score", "Safety_Score",
    ]
    st.dataframe(df[overview_cols], use_container_width=True, hide_index=True)

    st.markdown("## Candidate details")
    for _, row in df.iterrows():
        title = f"🌿 {row['Scientific_Name']} — {row['Decision_Class']} — {row['Final_Score']}/100"
        with st.expander(title):
            score_cols = [
                "Clinical_Score", "Chemistry_Score", "Compound_Score", "Target_Score",
                "Extraction_Score", "Regulatory_Score", "Safety_Score", "Novelty_Score",
                "Commercial_Score", "Market_Score",
            ]
            st.dataframe(pd.DataFrame([{c: row[c] for c in score_cols}]), use_container_width=True, hide_index=True)

            st.markdown(f"**Compound count:** {row['Compound_Count']}")
            st.markdown(f"**Relevant molecular targets hit:** {row['Relevant_Targets_Hit']}")
            st.markdown(f"**Clinical evidence:** {row['Clinical_Evidence_Notes']}")
            st.markdown(f"**Regulatory status:** {row['Regulatory_Notes']}")

    st.markdown("## Downloads")
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("Download ranking as CSV", data=csv, file_name="botanical_ranking.csv", mime="text/csv")

    st.markdown("## 🔬 Live scientific evidence lookup")
    st.caption("Fetches real, live data from PubChem, ChEMBL, Europe PMC and ClinicalTrials.gov. Requires internet access at runtime.")

    selected_plant = st.selectbox("Choose a plant to look up live", df["Scientific_Name"].tolist())

    if st.button("Fetch live evidence"):
        from connectors import get_pubchem_data, get_chembl_targets, search_articles, search_trials

        with st.spinner(f"Querying live sources for {selected_plant}..."):
            st.markdown("### Europe PMC articles")
            st.json(search_articles(selected_plant, disease.split(" /")[0]))

            st.markdown("### ClinicalTrials.gov trials")
            st.json(search_trials(selected_plant, disease.split(" /")[0]))

            st.markdown("### PubChem (test compound)")
            st.json(get_pubchem_data("Rosmarinic acid"))

            st.markdown("### ChEMBL (test compound)")
            st.json(get_chembl_targets("Rosmarinic acid"))

st.markdown("---")
st.caption(
    "Architecture: plants → plant_compounds → compound_targets → target_diseases, "
    "enriched by clinical_evidence / regulatory_status / safety_profile / market_information. "
    "The ranking query always starts from `plants`, never from `clinical_evidence`. "
    "Live lookups (PubChem, ChEMBL, Europe PMC, ClinicalTrials.gov) enrich on demand via `connectors.py`."
)
