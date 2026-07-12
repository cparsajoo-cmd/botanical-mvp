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

    # 6) Inspect the RAW indication column content directly -- is it
    # possibly truncated on the way into Supabase? Show length stats and
    # a couple of real samples for rows SQL already confirmed contain
    # "premenstrual".
    if df is not None and not df.empty and "indication" in df.columns:
        try:
            lengths = df["indication"].fillna("").astype(str).str.len()
            report.append((
                "indication column length stats",
                "OK",
                f"min={lengths.min()}, max={lengths.max()}, "
                f"mean={lengths.mean():.1f}, "
                f"rows at exactly max length={int((lengths == lengths.max()).sum())}",
            ))

            pms_rows = df[
                df["indication"].fillna("").astype(str).str.contains(
                    "premenstrual", case=False
                )
            ]
            report.append((
                "Rows where indication contains 'premenstrual' (pandas-side)",
                "OK" if not pms_rows.empty else "EMPTY",
                f"{len(pms_rows)} row(s)",
            ))
            if not pms_rows.empty:
                sample = pms_rows.iloc[0]
                report.append((
                    "Sample matching row",
                    "OK",
                    f"scientific_name={sample.get('scientific_name')}, "
                    f"compound_name={sample.get('compound_name')}, "
                    f"indication (repr, full)={repr(sample.get('indication'))}",
                ))
        except Exception as exc:
            report.append(("indication column inspection", "FAILED", repr(exc)))

    # 7) Replicate _reference_plants_from_supabase's internal logic
    # step-by-step, OUTSIDE the method, to see exactly where the row
    # count collapses.
    if df is not None and not df.empty and engine is not None:
        try:
            problem = "Menstrual / PMS support"
            problem_norm = engine._norm(problem)

            indication_norm = df["indication"].fillna("").map(engine._norm)

            mask1 = indication_norm.apply(
                lambda text: bool(text) and (problem_norm in text or text in problem_norm)
            )
            report.append((
                "Step-by-step: full-string containment mask.sum()",
                "OK",
                f"{int(mask1.sum())} rows matched (expected near 0)",
            ))

            problem_tokens = engine._meaningful_tokens(problem_norm)
            mask2 = indication_norm.apply(
                lambda text: bool(text)
                and engine._tokens_overlap(problem_tokens, engine._meaningful_tokens(text))
            )
            report.append((
                "Step-by-step: token-overlap mask.sum()",
                "OK",
                f"problem_tokens={problem_tokens}, {int(mask2.sum())} rows matched",
            ))

            matched_rows = df[mask2]
            report.append((
                "Step-by-step: matched_rows shape / unique plants",
                "OK",
                f"{matched_rows.shape[0]} rows, "
                f"{matched_rows['scientific_name'].nunique()} unique scientific_name values",
            ))

            if not matched_rows.empty:
                sample_plants = matched_rows["scientific_name"].dropna().unique()[:15]
                report.append((
                    "Step-by-step: sample matched plant names",
                    "OK",
                    str(list(sample_plants)),
                ))
        except Exception as exc:
            report.append(("Step-by-step replication", "FAILED", repr(exc)))

    st.markdown("### Results")
    for step, status, detail in report:
        icon = "✅" if status == "OK" else ("⚠️" if status == "EMPTY" else "❌")
        st.markdown(f"{icon} **{step}** — `{status}`")
        st.code(detail)
