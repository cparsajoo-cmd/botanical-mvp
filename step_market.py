import streamlit as st
import pandas as pd

from market_intelligence_engine import MarketIntelligenceEngine


def render_market_step():
    ranking = st.session_state.get("ranking")

    if ranking is None or ranking.empty:
        return

    st.markdown("---")
    st.markdown("## Step 8.5 — Market Intelligence")

    if st.button("Step 8.5: Analyze market potential"):
        engine = MarketIntelligenceEngine()
        results = []

        for _, row in ranking.iterrows():
            result = engine.evaluate(row)
            results.append(result)

        market_df = pd.DataFrame(results)
        st.session_state["market_df"] = market_df

    market_df = st.session_state.get("market_df")

    if market_df is None or market_df.empty:
        return

    st.success(f"{len(market_df)} market intelligence records generated.")

    st.dataframe(
        market_df,
        use_container_width=True,
        hide_index=True,
    )

    csv = market_df.to_csv(index=False).encode("utf-8")

    st.download_button(
        "Download market intelligence as CSV",
        data=csv,
        file_name="market_intelligence.csv",
        mime="text/csv",
    )
