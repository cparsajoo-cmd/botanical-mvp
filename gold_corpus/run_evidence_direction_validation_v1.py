from gold_corpus.evidence_direction_validation_v1 import evaluate, write_run

if __name__ == "__main__":
    result = evaluate()
    path = write_run()
    print(f"records={result['record_count']}")
    print(f"agreement={result['agreement']['value']:.3f}")
    for label, metrics in result["per_class_recall"].items():
        print(f"recall_{label}={metrics['recall']:.3f}")
    print(f"errors={len(result['errors'])}")
    print(f"written={path}")
