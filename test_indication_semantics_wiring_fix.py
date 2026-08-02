"""Regression test: Step 5 candidate discovery must generalize to any
indication in indication_semantics.py's 27-family list, using clinical
synonym and mechanistic terms -- not require the literal indication word to
appear verbatim in evidence text, and not require a second, separate
hardcoded term list in indication_candidate_discovery.py.

Two real, distinct problems were found and fixed here:

1. `indication_candidate_discovery._terms()` had its own local 4-family
   `DISEASE_FAMILIES` dict (metabolic, sleep, cognitive, skin_aging) and,
   for anything else, fell back to a bare single/few-word literal substring
   match with zero mechanistic support. Meanwhile `indication_semantics.py`
   already existed with a 27-family, alias-aware term set covering common
   indications (Cough, Migraine/"Headache", Eczema/"Skin inflammation",
   etc.) and was already used by the later scoring stage
   (candidate_shortlisting.py) -- its own docstring says it is meant to be
   "the single source of truth used by both raw candidate discovery and
   plant-level shortlisting" -- but it was never actually imported by
   indication_candidate_discovery.py. `_terms()` now delegates to it, so a
   new indication only needs one entry, in one file, to work at both
   pipeline stages.

2. Even indication_semantics.resolve_indication_semantics() itself had a gap:
   it only matched a free-text query against each family's canonical name
   and curated `aliases` list, not its `direct` clinical terms. A term
   already listed in `direct` (e.g. "migraine" under "Headache / mood
   support") could describe evidence once a family was found, but could
   never be used to find that family from a query in the first place.
   `resolve_indication_semantics()` now also matches against `direct` terms.

The existing test_cough_indication_generalization.py passed even before
these fixes, but only because its synthetic mock evidence happened to
contain the literal word "cough" -- so the bare-token fallback matched by
coincidence, masking the real gap. The tests below use evidence text that
deliberately avoids the literal indication word, to prove genuine semantic
matching rather than a lucky literal hit.
"""
import pandas as pd

from indication_candidate_discovery import _terms, discover_indication_candidates
from indication_semantics import indication_terms, resolve_indication_semantics


def test_terms_delegates_to_indication_semantics_for_cough():
    direct, mechanistic = _terms("Cough")
    assert direct == indication_terms("Cough")[0]
    assert "antitussive" in direct
    assert "expectorant" in mechanistic


def test_migraine_resolves_via_its_own_direct_term_not_just_aliases():
    family = resolve_indication_semantics("Migraine")
    assert family is not None
    assert "migraine" in family["direct"]


def test_previously_hardcoded_families_still_resolve_the_same_way():
    """Backward compatibility: the four indications that used to be served by
    the local DISEASE_FAMILIES dict must still resolve to sensible direct
    terms after delegating to indication_semantics.py."""
    for query, expected_direct_substring in [
        ("Type 2 diabetes", "diabetes"),
        ("Insomnia", "insomnia"),
        ("Alzheimer's disease", "alzheimer"),
        ("Skin aging", "skin aging"),
    ]:
        direct, _ = _terms(query)
        joined = " ".join(direct)
        assert expected_direct_substring in joined.lower()


class _Engine:
    """Mirrors BotanicalRDCandidateEngine._pick (the real production
    implementation)."""

    def __init__(self, evidence_records):
        self.evidence_df = pd.DataFrame()
        self.scientific_evidence_df = pd.DataFrame()
        self.evidence_records_df = pd.DataFrame(evidence_records)
        self._candidates = None

    def set_candidates(self, candidates):
        self._candidates = pd.DataFrame(candidates)

    def _candidate_frame(self):
        return self._candidates

    def _pick(self, row, names):
        for name in names:
            try:
                value = row.get(name, "")
            except AttributeError:
                value = ""
            if (
                value is not None
                and str(value).strip()
                and str(value).lower() not in {"nan", "none", "null"}
            ):
                return str(value).strip()
        return ""

    def _split_compound_terms(self, value):
        return [x.strip() for x in str(value).split(";") if x.strip()]

    def _evidence_level(self, text):
        return "High"


def test_cough_discovery_without_the_literal_word_cough_in_evidence():
    engine = _Engine([{
        "Scientific_Name": "Thymus vulgaris",
        "Evidence_Record_ID": 1,
        "Target_Indication": "Acute bronchitis",
        "Primary_Outcome": "Demonstrated antitussive and bronchorelaxant activity in a randomized human trial",
    }])
    engine.set_candidates([{
        "Scientific_Name": "Thymus vulgaris",
        "Known_Active_Compounds": "thymol",
        "Known_Targets": "expectorant; bronchorelaxant",
        "Indications_Text": "",
    }])
    out = discover_indication_candidates(engine, "Cough", dosage_form="oral")
    assert "Thymus vulgaris" in set(out["Alternative_Plant"])


def test_migraine_discovery_without_the_literal_word_migraine_in_evidence():
    engine = _Engine([{
        "Scientific_Name": "Tanacetum parthenium",
        "Evidence_Record_ID": 1,
        "Target_Indication": "Recurrent headache",
        "Primary_Outcome": "Reduced headache frequency in a randomized controlled trial via CGRP modulation",
    }])
    engine.set_candidates([{
        "Scientific_Name": "Tanacetum parthenium",
        "Known_Active_Compounds": "parthenolide",
        "Known_Targets": "cgrp; serotonin",
        "Indications_Text": "",
    }])
    out = discover_indication_candidates(engine, "Migraine", dosage_form="oral")
    assert "Tanacetum parthenium" in set(out["Alternative_Plant"])


def test_eczema_discovery_via_skin_inflammation_family_without_literal_eczema():
    engine = _Engine([{
        "Scientific_Name": "Matricaria chamomilla",
        "Evidence_Record_ID": 1,
        "Target_Indication": "Atopic dermatitis",
        "Primary_Outcome": "Reduced erythema and pruritus with topical anti-inflammatory activity",
    }])
    engine.set_candidates([{
        "Scientific_Name": "Matricaria chamomilla",
        "Known_Active_Compounds": "bisabolol",
        "Known_Targets": "mast cell; histamine",
        "Indications_Text": "",
    }])
    out = discover_indication_candidates(engine, "Eczema", dosage_form="oral")
    assert "Matricaria chamomilla" in set(out["Alternative_Plant"])


def test_unrelated_plant_still_excluded_no_cross_indication_leakage():
    engine = _Engine([
        {
            "Scientific_Name": "Thymus vulgaris",
            "Evidence_Record_ID": 1,
            "Target_Indication": "Acute bronchitis",
            "Primary_Outcome": "Demonstrated antitussive activity in a randomized human trial",
        },
        {
            "Scientific_Name": "Unrelated plant",
            "Evidence_Record_ID": 2,
            "Target_Indication": "Type 2 diabetes",
            "Primary_Outcome": "Reduced fasting blood glucose in a randomized trial",
        },
    ])
    engine.set_candidates([
        {"Scientific_Name": "Thymus vulgaris", "Known_Active_Compounds": "thymol",
         "Known_Targets": "expectorant", "Indications_Text": ""},
        {"Scientific_Name": "Unrelated plant", "Known_Active_Compounds": "x",
         "Known_Targets": "ampk", "Indications_Text": ""},
    ])
    out = discover_indication_candidates(engine, "Cough", dosage_form="oral")
    assert "Thymus vulgaris" in set(out["Alternative_Plant"])
    assert "Unrelated plant" not in set(out["Alternative_Plant"])
