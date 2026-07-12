import streamlit as st

st.markdown("---")
st.markdown("## 🔍 Diagnostic (temporary — remove after debugging)")

if st.button("Run diagnostic"):
    report = []

    # 1) Can we even import and call the Supabase client?
    try:
        from supabase_client import get_supabase_client
        client = get_supabase_client()
        report.append(("get_supabase_client()", "OK", str(type(client))))
    except Exception as exc:
        report.append(("get_supabase_client()", "FAILED", repr(exc)))
        client = None

    # 2) Can we run a raw, minimal query directly (bypassing all our own
    #    pagination/caching code entirely) to see the true row count?
    if client is not None:
        try:
            resp = client.table("plant_compounds").select("*", count="exact").limit(1).execute()
            report.append((
                "Raw count via client.table('plant_compounds')",
                "OK",
                f"reported total count = {resp.count}",
            ))
        except Exception as exc:
            report.append(("Raw count query", "FAILED", repr(exc)))

    # 3) Does our own loader (with pagination/retry) return the full data?
    try:
        from supabase_data import load_plant_compounds_df
        df = load_plant_compounds_df()
        report.append((
            "load_plant_compounds_df()",
            "OK" if not df.empty else "EMPTY",
            f"{len(df)} rows, columns: {list(df.columns)[:8]}",
        ))
    except Exception as exc:
        report.append(("load_plant_compounds_df()", "FAILED", repr(exc)))
        df = None

    # 4) Does a fresh, uncached engine actually see this data and pick
    #    "supabase" as its candidate_source?
    try:
        from botanical_rd_candidate_engine import BotanicalRDCandidateEngine
        engine = BotanicalRDCandidateEngine(use_live_search=False)
        report.append((
            "Fresh engine.candidate_source",
            "OK",
            str(engine.candidate_source),
        ))
        report.append((
            "Fresh engine.plant_compounds_df size",
            "OK",
            f"{len(engine.plant_compounds_df)} rows",
        ))
    except Exception as exc:
        report.append(("Fresh BotanicalRDCandidateEngine()", "FAILED", repr(exc)))
        engine = None

    # 5) Run the actual query for the problem indication end-to-end.
    if engine is not None:
        try:
            refs = engine._get_reference_plants(
                "Menstrual / PMS support", "Infusion", "European Union", 12
            )
            report.append((
                "engine._get_reference_plants('Menstrual / PMS support', ...)",
                "OK",
                f"{len(refs)} reference plant(s): "
                f"{refs['Scientific_Name'].tolist() if 'Scientific_Name' in refs.columns else refs.to_dict()}",
            ))
        except Exception as exc:
            report.append(("_get_reference_plants(...)", "FAILED", repr(exc)))

    st.markdown("### Results")
    for step, status, detail in report:
        icon = "✅" if status == "OK" else ("⚠️" if status == "EMPTY" else "❌")
        st.markdown(f"{icon} **{step}** — `{status}`")
        st.code(detail)

