import os
import json
import streamlit as st
from openai import OpenAI


def _streamlit_secret(name: str):
    """Read a Streamlit secret without requiring secrets.toml to exist."""
    try:
        value = st.secrets.get(name)
        return str(value).strip() if value else None
    except Exception:
        return None


def get_openai_client():
    # Environment-first is required for CLI tools and GitHub Actions.
    # Streamlit secrets remain the fallback for the deployed application.
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip() or _streamlit_secret(
        "OPENAI_API_KEY"
    )
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY is missing. Configure an environment variable for "
            "CLI/GitHub Actions or a Streamlit secret for the app."
        )
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
        "sample_size": {"type": "string"},
        "comparator": {"type": "string"},
        "main_outcome": {"type": "string"},
        "result_direction": {"type": "string"},
        "safety_signal": {"type": "string"},
        "evidence_level": {"type": "string"},
        "ema_relevance": {"type": "string"},
        "who_relevance": {"type": "string"},
        "escop_relevance": {"type": "string"},
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
        "sample_size",
        "comparator",
        "main_outcome",
        "result_direction",
        "safety_signal",
        "evidence_level",
        "ema_relevance",
        "who_relevance",
        "escop_relevance",
        "reason",
    ],
}


def extract_evidence_with_llm(record, selected_dosage_form="", selected_indication=""):
    client = get_openai_client()

    text = (
        f"Title: {record.get('Source_Title', '')}\n\n"
        f"Text:\n{record.get('Notes', '')}"
    )

    system_prompt = f"""
You are a botanical product evidence extraction engine.

Selected product dosage form: {selected_dosage_form}
Selected indication: {selected_indication}

Extract only what is supported by the provided text.

Evidence type must be one of:
Meta-analysis, Systematic Review, Randomized Controlled Trial, Clinical Study,
Observational Study, Case Report, Animal Study, In Vitro, Traditional/Regulatory,
Clinical Trial Registry, Review, Unknown.

Study model must be one of:
Human, Animal, Cell/In vitro, Traditional use, Registry, Unknown.

Evidence level must be one of:
Very High, High, Moderate, Low, Very Low, Traditional, Unknown.

Result direction must be one of:
Positive, Negative, Mixed, Neutral, Unknown.

Safety signal must be one of:
Serious, Moderate, Reassuring, None, Unknown.
Use Serious only for a documented serious/major safety risk, Moderate for a
clinically relevant caution/precaution that is not a hard serious risk,
Reassuring for explicit absence of important safety problems, None when the
text contains no safety finding, and Unknown when safety cannot be determined.

Dosage form relevance:
Direct = same dosage form as selected product.
Indirect = botanical evidence exists but dosage form differs.
Unknown = cannot determine dosage form.

EMA/WHO/ESCOP relevance:
Yes only if the text clearly mentions EMA, HMPC, WHO monograph, or ESCOP.
Otherwise No.
"""

    response = client.responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        input=[
            {"role": "system", "content": system_prompt},
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
