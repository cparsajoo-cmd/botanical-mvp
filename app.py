import streamlit as st

from evidence_database import load_evidence_database
from knowledge_retrieval_engine import retrieve_knowledge
from decision_engine import analyze_evidence
from report_generator import generate_report


st.set_page_config(
    page_title="Botanical Product Intelligence Platform",
    page_icon="🌿",
    layout="wide"
)

df = load_evidence_database()

st.title("🌿 Botanical Product Intelligence Platform")
st.caption("Evidence-based decision support for botanical product development")

st.markdown("## Product project inputs")

col1, col2 = st.columns(2)

with col1:
    product_type = st.selectbox(
        "Product type",
        sorted(df["Product_Type"].dropna().astype(str).unique())
    )

    indication = st.selectbox(
        "Target indication",
        sorted(df["Target_Indication"].dropna().astype(str).unique())
    )

with col2:
    dosage_form = st.selectbox(
        "Dosage form",
        sorted(df["Dosage_Form"].dropna().astype(str).unique())
    )

    market = st.selectbox(
        "Target market",
        sorted(df["Target_Market"].dropna().astype(str).unique())
    )

evidence_strictness = st.selectbox(
    "Evidence strictness",
    [
        "Dosage-form specific only",
        "Regulatory-first",
        "Clinical-first",
        "Flexible"
    ]
)

st.markdown("## Product development question")

st.info(
    f"Which medicinal plants are scientifically and commercially worth investing in "
    f"for **{product_type}** prepared as **{dosage_form}** for **{indication}** "
    f"in **{market}**?"
)

if st.button("Analyze evidence", type="primary"):

    retrieved = retrieve_knowledge(
        df=df,
        product_type=product_type,
        dosage_form=dosage_form,
        indication=indication,
        market=market,
        evidence_strictness=evidence_strictness
    )

    result = analyze_evidence(
        df=retrieved,
        product_type=product_type,
        dosage_form=dosage_form,
        indication=indication,
        market=market,
        min_score=0
    )

    st.markdown("## Decision output")

    if result.empty:
        st.warning("No matching evidence records were found.")
    else:
        st.success(str(len(result)) + " relevant plant records found.")

        priority = result[result["Decision_Class"] == "Priority candidate"]
        conditional = result[result["Decision_Class"] == "Conditional candidate"]
        supportive = result[result["Decision_Class"] == "Supportive candidate"]
        gaps = result[result["Decision_Class"] == "Evidence gap"]

        if not priority.empty:
            st.markdown("## Priority candidates")
            for _, row in priority.iterrows():
                st.markdown(f"### 🌿 {row.get('Scientific_Name', '')}")
                st.write(f"**Score:** {row.get('Evidence_Score', '')}/100")
                st.write(f"**Reason:** {row.get('Notes', '')}")

        if not conditional.empty:
            st.markdown("## Conditional candidates")
            for _, row in conditional.iterrows():
                st.markdown(f"### 🌱 {row.get('Scientific_Name', '')}")
                st.write(f"**Score:** {row.get('Evidence_Score', '')}/100")
                st.write(f"**Reason:** {row.get('Notes', '')}")

        if not supportive.empty:
            st.markdown("## Supportive candidates")
            for _, row in supportive.iterrows():
                st.markdown(f"### 🍃 {row.get('Scientific_Name', '')}")
                st.write(f"**Score:** {row.get('Evidence_Score', '')}/100")
                st.write(f"**Reason:** {row.get('Notes', '')}")

        if not gaps.empty:
            st.markdown("## Evidence gaps")
            for _, row in gaps.iterrows():
                st.markdown(f"### ⚠️ {row.get('Scientific_Name', '')}")
                st.write(f"**Score:** {row.get('Evidence_Score', '')}/100")
                st.write(f"**Gap:** {row.get('Notes', '')}")

        st.markdown("## Full evidence table")
        st.dataframe(result, use_container_width=True)

        csv = result.to_csv(index=False).encode("utf-8")

        st.download_button(
            label="Download decision table as CSV",
            data=csv,
            file_name="botanical_decision_output.csv",
            mime="text/csv"
        )

        report_text = generate_report(
            result=result,
            product_type=product_type,
            dosage_form=dosage_form,
            indication=indication,
            market=market
        )

        st.download_button(
            label="Download decision report as TXT",
            data=report_text.encode("utf-8"),
            file_name="botanical_decision_report.txt",
            mime="text/plain"
        )
