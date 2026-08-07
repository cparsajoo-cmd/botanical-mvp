from __future__ import annotations

from gold_corpus.e2e_pilot_diagnostics import build_diagnostics, write_diagnostics


def main():
    path = write_diagnostics()
    data = build_diagnostics()
    d = data["direction_diagnostics"]
    s = data["safety_diagnostics"]
    print(path)
    print("raw_mixed_domain_direction_accuracy:", d["raw_mixed_domain_accuracy"])
    print("indication_domain_direction_accuracy:", d["indication_domain_accuracy"])
    print("study_result_eligible_direction_accuracy:", d["study_result_eligible_accuracy"])
    print("safety_critical_source_recall:", s["critical_source_recall"])
    print("serious_safety_false_negative_rate:", s["serious_safety_false_negative_rate"])
    return data


if __name__ == "__main__":
    main()
