"""OpenSearch configuration for multi-language support."""

LANGUAGE_CODE_TO_ANALYZER_NAME = {
    "fr-fr": "french_analyzer",
    "en-us": "english_analyzer",
    "de-de": "german_analyzer",
    "nl": "dutch_analyzer",
}

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
            # "dutch_stemmer",
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
        "language": "light_english",
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
    # "dutch_stemmer": {
    #     "type": "stemmer",
    #     "language": "dutch",
    # },
    "trigram_filter": {
        "type": "ngram",
        "min_gram": 3,
        "max_gram": 3,
    },
}


def get_language_mapping():
    """Generated language mappings for direct use in index creation"""
    return {
        language_code: {
            "properties": {
                "title": get_language_field_mapping(analyzer),
                "content": get_language_field_mapping(analyzer),
            }
        }
        for language_code, analyzer in LANGUAGE_CODE_TO_ANALYZER_NAME.items()
    }


def get_language_field_mapping(analyzer_name):
    """Generate field mapping for a specific analyzer"""
    return {
        "type": "text",
        "analyzer": analyzer_name,
        "fields": {
            "trigrams": {
                "type": "text",
                "analyzer": "trigram_analyzer",
            }
        },
    }
