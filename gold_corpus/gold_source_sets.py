"""GoldSourceSet annotations for the active reference-grounded corpus.

Only verified governing references are promoted to CRITICAL here. Supporting
or competing references documented in case narratives remain in the manifest
until they have their own independently verified retrieval records/snapshots.
"""
from __future__ import annotations

import json
from pathlib import Path

from end_to_end_validation import GoldSourceExpectation, GoldSourceSet, SourceRole

_MANIFEST = Path(__file__).with_name("gold_corpus_manifest.json")


def load_gold_source_sets() -> dict[str, GoldSourceSet]:
    data = json.loads(_MANIFEST.read_text())
    out: dict[str, GoldSourceSet] = {}
    for case in data["cases"]:
        sources = []
        for src in case["critical_sources"]:
            sources.append(GoldSourceExpectation(
                reference_id=src["reference_id"],
                role=SourceRole.CRITICAL,
                source_type=src.get("source_type"),
                expected_study_design=(src.get("expected_study_design") if src.get("expected_study_design") in {
                    "randomized_controlled_trial", "clinical_trial", "clinical_trial_protocol", "review",
                    "animal_study", "in_vitro_study", "unspecified"
                } else None),
                expected_direction=src.get("expected_evidence_direction"),
                expected_applicability=None,  # GoldCase applicability vocabulary differs from free-text classifier vocabulary.
                expected_source_authority=None,
                expected_evidence_quality=None,
                safety_critical=bool(src.get("safety_critical")),
                regulatory_critical=bool(src.get("regulatory_critical")),
            ))
        out[case["case_id"]] = GoldSourceSet(tuple(sources))
    return out


GOLD_SOURCE_SETS = load_gold_source_sets()
