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
def load_n_process_task(service_id):
    """Celery Task : Re-index documents with deferred loading."""
    service = get_service(service_id)

    if service is not None:
        indexer = IndexerTaskService(service, force_refresh=True)

        logger.info("Start deferred loading on index %s", service.index_name)
        indexer.load_n_process_all()


@app.task
def process_task(service_id):
    """Celery Task : Re-index documents with deferred loading."""
    service = get_service(service_id)

    if service is not None:
        indexer = IndexerTaskService(service, force_refresh=True)

        logger.info("Start deferred preprocessing on index %s", service.index_name)
        indexer.process_all()


@app.task
def embedding_task(service_id):
    """Celery Task : Re-index documents for embedding."""
    service = get_service(service_id)

    if service is not None:
        indexer = IndexerTaskService(service, force_refresh=True)

        logger.info("Start embedding on index %s", service.index_name)
        indexer.embed_all()


def dispatch_indexing_tasks(service, documents: List[models.IndexDocument]):
    """
    Trigger task related to the different status of the documents
    """
    countdown = settings.INDEXER_TASK_COUNTDOWN
    should_load = any(doc.is_waiting for doc in documents)
    should_preprocess = any(doc.is_loaded for doc in documents)
    should_embed = check_hybrid_search_enabled() and any(
        doc.is_ready and not doc.embedding for doc in documents
    )

    # Trigger task for deferred loading if the file is too big
    if should_load:
        load_n_process_task.apply_async((service.pk,), countdown=countdown)

    # Trigger task for deferred preprocessing of the content (picture analysis for instance)
    if should_preprocess:
        process_task.apply_async((service.pk,), countdown=countdown)

    # Trigger task for semantic indexation
    if should_embed:
        embedding_task.apply_async((service.pk,), countdown=countdown)
