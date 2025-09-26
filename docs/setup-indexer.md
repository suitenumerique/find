# Using the Find indexer

This guide explains how to setup the Find service which provide an API for indexation and fulltext search of
documents from various sources in a secure way : only the documents within the scope of the user's OIDC token
are visible.

## Setup Opensearch

Add the following settings to your Django settings for the Find application.

```shell
# Login for opensearch
OPENSEARCH_USER=opensearch-user
OPENSEARCH_PASSWORD=your-opensearch-password

# Host configuration
OPENSEARCH_HOST=opensearch
OPENSEARCH_PORT=9200

# Enable SSL for opensearch connection (False in dev mode)
OPENSEARCH_USE_SSL=True
```

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

The command `make demo` will create a working service configuration for `docs` with the following secret key

```python
SEARCH_INDEXER_SECRET="find-api-key-for-docs-with-exactly-50-chars-length"
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
