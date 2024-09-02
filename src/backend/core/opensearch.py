"""Opensearch related utils."""
from django.conf import settings

from opensearchpy import OpenSearch
from opensearchpy.exceptions import NotFoundError

client = OpenSearch(
    hosts=[{"host": settings.OPENSEARCH_HOST, "port": settings.OPENSEARCH_PORT}],
    http_auth=(settings.OPENSEARCH_USER, settings.OPENSEARCH_PASSWORD),
    timeout=50,
    use_ssl=settings.OPENSEARCH_USE_SSL,
    verify_certs=False,
)


def ensure_index_exists(index_name):
    """Create index if it does not exist"""
    try:
        client.indices.get(index=index_name)
    except NotFoundError:
        client.indices.create(
            index=index_name,
            body={
                "mappings": {
                    "dynamic": "strict",
                    "properties": {
                        "title": {
                            "type": "keyword",  # Primary field for exact matches and sorting
                            "fields": {
                                "text": {
                                    "type": "text"  # Sub-field for full-text search
                                }
                            },
                        },
                        "content": {"type": "text"},
                        "created_at": {"type": "date"},
                        "updated_at": {"type": "date"},
                        "size": {"type": "long"},
                        "users": {"type": "keyword"},
                        "groups": {"type": "keyword"},
                        "is_public": {"type": "boolean"},
                    },
                }
            },
        )
