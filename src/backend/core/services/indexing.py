"""OpenSearch indexing utilities."""

import logging

from django.conf import settings

from opensearchpy.exceptions import NotFoundError, RequestError
from py3langid.langid import MODEL_FILE, LanguageIdentifier

from core.models import Service
from core.services.opensearch_configuration import (
    ANALYZERS,
    FILTERS,
    MAPPINGS,
)

from .opensearch import opensearch_client

logger = logging.getLogger(__name__)


# see https://pypi.org/project/py3langid/
LANGUAGE_IDENTIFIER = LanguageIdentifier.from_pickled_model(MODEL_FILE, norm_probs=True)
LANGUAGE_IDENTIFIER.set_languages(["en", "fr", "de", "nl"])


def get_service_index_name(service_slug: str) -> str:
    """Return the OpenSearch index name for a given service slug."""
    return f"{settings.OPENSEARCH_INDEX_PREFIX}-{service_slug}"


def get_all_active_service_indices() -> list[str]:
    """Return index names for all currently active services."""
    return [
        get_service_index_name(s.slug)
        for s in Service.objects.filter(is_active=True).only("slug")
    ]


def ensure_index_exists(index_name):
    """Create index if it does not exist"""
    client = opensearch_client()
    try:
        client.indices.get(index=index_name)
    except NotFoundError:
        logger.info("Creating index: %s", index_name)
        try:
            client.indices.create(
                index=index_name,
                body={
                    "settings": {
                        "analysis": {
                            "analyzer": ANALYZERS,
                            "filter": FILTERS,
                        },
                    },
                    "mappings": MAPPINGS,
                },
            )
        except RequestError as error:
            if error.error == "resource_already_exists_exception":
                pass  # Another process created the index first — idempotent
            else:
                raise


def prepare_document_for_indexing(document, service_name):
    """Prepare document for indexing using nested language structure."""
    language_code = detect_language_code(f"{document['title']} {document['content']}")
    return {
        "id": document["id"],
        "service": service_name,
        f"title.{language_code}": document["title"],
        f"content.{language_code}": document["content"],
        "depth": document["depth"],
        "path": document["path"],
        "numchild": document["numchild"],
        "created_at": document["created_at"],
        "updated_at": document["updated_at"],
        "size": document["size"],
        "users": document["users"],
        "groups": document["groups"],
        "reach": document["reach"],
        "tags": document.get("tags", []),
        "is_active": document["is_active"],
    }


def detect_language_code(text):
    """Detect the language code of the document content."""

    detected_code, confidence = LANGUAGE_IDENTIFIER.classify(text)

    if confidence < settings.LANGUAGE_DETECTION_CONFIDENCE_THRESHOLD:
        return settings.UNDETERMINED_LANGUAGE_CODE

    return detected_code
