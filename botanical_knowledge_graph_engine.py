from supabase import create_client
import os


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def add_node(
    node_type,
    node_name,
    canonical_name=None,
    source=None,
    source_url=None,
    metadata=None,
):
    if metadata is None:
        metadata = {}

    data = {
        "node_type": node_type,
        "node_name": node_name,
        "canonical_name": canonical_name or node_name,
        "source": source,
        "source_url": source_url,
        "metadata": metadata,
    }

    try:
        supabase.table("graph_nodes").upsert(
            data,
            on_conflict="node_type,node_name",
        ).execute()
    except Exception:
        pass


def add_edge(
    source_node_type,
    source_node_name,
    relation_type,
    target_node_type,
    target_node_name,
    evidence_source=None,
    evidence_url=None,
    confidence_score=0,
    metadata=None,
):
    if metadata is None:
        metadata = {}

    data = {
        "source_node_type": source_node_type,
        "source_node_name": source_node_name,
        "relation_type": relation_type,
        "target_node_type": target_node_type,
        "target_node_name": target_node_name,
        "evidence_source": evidence_source,
        "evidence_url": evidence_url,
        "confidence_score": confidence_score,
        "metadata": metadata,
    }

    try:
        supabase.table("graph_edges").upsert(
            data,
            on_conflict=(
                "source_node_type,source_node_name,"
                "relation_type,target_node_type,target_node_name"
            ),
        ).execute()
    except Exception:
        pass


def add_plant_compound_relation(
    plant,
    compound,
    source=None,
    source_url=None,
    confidence_score=70,
):
    add_node("plant", plant, source=source, source_url=source_url)
    add_node("compound", compound, source=source, source_url=source_url)

    add_edge(
        source_node_type="plant",
        source_node_name=plant,
        relation_type="contains",
        target_node_type="compound",
        target_node_name=compound,
        evidence_source=source,
        evidence_url=source_url,
        confidence_score=confidence_score,
    )


def add_compound_target_relation(
    compound,
    target,
    mechanism=None,
    source=None,
    source_url=None,
    confidence_score=70,
):
    add_node("compound", compound, source=source, source_url=source_url)
    add_node("target", target, source=source, source_url=source_url)

    add_edge(
        source_node_type="compound",
        source_node_name=compound,
        relation_type="modulates",
        target_node_type="target",
        target_node_name=target,
        evidence_source=source,
        evidence_url=source_url,
        confidence_score=confidence_score,
        metadata={"mechanism": mechanism or ""},
    )


def add_target_indication_relation(
    target,
    indication,
    source=None,
    source_url=None,
    confidence_score=70,
):
    add_node("target", target, source=source, source_url=source_url)
    add_node("indication", indication, source=source, source_url=source_url)

    add_edge(
        source_node_type="target",
        source_node_name=target,
        relation_type="relevant_to",
        target_node_type="indication",
        target_node_name=indication,
        evidence_source=source,
        evidence_url=source_url,
        confidence_score=confidence_score,
    )


def build_graph_from_ranking(ranking_df, indication):
    if ranking_df is None or ranking_df.empty:
        return 0

    count = 0

    for _, row in ranking_df.iterrows():
        plant = row.get("Scientific_Name", "")
        compound = row.get("compound_name", "")
        target = row.get("major_target", "")
        mechanism = row.get("mechanism", "")
        source_url = row.get("Source_URL", "")
        source_title = row.get("Source_Title", "")

        if plant and compound:
            add_plant_compound_relation(
                plant=plant,
                compound=compound,
                source=source_title,
                source_url=source_url,
                confidence_score=row.get("Chemistry_Score_Unified", 70),
            )
            count += 1

        if compound and target:
            add_compound_target_relation(
                compound=compound,
                target=target,
                mechanism=mechanism,
                source=source_title,
                source_url=source_url,
                confidence_score=row.get("Target_Match_Score", 70),
            )
            count += 1

        if target and indication:
            add_target_indication_relation(
                target=target,
                indication=indication,
                source=source_title,
                source_url=source_url,
                confidence_score=row.get("Evidence_Score_Unified", 70),
            )
            count += 1

    return count
