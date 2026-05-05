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

Language specific operations are applied to document titles and contents to improve search results.
The language is automatically detected  by Find.
If the language can not be detected no language specific operation are applied and the indexing process is not affected.

Find supports French, English, German and Dutch.

The search process is not language specific, a query can get documents of any language.

Language detection estimates a confidence between 0 and 1. If the confidence is below a threshold the language is considered unrecognized.
This threshold can be controlled with LANGUAGE_DETECTION_CONFIDENCE_THRESHOLD environment variable.

```python
LANGUAGE_DETECTION_CONFIDENCE_THRESHOLD=0.75
```

## trigrams

Find uses trigrams to improve the robustness of the full text search engine to spelling variations and errors. It can be configured by two environment variables.

````
TRIGRAMS_BOOST=0.25
TRIGRAMS_MINIMUM_SHOULD_MATCH=0.75%
````

`TRIGRAMS_BOOST` is weight boost applied to the trigram score in the document matching.
`TRIGRAMS_MINIMUM_SHOULD_MATCH` is the minimal number or proportion of trigrams having to match to score. It is
either an absolute number or proportion.

## Setup indexation API

Other applications can index their files through the **`/index/`** endpoint with a simple token authentication.

Services are configured via environment variables using the pattern `SERVICES__<NAME>__<FIELD>`:

| Environment Variable | Description |
|---------------------|-------------|
| `SERVICES__<NAME>__TOKEN` | Authentication token for the service |
| `SERVICES__<NAME>__CLIENT_ID` | Client identifier (typically the OIDC client ID) |

**Example Configuration:**

```bash
# Configure a "docs" service
SERVICES__DOCS__TOKEN=your-secret-token
SERVICES__DOCS__CLIENT_ID=impress

# Configure a "drive" service
SERVICES__DRIVE__TOKEN=another-secret-token
SERVICES__DRIVE__CLIENT_ID=drive
```

Service names are automatically normalized (lowercase, slugified). Multiple services can be configured by adding more `SERVICES__<NAME>__*` environment variables.

**Development Mode (Docs + Find)**

The Docker Compose setup includes pre-configured development tokens in `env.d/development/common`.
The command `make demo` creates OpenSearch indices and sample documents for `docs` and `drive`.

In the calling application (e.g., Docs), set the indexer secret to match the token in your environment:

```python
# Docs settings.py
SEARCH_INDEXER_SECRET="find-api-key-for-docs"
```

```python
# Drive settings.py
SEARCH_INDEXER_SECRET="find-api-key-for-drive"
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
