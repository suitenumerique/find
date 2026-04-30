"""OpenSearch indexing utilities."""

import logging

from django.conf import settings
from django.core.exceptions import SuspiciousOperation

from langchain_text_splitters import RecursiveCharacterTextSplitter
from opensearchpy.exceptions import NotFoundError
from py3langid.langid import MODEL_FILE, LanguageIdentifier

from core.services.opensearch_configuration import (
    ANALYZERS,
    FILTERS,
    MAPPINGS,
)

from ..models import Service, get_opensearch_index_name
from .embedding import embed_text
from .opensearch import opensearch_client

logger = logging.getLogger(__name__)


# see https://pypi.org/project/py3langid/
LANGUAGE_IDENTIFIER = LanguageIdentifier.from_pickled_model(MODEL_FILE, norm_probs=True)
LANGUAGE_IDENTIFIER.set_languages(["en", "fr", "de", "nl"])

TEXT_SPLITER = RecursiveCharacterTextSplitter(
    chunk_size=settings.CHUNK_SIZE,
    chunk_overlap=settings.CHUNK_OVERLAP,
)


def ensure_index_exists(index_name):
    """Create index if it does not exist"""
    try:
        opensearch_client().indices.get(index=index_name)
    except NotFoundError:
        logger.info("Creating index: %s", index_name)
        opensearch_client().indices.create(
            index=index_name,
            body={
                "settings": {
                    "index.knn": True,
                    "analysis": {
                        "analyzer": ANALYZERS,
                        "filter": FILTERS,
                    },
                },
                "mappings": MAPPINGS,
            },
        )


def chunk_document(title, content):
    """
    Chunk a document into multiple pieces and embed them.
    """
    chunks = []
    for idx, chunked_content in enumerate(TEXT_SPLITER.split_text(content)):
        embedding = embed_text(format_document(title, chunked_content))

        if not embedding:
            logger.warning(
                "Failed to embed chunk %d of document '%s'. Document embedding is skipped",
                idx,
                title,
            )
            # if embedding fails for any chunk, we skip chunking the document
            return None

        chunks.append(
            {
                "index": idx,
                "content": chunked_content,
                "embedding": embedding,
            }
        )

    logger.info("Document %s chunked into %d pieces", title, len(chunks))
    return chunks


def format_document(title, content):
    """Get the embedding input format for a document"""
    return f"<{title}>:<{content}>"


def detect_language_code(text):
    """Detect the language code of the document content."""

    detected_code, confidence = LANGUAGE_IDENTIFIER.classify(text)

    if confidence < settings.LANGUAGE_DETECTION_CONFIDENCE_THRESHOLD:
        return settings.UNDETERMINED_LANGUAGE_CODE

    return detected_code


def get_opensearch_indices(audience, services):
    """
    Get OpenSearch indices for the given audience and services.
    """
    try:
        user_service = Service.objects.get(client_id=audience, is_active=True)
    except Service.DoesNotExist as e:
        logger.warning("Login failed: No service %s found", audience)
        raise SuspiciousOperation("Service is not available") from e

    # Find allowed sub-services for this service
    allowed_services = set(user_service.services.values_list("name", flat=True))
    allowed_services.add(user_service.name)

    if services:
        available_service = set(services).intersection(allowed_services)

        if len(available_service) < len(services):
            raise SuspiciousOperation("Some requested services are not available")

    return [get_opensearch_index_name(service) for service in allowed_services]
