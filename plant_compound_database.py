import os
from supabase import create_client


def get_supabase_client():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")

    if not url or not key:
        raise ValueError("SUPABASE_URL or SUPABASE_KEY is missing.")

    return create_client(url, key)


def save_plant_compound_record(record):
    supabase = get_supabase_client()

    response = (
        supabase
        .table("plant_compounds")
        .insert(record)
        .execute()
    )

    if response.data:
        return response.data[0].get("id")

    return None


def load_plant_compound_database():
    supabase = get_supabase_client()

    response = (
        supabase
        .table("plant_compounds")
        .select("*")
        .execute()
    )

    return response.data or []
