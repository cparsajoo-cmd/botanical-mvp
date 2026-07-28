"""
Validation Architecture v3 — Phase 1: Dataset Canonicalization & Hashing.

WHAT THIS IS
A deterministic, order-independent serialization of a list of
GoldCase objects, plus a hash of that serialization — the mechanism
EvaluationRun (Phase 2) will use for dataset_snapshot_hash, so a
locked-holdout evaluation can prove exactly which case content it ran
against, byte-for-byte, independent of dict/list ordering at
construction time.

DETERMINISM GUARANTEES
- Case order in the input list does not affect the hash — cases are
  sorted by case_id before serialization.
- Dict key order does not affect the hash — every dict is serialized
  with sorted keys (json.dumps(..., sort_keys=True)).
- taxon_synonyms (ValidationUnit) is EXCLUDED from the identity-
  relevant hashed content by design — see validation_unit.py's own
  docstring: synonyms are metadata for matching, not part of a unit's
  identity, so two datasets differing only in synonym list order (or
  even content) must not be treated as scientifically different
  datasets for holdout-integrity purposes. This is Phase 1's one
  deliberate exclusion; every other field is included.

WHAT THIS IS NOT
Not a general-purpose object serializer — canonicalize_gold_case()
only extracts the fields relevant to reproducibility (case_id,
validation_unit content, risk_strata, expected_output,
references' reference_id/source_type/version, dataset_split). Runtime-
only bookkeeping (e.g. leakage_control.observed_at, a wall-clock
timestamp) is deliberately excluded — including a timestamp in a
content hash would make the hash change every time the SAME dataset
content is re-canonicalized, defeating its purpose.
"""

from __future__ import annotations

import hashlib
import json

from gold_case import GoldCase


def _canonicalize_validation_unit(unit) -> dict:
    prep = None
    if unit.preparation is not None:
        prep = {
            "dosage_form": unit.preparation.dosage_form,
            "solvent": unit.preparation.solvent,
            "der_min": unit.preparation.der_min,
            "der_max": unit.preparation.der_max,
            "source_status": unit.preparation.source_status,
        }
    dose = None
    if unit.dose is not None:
        dose = {"amount": unit.dose.amount, "unit": unit.dose.unit, "frequency": unit.dose.frequency}
    return {
        "taxon": unit.taxon,
        # taxon_synonyms deliberately excluded — see module docstring.
        "plant_part": unit.plant_part,
        "preparation": prep,
        "dose": dose,
        "duration": unit.duration,
        "route_of_administration": unit.route_of_administration,
        "indication": unit.indication,
        "population": unit.population,
        "jurisdiction": unit.jurisdiction,
    }


def _canonicalize_expected_output(expected) -> dict:
    return {
        "expected_gate_results": dict(sorted(expected.expected_gate_results.items())),
        "expected_decision_direction": (
            expected.expected_decision_direction.value
            if expected.expected_decision_direction is not None else None
        ),
        "expected_abstention_reason": expected.expected_abstention_reason,
        "expected_warnings": sorted(expected.expected_warnings),
        "acceptable_decision_class_min": expected.acceptable_decision_class_min,
        "acceptable_decision_class_max": expected.acceptable_decision_class_max,
    }


def _canonicalize_reference(gold_case_reference) -> dict:
    ref = gold_case_reference.reference
    return {
        "reference_id": ref.reference_id,
        "source_type": ref.source_type,
        "version": ref.version,
        "jurisdiction": ref.jurisdiction,
        "retracted_or_superseded": ref.retracted_or_superseded,
    }


def canonicalize_gold_case(case: GoldCase) -> dict:
    """Extracts exactly the content-relevant fields of one GoldCase —
    see module docstring for what is deliberately excluded and why."""
    return {
        "case_id": case.case_id,
        "validation_unit": _canonicalize_validation_unit(case.validation_unit),
        "risk_strata": sorted(s.value for s in case.risk_strata),
        "expected_output": _canonicalize_expected_output(case.expected_output),
        "references": sorted(
            (_canonicalize_reference(r) for r in case.references),
            key=lambda r: r["reference_id"],
        ),
        "correct_abstention_expected": case.correct_abstention_expected,
        "dataset_split": case.dataset_split.value,
    }


def canonicalize_dataset(cases: list) -> str:
    """Deterministic JSON string for a list of GoldCase objects — same
    content in any input order produces the same string."""
    canonical_cases = sorted(
        (canonicalize_gold_case(c) for c in cases),
        key=lambda c: c["case_id"],
    )
    return json.dumps(canonical_cases, sort_keys=True, separators=(",", ":"))


def hash_dataset(cases: list) -> str:
    """SHA-256 hex digest of canonicalize_dataset()'s output — the
    value Phase 2's EvaluationRun.dataset_snapshot_hash will store."""
    canonical = canonicalize_dataset(cases)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
