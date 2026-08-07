from gold_corpus.human_evidence_direction_benchmark import evaluate_benchmark, write_run

if __name__ == "__main__":
    result = evaluate_benchmark()
    path = write_run()
    print(f"records={result['record_count']}")
    print(f"direction_accuracy={result['direction_accuracy']}")
    print(f"study_design_accuracy={result['study_design_accuracy']}")
    print(f"written={path}")
