"""Celery task for deferred indexing"""

import logging
from typing import List

from django.conf import settings

from core import models
from core.services.indexer_services import IndexerTaskService
from core.services.opensearch import check_hybrid_search_enabled

from find.celery_app import app

logger = logging.getLogger(__file__)


def get_service(service_id):
    """Returns the required active service"""
    try:
        return models.Service.objects.get(pk=service_id, is_active=True)
    except models.Service.DoesNotExist:
        logging.warning("The service {service_id} does not exit or disabled")
        return None


@app.task
def loading_task(service_id):
    """Celery Task : Re-index documents with deferred loading."""
    service = get_service(service_id)

    if service is not None:
        indexer = IndexerTaskService(service)

        logger.info("Start deferred loading on index %s", service.index_name)
        indexer.load_all()

        # Trigger the embedding task if enabled
        if check_hybrid_search_enabled():
            embedding_task.apply_async((service_id,))


@app.task
def preprocess_task(service_id):
    """Celery Task : Re-index documents with deferred loading."""
    service = get_service(service_id)

    if service is not None:
        indexer = IndexerTaskService(service)

        logger.info("Start deferred preprocessing on index %s", service.index_name)
        indexer.preprocess_all()

        # Trigger the embedding task if enabled
        if check_hybrid_search_enabled():
            embedding_task.apply_async((service_id,))


@app.task
def embedding_task(service_id):
    """Celery Task : Re-index documents for embedding."""
    service = get_service(service_id)

    if service is not None:
        indexer = IndexerTaskService(service)

        logger.info("Start embedding on index %s", service.index_name)
        indexer.embed_all()


def dispatch_indexing_tasks(service, documents: List[models.IndexDocument]):
    """
    Trigger task related to the different status of the documents
    """
    countdown = settings.INDEXER_DISPATCH_COUNTDOWN

    # Trigger tasks for deferred loading
    if any(doc.is_waiting for doc in documents):
        loading_task.apply_async((service.pk,), countdown=countdown)
    elif any(doc.is_loaded for doc in documents):
        preprocess_task.apply_async((service.pk,), countdown=countdown)
    elif check_hybrid_search_enabled():
        embedding_task.apply_async((service.pk,), countdown=countdown)
