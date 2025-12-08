"""OpenSearch configuration."""

from django.conf import settings

ANALYZERS = {
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
    "undetermined_language_analyzer": {
        "type": "custom",
        "tokenizer": "standard",
        "filter": [
            "lowercase",
            "asciifolding",
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

FILTERS = {
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
        "title.fr": {
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
        "content.fr": {
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
        "title.en": {
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
        "content.en": {
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
        "title.de": {
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
        "content.de": {
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
        "title.nl": {
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
        "content.nl": {
            "type": "text",
            "analyzer": "dutch_analyzer",
            "fields": {
                "trigrams": {
                    "type": "text",
                    "analyzer": "trigram_analyzer",
                }
            },
        },
        # Undetermined language
        "title.und": {
            "type": "keyword",
            "fields": {
                "text": {
                    "type": "text",
                    "analyzer": "undetermined_language_analyzer",
                    "fields": {
                        "trigrams": {
                            "type": "text",
                            "analyzer": "trigram_analyzer",
                        }
                    },
                }
            },
        },
        "content.und": {
            "type": "text",
            "analyzer": "undetermined_language_analyzer",
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
        "chunks": {
            "type": "nested",
            "properties": {
                "index": {"type": "integer"},
                "content": {"type": "text"},
                "embedding": {
                    "type": "knn_vector",
                    "dimension": settings.EMBEDDING_DIMENSION,
                    "method": {
                        "engine": "lucene",
                        "space_type": "l2",
                        "name": "hnsw",
                        "parameters": {},
                    },
                },
            },
        },
        "embedding_model": {"type": "keyword"},
    },
}
