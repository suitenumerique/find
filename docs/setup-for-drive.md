# Setup the Find search for Drive

This configuration will enable the fulltext search feature for Docs :
- Each save on **core.Item** or **core.Item** will trigger the indexer
- Once indexer service configured, the `api/v1.0/item/search/` will work as a proxy with the Find API for fulltext search.

## Create an index service for Drive

Configure a **Service** for Docs application with these settings

- **Name**: `drive`<br>_request.auth.name of the Docs application._

See [how-to-use-indexer.md](how-to-use-indexer.md) for details.

## Configure settings of Drive

Add those Django settings the Docs application to enable the feature.

```python
SEARCH_INDEXER_CLASS="core.services.search_indexers.SearchIndexer"
SEARCH_INDEXER_COUNTDOWN=10  # Debounce delay in seconds for the indexer calls.

# The token from service "drive" of Find application (development)
SEARCH_INDEXER_SECRET=find-api-key-for-driv-with-exactly-50-chars-length
SEARCH_INDEXER_URL="http://find:8000/api/v1.0/documents/index/"

# Search endpoint. Uses a user token exchanged with Menshen for authentication
SEARCH_INDEXER_QUERY_URL="http://find:8000/api/v1.0/documents/search/"

# Limit the mimetypes and size of indexable files
SEARCH_INDEXER_ALLOWED_MIMETYPES=["text/"]
SEARCH_INDEXER_UPLOAD_MAX_SIZE=2 * 2**20  # 2Mb
```

Find authenticates search and delete requests with a user token exchanged with
Menshen: before calling Find, the application exchanges the user's access token
for a token with audience `find`, requesting the `action:search-find-drive` (or
`action:delete-find-drive`) action scope, which Menshen grants as
`find:drive:search` (or `find:drive:delete`). See
[setup-menshen.md](setup-menshen.md) and [setup-indexer.md](setup-indexer.md).
This is being implemented on the application side in suitenumerique/drive#934.

The user's access token is needed for the exchange, so we also need to enable
the **OIDC Token** refresh or the authentication will fail quickly.

```shell
# Store OIDC tokens in the session
OIDC_STORE_ACCESS_TOKEN = True  # Store the access token in the session
OIDC_STORE_REFRESH_TOKEN = True  # Store the encrypted refresh token in the session
OIDC_STORE_REFRESH_TOKEN_KEY = "your-32-byte-encryption-key=="  # Must be a valid Fernet key (32 url-safe base64-encoded bytes)
```
