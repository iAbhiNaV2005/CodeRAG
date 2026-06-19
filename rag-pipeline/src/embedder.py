"""
Embedding service using sentence-transformers/all-MiniLM-L6-v2.

Loads the model once (singleton) and provides batch encoding.
Produces 384-dimensional vectors, entirely local — no API calls.
"""

import logging

from sentence_transformers import SentenceTransformer

from src.config import get_settings

logger = logging.getLogger(__name__)

# Module-level singleton — model loads on first call
_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    """Load the embedding model (cached as a module-level singleton)."""
    global _model
    if _model is None:
        settings = get_settings()
        logger.info("Loading embedding model: %s", settings.embedding_model)
        _model = SentenceTransformer(settings.embedding_model)
        logger.info(
            "Model loaded. Dimension: %d",
            _model.get_sentence_embedding_dimension(),
        )
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Embed a list of text strings into 384-dimensional vectors.

    Args:
        texts: List of code chunks or queries to embed.

    Returns:
        List of embedding vectors (each is a list of 384 floats).
    """
    if not texts:
        return []

    settings = get_settings()
    model = _get_model()

    logger.info("Embedding %d texts (batch_size=%d)", len(texts), settings.embedding_batch_size)

    embeddings = model.encode(
        texts,
        batch_size=settings.embedding_batch_size,
        show_progress_bar=len(texts) > 100,
        normalize_embeddings=True,  # Pre-normalize for cosine similarity
    )

    # Convert numpy arrays to plain Python lists for pgvector compatibility
    result = [emb.tolist() for emb in embeddings]

    logger.info("Embedding complete. %d vectors produced.", len(result))
    return result


def embed_query(query: str) -> list[float]:
    """
    Embed a single query string.

    Uses the same model as chunk embedding for consistency.

    Args:
        query: The user's question text.

    Returns:
        A single 384-dimensional embedding vector.
    """
    result = embed_texts([query])
    return result[0]
