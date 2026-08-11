"""Held-back semantic gate validation for safety/regulatory extraction.

This validator is intentionally local-only with respect to project data:
* NO Supabase client import
* NO database reads/writes
* LLM sees only source text + neutral candidate context, never the gold label
* cases used by shadow_semantic_gate_stress.py are excluded

The source records come from curator-verified local gold-corpus extensions that are
separate from the 10-case exposed stress set. This is a held-back semantic-gate
validation, not a claim of a never-before-seen external benchmark.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from llm_extractor import extract_gate_assertions_with_llm
from semantic_gate_assertions import parse_semantic_gate_payload

ROOT = Path(__file__).resolve().parent

# Do not reuse the 10 exposed stress cases or their source-record controls.
EXPOSED_STRESS_IDS = {
    "rgv1_017_chaparral_oral",
    "rgv2_017_aconitum_oral",
    "rgv2_018_datura_oral",
    "rgv2_019_colchicum_oral",
    "rgv2_020_belladonna_oral",
    "rgv3_017_cistanche_eu_food",
    "rgv3_018_terminaliacatappa_eu_food",
    "rgv2_022_cbd_eu_food",
    "control_ginkgo_dabigatran_moderate",
    "control_ephedra_conditional_access",
}

# Gold labels are intentionally separate from the text extraction step.
# The LLM never receives "expect" or the corpus category.
MANIFEST = [
    # Serious-safety positives: wording not used in the exposed 10-case stress set.
    ("gold_corpus/safety_interaction_corpus_extension_09.json", "safe09_echinacea_hypersensitivity", "serious_safety"),
    ("gold_corpus/safety_interaction_corpus_extension_09.json", "safe09_matricaria_allergy", "serious_safety"),
    ("gold_corpus/safety_interaction_corpus_extension_09.json", "safe09_black_cohosh_hepatotoxicity", "serious_safety"),
    ("gold_corpus/safety_corpus_extension_11.json", "safe11_agnus_castus_severe_allergy", "serious_safety"),

    # Safety controls: warnings/contraindications/interactions must not be promoted
    # to a serious/life-threatening hard-gate signal merely because risk language exists.
    ("gold_corpus/safety_interaction_corpus_extension_09.json", "safe09_matricaria_cyp450_interaction", "no_serious_safety"),
    ("gold_corpus/safety_corpus_extension_11.json", "safe11_senna_pod_long_term_dependence", "no_serious_safety"),
    ("gold_corpus/safety_corpus_extension_11.json", "safe11_senna_pod_under12", "no_serious_safety"),
    ("gold_corpus/safety_corpus_extension_11.json", "safe11_caraway_cross_allergy", "no_serious_safety"),

    # Genuine market-access blocks.
    ("gold_corpus/regulatory_corpus_extension_07_national_fda.json", "reg07_mhra_aristolochia_prohibition", "regulatory_block"),
    ("gold_corpus/regulatory_corpus_extension_07_national_fda.json", "reg07_mhra_senecio_prohibition", "regulatory_block"),
    ("gold_corpus/regulatory_corpus_extension_07_national_fda.json", "reg07_fda_aristolochic_acid_import_alert", "regulatory_block"),

    # Restrictions/controlled channels are not absolute market-access prohibitions.
    ("gold_corpus/regulatory_corpus_extension_07_national_fda.json", "reg07_mhra_adonis_dose_restriction", "no_regulatory_block"),
    ("gold_corpus/regulatory_corpus_extension_07_national_fda.json", "reg07_mhra_areca_pharmacy_only", "no_regulatory_block"),
    ("gold_corpus/regulatory_corpus_extension_07_national_fda.json", "reg07_mhra_gelsemium_dose_restriction", "no_regulatory_block"),
    ("gold_corpus/regulatory_corpus_extension_07_national_fda.json", "reg07_mhra_yohimbe_pharmacy_only", "no_regulatory_block"),
]


def _load_records(path: str) -> dict[str, dict[str, Any]]:
    payload = json.loads((ROOT / path).read_text(encoding="utf-8"))
    return {str(r["record_id"]): r for r in payload["records"]}


def _source_text(record: dict[str, Any]) -> str:
    return str(record.get("safety_effect") or record.get("regulatory_effect") or "").strip()


def _neutral_context(record: dict[str, Any]) -> str:
    parts = [
        record.get("botanical_name"),
        record.get("plant_part"),
        record.get("jurisdiction"),
        record.get("authority"),
        record.get("product_scope"),
        record.get("population_or_drug"),
    ]
    return " | ".join(str(x).strip() for x in parts if x)


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _is_serious(assertion: Any) -> bool:
    return _enum_value(getattr(assertion, "severity", "")).lower() == "serious"


def _record_fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _metric(numer: int, denom: int) -> str:
    if not denom:
        return "NA"
    return f"{numer / denom:.3f}"


def main() -> int:
    caches: dict[str, dict[str, dict[str, Any]]] = {}
    cases: list[dict[str, Any]] = []

    for path, record_id, expect in MANIFEST:
        if record_id in EXPOSED_STRESS_IDS:
            raise RuntimeError(f"Leakage guard: exposed stress id in blind manifest: {record_id}")
        caches.setdefault(path, _load_records(path))
        try:
            record = caches[path][record_id]
        except KeyError as exc:
            raise RuntimeError(f"Missing held-back record {record_id} in {path}") from exc
        text = _source_text(record)
        if not text:
            raise RuntimeError(f"Empty source text for {record_id}")
        cases.append({"id": record_id, "expect": expect, "record": record, "text": text})

    # Protect against accidental duplicate texts within this validation set.
    fingerprints: dict[str, str] = {}
    for case in cases:
        fp = _record_fingerprint(case["text"])
        prior = fingerprints.get(fp)
        if prior:
            raise RuntimeError(f"Duplicate text leakage: {case['id']} duplicates {prior}")
        fingerprints[fp] = case["id"]

    failed = 0
    catastrophic_fn = 0
    false_hard_stop = 0

    safety_pos = safety_tp = safety_neg = safety_tn = 0
    reg_pos = reg_tp = reg_neg = reg_tn = 0

    for case in cases:
        record = case["record"]
        source_text = case["text"]
        llm_record = {
            "Notes": source_text,
            "Source_Title": str(record.get("source_reference") or record.get("source_family") or ""),
        }
        raw = extract_gate_assertions_with_llm(
            llm_record,
            candidate_context=_neutral_context(record),
        )
        safety, regulatory, warnings = parse_semantic_gate_payload(
            raw,
            source_text=source_text,
            evidence_record_id=case["id"],
            authority=str(record.get("authority") or record.get("source_family") or "Unknown Source"),
            source_url=str(record.get("source_url") or ""),
        )

        serious = [a for a in safety if _is_serious(a)]
        blocking = [a for a in regulatory if bool(getattr(a, "blocking", False))]
        expect = case["expect"]
        ok = True

        if expect == "serious_safety":
            safety_pos += 1
            if serious:
                safety_tp += 1
            else:
                ok = False
                catastrophic_fn += 1
        elif expect == "no_serious_safety":
            safety_neg += 1
            if not serious:
                safety_tn += 1
            else:
                ok = False
                false_hard_stop += 1
        elif expect == "regulatory_block":
            reg_pos += 1
            if blocking:
                reg_tp += 1
            else:
                ok = False
                catastrophic_fn += 1
        elif expect == "no_regulatory_block":
            reg_neg += 1
            if not blocking:
                reg_tn += 1
            else:
                ok = False
                false_hard_stop += 1
        else:
            raise RuntimeError(f"Unknown gold expectation: {expect}")

        if not ok:
            failed += 1

        print("BLIND " + json.dumps({
            "case": case["id"],
            "fingerprint": _record_fingerprint(source_text),
            "expect": expect,
            "status": "PASS" if ok else "FAIL",
            "serious_safety": len(serious),
            "regulatory_blocks": len(blocking),
            "safety": [
                {
                    "type": _enum_value(getattr(a, "assertion_type", "")),
                    "severity": _enum_value(getattr(a, "severity", "")),
                    "span": getattr(a, "source_sentence", ""),
                }
                for a in safety
            ],
            "regulatory": [
                {
                    "action": _enum_value(getattr(a, "action", "")),
                    "effect": _enum_value(getattr(a, "market_access_effect", "")),
                    "span": getattr(a, "supporting_text", ""),
                }
                for a in regulatory
            ],
            "warnings": warnings,
        }, ensure_ascii=False, separators=(",", ":")))

    safety_sensitivity = _metric(safety_tp, safety_pos)
    safety_specificity = _metric(safety_tn, safety_neg)
    reg_sensitivity = _metric(reg_tp, reg_pos)
    reg_specificity = _metric(reg_tn, reg_neg)

    summary = (
        f"SUMMARY cases={len(cases)} passed={len(cases)-failed} failed={failed} "
        f"catastrophic_fn={catastrophic_fn} false_hard_stop={false_hard_stop} "
        f"safety_sensitivity={safety_sensitivity} safety_specificity={safety_specificity} "
        f"regulatory_sensitivity={reg_sensitivity} regulatory_specificity={reg_specificity} "
        "supabase_reads=0 supabase_writes=0"
    )
    print(summary)

    # For this safety-critical pre-production gate, any catastrophic miss or
    # false hard-stop is a failing validation that must be inspected before apply.
    return 1 if (catastrophic_fn or false_hard_stop or failed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
