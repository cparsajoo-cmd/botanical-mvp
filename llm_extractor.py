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

# ---------------------------------------------------------------------------
# High-stakes semantic gate extraction
# ---------------------------------------------------------------------------
# Kept separate from EVIDENCE_SCHEMA so existing ingestion/backfill contracts
# remain backward compatible.  The output is assertion-level evidence only;
# it never emits GO/NO-GO decisions.

GATE_ASSERTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "safety_assertions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "hazard_present": {"type": "boolean"},
                    "hazard_type": {
                        "type": "string",
                        "enum": [
                            "fatal_adverse_event", "serious_adverse_event", "organ_toxicity",
                            "contraindication", "serious_drug_interaction", "pregnancy",
                            "lactation", "pediatric_restriction", "qt_prolongation",
                            "bleeding_risk", "allergic_risk", "carcinogenicity",
                            "genotoxicity", "reproductive_toxicity",
                            "major_regulatory_safety_warning", "warning", "precaution",
                            "reassurance", "other"
                        ],
                    },
                    "reported_outcome": {"type": "string"},
                    "seriousness": {
                        "type": "string",
                        "enum": ["serious", "moderate", "minor", "none", "unknown"],
                    },
                    "seriousness_criterion": {
                        "type": "string",
                        "enum": [
                            "death", "life_threatening", "hospitalization",
                            "persistent_or_significant_disability", "congenital_anomaly",
                            "medically_important_event", "major_organ_injury",
                            "explicit_serious_warning", "none", "unknown"
                        ],
                    },
                    "polarity": {
                        "type": "string",
                        "enum": ["risk_present", "risk_absent", "conditional", "mechanistic_only"],
                    },
                    "causal_relationship": {
                        "type": "string",
                        "enum": ["causal", "associated", "suspected", "hypothetical", "unclear"],
                    },
                    "preparation": {"type": "string"},
                    "route": {"type": "string"},
                    "dose_dependency": {"type": "string"},
                    "affected_population": {"type": "array", "items": {"type": "string"}},
                    "context_applicability": {
                        "type": "string",
                        "enum": ["relevant", "irrelevant", "unknown"],
                    },
                    "supporting_text": {"type": "string"},
                    "extraction_confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": [
                    "hazard_present", "hazard_type", "reported_outcome", "seriousness",
                    "seriousness_criterion", "polarity", "causal_relationship", "preparation", "route",
                    "dose_dependency", "affected_population", "context_applicability",
                    "supporting_text", "extraction_confidence"
                ],
            },
        },
        "regulatory_assertions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "prohibited", "authorization_required", "authorized",
                            "authorized_with_conditions", "refused", "withdrawn",
                            "suspended", "pending", "restricted", "not_authorized",
                            "terminated", "unclear"
                        ],
                    },
                    "market_access_effect": {
                        "type": "string",
                        "enum": ["blocks_market_access", "conditional_access", "no_block", "unclear"],
                    },
                    "jurisdiction": {"type": "string"},
                    "authority": {"type": "string"},
                    "ingredient": {"type": "string"},
                    "plant_part": {"type": "string"},
                    "preparation": {"type": "string"},
                    "route": {"type": "string"},
                    "product_category": {"type": "string"},
                    "conditions": {"type": "string"},
                    "effective_date": {"type": "string"},
                    "context_applicability": {
                        "type": "string",
                        "enum": ["relevant", "irrelevant", "unknown"],
                    },
                    "supporting_text": {"type": "string"},
                    "extraction_confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": [
                    "action", "market_access_effect", "jurisdiction", "authority",
                    "ingredient", "plant_part", "preparation", "route",
                    "product_category", "conditions", "effective_date",
                    "context_applicability", "supporting_text", "extraction_confidence"
                ],
            },
        },
    },
    "required": ["safety_assertions", "regulatory_assertions"],
}


def extract_gate_assertions_with_llm(record, candidate_context=""):
    """Extract auditable safety/regulatory assertions from ONE evidence record.

    The function intentionally does not produce a recommendation.  Callers must
    validate supporting spans and pass assertions through deterministic gate
    policy.  This separation prevents prompt/model changes from directly
    redefining NO-GO policy.
    """
    client = get_openai_client()
    title = str(record.get("Source_Title") or record.get("title") or "")
    body = str(record.get("Notes") or record.get("text") or record.get("assertion_text") or "")
    source_text = body

    system_prompt = f"""
You extract safety and regulatory ASSERTIONS from botanical scientific or
regulatory evidence. You do not make GO/NO-GO decisions.

Evidence title (metadata only; supporting_text must come from the evidence text, not the title):
{title}

Candidate context, when available:
{candidate_context}

Critical rules:
1. Use only facts stated in the supplied record. Never infer a ban, toxicity,
   authorization, jurisdiction, route, preparation, dose, population, or causal
   relationship that is not supported by the text.
2. Every assertion MUST include supporting_text copied VERBATIM from the input.
   If no exact supporting span exists, emit no assertion for that claim.
3. Distinguish model/extraction certainty from seriousness. A clearly extracted
   minor event is not serious; a serious event in a weak source is still
   semantically serious.
4. Negation matters. "No hepatotoxicity was observed" is reassurance, not risk.
5. Animal/in-vitro or hypothetical/mechanistic findings must not be rewritten as
   documented human clinical harm. Preserve uncertainty in causal_relationship.
6. A regulatory requirement is not automatically a prohibition. Distinguish:
   authorization_required, pending, authorized, authorized_with_conditions,
   refused, withdrawn, suspended, not_authorized, terminated, restricted,
   prohibited, and unclear.
6b. A regulatory action can only come from a government/statutory authority
    with legal power over market access (e.g. EMA, FDA, EFSA, a national
    medicines/food agency, or an official government decision). A
    professional medical society, clinical association, specialty college,
    advisory body, or expert panel changing or withdrawing its OWN clinical
    recommendation/guideline is NOT a regulatory action and must never be
    extracted as one, however strongly worded ("withdrew its
    recommendation", "no longer recommends", "advises against use") -- that
    is a clinical-practice opinion, not a market-access determination. If
    the text does not name a body with actual legal/statutory market-access
    authority, do not emit a regulatory_assertion for it at all.
7. market_access_effect=blocks_market_access only when the text itself establishes
   that the matched product/context cannot legally be marketed/accessed now.
   A generic statement that something is a "novel food" is insufficient by
   itself unless the record also establishes the applicable authorization state.
8. If context applicability cannot be established from both the source and the
   supplied candidate context, use unknown rather than guessing.
9. "serious" is a high-threshold clinical category, not a synonym for
   "adverse", "clinically relevant", "toxicity", or "side effect". Set
   seriousness=serious ONLY when the supplied supporting span explicitly supports
   at least one seriousness_criterion other than none/unknown: death;
   life-threatening harm; hospitalization; persistent/significant disability;
   congenital anomaly; a medically important event requiring intervention to
   prevent one of those outcomes; major/irreversible organ injury; or an explicit
   serious regulator/contraindication warning.
10. Common tolerability findings such as local burning/irritation, itching,
    headache, dizziness, nausea, mild GI symptoms, transient discomfort, or a
    generic list of side effects are NOT serious unless the same record explicitly
    states one of the serious criteria above. Classify them minor/moderate as the
    text warrants.
11. Statements such as "more toxicity tests are needed", "further safety studies
    are required", "safety remains uncertain", or "data are insufficient" describe
    evidence uncertainty, not an observed hazard. Do not convert them into a
    risk-present safety assertion unless the text separately reports an actual
    adverse outcome or precaution.
12. medically_important_event is not a catch-all for uncomfortable symptoms. Use
    it only when the text indicates an event requiring medical intervention to
    prevent death, life-threatening harm, hospitalization, disability, congenital
    anomaly, or comparable serious deterioration.
13. If seriousness=serious, seriousness_criterion MUST be a specific criterion
    other than none/unknown. If no such criterion is explicitly supported, choose
    moderate/minor/unknown instead.
14. Do not let reassuring text erase a separate risk assertion; emit both when
    the record genuinely contains both.
"""

    # Use the project's already-working evidence model as the safe default.
    # OPENAI_GATE_MODEL is optional; if it is stale/invalid, retry exactly once
    # with OPENAI_MODEL (or the legacy project default). This keeps a bad gate
    # model secret from breaking a bounded shadow/backfill run.
    project_model = (os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip()
    gate_model = (os.getenv("OPENAI_GATE_MODEL") or "").strip() or project_model

    request_kwargs = {
        "input": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": source_text},
        ],
        "temperature": 0,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "botanical_gate_assertions",
                "schema": GATE_ASSERTION_SCHEMA,
                "strict": True,
            }
        },
    }

    try:
        response = client.responses.create(model=gate_model, **request_kwargs)
    except Exception as exc:
        # Only fall back for a model-name/access failure. Schema/prompt/auth/rate
        # errors must remain visible rather than being disguised by a retry.
        message = str(exc).lower()
        model_error = "model_not_found" in message or "does not exist" in message
        if not model_error or gate_model == project_model:
            raise
        response = client.responses.create(model=project_model, **request_kwargs)

    return json.loads(response.output_text)
