"""Small, locally trained advisory models; regulatory decisions use hard identifier rules."""

import json
import math
import re
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path


MODEL_DIR = Path(__file__).resolve().parent.parent / "model_artifacts"


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.casefold())) - {"ip", "the"}


def finding_tokens(value: str) -> list[str]:
    common = {"the", "of", "in", "not", "test", "failed", "failure", "result", "results", "out", "specification", "parameter", "comply", "complying", "below", "limit", "to", "does", "drug"}
    return [word[:7] for word in re.findall(r"[a-z0-9]+", value.casefold()) if word not in common]


def match_features(a: str, b: str) -> list[float]:
    left, right = _tokens(a), _tokens(b)
    overlap = len(left & right)
    numbers_a = {token for token in left if any(c.isdigit() for c in token)}
    numbers_b = {token for token in right if any(c.isdigit() for c in token)}
    return [
        overlap / len(left | right) if left | right else 0.0,
        overlap / max(len(left), len(right)) if left and right else 0.0,
        SequenceMatcher(None, a.casefold(), b.casefold()).ratio(),
        float(bool(numbers_a) and numbers_a == numbers_b),
        float(bool(numbers_a and numbers_b and numbers_a != numbers_b)),
        float(bool(left) and left == right),
    ]


@lru_cache(maxsize=2)
def _artifact(name: str) -> dict:
    # Only checked-in, locally generated JSON is loaded; no untrusted pickle.
    return json.loads((MODEL_DIR / f"{name}.json").read_text(encoding="utf-8"))


def pharma_match(a: str, b: str) -> dict:
    model = _artifact("pharmamatch")
    features = match_features(a, b)
    z = model["bias"] + sum(w * value for w, value in zip(model["weights"], features))
    score = 1 / (1 + math.exp(-max(-30, min(30, z))))
    return {"model": "PharmaMatch", "version": model["version"], "product_similarity": round(score, 4), "advisory_only": True}


def pharma_classify(finding: str) -> dict:
    model = _artifact("pharmaclassify")
    tokens = finding_tokens(finding)
    if not tokens:
        return {"model": "PharmaClassify", "version": model["version"], "category": "unclassified", "confidence": 0.0, "advisory_only": True}
    scores = {}
    vocabulary_size = len(model["vocabulary"])
    total_docs = sum(model["class_documents"].values())
    for label, docs in model["class_documents"].items():
        counts = model["token_counts"][label]
        denominator = model["class_tokens"][label] + vocabulary_size
        log_score = math.log(docs / total_docs)
        log_score += sum(math.log((counts.get(token, 0) + 1) / denominator) for token in tokens if token in model["vocabulary"])
        scores[label] = log_score
    peak = max(scores.values())
    probabilities = {label: math.exp(score - peak) for label, score in scores.items()}
    total = sum(probabilities.values())
    label = max(probabilities, key=probabilities.get)
    confidence = probabilities[label] / total
    return {"model": "PharmaClassify", "version": model["version"],
            "category": label if confidence >= 0.4 else "unclassified",
            "confidence": round(confidence, 4), "advisory_only": True}
