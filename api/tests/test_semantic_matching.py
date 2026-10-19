"""Cache tests replace only the optional encoder; no weights or network needed."""

import math

import pytest

from app import semantic_matching as semantic


class Vector(list):
    def __matmul__(self, other):
        return sum(a * b for a, b in zip(self, other))


class Encoder:
    def __init__(self):
        self.encoded = []

    def encode(self, texts, **kwargs):
        self.encoded.extend(texts)
        return [Vector([1.0, 0.0]) for _ in texts]


@pytest.fixture
def encoder(monkeypatch):
    encoder = Encoder()
    monkeypatch.setattr(semantic, "get_model", lambda: encoder)
    if hasattr(semantic, "_embedding"):
        semantic._embedding.cache_clear()
    yield encoder
    if hasattr(semantic, "_embedding"):
        semantic._embedding.cache_clear()


def test_normalized_names_share_an_embedding_across_pairs(encoder):
    assert semantic.semantic_similarity("  Linezolid\u00a0TABLET 600ｍｇ ", "linezolid tablet 600mg") == 1.0
    assert semantic.semantic_similarity("linezolid tablet 600mg", "Linezolid TABLET 600mg") == 1.0
    assert encoder.encoded == ["linezolid tablet 600mg"]


def test_embedding_cache_is_bounded_and_evicts_old_names(encoder):
    for index in range(1030):
        semantic.semantic_similarity(f"drug {index}", "reference")
    assert semantic._embedding.cache_info().currsize == 1024
    count = len(encoder.encoded)
    semantic.semantic_similarity("drug 0", "reference")
    assert len(encoder.encoded) == count + 1


def test_whitespace_only_names_do_not_load_encoder(encoder):
    assert semantic.semantic_similarity(" \t ", "drug") == 0.0
    assert encoder.encoded == []


def test_nonfinite_encoder_output_is_rejected(encoder):
    encoder.encode = lambda texts, **_kwargs: [Vector([math.nan, 0.0]) for _ in texts]
    with pytest.raises(ValueError, match="finite"):
        semantic.semantic_similarity("drug", "other")


def test_model_is_loaded_once_and_local_only(monkeypatch):
    import sys
    from types import SimpleNamespace

    calls = []
    model = object()

    def constructor(*args, **kwargs):
        calls.append((args, kwargs))
        return model

    semantic.get_model.cache_clear()
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=constructor))
    try:
        assert semantic.get_model() is model
        assert semantic.get_model() is model
        assert len(calls) == 1
        assert calls[0][1]["local_files_only"] is True
        assert calls[0][1]["device"] == "cpu"
    finally:
        semantic.get_model.cache_clear()


def test_concurrent_cold_requests_construct_only_one_model(monkeypatch):
    import sys
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor
    from types import SimpleNamespace

    calls = []
    model = object()
    entered = threading.Barrier(4)

    def constructor(*args, **kwargs):
        calls.append(1)
        time.sleep(0.05)  # Simulate native loading while other callers arrive.
        return model

    semantic.get_model.cache_clear()
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=constructor))
    def request():
        entered.wait(timeout=2)
        return semantic.get_model()
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            outputs = list(pool.map(lambda _: request(), range(4)))
        assert all(output is model for output in outputs)
        assert len(calls) == 1
    finally:
        semantic.get_model.cache_clear()
