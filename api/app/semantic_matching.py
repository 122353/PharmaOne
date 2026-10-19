
"""Optional local MiniLM scoring for PharmaOne."""

from functools import lru_cache
import math
import unicodedata
from threading import RLock


EMBEDDING_CACHE_SIZE = 1024
MAX_NAME_CHARACTERS = 2048
_model_lock = RLock()
_encoding_lock = RLock()


@lru_cache(maxsize=1)
def _load_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(
        "sentence-transformers/all-MiniLM-L6-v2",
        device="cpu",
        local_files_only=True,
    )


def get_model():
    # Lock outside the cached loader so concurrent cold callers check the
    # populated cache after construction, rather than each building a model.
    with _model_lock:
        return _load_model()


get_model.cache_clear = _load_model.cache_clear
get_model.cache_info = _load_model.cache_info


def _normalized_name(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value or "").casefold().split())


@lru_cache(maxsize=EMBEDDING_CACHE_SIZE)
def _embedding(name: str) -> tuple[float, ...]:
    """Cache immutable vectors by normalized name; failures are not cached."""
    if len(name) > MAX_NAME_CHARACTERS:
        raise ValueError("medicine name exceeds local embedding limit")
    model = get_model()
    with _encoding_lock:
        vector = model.encode(
            [name],
            normalize_embeddings=True,
            convert_to_numpy=True,
        )[0]
    result = tuple(float(component) for component in vector)
    if not result or not all(math.isfinite(component) for component in result):
        raise ValueError("embedding must contain finite values")
    return result


def semantic_similarity(left: str, right: str) -> float:
    """Return advisory cosine similarity using bounded normalized-name caching."""
    left, right = _normalized_name(left), _normalized_name(right)
    if not left or not right:
        return 0.0

    a, b = _embedding(left), _embedding(right)
    if len(a) != len(b):
        raise ValueError("embedding dimensions differ")
    score = sum(x * y for x, y in zip(a, b))

    return round(max(-1.0, min(1.0, score)), 4)


def semantic_evidence(left: str, right: str) -> dict:
    """Return an advisory score for the existing matcher."""
    score = semantic_similarity(left, right)

    return {
        "model": "all-MiniLM-L6-v2",
        "semantic_similarity": score,
        "threshold_role": "candidate_retrieval_only",
        "advisory_only": True,
    }
