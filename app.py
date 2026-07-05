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
st.caption(
    "Plant-first decision support — every plant in the database is ranked, "
    "not just plants with existing evidence"
)

if not Path(DB_PATH).exists():
    with st.spinner("First run: building the local database..."):
        seed_all()


st.markdown("## Product project inputs")

col1, col2 = st.columns(2)

with col1:
    product_type = st.selectbox(
        "Product type",
        [
            "Herbal product",
            "Food supplement",
            "Cosmetic",
            "Medical device",
            "Veterinary botanical product",
        ],
    )

    disease = st.selectbox(
        "Target indication",
        list_diseases(),
    )

    evidence_strictness = st.selectbox(
        "Evidence strictness",
        [
            "Dosage-form specific only",
            "Regulatory-first",
            "Clinical-first",
            "Flexible",
        ],
    )

with col2:
    dosage_form = st.selectbox(
        "Dosage form",
        [
            "Infusion",
            "Extract",
            "Capsule",
            "Tablet",
            "Syrup",
            "Cream",
            "Gel",
            "Mouthwash",
            "Nasal spray",
            "Powder",
            "Essential oil",
        ],
    )

    market = st.selectbox(
        "Target market",
        [
            "European Union",
            "France",
            "United States",
            "Canada",
            "United Kingdom",
            "Australia",
            "Iran",
            "Global",
        ],
    )

st.markdown("---")

if st.button("Rebuild seed database"):
    seed_all()
    st.success("Database rebuilt.")


st.markdown(
    f"**Decision question:** Which medicinal plants are scientifically and commercially "
    f"worth investigating for **{product_type}** prepared as **{dosage_form}** "
    f"for **{disease}** in **{market}**?"
)

results = rank_plants(disease, dosage_form)
df = pd.DataFrame(results)

if df.empty:
    st.warning("No plants found. Try rebuilding the database.")
else:
    st.success(
        f"{len(df)} plants ranked out of {len(df)} in the global plant database "
        f"(plant-first: no plant is excluded for lack of evidence)."
    )

    st.markdown("## Final Global Botanical Ranking")

    overview_cols = [
        "Scientific_Name",
        "Common_Name",
        "Region",
        "Decision_Class",
        "Final_Score",
        "Clinical_Score",
        "Chemistry_Score",
        "Compound_Score",
        "Target_Score",
        "Extraction_Score",
        "Regulatory_Score",
        "Safety_Score",
        "Novelty_Score",
        "Commercial_Score",
        "Market_Score",
    ]

    visible_overview_cols = [
        col for col in overview_cols
        if col in df.columns
    ]

    st.dataframe(
        df[visible_overview_cols],
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("## Candidate details")

    for _, row in df.iterrows():
        title = (
            f"🌿 {row.get('Scientific_Name', '')} — "
            f"{row.get('Decision_Class', '')} — "
            f"{row.get('Final_Score', '')}/100"
        )

        with st.expander(title):
            score_cols = [
                "Clinical_Score",
                "Chemistry_Score",
                "Compound_Score",
                "Target_Score",
                "Extraction_Score",
                "Regulatory_Score",
                "Safety_Score",
                "Novelty_Score",
                "Commercial_Score",
                "Market_Score",
            ]

            available_score_cols = [
                col for col in score_cols
                if col in df.columns
            ]

            st.dataframe(
                pd.DataFrame([{c: row.get(c, "") for c in available_score_cols}]),
                use_container_width=True,
                hide_index=True,
            )

            st.markdown("### Botanical profile")
            st.markdown(f"**Scientific name:** {row.get('Scientific_Name', '')}")
            st.markdown(f"**Common name:** {row.get('Common_Name', '')}")
            st.markdown(f"**Region:** {row.get('Region', '')}")

            st.markdown("### Chemistry and targets")
            st.markdown(f"**Compound count:** {row.get('Compound_Count', '')}")
            st.markdown(f"**Relevant molecular targets hit:** {row.get('Relevant_Targets_Hit', '')}")

            st.markdown("### Evidence and regulation")
            st.markdown(f"**Clinical evidence:** {row.get('Clinical_Evidence_Notes', '')}")
            st.markdown(f"**Regulatory status:** {row.get('Regulatory_Notes', '')}")

    st.markdown("## Downloads")

    csv = df.to_csv(index=False).encode("utf-8")

    st.download_button(
        "Download ranking as CSV",
        data=csv,
        file_name="botanical_ranking.csv",
        mime="text/csv",
    )


st.markdown("---")

st.caption(
    "Architecture: plants → plant_compounds → compound_targets → target_diseases, "
    "enriched by clinical_evidence / regulatory_status / safety_profile / market_information. "
    "The ranking query always starts from plants, never from clinical_evidence."
)
