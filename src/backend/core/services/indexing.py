"""OpenSearch indexing utilities."""

import asyncio
import logging

from django.conf import settings
from django.core.exceptions import SuspiciousOperation

from opensearchpy.exceptions import NotFoundError
from py3langid.langid import MODEL_FILE, LanguageIdentifier
from pydantic import ValidationError as PydanticValidationError

from core.services.opensearch_configuration import (
    ANALYZERS,
    FILTERS,
    MAPPINGS,
)

from .. import schemas
from ..models import Service, get_opensearch_index_name
from .opensearch import async_opensearch_client, opensearch_client

logger = logging.getLogger(__name__)


# see https://pypi.org/project/py3langid/
LANGUAGE_IDENTIFIER = LanguageIdentifier.from_pickled_model(MODEL_FILE, norm_probs=True)
LANGUAGE_IDENTIFIER.set_languages(["en", "fr", "de", "nl"])


INDEX_BODY = {
    "settings": {
        "analysis": {
            "analyzer": ANALYZERS,
            "filter": FILTERS,
        },
    },
    "mappings": MAPPINGS,
}


def ensure_index_exists(index_name):
    """Create index if it does not exist"""
    try:
        opensearch_client().indices.get(index=index_name)
    except NotFoundError:
        logger.info("Creating index: %s", index_name)
        opensearch_client().indices.create(index=index_name, body=INDEX_BODY)


async def aensure_index_exists(index_name):
    """Create index if it does not exist, with the async client"""
    client = async_opensearch_client()
    try:
        await client.indices.get(index=index_name)
    except NotFoundError:
        logger.info("Creating index: %s", index_name)
        await client.indices.create(index=index_name, body=INDEX_BODY)


async def index_document(index_name, document):
    """
    Index a validated document into an OpenSearch index, creating it if needed.

    Args:
        index_name: The name of the OpenSearch index.
        document: A schemas.DocumentSchema instance.

    Returns:
        The id of the indexed document.
    """
    # Language detection is CPU-bound: keep it out of the event loop
    document_dict = await asyncio.to_thread(
        prepare_document_for_indexing, document.model_dump()
    )
    _id = document_dict.pop("id")
    logger.info("Indexing single document %s on index %s", document.title, index_name)

    await aensure_index_exists(index_name)
    await async_opensearch_client().index(index=index_name, body=document_dict, id=_id)
    return _id


def prepare_bulk(index_name, documents_data):
    """
    Validate and prepare documents for bulk indexing.

    Returns:
        A tuple with the status of each document, the bulk actions and whether
        any document failed validation.
    """
    results = []
    actions = []
    has_errors = False

    for i, document_data in enumerate(documents_data):
        try:
            document = schemas.DocumentSchema(**document_data)
        except PydanticValidationError as excpt:
            errors = [
                {key: error[key] for key in ("msg", "type", "loc")}
                for error in excpt.errors()
            ]
            results.append({"index": i, "status": "error", "errors": errors})
            has_errors = True
        else:
            document_dict = prepare_document_for_indexing(document.model_dump())
            logger.info("Indexing document %s on index %s", document.title, index_name)
            _id = document_dict.pop("id")
            actions.append({"index": {"_id": _id}})
            actions.append(document_dict)
            results.append({"index": i, "_id": _id, "status": "valid"})

    return results, actions, has_errors


async def bulk_index_documents(index_name, documents_data):
    """
    Index documents into an OpenSearch index in bulk, creating it if needed.
    Nothing is indexed if any document fails validation.

    Args:
        index_name: The name of the OpenSearch index.
        documents_data: A list of documents, as dicts to validate.

    Returns:
        A tuple with the status of each document and whether any document failed
        validation.
    """
    # Validation and language detection are CPU-bound: keep them out of the event loop
    results, actions, has_errors = await asyncio.to_thread(
        prepare_bulk, index_name, documents_data
    )
    if has_errors:
        return results, has_errors

    await aensure_index_exists(index_name)
    response = await async_opensearch_client().bulk(index=index_name, body=actions)
    for i, item in enumerate(response["items"]):
        if item["index"]["status"] != 201:
            results[i]["status"] = "error"
            results[i]["message"] = (
                item["index"].get("error", {}).get("reason", "Unknown error")
            )
        else:
            results[i]["status"] = "success"

    return results, has_errors


def prepare_document_for_indexing(document):
    """Prepare document for indexing using nested language structure"""
    language_code = detect_language_code(f"{document['title']} {document['content']}")
    return {
        "id": document["id"],
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
