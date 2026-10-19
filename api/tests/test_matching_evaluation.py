import json

from scripts import evaluate_matching as evaluation


def test_retrieval_positives_are_scored_separately_from_final_classification():
    cases = [
        {"id": "exact", "label": "positive", "retrieval_label": "positive"},
        {"id": "typo", "label": "ambiguous", "retrieval_label": "positive"},
        {"id": "wrong", "label": "negative", "retrieval_label": "negative"},
        {"id": "unknown", "label": "ambiguous", "retrieval_label": "ambiguous"},
    ]
    predictions = {
        "exact": {"potential": True, "retrieved": True},
        "typo": {"potential": False, "retrieved": True},
        "wrong": {"potential": False, "retrieved": False},
        "unknown": {"potential": False, "retrieved": True},
    }
    final = evaluation.binary_metrics(cases, predictions)
    retrieval = evaluation.binary_metrics(
        cases, predictions, label_field="retrieval_label", prediction_field="retrieved"
    )
    assert final["determinate_count"] == 2
    assert final["true_positive"] == 1
    assert final["ambiguous_predicted_positive"] == 0
    assert retrieval["determinate_count"] == 3
    assert retrieval["true_positive"] == 2
    assert retrieval["precision"] == retrieval["recall"] == retrieval["f1"] == 1.0
    assert retrieval["ambiguous_predicted_positive"] == 1


def test_dataset_explicitly_labels_legitimate_variants_and_unknown_aliases():
    dataset = json.loads(evaluation.DATASET_PATH.read_text(encoding="utf-8"))
    cases = dataset["cases"]
    assert all(case["retrieval_label"] in {"positive", "negative", "ambiguous"} for case in cases)
    variants = [case for case in cases if case["retrieval_label"] == "positive" and case["label"] == "ambiguous"]
    assert len(variants) >= 3
    assert all(case["rationale"] for case in variants)
    assert any(case["retrieval_label"] == "negative" for case in cases)
    assert any(case["retrieval_label"] == "ambiguous" for case in cases)


def test_p95_uses_nearest_rank_on_small_evaluation_set():
    assert evaluation.percentile95(list(range(1, 19))) == 18
    assert evaluation.percentile95([]) == 0.0
