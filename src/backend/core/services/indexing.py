"""OpenSearch indexing utilities."""

import logging

from django.conf import settings

from opensearchpy.exceptions import NotFoundError
from py3langid.langid import MODEL_FILE, LanguageIdentifier

from core.services import opensearch
from core.services.opensearch_configuration import (
    ANALYZERS,
    FILTERS,
    MAPPINGS,
)

logger = logging.getLogger(__name__)


# see https://pypi.org/project/py3langid/
LANGUAGE_IDENTIFIER = LanguageIdentifier.from_pickled_model(MODEL_FILE, norm_probs=True)
LANGUAGE_IDENTIFIER.set_languages(["en", "fr", "de", "nl"])


def ensure_index_exists(index_name):
    """Create index if it does not exist"""
    try:
        opensearch.opensearch_client().indices.get(index=index_name)
    except NotFoundError:
        logger.info("Creating index: %s", index_name)
        opensearch.opensearch_client().indices.create(
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
