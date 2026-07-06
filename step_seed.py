import streamlit as st
from compound_profile_seed import seed_compound_profiles


def render_seed_step():
    st.markdown("---")
    st.markdown("## Step 2 — Prepare compound database")

    if st.button("Step 2: Seed compound profiles"):
        saved_count = seed_compound_profiles()
        st.success(f"{saved_count} compound profiles saved.")
