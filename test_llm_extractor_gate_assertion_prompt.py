"""Root-cause regression (2026-08-11, RGV v3 rerun after the 5 audit
blocker fixes): rgv3_008_butterbur_migraine went from the expected
EXPERT REVIEW REQUIRED to a false NO GO REGULATORY hard-stop.
Confirmed by direct test that the deterministic regulatory classifier
(regulatory_barrier_classifier.classify_regulatory_barriers) finds
nothing in this case's evidence text -- the false hard-stop can only
have come from the semantic (LLM) gate wired into the validation
harness this same session.

The evidence text says a professional medical body withdrew its own
clinical RECOMMENDATION over a hepatotoxicity concern -- not that any
government/statutory regulator withdrew market authorization. The
system prompt's regulatory rules (llm_extractor.py) did not previously
distinguish "a professional medical society changed its own guidance"
from "a government authority took a market-access action", so a model
call could plausibly extract the former as if it were the latter.

This cannot be fully verified without a live OpenAI call (the actual
extraction that produced the false NO GO REGULATORY happened in a real
GitHub Actions run, not reproducible in this offline environment), so
this test only guards the prompt-level fix: that the clarifying rule
is present and unambiguous. A live RGV v3 rerun is the real proof.
"""
import llm_extractor


def test_gate_assertion_prompt_distinguishes_professional_body_from_regulator():
    captured = {}

    class _FakeResponses:
        def create(self, **kwargs):
            captured["request"] = kwargs
            class _Resp:
                output_text = '{"safety_assertions": [], "regulatory_assertions": []}'
            return _Resp()

    class _FakeClient:
        responses = _FakeResponses()

    llm_extractor_client_patch = llm_extractor.get_openai_client
    llm_extractor.get_openai_client = lambda: _FakeClient()
    try:
        llm_extractor.extract_gate_assertions_with_llm(
            {"Notes": "unprocessed butterbur contains hepatotoxic pyrrolizidine "
                      "alkaloids that led some professional bodies to withdraw "
                      "their recommendation"},
            candidate_context="migraine prophylaxis",
        )
    finally:
        llm_extractor.get_openai_client = llm_extractor_client_patch

    system_prompt = captured["request"]["input"][0]["content"]
    assert "professional medical society" in system_prompt
    assert "NOT a regulatory action" in system_prompt
    assert "statutory authority" in system_prompt or "legal power over market access" in system_prompt
