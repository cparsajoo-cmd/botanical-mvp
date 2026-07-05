import streamlit as st
import pandas as pd
from pathlib import Path

from schema import DB_PATH
from seed_data import seed_all
from scoring_engine import rank_plants, list_diseases

from scientific_evidence_collector import (
    collect_or_load_evidence,
    evidence_records_to_dataframe,
)
from scientific_decision_engine import get_scientific_decision


st.set_page_config(
    page_title="Botanical Product Intelligence Platform",
    page_icon="🌿",
    layout="wide",
)

st.title("🌿 Botanical Product Intelligence Platform")
st.caption(
    "Plant-first botanical product intelligence — ranking starts from plants, "
    "then scientific evidence is collected and integrated."
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

    st.markdown("## 1. Initial Plant-first Ranking")

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

    visible_overview_cols = [c for c in overview_cols if c in df.columns]

    st.dataframe(
        df[visible_overview_cols],
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("## 2. Scientific Evidence Collector")

    selected_plant = st.selectbox(
        "Select a plant for scientific evidence collection",
        df["Scientific_Name"].tolist(),
    )

    col_a, col_b = st.columns(2)

    with col_a:
        collect_button = st.button("Collect scientific evidence")

    with col_b:
        force_refresh = st.checkbox("Force refresh online sources", value=False)

    if collect_button:
        with st.spinner(f"Collecting scientific evidence for {selected_plant}..."):
            evidence_output = collect_or_load_evidence(
                plant=selected_plant,
                indication=disease,
                compounds=[],
                market=market,
                max_results=8,
                force_refresh=force_refresh,
            )

        if evidence_output.get("from_cache"):
            st.info("Evidence loaded from Supabase cache.")
        else:
            st.success(
                f"{evidence_output.get('saved_count', 0)} evidence records saved to Supabase."
            )

        decision = evidence_output.get("decision", {})

        st.markdown("### Scientific decision summary")
        st.write(f"**Decision class:** {decision.get('decision_class', '')}")
        st.write(f"**Final scientific score:** {decision.get('final_scientific_score', '')}/100")
        st.write(f"**Clinical score:** {decision.get('clinical_score', '')}/100")
        st.write(f"**Chemistry score:** {decision.get('chemistry_score', '')}/100")
        st.write(f"**Regulatory score:** {decision.get('regulatory_score', '')}/100")
        st.write(f"**Reason:** {decision.get('decision_reason', '')}")

        records_df = evidence_records_to_dataframe(evidence_output.get("records", []))

        if not records_df.empty:
            show_cols = [
                "source",
                "title",
                "year",
                "trust_score",
                "evidence_score",
                "final_source_score",
                "evidence_flags",
                "url",
            ]
            show_cols = [c for c in show_cols if c in records_df.columns]

            st.markdown("### Retrieved scientific evidence")
            st.dataframe(
                records_df[show_cols],
                use_container_width=True,
                hide_index=True,
            )

    st.markdown("## 3. Scientific Decision From Evidence Database")

    if st.button("Show scientific decision from Supabase"):
        sci_decision = get_scientific_decision(
            plant=None,
            indication=disease,
            market=market,
        )

        if sci_decision.empty:
            st.warning("No scientific evidence found in Supabase yet.")
        else:
            st.dataframe(
                sci_decision,
                use_container_width=True,
                hide_index=True,
            )

    st.markdown("## 4. Candidate details")

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

            available_score_cols = [c for c in score_cols if c in df.columns]

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
            st.markdown(
                f"**Relevant molecular targets hit:** {row.get('Relevant_Targets_Hit', '')}"
            )

            st.markdown("### Evidence and regulation")
            st.markdown(f"**Clinical evidence:** {row.get('Clinical_Evidence_Notes', '')}")
            st.markdown(f"**Regulatory status:** {row.get('Regulatory_Notes', '')}")

    st.markdown("## 5. Downloads")

    csv = df.to_csv(index=False).encode("utf-8")

    st.download_button(
        "Download initial ranking as CSV",
        data=csv,
        file_name="botanical_ranking.csv",
        mime="text/csv",
    )


st.markdown("---")

st.caption(
    "Architecture: plants → plant_compounds → compound_targets → target_diseases → "
    "scientific_evidence_collector → Supabase evidence cache → scientific decision engine."
)
