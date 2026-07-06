import streamlit as st
from ai_discovery_engine import understand_question


def render_question_step(inputs):
    st.markdown("---")
    st.markdown("## Step 1 — Understand question")

    if st.button("Step 1: Understand R&D question"):
        question = understand_question(
            therapeutic_area=inputs["indication"],
            dosage_form=inputs["dosage_form"],
            target_market=inputs["market"],
        )

        st.session_state["question"] = question

        if question is None:
            st.warning("No therapeutic profile found for this indication yet.")
        else:
            st.success("Question understood.")
            st.write("**Therapeutic area:**", question.get("therapeutic_area"))
            st.write("**Dosage form:**", question.get("dosage_form"))
            st.write("**Target market:**", question.get("target_market"))
            st.write("**Targets:**")
            st.write(", ".join(question.get("targets", [])))
            st.write("**Search keywords:**")
            st.write(", ".join(question.get("keywords", [])))
            st.write("**Compound classes:**")
            st.write(", ".join(question.get("compound_classes", [])))
