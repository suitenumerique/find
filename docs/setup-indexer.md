# Using the Find indexer

This guide explains how to setup the Find service which provide an API for indexation and fulltext search of
documents from various sources in a secure way : only the documents within the scope of the user's OIDC token
are visible.

## Setup Opensearch

### General

Add the following variables to your Django settings to configure Find and enable full-text search.

```python
# Login for opensearch
OPENSEARCH_USER=opensearch-user
OPENSEARCH_PASSWORD=your-opensearch-password

# Host configuration
OPENSEARCH_HOST=opensearch
OPENSEARCH_PORT=9200

# Enable SSL for opensearch connection (False in dev mode)
OPENSEARCH_USE_SSL=True

# Prefix for the index name of the registered services.
OPENSEARCH_INDEX_PREFIX=find
```

### Language
Find supports french, english, german and dutch. 

Language specific operations are applied to document titles and contents to improve search results. 
The indexing and search endpoints take an optional 'language_code' query param to identify the language.
If the language is not provided the language will fall-back to the default language. The default language can
be control with a DEFAULT_LANGUAGE_CODE environment variable.

```python
DEFAULT_LANGUAGE_CODE=en-us
````

Supported values are 'fr-fr', 'en-us', 'de-de', 'nl-nl'.

### Semantic search

Find offers a semantic search feature. You can either use pure full-text search or a hybrid full-text + semantic search. To enable the hybrid search, add the following settings. 

```python
# Enable flag
HYBRID_SEARCH_ENABLED = True

# weighted sum: full_text_weight, semantic_search_weight
HYBRID_SEARCH_WEIGHTS = 0.7,0.3

# Embedding
EMBEDDING_API_PATH = https://embedding.api.example.com/full/path/
EMBEDDING_API_KEY = your-embedding-api-key
EMBEDDING_REQUEST_TIMEOUT = 10
EMBEDDING_API_MODEL_NAME = embedding-api-model-name
EMBEDDING_DIMENSION = 1024
```

The hybrid search computes a score for full-text and semantic search and combines them through a weighted sum. HYBRID_SEARCH_WEIGHTS contains the weights of full-text and semantic respectively. 

You need to use an embedding api similar to https://albert.api.etalab.gouv.fr/documentation#tag/Embeddings/operation/embeddings_v1_embeddings_post. 

## trigrams

Find uses trigrams to improve the robustness of the full text search engine to spelling variations and errors. It can be configured by two environment variables. 

````
TRIGRAMS_BOOST=0.25
TRIGRAMS_MINIMUM_SHOULD_MATCH=0.75%
````

`TRIGRAMS_BOOST` is weight boost applied to the trigram score in the document matching. 
`TRIGRAMS_MINIMUM_SHOULD_MATCH` is the minimal number or proportion of trigrams having to match to score. It
either an absolute number or proportion as the default value.

## Setup indexation API

Other applications can index their files through the **`/index/`** endpoint with a simple token authentication.

For each application a new **Service** must be created through the admin interface
(see http://localhost:9071/admin/core/service/add/)

| Field                       | Description                                        |
|-----------------------------|----------------------------------------------------|
| Name                        | Name of the service and also the name of the index in Opensearch database |
| Is active                   | Toggle service availability                        |
| Client id                   | Calling service client_id (e.g `impress` for docs) |
| Allowed services for search | List of sub-services. Will add the results from all these index<br>to the search results. |
| Token (_read-only_)         | Random token for calling service authentication    |

And add the key in the calling application Django settings.

**Development Mode (Docs + Find)**

The command `make demo` will create a working service configuration for `docs` and `drive` with predefined secret keys

```python
# Docs
SEARCH_INDEXER_SECRET="find-api-key-for-docs-with-exactly-50-chars-length"
```

```python
# Drive
SEARCH_INDEXER_SECRET="find-api-key-for-driv-with-exactly-50-chars-length"
```

## Setup search API

The **`/search/`** endpoint is an OIDC ResourceServer view and needs extra Django settings (see [lasuite](https://github.com/suitenumerique/django-lasuite/blob/main/documentation/how-to-use-oidc-resource-server-backend.md) for details)

```shell
OIDC_OP_JWKS_ENDPOINT=http://nginx:8083/realms/impress/protocol/openid-connect/certs
OIDC_OP_AUTHORIZATION_ENDPOINT=http://nginx:8083/realms/impress/protocol/openid-connect/auth
OIDC_OP_TOKEN_ENDPOINT=http://nginx:8083/realms/impress/protocol/openid-connect/token
OIDC_OP_USER_ENDPOINT=http://nginx:8083/realms/impress/protocol/openid-connect/userinfo

# To run Find in development mode along other projects like docs/impress
# we should to use OIDC endpoints on a common keycloak realm. e.g :
# OIDC_OP_URL = http://nginx:8083/realms/impress
#
# This will cause a conflict with the 'iss' claim validation rule because the docs realm
# gives {'iss': 'http://localhost:8083/realms/impress'} so it must be the same
OIDC_OP_URL=http://localhost:8083/realms/impress

# Introspection endpoint is needed to get the "audience" and "sub" from the user token
OIDC_OP_INTROSPECTION_ENDPOINT=http://nginx:8083/realms/impress/protocol/openid-connect/token/introspect

# In development, the resource server use insecure settings
# OIDC_VERIFY_SSL=False

# Resource server
OIDC_RS_SCOPES="openid"
OIDC_RS_SIGN_ALGO=RS256

# This backend allows authentication without any model in database. 
OIDC_RS_BACKEND_CLASS="core.authentication.FinderResourceServerBackend"
```

**Development mode (Docs + Find)**

Docs and Find projects stacks can be run together but must have the same keycloak server.

So the endpoints of Docs on the 'nginx' domain for ResourceServer authentication and introspection are also used for Find.

**IMPORTANT:** Keep OIDC_OP_URL on 'localhost' or it will break the OIDC token claims validation : the `iss` claim from the token of the 'impress' users are 'localhost' and not 'nginx'.
