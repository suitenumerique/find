"""OpenSearch deletion utilities."""

import logging

from .opensearch import async_opensearch_client

logger = logging.getLogger(__name__)


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
        response = await client.delete_by_query(index=index_name, body={"query": query})
        return response.get("deleted", 0), []

    # An ids filter cannot match more documents than requested ids
    deletable_matches = await client.search(
        index=index_name,
        body={"query": query, "_source": False, "seq_no_primary_term": True},
        size=len(set(document_ids)),
    )
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
    return {
        item["delete"]["_id"]
        for item in response["items"]
        if item["delete"].get("result") == "deleted"
    }


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
