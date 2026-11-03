# Using the Find indexer

This guide explains how to setup the Find service which provide an API for indexation and fulltext search of
documents from various sources in a secure way: only the documents the user may access, in the services
granted by the user's token, are visible.

## Setup OpenSearch

### General

Add the following variables to your Django settings to configure Find
and enable full-text search.

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
The language is automatically detected by Find.
If the language can not be detected no language specific operation are applied and the indexing process is not affected.

Find supports French, English, German and Dutch.

The search process is not language specific, a query can get documents of any language.

Language detection estimates a confidence between 0 and 1. If the confidence is below a threshold the language is considered unrecognized.
This threshold can be controlled with `LANGUAGE_DETECTION_CONFIDENCE_THRESHOLD` environment variable.

```python
LANGUAGE_DETECTION_CONFIDENCE_THRESHOLD=0.75
```

## trigrams

Find uses trigrams to improve the robustness of the full text search engine to spelling variations and errors. It can be configured by two environment variables.

```
TRIGRAMS_BOOST=0.25
TRIGRAMS_MINIMUM_SHOULD_MATCH=0.75%
```

`TRIGRAMS_BOOST` is weight boost applied to the trigram score in the document matching.
`TRIGRAMS_MINIMUM_SHOULD_MATCH` is the minimal number or proportion of trigrams having to match to score. It is
either an absolute number or proportion.

## Setup indexation API

Other applications can index their files through the **`/index/`** endpoint with a simple token authentication.

For each application a new **Service** must be created through the admin interface
(see http://localhost:9071/admin/core/service/add/)

| Field     | Description                                                               |
| --------- | ------------------------------------------------------------------------- |
| Name      | Name of the service and also the name of the index in Opensearch database |
| Is active | Toggle service availability                                               |

The services a caller may search or delete from are not configured here: they
are granted by Menshen scopes (see below).

When the service is created, Find shows its random token, used by the calling
service to authenticate. Copy it then: Find only stores its hash, so it cannot
be shown again. If it is lost, select the service in the list and run the
**Regenerate the tokens of selected services** action, which shows a new token
and invalidates the old one.

Add the token to the calling application's Django settings.

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

## Setup search and delete API

The **`/search/`** and **`/delete/`** endpoints authenticate users with access
tokens exchanged with [Menshen](https://github.com/suitenumerique/menshen)
(OAuth 2.0 Token Exchange): the calling service exchanges the user's access
token for a token targeting Find, and sends it as a bearer token. Find
introspects it with Menshen, and caches the result for a few seconds.

```shell
# Menshen root URL
MENSHEN_URL=http://menshen:8000
# Find's credentials in Menshen, to introspect the user tokens
MENSHEN_CLIENT_ID=find
MENSHEN_CLIENT_SECRET=find-secret
# Find's audience id in Menshen, expected in the introspected tokens
MENSHEN_AUDIENCE=find
```

The token's scopes select the services whose documents the request may touch:

- `find:<service>:search` allows searching the documents indexed by `<service>`.
  The search covers all the granted services, or only the services requested
  with the `services` parameter, which must all be granted (otherwise 400).
- `find:<service>:delete` allows deleting the documents indexed by `<service>`,
  the `service` parameter of the request.

A token granting no applicable scope is answered with a 403. Scopes naming an
unknown or inactive service are ignored. Inside the granted services, users
only get the documents they may access (`users`, `reach` and `visited`).

These scopes are configured in Menshen, see
[setup-menshen.md](setup-menshen.md) for a local setup.
