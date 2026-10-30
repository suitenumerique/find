"""OpenSearch deletion utilities."""

import logging

from .opensearch import async_opensearch_client

logger = logging.getLogger(__name__)


async def delete_documents(index_name, user_sub, document_ids=None, tags=None):
    """
    Delete the documents of an index that the user is allowed to delete, i.e. the
    documents listing the user in their 'users' field.

    Args:
        index_name: Name of the OpenSearch index to delete documents from.
        user_sub: User subject identifier for authorization.
        document_ids: Optional list of document IDs to filter.
        tags: Optional list of tags to filter.

    Returns:
        A tuple with the number of deleted documents and the list of the ids
        of the documents matching the filters that the user may delete.
    """
    logger.info(
        "Deleting documents from index %s with filters: document_ids=%s, tags=%s",
        index_name,
        document_ids,
        tags,
    )

    client = async_opensearch_client()
    deletable_matches = await client.search(
        index=index_name,
        body={"query": get_query(user_sub, document_ids=document_ids, tags=tags)},
    )
    deletable_ids = [hit["_id"] for hit in deletable_matches["hits"]["hits"]]

    if not deletable_ids:
        return 0, deletable_ids

    response = await client.delete_by_query(
        index=index_name,
        body={"query": {"ids": {"values": deletable_ids}}},
    )
    return response.get("deleted", 0), deletable_ids


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
