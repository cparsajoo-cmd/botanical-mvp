"""Shared Supabase client construction.

Configuration precedence is deliberately environment-first so CLI tools and
GitHub Actions can run without a Streamlit ``secrets.toml`` file.  Streamlit
secrets remain a fallback for the deployed app.
"""
from __future__ import annotations

import os
from typing import Optional

from supabase import create_client


def _streamlit_secret(name: str) -> Optional[str]:
    """Read one Streamlit secret without requiring secrets.toml to exist.

    Accessing ``st.secrets.get`` can itself raise
    ``StreamlitSecretNotFoundError`` when no secrets file is configured, which
    previously prevented the environment-variable fallback from running in
    GitHub Actions.
    """
    try:
        import streamlit as st

        value = st.secrets.get(name)
        return str(value).strip() if value else None
    except Exception:
        return None


def _get_setting(name: str) -> Optional[str]:
    """Return a non-empty environment value, then Streamlit fallback."""
    env_value = os.getenv(name)
    if env_value and env_value.strip():
        return env_value.strip()
    return _streamlit_secret(name)


def get_supabase_client():
    url = _get_setting("SUPABASE_URL")
    key = _get_setting("SUPABASE_KEY")

    if not url or not key:
        raise ValueError(
            "SUPABASE_URL or SUPABASE_KEY is missing. Configure environment "
            "variables for CLI/GitHub Actions or Streamlit secrets for the app."
        )

    return create_client(url, key)
