"""Focused Stage 1 regressions for general scientific direction language."""
import pytest

from evidence_interpretation import classify_evidence_direction


@pytest.mark.parametrize("text", [
    "The intervention was more effective than placebo for reducing symptom severity.",
    "The randomized trial confirmed efficacy on the prespecified primary clinical endpoint.",
    "The botanical was non-inferior to the active comparator for the primary efficacy endpoint.",
    "Participants receiving treatment had significantly lower symptom scores than those receiving placebo.",
])
def test_general_positive_language(text):
    assert classify_evidence_direction(text)[0] == "positive"


@pytest.mark.parametrize("text", [
    "The study concluded that the intervention was ineffective for preventing recurrence.",
    "Treatment was associated with an increased risk of serious adverse events compared with placebo.",
    "A negative safety signal emerged, with a higher incidence of hepatotoxicity in the treatment arm.",
])
def test_general_negative_language(text):
    assert classify_evidence_direction(text)[0] == "negative"


@pytest.mark.parametrize("text", [
    "The primary analysis yielded a null result, with comparable outcomes in both groups.",
    "No significant treatment effect was detected for the primary endpoint.",
    "Changes from baseline did not differ significantly between the intervention and control groups.",
    "The confidence interval crossed the null and there was no evidence of a between-group difference.",
])
def test_general_null_language(text):
    assert classify_evidence_direction(text)[0] == "null"


@pytest.mark.parametrize("text", [
    "Symptoms improved at week 4, but the effect was not sustained at week 12.",
    "No significant benefit was found in the overall population, but a prespecified subgroup showed significant improvement.",
    "Pain scores improved significantly, but functional outcomes worsened relative to control.",
])
def test_general_mixed_language(text):
    assert classify_evidence_direction(text)[0] == "mixed"


@pytest.mark.parametrize("text", [
    "The findings were inconclusive and do not permit a firm conclusion about efficacy.",
    "The intervention may offer benefit, although confidence intervals were wide and the evidence remains uncertain.",
    "Evidence was insufficient to determine whether the treatment improves clinically important outcomes.",
])
def test_hedged_or_insufficient_language_remains_unclear(text):
    assert classify_evidence_direction(text)[0] == "unclear"
