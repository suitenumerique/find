"""OpenSearch deletion utilities."""

import logging

from .opensearch import async_opensearch_client

logger = logging.getLogger(__name__)

# A document changed or deleted since it was matched is not deleted, without error
SKIPPED_STATUSES = {404, 409}


class DeletionError(Exception):
    """OpenSearch could not delete some of the deletable documents"""


async def delete_documents(index_name, user_sub, document_ids=None, tags=None):
    """
    Delete all the documents of an index matching the filters that the user is
    allowed to delete, i.e. the documents listing the user in their 'users' field.

    Args:
        index_name: Name of the OpenSearch index to delete documents from.
        user_sub: User subject identifier for authorization.
        document_ids: Optional list of document IDs to filter.
        tags: Optional list of tags to filter.

    Returns:
        A tuple with the number of deleted documents and the list of the requested
        document ids that were not deleted, because they do not exist, the user may
        not delete them or they do not match the tags.

    Raises:
        DeletionError: if OpenSearch failed to delete deletable documents, which
            may then be partially deleted.
    """
    logger.info(
        "Deleting documents from index %s with filters: document_ids=%s, tags=%s",
        index_name,
        document_ids,
        tags,
    )

    client = async_opensearch_client()
    query = get_query(user_sub, document_ids=document_ids, tags=tags)

    if not document_ids:
        response = await client.delete_by_query(
            index=index_name,
            body={"query": query},
            # A document changed since it was matched is kept, as with ids
            conflicts="proceed",
            # A service that never indexed documents has no index
            ignore_unavailable=True,
        )
        if response.get("failures") or response.get("timed_out"):
            logger.error(
                "Failed to delete documents from index %s: %s",
                index_name,
                response.get("failures") or "timed out",
            )
            raise DeletionError(index_name)
        return response.get("deleted", 0), []

    # An ids filter cannot match more documents than requested ids
    deletable_matches = await client.search(
        index=index_name,
        body={"query": query, "_source": False, "seq_no_primary_term": True},
        size=len(set(document_ids)),
        ignore_unavailable=True,
    )
    # Partial hits would report deletable documents as undeleted
    if deletable_matches.get("timed_out") or deletable_matches["_shards"].get("failed"):
        logger.error(
            "Failed to search the deletable documents of index %s: %s",
            index_name,
            deletable_matches["_shards"].get("failures") or "timed out",
        )
        raise DeletionError(index_name)
    deleted_ids = await delete_unchanged(
        client, index_name, deletable_matches["hits"]["hits"]
    )
    undeleted_ids = [
        document_id for document_id in document_ids if document_id not in deleted_ids
    ]
    return len(deleted_ids), undeleted_ids


async def delete_unchanged(client, index_name, hits):
    """
    Delete the documents of search hits, only if they did not change since the
    search: a document updated in between may no longer match the user or the
    tags, so its deletion fails with a version conflict and it is kept.

    Returns:
        The set of the ids of the deleted documents.

    Raises:
        DeletionError: if a deletion failed for another reason.
    """
    if not hits:
        return set()
    actions = [
        {
            "delete": {
                "_id": hit["_id"],
                "if_seq_no": hit["_seq_no"],
                "if_primary_term": hit["_primary_term"],
            }
        }
        for hit in hits
    ]
    response = await client.bulk(index=index_name, body=actions)
    items = [item["delete"] for item in response["items"]]
    failures = [
        item
        for item in items
        if "error" in item and item["status"] not in SKIPPED_STATUSES
    ]
    if failures:
        logger.error(
            "Failed to delete documents from index %s: %s", index_name, failures
        )
        raise DeletionError(index_name)
    return {item["_id"] for item in items if item.get("result") == "deleted"}


def get_query(user_sub, document_ids=None, tags=None):
    """
    Build OpenSearch query for document deletion.

    Args:
        user_sub: User subject identifier for authorization.
        document_ids: Optional list of document IDs to filter.
        tags: Optional list of tags to filter.

    Returns:
        Deletion OpenSearch query.
    """
    filters = [{"term": {"users": user_sub}}]
    if document_ids:
        filters.append({"ids": {"values": document_ids}})
    if tags:
        filters.append({"terms": {"tags": tags}})
    return {"bool": {"must": filters}}
