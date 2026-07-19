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

st.markdown("---")
st.markdown("## 🌿 EMA regulatory pipeline diagnostic (temporary)")
st.caption(
    "Tests the REAL, currently-deployed code directly — the exact same "
    "functions the app itself calls — with no Supabase writes/deletes "
    "involved. If this shows the right Evidence_Level here but Supabase "
    "still shows 'Unknown', the problem is in the save step or old "
    "leftover data. If it's already wrong HERE, the deployed code itself "
    "isn't what we think it is (e.g. the file didn't actually save/"
    "deploy) — that narrows things down immediately, in one click."
)

if st.button("Run EMA pipeline diagnostic"):
    ema_report = []

    try:
        import ema_regulatory_connector as ema_mod
        import importlib
        importlib.reload(ema_mod)
        ema_report.append((
            "import ema_regulatory_connector",
            "OK",
            f"module file: {ema_mod.__file__}",
        ))
    except Exception as exc:
        ema_report.append(("import ema_regulatory_connector", "FAILED", repr(exc)))
        ema_mod = None

    if ema_mod is not None:
        try:
            records = ema_mod.search_regulatory_sources_real(
                "Valeriana officinalis", "Sleep", "Infusion", "European Union"
            )
            r = records[0]
            ema_report.append((
                "search_regulatory_sources_real('Valeriana officinalis')",
                "OK",
                f"Evidence_Level={r.get('Evidence_Level')!r}, "
                f"EMA_Status={r.get('EMA_Status')!r}, "
                f"Source_Title={r.get('Source_Title')!r}",
            ))
        except Exception as exc:
            ema_report.append((
                "search_regulatory_sources_real('Valeriana officinalis')",
                "FAILED", repr(exc),
            ))
            r = None

        if r is not None:
            try:
                import evidence_standardizer as es_mod
                importlib.reload(es_mod)
                ema_report.append((
                    "import evidence_standardizer",
                    "OK",
                    f"module file: {es_mod.__file__}",
                ))
                standardized = es_mod.standardize_extracted_record(
                    r,
                    {
                        "source_type": r.get("Source_Type", "Regulatory"),
                        "source_title": r.get("Source_Title", ""),
                        "source_url": r.get("Source_URL", ""),
                        "source_organization": r.get("Source_Organization", ""),
                        "source_year": r.get("Source_Year", ""),
                    },
                )
                final_level = standardized.get("Evidence_Level")
                ema_report.append((
                    "standardize_extracted_record(...) final Evidence_Level",
                    "OK" if final_level and final_level != "Unknown" else "STILL WRONG",
                    f"Evidence_Level={final_level!r}",
                ))
            except Exception as exc:
                ema_report.append((
                    "standardize_extracted_record(...)", "FAILED", repr(exc),
                ))

    try:
        import regulatory_connector as rc_mod
        importlib.reload(rc_mod)
        recs = rc_mod.search_regulatory_sources(
            "Rosa canina", "General wellness", "Infusion", "European Union"
        )
        ema_report.append((
            "regulatory_connector.search_regulatory_sources('Rosa canina') "
            "(a plant NOT in the 4-plant curated dict — should use the real connector)",
            "OK",
            f"{recs[0].get('EMA_Status') if recs else 'NO RECORDS'}",
        ))
    except Exception as exc:
        ema_report.append((
            "regulatory_connector.search_regulatory_sources('Rosa canina')",
            "FAILED", repr(exc),
        ))

    st.markdown("### EMA diagnostic results")
    for step, status, detail in ema_report:
        icon = "✅" if status == "OK" else ("⚠️" if status == "STILL WRONG" else "❌")
        st.markdown(f"{icon} **{step}** — `{status}`")
        st.code(detail)
