import streamlit as st
import pandas as pd

from evidence_database import load_evidence_database
from knowledge_retrieval_engine import retrieve_knowledge
from evidence_filtering_engine import apply_evidence_filters
from decision_engine import analyze_evidence
from report_generator import generate_report
from research_engine import run_research_engine


st.set_page_config(
    page_title="Botanical Product Intelligence Platform",
    page_icon="🌿",
    layout="wide"
)

st.title("🌿 Botanical Product Intelligence Platform")
st.caption("Evidence-based botanical product decision support")

df = load_evidence_database()

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

    indication = st.selectbox(
        "Target indication",
        [
            "Sleep and relaxation",
            "Constipation",
            "Cough",
            "Digestive comfort",
            "Anxiety",
            "Skin inflammation",
            "Dry mouth",
            "Allergic rhinitis",
            "IBS",
            "Wound healing",
        ],
    )

with col2:
    dosage_form = st.selectbox(
        "Dosage form",
        [
            "Infusion",
            "Capsule",
            "Tablet",
            "Syrup",
            "Cream",
            "Gel",
            "Mouthwash",
            "Nasal spray",
            "Chewing gum",
            "Powder",
            "Extract",
        ],
    )

    market = st.selectbox(
        "Target market",
        [
            "European Union",
            "France",
            "United States",
            "Canada",
            "Iran",
        ],
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

max_pubmed_results = st.slider(
    "Online PubMed results per candidate plant",
    1,
    10,
    3,
)

st.markdown("## Product development question")

st.info(
    f"Which medicinal plants are scientifically and commercially worth investing in "
    f"for **{product_type}** prepared as **{dosage_form}** for **{indication}** "
    f"in **{market}**?"
)


def generate_decision(current_df):
    retrieved = retrieve_knowledge(
        df=current_df,
        product_type=product_type,
        dosage_form=dosage_form,
        indication=indication,
        market=market,
        evidence_strictness=evidence_strictness,
    )

    filtered = apply_evidence_filters(
        df=retrieved,
        dosage_form=dosage_form,
        evidence_strictness=evidence_strictness,
    )

    result = analyze_evidence(
        df=filtered,
        product_type=product_type,
        dosage_form=dosage_form,
        indication=indication,
        market=market,
        min_score=0,
    )

    return result


col_button_1, col_button_2 = st.columns(2)

with col_button_1:
    generate_only = st.button(
        "Generate decision from database",
        type="primary"
    )

with col_button_2:
    collect_and_generate = st.button(
        "Collect online evidence + generate decision"
    )


if collect_and_generate:
    st.markdown("## Online evidence collection")

    with st.spinner("Searching PubMed, extracting evidence, and saving records to Supabase..."):
        research_output = run_research_engine(
            product_type=product_type,
            dosage_form=dosage_form,
            indication=indication,
            target_market=market,
            max_results_per_plant=max_pubmed_results,
            save=True,
        )

    st.success(
        f"{len(research_output.get('saved_records', []))} online evidence records saved."
    )

    if research_output.get("candidate_plants"):
        st.write("**Candidate plants searched:**")
        st.write(", ".join(research_output["candidate_plants"]))

    if research_output.get("errors"):
        st.warning("Some searches produced errors.")
        st.dataframe(pd.DataFrame(research_output["errors"]), use_container_width=True)

    if research_output.get("saved_records"):
        st.markdown("### Saved online evidence records")
        st.dataframe(
            pd.DataFrame(research_output["saved_records"]),
            use_container_width=True
        )

    df = load_evidence_database()
    result = generate_decision(df)

elif generate_only:
    result = generate_decision(df)

else:
    result = None


if result is not None:

    st.markdown("## Decision output")

    if result.empty:
        st.warning("No evidence records found yet for this product question.")
    else:
        st.success(str(len(result)) + " relevant plant records found.")

        for _, row in result.iterrows():
            with st.expander(
                f"🌿 {row.get('Scientific_Name', '')} — "
                f"{row.get('Decision_Class', '')} — "
                f"Score {row.get('Evidence_Score', '')}/100",
                expanded=True,
            ):
                st.write(f"**Common name:** {row.get('Common_Name', '')}")
                st.write(f"**Product type:** {row.get('Product_Type', '')}")
                st.write(f"**Dosage form:** {row.get('Dosage_Form', '')}")
                st.write(f"**Indication:** {row.get('Target_Indication', '')}")
                st.write(f"**Market:** {row.get('Target_Market', '')}")

                st.markdown("### Regulatory evidence")
                st.write(f"**EMA:** {row.get('EMA_Status', '')}")
                st.write(f"**WHO:** {row.get('WHO_Status', '')}")
                st.write(f"**ESCOP:** {row.get('ESCOP_Status', '')}")

                st.markdown("### Scientific evidence")
                st.write(f"**Clinical level:** {row.get('Clinical_Level', '')}")
                st.write(f"**RCT count:** {row.get('Clinical_RCT_Count', '')}")
                st.write(f"**Meta-analysis level:** {row.get('Meta_Level', '')}")
                st.write(f"**Dosage-form evidence:** {row.get('Infusion_Evidence', '')}")

                st.markdown("### Safety and decision")
                st.write(f"**Safety:** {row.get('Safety_Level', '')}")
                st.write(f"**Evidence filter status:** {row.get('Evidence_Filter_Status', '')}")
                st.write(f"**Evidence filter reason:** {row.get('Evidence_Filter_Reason', '')}")
                st.write(f"**Notes:** {row.get('Notes', '')}")

        st.markdown("## Full evidence table")
        st.dataframe(result, use_container_width=True)

        csv = result.to_csv(index=False).encode("utf-8")

        st.download_button(
            "Download decision table as CSV",
            data=csv,
            file_name="botanical_decision_output.csv",
            mime="text/csv",
        )

        report_text = generate_report(
            result=result,
            product_type=product_type,
            dosage_form=dosage_form,
            indication=indication,
            market=market,
        )

        st.download_button(
            "Download decision report as TXT",
            data=report_text.encode("utf-8"),
            file_name="botanical_decision_report.txt",
            mime="text/plain",
        )

st.markdown("---")

with st.expander("Current Supabase evidence database preview"):
    refreshed_df = load_evidence_database()
    st.write(f"Total records: {len(refreshed_df)}")
    st.dataframe(refreshed_df, use_container_width=True)
