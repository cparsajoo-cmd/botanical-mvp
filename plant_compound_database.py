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

    # No unique constraint exists on this table, so repeated processing
    # of the same plant (retries, re-running Bulk Evidence, the same
    # paper turning up across multiple search-keyword variations for the
    # same plant) was inserting the exact same (plant, compound, source
    # paper) row over and over — some plant/compound/paper combinations
    # ended up duplicated 25+ times. That's wasted storage at best, and
    # at worst silently inflates anything downstream that counts rows
    # rather than distinct facts. Checking for an existing match first
    # makes this idempotent — safe to re-run the same search on the same
    # plant any number of times — for any plant, any compound, any
    # source, not just the ones that happened to surface this so far.
    scientific_name = record.get("scientific_name", "")
    compound_name = record.get("compound_name", "")
    reference_title = record.get("reference_title", "")
    reference_url = record.get("reference_url", "")

    if scientific_name and compound_name and (reference_title or reference_url):
        query = (
            supabase.table("plant_compounds")
            .select("id")
            .eq("scientific_name", scientific_name)
            .eq("compound_name", compound_name)
        )
        if reference_url:
            query = query.eq("reference_url", reference_url)
        else:
            query = query.eq("reference_title", reference_title)

        existing = query.limit(1).execute()
        if existing.data:
            return existing.data[0].get("id")

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
