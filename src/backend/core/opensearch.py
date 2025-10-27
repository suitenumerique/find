"""Opensearch related utils."""

from functools import cache
from django.conf import settings

from . import enums
from opensearchpy import OpenSearch
from opensearchpy.exceptions import NotFoundError
from sentence_transformers import SentenceTransformer


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
        print(f"Creating index: {index_name}")
        client.indices.create(
            index=index_name,
            body={
                "mappings": {
                    "dynamic": "strict",
                    "properties": {
                        "id": {"type": "keyword"},
                        "title": {
                            "type": "keyword",  # Primary field for exact matches and sorting
                            "fields": {
                                "text": {
                                    "type": "text"
                                }  # Sub-field for full-text search
                            },
                        },
                        "depth": {"type": "integer"},
                        "path": {
                            "type": "keyword",
                            "fields": {"text": {"type": "text"}},
                        },
                        "numchild": {"type": "integer"},
                        "content": {"type": "text"},
                        "created_at": {"type": "date"},
                        "updated_at": {"type": "date"},
                        "size": {"type": "long"},
                        "users": {"type": "keyword"},
                        "groups": {"type": "keyword"},
                        "reach": {"type": "keyword"},
                        "is_active": {"type": "boolean"},
                        "embedding": {
                            "type": "knn_vector",
                            "dimension": 384,
                        }
                    },
                },
                "settings": {
                    "index": {
                        "knn": True,
                    },
                },
            },
        )

def ensure_search_pipeline_exists(pipeline_id):
    """Create search pipeline for hybrid search if it does not exist"""
    try:
        client.search_pipeline.get(pipeline_id)
    except NotFoundError:
        print(f"Creating search pipeline: {pipeline_id}")
        client.transport.perform_request(
            method="PUT",
            url=f"/_search/pipeline/{pipeline_id}",
            body={
                "description": "Post processor for hybrid search",
                "phase_results_processors": [
                    {
                        "normalization-processor": {
                            "combination": {
                                "technique": "arithmetic_mean",
                                "parameters": {
                                    "weights": settings.HYBRID_SEARCH_WEIGHTS
                                }
                            }
                        }
                    }
                ]
            }
        )

def search(
    q, 
    page_number, 
    page_size, 
    order_by, 
    order_direction, 
    search_indices, 
    reach,
    visited,
    user_sub, 
    groups
):
    ensure_search_pipeline_exists(settings.NLP_SEARCH_PIPELINE_ID)
    return client.search(
        index=",".join(search_indices),
        body={
            "_source": enums.SOURCE_FIELDS,  # limit the fields to return
            "script_fields": {
                "number_of_users": {"script": {"source": "doc['users'].size()"}},
                "number_of_groups": {"script": {"source": "doc['groups'].size()"}},
            },
            "sort": get_sort(order_by, order_direction),
            # Compute pagination parameters
            "from": (page_number - 1) * page_size,
            "size":  page_size,
            # Compute query
            "query": get_query(q, reach, visited, user_sub, groups),
        },
        params={"search_pipeline": settings.NLP_SEARCH_PIPELINE_ID},
        ignore_unavailable=True,
    ) 

def get_query(q, reach, visited, user_sub, groups): 
    filter = get_filter(reach, visited, user_sub, groups)

    if q == "*":
        return {
            "bool": {
                "must": {"match_all": {}},
                "filter": {"bool": {"filter": filter}} 
            }, 
        }
    else:
        model = load_embedding_model()
        return {
            "hybrid": {
                "queries": [
                    {
                        "bool": {
                            "must": {
                                "multi_match": {
                                    "query": q,
                                    # Give title more importance over content by a power of 3
                                    "fields": ["title.text^3", "content"],
                                }
                            },
                            "filter": filter
                        }
                    },
                    {
                        "bool": {
                            "must": {
                                "knn": {
                                    "embedding": {
                                        "vector": model.encode(q),
                                        "k": 20  
                                    }
                                }
                            },
                            "filter": filter
                        }
                    }
                ]
            }
        }

def get_filter(reach, visited, user_sub, groups):
    filters = []

    # Optional reach filter
    if reach is not None:
        filters.append({"term": {enums.REACH: reach}})

    # Always filter out inactive documents
    filters.append({"term": {"is_active": True}})

    # Access control filters
    filters.append( {
        "bool": {
            "should": [
                # Public or authenticated (not restricted)
                {
                    "bool": {
                        "must_not": {
                            "term": {enums.REACH: enums.ReachEnum.RESTRICTED},
                        },
                        "must": {
                            "terms": {"_id": sorted(visited)},
                        },
                    }
                },
                # Restricted: either user or group must match
                {"term": {enums.USERS: user_sub}},
                {"terms": {enums.GROUPS: groups}},
            ],
            "minimum_should_match": 1,
        }
    })
    return filters

def get_sort(order_by, order_direction):
    # Add sorting logic based on relevance or specified field
    if order_by == enums.RELEVANCE:
        return {"_score": {"order": order_direction}}
    else:
        return {order_by: {"order": order_direction}}

def embbed_document(document):
    model = load_embedding_model()
    return model.encode(f"[{document.title}] [{document.content}]")

@cache
def load_embedding_model():
    return SentenceTransformer(settings.EMBEDDING_MODEL_PATH)
