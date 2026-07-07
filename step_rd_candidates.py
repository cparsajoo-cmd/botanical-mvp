import pandas as pd
import streamlit as st

from botanical_rd_candidate_engine import (
    BotanicalRDCandidateEngine,
    load_default_evidence,
)


def render_rd_candidate_step(inputs):
    st.markdown("## Central Botanical R&D Candidate Engine")

    st.write(
        "This engine starts from the product/problem, identifies known "
        "plant–compound–target evidence, and proposes alternative botanical "
        "R&D candidates."
    )

    run_engine = st.button(
        "Run central R&D candidate engine",
        type="primary",
    )

    if run_engine:
        evidence_df = st.session_state.get("evidence_df")

        if evidence_df is None:
            evidence_df = load_default_evidence()

        if evidence_df is None:
            evidence_df = pd.DataFrame()

        engine = BotanicalRDCandidateEngine(
            evidence_df=evidence_df,
        )

        result = engine.run(
            product_type=inputs.get("product_type", ""),
            problem=inputs.get("indication", ""),
            dosage_form=inputs.get("dosage_form", ""),
            market=inputs.get("market", ""),
            max_reference_plants=inputs.get("target_count", 50),
        )

        st.session_state["rd_candidate_df"] = result

    result = st.session_state.get("rd_candidate_df")

    if result is None:
        return

    if result.empty:
        st.warning(
            "No R&D candidates found. Add more seed plants, compounds, "
            "or evidence records for this indication."
        )
        return

    st.success(
        f"{len(result)} R&D candidate decisions generated."
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Candidates", len(result))

    with col2:
        st.metric(
            "Reference plants",
            result["Reference_Plant"].nunique(),
        )

    with col3:
        st.metric(
            "Alternative plants",
            result["Alternative_Plant"].nunique(),
        )

    strong = result[
        result["Decision_Class"].str.contains(
            "Strong",
            case=False,
            na=False,
        )
    ]

    promising = result[
        result["Decision_Class"].str.contains(
            "Promising",
            case=False,
            na=False,
        )
    ]

    st.markdown("### Strong R&D candidates")
    st.dataframe(
        strong,
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("### Promising candidates")
    st.dataframe(
        promising,
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("### Full decision table")
    st.dataframe(
        result,
        use_container_width=True,
        hide_index=True,
    )

    csv = result.to_csv(index=False).encode("utf-8")

    st.download_button(
        "Download R&D candidate decision table",
        data=csv,
        file_name="botanical_rd_candidate_decision_table.csv",
        mime="text/csv",
    )
