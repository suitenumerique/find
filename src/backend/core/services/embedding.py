"""OpenSearch embedding utilities."""

import logging

from django.conf import settings

import requests

logger = logging.getLogger(__name__)


def embed_text(text):
    """
    Get embedding vector for the given text from any OpenAI-compatible embedding API
    """
    logger.info("embed: '%s'", text)

    response = requests.post(
        settings.EMBEDDING_API_PATH,
        headers={"Authorization": f"Bearer {settings.EMBEDDING_API_KEY}"},
        json={
            "input": text,
            "model": settings.EMBEDDING_API_MODEL_NAME,
            "dimensions": settings.EMBEDDING_DIMENSION,
            "encoding_format": "float",
        },
        timeout=settings.EMBEDDING_REQUEST_TIMEOUT,
    )

    try:
        response.raise_for_status()
    except requests.HTTPError as e:
        logger.warning("embedding API request failed: %s", str(e))
        return None

    try:
        embedding = response.json()["data"][0]["embedding"]
    except (KeyError, IndexError, TypeError):
        logger.warning("unexpected embedding response format: %s", response.text)
        return None

    return embedding
