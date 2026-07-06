import streamlit as st
import pandas as pd
from ai_opportunity_engine import build_opportunity_table


def render_opportunity_step():
    ranking = st.session_state.get("ranking")

    if ranking is None or ranking.empty:
        return

    st.markdown("---")
    st.markdown("## Step 8 — AI Opportunity Assessment")

    opportunities = build_opportunity_table(ranking)

    if not opportunities:
        st.info("No opportunity assessment generated.")
        return

    opportunity_df = pd.DataFrame(opportunities)
    st.session_state["opportunity_df"] = opportunity_df

    st.success(f"{len(opportunity_df)} AI opportunity assessments generated.")

    opportunity_cols = [
        "Plant",
        "Compound",
        "Current_Class",
        "AI_Opportunity_Decision",
        "Investment_Opportunity_Score",
        "Overall_Risk_Score",
        "Scientific_Strength",
        "Chemistry_Strength",
        "Target_Relevance",
        "Regulatory_Readiness",
        "Safety_Profile",
        "Innovation_Opportunity",
        "Market_Saturation_Risk",
        "Patent_Crowding_Risk",
        "AI_Opportunity_Summary",
    ]

    opportunity_cols = [c for c in opportunity_cols if c in opportunity_df.columns]

    st.dataframe(
        opportunity_df[opportunity_cols],
        use_container_width=True,
        hide_index=True,
    )

    opportunity_csv = opportunity_df.to_csv(index=False).encode("utf-8")

    st.download_button(
        "Download AI opportunity assessment as CSV",
        data=opportunity_csv,
        file_name="ai_opportunity_assessment.csv",
        mime="text/csv",
    )
