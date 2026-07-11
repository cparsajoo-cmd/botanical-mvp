import streamlit as st
from evidence_database import load_evidence_database

st.set_page_config(
    page_title="Plant Profile",
    page_icon="🌿",
    layout="wide"
)

st.title("🌿 Plant Profile")
st.caption("Detailed botanical evidence profile")

try:
    df = load_evidence_database()
except Exception as exc:
    df = None
    st.error(f"Could not load the evidence database: {exc}")

if df is None or df.empty or "Scientific_Name" not in df.columns:
    st.info(
        "No evidence records are available yet. This page will populate "
        "once evidence has been collected (Step 2 on the main page) or "
        "imported."
    )
else:
    plant_list = sorted(df["Scientific_Name"].dropna().unique())

    if not plant_list:
        st.info("No plants with a name are available in the evidence database yet.")
    else:
        selected_plant = st.selectbox("Select a plant", plant_list)

        plant_data = df[df["Scientific_Name"] == selected_plant]

        if plant_data.empty:
            st.warning("No profile found for this plant.")
        else:
            row = plant_data.iloc[0]

            st.markdown(f"## {row.get('Scientific_Name', '')}")
            st.markdown(f"**Common name:** {row.get('Common_Name', '')}")

            st.divider()

            st.markdown("## Product development summary")
            st.markdown(f"**Decision class:** {row.get('Decision_Class', '')}")
            st.markdown(f"**Evidence score:** {row.get('Evidence_Score', '')}/100")
            st.markdown(f"**Commercial potential:** {row.get('Commercial_Potential', '')}")
            st.markdown(f"**Decision reason:** {row.get('Decision_Reason', '')}")

            st.markdown("## Regulatory evidence")
            st.markdown(f"**EMA status:** {row.get('EMA_Status', '')}")
            st.markdown(f"**WHO status:** {row.get('WHO_Status', '')}")
            st.markdown(f"**ESCOP status:** {row.get('ESCOP_Status', '')}")
            st.markdown(f"**Regulatory status:** {row.get('Regulatory_Status', '')}")

            st.markdown("## Scientific evidence")
            st.markdown(f"**Clinical evidence:** {row.get('Clinical_Evidence', '')}")
            st.markdown(f"**Infusion-specific evidence:** {row.get('Infusion_Specific_Evidence', '')}")

            st.markdown("## Safety")
            st.markdown(f"**Safety:** {row.get('Safety', '')}")
            st.markdown(f"**Drug interactions:** {row.get('Drug_Interactions', '')}")

            st.markdown("## Source")
            st.markdown(f"**Evidence source:** {row.get('Evidence_Source', '')}")
            st.markdown(f"**Source document:** {row.get('Source_Document', '')}")
            st.markdown(f"**Reference:** {row.get('Reference', '')}")
