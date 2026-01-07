from functools import lru_cache
from typing import List

from sentence_transformers import SentenceTransformer

from app.core.config import settings


@lru_cache(maxsize=1)
def get_embedder() -> SentenceTransformer:
    # Heavy model load is memoized so workers reuse the same instance.
    return SentenceTransformer(settings.EMBED_MODEL)


def embed_chunks(chunks: List[str]):
    """Run embeddings; return numpy array for optional downstream storage."""
    model = get_embedder()
    return model.encode(chunks, normalize_embeddings=True)
