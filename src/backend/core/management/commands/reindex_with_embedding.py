"""
Handle reindexing of documents with embeddings in OpenSearch.
"""

from django.core.management.base import BaseCommand, CommandError

from opensearchpy.exceptions import NotFoundError

from core.services.opensearch import (
    check_hybrid_search_enabled,
    embed_text,
    ensure_index_exists,
    opensearch_client,
)


class Command(BaseCommand):
    """Reindex all documents with embeddings"""

    help = __doc__
    opensearch_client_ = opensearch_client()

    def add_arguments(self, parser):
        parser.add_argument("index_name", type=str)

    def handle(self, *args, **options):
        """Launch the reindexing with embedding."""

        source_index = options["index_name"]
        # destination index is used to duplicate the source index with embeddings.
        # It is then rename to the source index name after reindexing.
        destination_index = f"{source_index}-embedded"

        if not check_hybrid_search_enabled():
            raise CommandError("Hybrid search is not enabled or properly configured.")

        try:
            self.opensearch_client_.indices.get(index=source_index)
        except NotFoundError as error:
            raise CommandError(
                f"Source index {source_index} does not exist."
            ) from error

        self.stdout.write(f"[INFO] Start reindexing {source_index} with embedding.")

        reindex_with_embedding(self.opensearch_client_, source_index, destination_index)

        self.opensearch_client_.indices.refresh(index=destination_index)
        # Validate that reindexing completed successfully
        # before renaming destination index to source index.
        self.validate_reindex(source_index, destination_index)
        self.replace_source_index_with_destination_index(
            source_index, destination_index
        )

        self.stdout.write(f"[INFO] Reindexing of {source_index} is successful.")

    def validate_reindex(self, source_index, destination_index):
        """
        Checks destination index is the same as source index with embeddings added.
        """

        success, message = check_index_dimensions_match(
            self.opensearch_client_, source_index, destination_index
        )
        if not success:
            raise CommandError(message)

        sample_size = 100
        source_sample_documents = self.opensearch_client_.search(
            index=source_index, size=sample_size, body={"query": {"match_all": {}}}
        )
        destination_sample_documents = self.opensearch_client_.search(
            index=destination_index, size=sample_size, body={"query": {"match_all": {}}}
        )

        success, message = check_embeddings_populated(destination_sample_documents)
        if not success:
            raise CommandError(message)

        success, message = check_document_fields(
            source_sample_documents, destination_sample_documents
        )
        if not success:
            raise CommandError(message)

    def replace_source_index_with_destination_index(
        self, source_index, destination_index
    ):
        """Delete source index and rename destination index to source index."""
        self.opensearch_client_.indices.delete(index=source_index)
        self.opensearch_client_.indices.put_alias(
            index=destination_index, name=source_index
        )


def reindex_with_embedding(
    opensearch_client_, source_index, destination_index, batch_size=500
):
    """Reindex documents from source index to destination index with embeddings."""

    destination_index = f"{source_index}-embedded"
    ensure_index_exists(destination_index)

    page = opensearch_client_.search(
        index=source_index,
        scroll="5m",
        size=batch_size,
        body={"query": {"match_all": {}}},
    )
    scroll_id = page["_scroll_id"]
    scroll_size = len(page["hits"]["hits"])

    while scroll_size > 0:
        actions = []
        for hit in page["hits"]["hits"]:
            document = hit["_source"]

            if document.get("embedding") is None:
                document["embedding"] = embed_text(
                    f"<{document.get('text')}>:<{document.get('content')}>"
                )

            actions.append({"index": {"_id": hit["_id"]}})
            actions.append(document)

        page = opensearch_client_.scroll(scroll_id=scroll_id, scroll="5m")
        scroll_id = page["_scroll_id"]
        scroll_size = len(page["hits"]["hits"])

        opensearch_client_.bulk(index=destination_index, body=actions)

    opensearch_client_.clear_scroll(scroll_id=scroll_id)


def check_index_dimensions_match(opensearch_client_, source_index, destination_index):
    """Check that source and destination index have the same document count."""
    source_count = opensearch_client_.count(index=source_index)["count"]
    destination_count = opensearch_client_.count(index=destination_index)["count"]
    if source_count != destination_count:
        return (
            False,
            f"Destination index does not match source index dimension: {source_count} != {destination_count}",
        )
    return True, None


def check_embeddings_populated(destination_sample_docs):
    """Check that all documents in destination sample have embeddings."""
    for hit in destination_sample_docs["hits"]["hits"]:
        if not hit["_source"]["embedding"]:
            return False, "some documents are missing embeddings"
    return True, None


def check_document_fields(source_sample_documents, destination_sample_documents):
    """Check that all documents in destination sample have the same fields as source."""
    for source_hit, destination_hit in zip(
        source_sample_documents["hits"]["hits"],
        destination_sample_documents["hits"]["hits"],
        strict=False,
    ):
        source_fields = set(source_hit["_source"].keys())
        destination_fields = set(destination_hit["_source"].keys())
        if not source_fields.issubset(destination_fields):
            missing = source_fields - destination_fields
            return (
                False,
                f"Document {destination_hit['_id']} is missing fields: {missing}",
            )
    return True, None
