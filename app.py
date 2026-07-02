import streamlit as st

from evidence_database import load_evidence_database
from decision_engine import analyze_evidence

st.set_page_config(
    page_title="Botanical Product Intelligence Platform",
    page_icon="🌿",
    layout="wide"
)

st.title("🌿 Botanical Product Intelligence Platform")
st.caption("MVP demo — evidence-based botanical product decision support")

df = load_evidence_database()

st.sidebar.title("New Project")

product_type = st.sidebar.selectbox(
    "Product type",
    ["Herbal product"]
)

dosage_form = st.sidebar.selectbox(
    "Dosage form",
    ["Infusion", "Capsule", "Tablet", "Cream", "Syrup"]
)

indication = st.sidebar.selectbox(
    "Target indication",
    ["Sleep and relaxation", "Constipation", "Cough", "Digestive comfort"]
)

market = st.sidebar.selectbox(
    "Target market",
    ["European Union", "United States", "Canada", "Iran"]
)

st.markdown("## Input question")

st.write(
    f"Which medicinal plants are scientifically and commercially worth investing in "
    f"for **{product_type}** prepared as **{dosage_form}** for **{indication}** "
    f"in **{market}**?"
)

if st.button("Analyze evidence"):
    result = analyze_evidence(
        df=df,
        product_type=product_type,
        dosage_form=dosage_form,
        indication=indication,
        market=market
    )

    st.markdown("## Output decision")

    if result.empty:
        st.warning("No evidence record found for this product question in the current MVP database.")
        st.info("Next step: add structured evidence records for this product form, indication, and market.")
    else:
        st.success(f"{len(result)} relevant plant records found.")

        st.dataframe(
            result[
                [
                    "plant",
                    "common_name",
                    "decision_class",
                    "ema_status",
                    "infusion_specific",
                    "safety_level",
                    "commercial_value",
                    "reason",
                ]
            ],
            use_container_width=True
        )

        st.markdown("### Recommended interpretation")

        for decision_class in result["decision_class"].unique():
            subset = result[result["decision_class"] == decision_class]
            st.markdown(f"#### {decision_class}")
            for _, row in subset.iterrows():
                st.write(f"**{row['plant']}** ({row['common_name']}) — {row['reason']}")

        csv = result.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download decision table as CSV",
            data=csv,
            file_name="botanical_decision_output.csv",
            mime="text/csv"
        )

st.divider()

st.caption(
    "MVP note: This version separates the user interface, evidence database, "
    "and decision engine. The next version will expand the database and add source-level evidence."
                    )
