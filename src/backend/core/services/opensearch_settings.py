"""OpenSearch configuration for multi-language support."""

from django.conf import settings

LANGUAGE_ANALYZERS = {
    "french_analyzer": {
        "type": "custom",
        "tokenizer": "standard",
        "filter": [
            "lowercase",
            "asciifolding",
            "french_elision",
            "french_stop",
            "french_stemmer",
        ],
    },
    "english_analyzer": {
        "type": "custom",
        "tokenizer": "standard",
        "filter": [
            "lowercase",
            "asciifolding",
            "english_stop",
            "english_stemmer",
        ],
    },
    "german_analyzer": {
        "type": "custom",
        "tokenizer": "standard",
        "filter": [
            "lowercase",
            "asciifolding",
            "german_stop",
            "german_stemmer",
        ],
    },
    "dutch_analyzer": {
        "type": "custom",
        "tokenizer": "standard",
        "filter": [
            "lowercase",
            "asciifolding",
            "dutch_stop",
            "dutch_stemmer",
        ],
    },
    "trigram_analyzer": {
        "type": "custom",
        "tokenizer": "standard",
        "filter": [
            "lowercase",
            "asciifolding",
            "trigram_filter",
        ],
    },
}

LANGUAGE_FILTERS = {
    "french_elision": {
        "type": "elision",
        "articles_case": True,
        "articles": [
            "l",
            "m",
            "t",
            "qu",
            "n",
            "s",
            "j",
            "d",
            "c",
            "jusqu",
            "quoiqu",
            "lorsqu",
            "puisqu",
        ],
    },
    "french_stop": {
        "type": "stop",
        "stopwords": "_french_",
    },
    "french_stemmer": {
        "type": "stemmer",
        "language": "light_french",
    },
    "english_stop": {
        "type": "stop",
        "stopwords": "_english_",
    },
    "english_stemmer": {
        "type": "stemmer",
        "language": "english",
    },
    "german_stop": {
        "type": "stop",
        "stopwords": "_german_",
    },
    "german_stemmer": {
        "type": "stemmer",
        "language": "light_german",
    },
    "dutch_stop": {
        "type": "stop",
        "stopwords": "_dutch_",
    },
    "dutch_stemmer": {
        "type": "stemmer",
        "language": "dutch",
    },
    "trigram_filter": {
        "type": "ngram",
        "min_gram": 3,
        "max_gram": 3,
    },
}

MAPPINGS = {
    "dynamic": "strict",
    "properties": {
        "id": {"type": "keyword"},
        # French
        "title.fr-fr": {
            "type": "keyword",
            "fields": {
                "text": {
                    "type": "text",
                    "analyzer": "french_analyzer",
                    "fields": {
                        "trigrams": {
                            "type": "text",
                            "analyzer": "trigram_analyzer",
                        }
                    },
                }
            },
        },
        "content.fr-fr": {
            "type": "text",
            "analyzer": "french_analyzer",
            "fields": {
                "trigrams": {
                    "type": "text",
                    "analyzer": "trigram_analyzer",
                }
            },
        },
        # English
        "title.en-us": {
            "type": "keyword",
            "fields": {
                "text": {
                    "type": "text",
                    "analyzer": "english_analyzer",
                    "fields": {
                        "trigrams": {
                            "type": "text",
                            "analyzer": "trigram_analyzer",
                        }
                    },
                }
            },
        },
        "content.en-us": {
            "type": "text",
            "analyzer": "english_analyzer",
            "fields": {
                "trigrams": {
                    "type": "text",
                    "analyzer": "trigram_analyzer",
                }
            },
        },
        # German
        "title.de-de": {
            "type": "keyword",
            "fields": {
                "text": {
                    "type": "text",
                    "analyzer": "german_analyzer",
                    "fields": {
                        "trigrams": {
                            "type": "text",
                            "analyzer": "trigram_analyzer",
                        }
                    },
                }
            },
        },
        "content.de-de": {
            "type": "text",
            "analyzer": "german_analyzer",
            "fields": {
                "trigrams": {
                    "type": "text",
                    "analyzer": "trigram_analyzer",
                }
            },
        },
        # Dutch
        "title.nl-nl": {
            "type": "keyword",
            "fields": {
                "text": {
                    "type": "text",
                    "analyzer": "dutch_analyzer",
                    "fields": {
                        "trigrams": {
                            "type": "text",
                            "analyzer": "trigram_analyzer",
                        }
                    },
                }
            },
        },
        "content.nl-nl": {
            "type": "text",
            "analyzer": "dutch_analyzer",
            "fields": {
                "trigrams": {
                    "type": "text",
                    "analyzer": "trigram_analyzer",
                }
            },
        },
        "depth": {"type": "integer"},
        "path": {
            "type": "keyword",
            "fields": {"text": {"type": "text"}},
        },
        "numchild": {"type": "integer"},
        "created_at": {"type": "date"},
        "updated_at": {"type": "date"},
        "size": {"type": "long"},
        "users": {"type": "keyword"},
        "groups": {"type": "keyword"},
        "reach": {"type": "keyword"},
        "is_active": {"type": "boolean"},
        "embedding": {
            # for simplicity, embedding is always present but is empty
            # when hybrid search is disabled
            "type": "knn_vector",
            "dimension": settings.EMBEDDING_DIMENSION,
            "method": {
                "engine": "lucene",
                "space_type": "l2",
                "name": "hnsw",
                "parameters": {},
            },
        },
        "embedding_model": {"type": "keyword"},
    },
}
