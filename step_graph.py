import streamlit as st
import pandas as pd
from evidence_database import load_evidence_database


def _safe(x):
    if x is None:
        return ""
    x = str(x).strip()
    if x.lower() in ["nan", "none", "null"]:
        return ""
    return x


def _add_relation(rows, source_type, source, relation, target_type, target, evidence="", score=""):
    source = _safe(source)
    target = _safe(target)

    if not source or not target:
        return

    rows.append({
        "Source_Type": source_type,
        "Source": source,
        "Relation": relation,
        "Target_Type": target_type,
        "Target": target,
        "Evidence": _safe(evidence),
        "Score": score,
    })


def build_graph_relations():
    rows = []

    ranking = st.session_state.get("ranking")
    knowledge_df = st.session_state.get("knowledge_df")
    white_space_df = st.session_state.get("white_space_df")
    mechanism_df = st.session_state.get("mechanism_df")

    # 1) Ranking relations
    if ranking is not None and not ranking.empty:
        for _, r in ranking.iterrows():
            plant = r.get("Scientific_Name", "")
            common = r.get("Common_Name", "")
            compound = r.get("compound_name", "")
            target = r.get("major_target", "")
            mechanism = r.get("mechanism", "")
            decision = r.get("Decision_Category", "")
            score = r.get("Final_RnD_Score", "")

            _add_relation(rows, "Plant", plant, "has_common_name", "Common name", common)
            _add_relation(rows, "Plant", plant, "contains_compound", "Compound", compound, decision, score)
            _add_relation(rows, "Compound", compound, "acts_on_target", "Target", target, decision, score)
            _add_relation(rows, "Compound", compound, "has_mechanism", "Mechanism", mechanism, decision, score)
            _add_relation(rows, "Plant", plant, "has_decision", "Decision", decision, decision, score)

    # 2) Knowledge extraction relations
    if knowledge_df is not None and not knowledge_df.empty:
        for _, r in knowledge_df.iterrows():
            plant = r.get("Plant", "")
            compound = r.get("Compound", "")
            target = r.get("Target", "")
            mechanism = r.get("Mechanism", "")
            indication = r.get("Indication", "")
            evidence_type = r.get("Evidence_Type", "")
            confidence = r.get("Confidence", "")

            _add_relation(rows, "Plant", plant, "contains_compound", "Compound", compound, evidence_type, confidence)
            _add_relation(rows, "Compound", compound, "acts_on_target", "Target", target, evidence_type, confidence)
            _add_relation(rows, "Compound", compound, "has_mechanism", "Mechanism", mechanism, evidence_type, confidence)
            _add_relation(rows, "Plant", plant, "relevant_to_indication", "Indication", indication, evidence_type, confidence)
            _add_relation(rows, "Target", target, "linked_to_indication", "Indication", indication, evidence_type, confidence)
            _add_relation(rows, "Mechanism", mechanism, "linked_to_indication", "Indication", indication, evidence_type, confidence)

    # 3) White-space relations
    if white_space_df is not None and not white_space_df.empty:
        for _, r in white_space_df.iterrows():
            known = r.get("Original_Known_Plant", "")
            new = r.get("New_Candidate_Plant", "")
            compound = r.get("Active_Compound", "")
            category = r.get("White_Space_Category", "")
            score = r.get("White_Space_Score", "")

            _add_relation(rows, "Known plant", known, "shares_compound_opportunity_with", "New candidate plant", new, category, score)
            _add_relation(rows, "Compound", compound, "creates_white_space_candidate", "Plant", new, category, score)

    # 4) Mechanism discovery relations
    if mechanism_df is not None and not mechanism_df.empty:
        for _, r in mechanism_df.iterrows():
            source = r.get("Source_Plant", "")
            candidate = r.get("New_Candidate_Plant", "")
            target = r.get("Shared_Target", "")
            mechanism = r.get("Shared_Mechanism", "")
            category = r.get("Mechanism_Category", "")
            score = r.get("Mechanism_Discovery_Score", "")

            _add_relation(rows, "Source plant", source, "mechanism_similarity_candidate", "New candidate plant", candidate, category, score)
            _add_relation(rows, "Target", target, "connects_plants", "Plant pair", f"{source} → {candidate}", category, score)
            _add_relation(rows, "Mechanism", mechanism, "connects_plants", "Plant pair", f"{source} → {candidate}", category, score)

    # 5) Fallback from Supabase evidence database
    if not rows:
        try:
            evidence_df = load_evidence_database()
        except Exception:
            evidence_df = pd.DataFrame()

        if evidence_df is not None and not evidence_df.empty:
            for _, r in evidence_df.iterrows():
                plant = (
                    r.get("plant", "")
                    or r.get("scientific_name", "")
                    or r.get("Scientific_Name", "")
                    or r.get("common_name", "")
                )

                compound = (
                    r.get("compound", "")
                    or r.get("compound_name", "")
                    or r.get("Compound", "")
                )

                source = r.get("source", "") or r.get("Source", "")
                title = r.get("title", "") or r.get("source_title", "") or r.get("Source_Title", "")
                url = r.get("source_url", "") or r.get("url", "")

                _add_relation(rows, "Plant", plant, "has_evidence_source", "Source", source, title, "")
                _add_relation(rows, "Plant", plant, "contains_compound", "Compound", compound, title, "")
                _add_relation(rows, "Evidence", title, "has_url", "URL", url, source, "")

    graph_df = pd.DataFrame(rows)

    if graph_df.empty:
        return graph_df

    graph_df = graph_df.drop_duplicates().reset_index(drop=True)
    graph_df.insert(0, "Relation_ID", range(1, len(graph_df) + 1))

    return graph_df


def render_graph_step(inputs):
    st.markdown("---")
    st.markdown("## Step 9 — Build Botanical Knowledge Graph")

    st.write(
        "This builds and displays plant–compound–target–mechanism–indication relationships."
    )

    if st.button("Step 9: Build Knowledge Graph"):
        graph_df = build_graph_relations()
        st.session_state["graph_df"] = graph_df

    graph_df = st.session_state.get("graph_df")

    if graph_df is None:
        return

    if graph_df.empty:
        st.warning("No graph relations found yet.")
        return

    st.success(f"{len(graph_df)} graph relations built.")

    c1, c2, c3 = st.columns(3)

    with c1:
        st.metric("Relations", len(graph_df))

    with c2:
        st.metric("Source nodes", graph_df["Source"].nunique())

    with c3:
        st.metric("Target nodes", graph_df["Target"].nunique())

    st.markdown("### Graph relation table")
    st.dataframe(graph_df, use_container_width=True, hide_index=True)

    st.markdown("### Relations by type")
    relation_counts = (
        graph_df.groupby("Relation")
        .size()
        .reset_index(name="Count")
        .sort_values("Count", ascending=False)
    )
    st.dataframe(relation_counts, use_container_width=True, hide_index=True)

    st.markdown("### Node types")
    node_types = pd.concat([
        graph_df[["Source_Type", "Source"]].rename(columns={"Source_Type": "Node_Type", "Source": "Node"}),
        graph_df[["Target_Type", "Target"]].rename(columns={"Target_Type": "Node_Type", "Target": "Node"}),
    ]).drop_duplicates()

    node_summary = (
        node_types.groupby("Node_Type")
        .size()
        .reset_index(name="Count")
        .sort_values("Count", ascending=False)
    )

    st.dataframe(node_summary, use_container_width=True, hide_index=True)

    csv = graph_df.to_csv(index=False).encode("utf-8")

    st.download_button(
        "Download knowledge graph relations as CSV",
        data=csv,
        file_name="botanical_knowledge_graph_relations.csv",
        mime="text/csv",
    )
