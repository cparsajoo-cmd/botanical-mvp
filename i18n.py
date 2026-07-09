import json
from pathlib import Path

import streamlit as st

LANGUAGES = {
    "en": "🇬🇧 English",
    "fr": "🇫🇷 Français",
    "fa": "🇮🇷 فارسی",
}

LOCALE_DIR = Path(__file__).parent / "locales"


@st.cache_data(show_spinner=False)
def load_translations(lang_code: str) -> dict:
    fallback_path = LOCALE_DIR / "en.json"
    selected_path = LOCALE_DIR / f"{lang_code}.json"

    with open(fallback_path, "r", encoding="utf-8") as f:
        fallback = json.load(f)

    if selected_path.exists():
        with open(selected_path, "r", encoding="utf-8") as f:
            selected = json.load(f)
    else:
        selected = {}

    merged = fallback.copy()
    merged.update(selected)
    return merged


def language_selector(location: str = "sidebar") -> str:
    current = st.session_state.get("language", "en")
    labels = list(LANGUAGES.values())
    codes = list(LANGUAGES.keys())
    index = codes.index(current) if current in codes else 0

    container = st.sidebar if location == "sidebar" else st
    selected_label = container.selectbox(
        "Language / Langue / زبان",
        labels,
        index=index,
        key="language_selector",
    )
    selected_code = codes[labels.index(selected_label)]
    st.session_state["language"] = selected_code
    return selected_code


def t(key: str, **kwargs) -> str:
    lang = st.session_state.get("language", "en")
    text = load_translations(lang).get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text


def apply_language_style() -> None:
    lang = st.session_state.get("language", "en")
    if lang == "fa":
        st.markdown(
            """
            <style>
            .stApp, .stMarkdown, .stText, .stCaption, .stAlert, label, p, div, span {
                direction: rtl;
                text-align: right;
            }
            .stDataFrame, .stTable, table, th, td {
                direction: ltr;
                text-align: left;
            }
            .stButton > button, .stDownloadButton > button {
                direction: rtl;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
