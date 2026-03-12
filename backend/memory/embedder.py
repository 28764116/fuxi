"""Embedding generation using MiniMax embo-01 model.

MiniMax embedding API requires 'texts' and 'type' parameters,
which differ from OpenAI's interface, so we use httpx directly.
"""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def get_embeddings(texts: list[str], embedding_type: str = "db") -> list[list[float]]:
    """Generate embeddings for a batch of texts using MiniMax API.

    Args:
        texts: List of strings to embed.
        embedding_type: "db" for storage/indexing, "query" for search queries.
    """
    if not texts:
        return []

    try:
        resp = httpx.post(
            f"{settings.embedding_base_url}/embeddings",
            headers={
                "Authorization": f"Bearer {settings.embedding_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.embedding_model,
                "texts": texts,
                "type": embedding_type,
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()

        vectors = data.get("vectors")
        if not vectors:
            logger.warning("No vectors in response: %s", data.get("base_resp"))
            return []

        logger.info("Generated %d embeddings (type=%s)", len(vectors), embedding_type)
        return vectors
    except Exception:
        logger.exception("Embedding generation failed")
        return []
