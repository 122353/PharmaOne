"""Rebuild lightweight advisory models from disclosed synthetic examples.

No CDSCO outcome labels or real pharmacy data are used as training labels.
Runtime inference uses only JSON and Python's standard library.
"""

import json
import math
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.ml import MODEL_DIR, finding_tokens, match_features  # noqa: E402


def match_examples():
    names = [
        ("Linezolid Tablets IP 600mg", "Linezolid Tablets 600mg", "Linezolid 600mg Tablets"),
        ("Paracetamol Tablets IP 500mg", "Paracetamol 500mg Tablets", "Paracetamol Tablets 500mg"),
        ("Amoxicillin Capsules IP 250mg", "Amoxicillin Capsules 250mg", "Amoxicillin 250mg Capsules"),
        ("Cetirizine Tablets IP 10mg", "Cetirizine 10mg Tablets", "Cetirizine Tablets 10mg"),
        ("Metformin Tablets IP 500mg", "Metformin Tablets 500mg", "Metformin 500mg Tablets"),
        ("Omeprazole Capsules IP 20mg", "Omeprazole 20mg Capsules", "Omeprazole Capsules 20mg"),
        ("Amlodipine Tablets IP 5mg", "Amlodipine 5mg Tablets", "Amlodipine Tablets 5mg"),
        ("Azithromycin Tablets IP 500mg", "Azithromycin 500mg Tablets", "Azithromycin Tablets 500mg"),
        ("Levocetirizine Tablets IP 5mg", "Levocetirizine 5mg Tablets", "Levocetirizine Tablets 5mg"),
        ("Ibuprofen Tablets IP 400mg", "Ibuprofen 400mg Tablets", "Ibuprofen Tablets 400mg"),
    ]
    samples = []
    for index, (source, variant, shuffled) in enumerate(names):
        samples.extend([(source, source, 1), (source, variant, 1), (source, shuffled, 1)])
        samples.extend([(source, names[(index + 1) % len(names)][0], 0),
                        (source, names[(index + 3) % len(names)][0], 0),
                        (source, source.replace(next(token for token in source.split() if any(c.isdigit() for c in token)), "999mg"), 0)])
    return samples


CLASS_EXAMPLES = {
    "dissolution": ["Dissolution", "Failed dissolution test", "Dissolution results out of specification", "Unsatisfactory dissolution", "Dissolution parameter failed", "Poor drug release in dissolution", "Dissolution test failure", "Dissolution of tablets not complying"],
    "assay_or_content": ["Assay", "Assay value below specification", "Content of active ingredient failed", "Assay of drug substance not complying", "Low active content", "Content uniformity failed", "Assay results out of limit", "Potency below specification"],
    "identification": ["Identification", "Failed identification test", "Identity of active ingredient not confirmed", "Identification parameter failed", "Incorrect identity", "Identification test not complying", "Identity test failure", "Active ingredient identification failed"],
    "contamination": ["Microbial contamination", "Sterility test failed", "Microbial limit test not complying", "Particulate contamination", "Bacterial contamination observed", "Foreign particles in sample", "Microbial count exceeds limit", "Sterility failure"],
    "other_quality_finding": ["Disintegration", "Failed disintegration test", "Appearance does not comply", "pH out of specification", "Weight variation failed", "Hardness test failure", "Friability not complying", "Labelling defect observed"],
}


def train_match(samples):
    random.Random(2301).shuffle(samples)
    split = int(len(samples) * 0.8)
    training, holdout = samples[:split], samples[split:]
    weights, bias = [0.0] * 6, 0.0
    for _ in range(700):
        for a, b, label in training:
            x = match_features(a, b)
            z = max(-30, min(30, bias + sum(w * v for w, v in zip(weights, x))))
            error = label - 1 / (1 + math.exp(-z))
            weights = [w + 0.07 * error * value for w, value in zip(weights, x)]
            bias += 0.07 * error
    def correct(a, b, label):
        score = bias + sum(w * v for w, v in zip(weights, match_features(a, b)))
        return int(score >= 0) == label
    return {"version": "1.0", "weights": weights, "bias": bias, "training_source": "synthetic name variants", "synthetic_holdout": {"correct": sum(correct(*row) for row in holdout), "total": len(holdout)}}


def train_classify():
    examples = [(label, sentence) for label, sentences in CLASS_EXAMPLES.items() for sentence in sentences]
    training, holdout = [], []
    for label, sentences in CLASS_EXAMPLES.items():
        local = [(label, sentence) for sentence in sentences]
        random.Random(2302).shuffle(local)
        training.extend(local[:6])
        holdout.extend(local[6:])
    documents = Counter()
    counts = {label: Counter() for label in CLASS_EXAMPLES}
    for label, sentence in training:
        documents[label] += 1
        counts[label].update(finding_tokens(sentence))
    model = {"version": "1.0", "training_source": "synthetic quality-finding phrases",
             "class_documents": dict(documents), "token_counts": {key: dict(value) for key, value in counts.items()},
             "class_tokens": {key: sum(value.values()) for key, value in counts.items()},
             "vocabulary": sorted(set().union(*(value.keys() for value in counts.values())))}
    # Evaluate through the exact runtime implementation after writing the artifact.
    return model, holdout


def main():
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    match_model = train_match(match_examples())
    (MODEL_DIR / "pharmamatch.json").write_text(json.dumps(match_model, indent=2) + "\n", encoding="utf-8")
    classify_model, holdout = train_classify()
    (MODEL_DIR / "pharmaclassify.json").write_text(json.dumps(classify_model, indent=2) + "\n", encoding="utf-8")
    from app.ml import pharma_classify
    classify_model["synthetic_holdout"] = {"correct": sum(pharma_classify(sentence)["category"] == label for label, sentence in holdout), "total": len(holdout)}
    (MODEL_DIR / "pharmaclassify.json").write_text(json.dumps(classify_model, indent=2) + "\n", encoding="utf-8")
    print("PharmaMatch synthetic holdout:", match_model["synthetic_holdout"])
    print("PharmaClassify synthetic holdout:", classify_model["synthetic_holdout"])


if __name__ == "__main__":
    main()
