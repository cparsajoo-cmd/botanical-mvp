import os
import pandas as pd
from supabase import create_client


def get_supabase_client():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")

    if not url or not key:
        raise ValueError("SUPABASE_URL or SUPABASE_KEY is missing.")

    return create_client(url, key)


def save_compound_profile(record):
    supabase = get_supabase_client()

    response = (
        supabase
        .table("compound_profiles")
        .insert(record)
        .execute()
    )

    if response.data:
        return response.data[0].get("id")

    return None


def load_compound_profiles():
    supabase = get_supabase_client()

    response = (
        supabase
        .table("compound_profiles")
        .select("*")
        .execute()
    )

    data = response.data or []

    if not data:
        return pd.DataFrame()

    return pd.DataFrame(data)
