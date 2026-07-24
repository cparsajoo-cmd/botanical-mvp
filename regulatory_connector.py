"""
SPRINT 5, PHASE A, ISSUE 2 — this module's REGULATORY_DB (below) was
identified in the Sprint 5 audit as a source of FABRICATED regulatory
data still reachable in production (via multi_source_collector.py's
Step 2 bulk evidence collection). Its "EMA_Status": "Yes" /
"WHO_Status": "Yes"/"No" / "ESCOP_Status": "Yes" values for these 4
plants were never independently verified against a real source, yet
appeared identical in shape to genuine connector output.

REGULATORY_DB is kept (not deleted) as historical reference. It is
disabled from production via the flag below — search_regulatory_sources()
now always calls the real ema_regulatory_connector, for every plant,
including these 4. Do not silently flip this flag back on; if there is
ever a specific, reviewed reason to trust this dict again, that
decision (and who verified it, and when) belongs in a comment right
here, not a silent revert.
"""
_LEGACY_STUB_ENABLED = False

REGULATORY_DB = {
    "Valeriana officinalis": {
        "EMA_Status": "Yes",
        "WHO_Status": "Yes",
        "ESCOP_Status": "Yes",
        "Regulatory_Status": "EMA/HMPC, WHO and ESCOP support for traditional use in mild nervous tension and sleep disorders.",
    },
    "Passiflora incarnata": {
        "EMA_Status": "Yes",
        "WHO_Status": "No",
        "ESCOP_Status": "Yes",
        "Regulatory_Status": "EMA/HMPC and ESCOP support for traditional use in mild symptoms of mental stress and sleep aid.",
    },
    "Melissa officinalis": {
        "EMA_Status": "Yes",
        "WHO_Status": "No",
        "ESCOP_Status": "Yes",
        "Regulatory_Status": "EMA/HMPC and ESCOP support for traditional use in mild stress and sleep disorders.",
    },
    "Lavandula angustifolia": {
        "EMA_Status": "Yes",
        "WHO_Status": "No",
        "ESCOP_Status": "Yes",
        "Regulatory_Status": "EMA/HMPC and ESCOP support for traditional use in mild stress and exhaustion.",
    },
}


def search_regulatory_sources(
    scientific_name,
    indication,
    dosage_form="",
    market="European Union",
):
    """Regulatory lookup — see ema_regulatory_connector.py's module
    docstring for exactly what the real connector can and can't tell you.

    SPRINT 5 PHASE A, ISSUE 2 (production bug fix): this function
    previously checked REGULATORY_DB (the hand-typed dict above) FIRST,
    for exactly 4 plants — returning FABRICATED "EMA_Status": "Yes" /
    "WHO_Status": "Yes"/"No" / "ESCOP_Status": "Yes" values that were
    never independently verified against any real source, while
    APPEARING in "Sources checked" output identically to genuine API
    results. Combined with Phase A Issue 1's separate bug (a string-
    format mismatch that meant the REAL connector's output could never
    satisfy _market_status()'s old comparison), this stub was, in
    practice, the ONLY thing that could ever make "Regulatory monograph
    exists" appear anywhere in this pipeline — and only for these 4
    plants, with data nobody actually verified.

    RESOLUTION: REGULATORY_DB is NOT deleted (kept below as historical
    reference — it documents what a human once believed, even though
    it should not have been presented as verified). It is disabled from
    production via _LEGACY_STUB_ENABLED (default False) — every call
    now goes straight to the real ema_regulatory_connector, for EVERY
    plant, including the original 4. If there is ever a specific,
    reviewed reason to re-enable the legacy dict for those 4 plants
    (e.g. someone has since independently verified it against the real
    EMA/WHO/ESCOP sources), flip that one flag with a comment explaining
    why and when — do not silently restore this branch.
    """
    if _LEGACY_STUB_ENABLED:
        data = REGULATORY_DB.get(scientific_name)
        if data:
            return [{
                "Scientific_Name": scientific_name,
                "Common_Name": "",
                "Product_Type": "Herbal product",
                "Dosage_Form": dosage_form,
                "Target_Indication": indication,
                "Target_Market": market,

                "Source_Type": "Regulatory",
                "Source_Organization": "EMA/WHO/ESCOP seed database",
                "Source_Title": f"Regulatory evidence summary for {scientific_name}",
                "Source_URL": "",
                "Source_Year": "",

                "Notes": data["Regulatory_Status"],

                "Publication_Type": "Traditional/Regulatory",
                "Evidence_Type": "Traditional/Regulatory",
                "Study_Type": "Traditional/Regulatory",
                "Study_Model": "Traditional use",
                "Evidence_Level": "Traditional",

                "EMA_Status": data["EMA_Status"],
                "WHO_Status": data["WHO_Status"],
                "ESCOP_Status": data["ESCOP_Status"],

                "Clinical_Level": "Not found",
                "Clinical_RCT_Count": 0,
                "Meta_Level": "Not found",
                "Meta_Count": 0,

                "Detected_Dosage_Forms": dosage_form,
                "Detected_Indications": indication,
                "Dosage_Form_Relevance": "Direct",

                "Safety_Level": "To verify",
                "Safety_Signal": "",
                "Drug_Interaction_Level": "To verify",
                "Commercial_Level": "Unknown",
                "Regulatory_Status": data["Regulatory_Status"],
                "Novel_Food_Status": "To verify",

                "Population": "Traditional adult use",
                "Sample_Size": "",
                "Comparator": "",
                "Primary_Outcome": "Traditional regulatory support",
                "Result_Direction": "Positive",
            }]

    try:
        from ema_regulatory_connector import search_regulatory_sources_real
        return search_regulatory_sources_real(
            scientific_name, indication, dosage_form, market
        )
    except Exception as exc:
        return [{
            "Scientific_Name": scientific_name,
            "Common_Name": "",
            "Product_Type": "Herbal product",
            "Dosage_Form": dosage_form,
            "Target_Indication": indication,
            "Target_Market": market,
            "Source_Type": "Regulatory",
            "Source_Organization": "EMA HMPC (lookup unavailable)",
            "Source_Title": "EMA HMPC inventory of herbal substances",
            "Source_URL": "",
            "Source_Year": "",
            "Notes": f"Real EMA lookup failed: {exc}",
            "Evidence_Level": "Not available",
            "EMA_Status": "Not yet verified",
            "WHO_Status": "Not yet verified",
            "ESCOP_Status": "Not yet verified",
            "Regulatory_Status": "Lookup failed — see Notes.",
        }]
