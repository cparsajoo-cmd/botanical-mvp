import os
import json
import streamlit as st
from openai import OpenAI


def get_openai_client():
    api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is missing.")
    return OpenAI(api_key=api_key)


EVIDENCE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "plant_scientific_name": {"type": "string"},
        "evidence_type": {"type": "string"},
        "study_model": {"type": "string"},
        "dosage_form": {"type": "string"},
        "target_indication": {"type": "string"},
        "dosage_form_relevance": {"type": "string"},
        "population": {"type": "string"},
        "comparator": {"type": "string"},
        "main_outcome": {"type": "string"},
        "safety_signal": {"type": "string"},
        "evidence_level": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": [
        "plant_scientific_name",
        "evidence_type",
        "study_model",
        "dosage_form",
        "target_indication",
        "dosage_form_relevance",
        "population",
        "comparator",
        "main_outcome",
        "safety_signal",
        "evidence_level",
        "reason",
    ],
}


def extract_evidence_with_llm(record, selected_dosage_form="", selected_indication=""):
    client = get_openai_client()

    text = (
        f"Title: {record.get('Source_Title', '')}\n\n"
        f"Abstract/Text:\n{record.get('Notes', '')}"
    )

    prompt = f"""
You are a scientific evidence extraction engine for botanical product development.

User-selected dosage form: {selected_dosage_form}
User-selected indication: {selected_indication}

Extract structured evidence from the text.
Classify dosage_form_relevance as:
- Direct: same dosage form as selected
- Indirect: botanical evidence exists but dosage form differs
- Unknown: dosage form cannot be determined

Evidence type must be one of:
Meta-analysis, Systematic Review, Randomized Controlled Trial, Clinical Study,
Observational Study, Case Report, Animal Study, In Vitro, Traditional/Regulatory, Review, Unknown.

Study model must be:
Human, Animal, Cell/In vitro, Traditional use, Unknown.

Evidence level must be:
Very High, High, Moderate, Low, Very Low, Traditional, Unknown.
"""

    response = client.responses.create(
        model="gpt-5.5-mini",
        input=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": text},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "botanical_evidence_extraction",
                "schema": EVIDENCE_SCHEMA,
                "strict": True,
            }
        },
    )

    return json.loads(response.output_text)
