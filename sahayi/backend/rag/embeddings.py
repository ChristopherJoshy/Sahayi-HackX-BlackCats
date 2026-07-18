"""Embedding helpers for SAHAYI."""

from __future__ import annotations

import hashlib
from functools import lru_cache

try:
    from sentence_transformers import SentenceTransformer
except ImportError:  # pragma: no cover - optional fast path only.
    SentenceTransformer = None


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of text strings.

    Args:
        texts: Text strings to embed.
    Returns:
        Dense vector embeddings as Python lists.
    Agent:
        RAG
    """

    if not texts:
        return []
    if SentenceTransformer:
        return _get_embedding_model().encode(texts, normalize_embeddings=True).tolist()
    return [_hash_embedding(text) for text in texts]


@lru_cache(maxsize=1)
def _get_embedding_model() -> SentenceTransformer:
    """Load and cache the sentence-transformer model when available.

    Args:
        None: Uses the fixed local embedding model name.
    Returns:
        Loaded SentenceTransformer instance.
    Agent:
        RAG
    """

    return SentenceTransformer("all-MiniLM-L6-v2")


def warmup_embeddings() -> None:
    """Preload the embedding model at startup so the first call is instant.

    Loading ``all-MiniLM-L6-v2`` pulls weights from the HuggingFace hub on
    first use, which otherwise happens mid-call and stalls the voice/Research
    flow with a download + progress bar. Calling this during app boot warms
    the lru-cached model before any request arrives.

    Args:
        None: Triggers ``_get_embedding_model`` and a tiny probe encode.
    Returns:
        None.
    Agent:
        RAG
    """

    if not SentenceTransformer:
        return
    # Loading the model prints a "Loading weights" tqdm bar (and an HF notice)
    # on first download. Silence all stdout/stderr during warmup so those only
    # ever appear at boot, never mid-call. Restores streams afterwards.
    import os
    import sys
    env_prev = os.environ.get("HF_HUB_DISABLE_PROGRESS_BARS")
    os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    old_out, old_err = sys.stdout, sys.stderr
    devnull = open(os.devnull, "w")
    sys.stdout, sys.stderr = devnull, devnull
    try:
        _get_embedding_model().encode(["warmup"], normalize_embeddings=True)
    finally:
        sys.stdout, sys.stderr = old_out, old_err
        devnull.close()
        if env_prev is None:
            os.environ.pop("HF_HUB_DISABLE_PROGRESS_BARS", None)
        else:
            os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = env_prev


def _hash_embedding(text: str) -> list[float]:
    """Build a deterministic lightweight fallback embedding.

    Args:
        text: Input text string.
    Returns:
        Dense pseudo-embedding vector.
    Agent:
        RAG
    """

    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [((digest[index % len(digest)] / 255.0) * 2) - 1 for index in range(128)]
