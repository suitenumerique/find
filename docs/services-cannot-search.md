# Contract: Services Cannot Search

Services registered in Find can index and delete documents, but they cannot search. Only users
authenticated via OIDC tokens can call `/search/`.

## Authentication model

Find exposes three endpoints, each with a distinct authentication requirement:

| Endpoint    | Auth class                    | Who can call it          |
|-------------|-------------------------------|--------------------------|
| `/index/`   | `ServiceTokenAuthentication`  | Services (bearer token)  |
| `/search/`  | `ResourceServerAuthentication` + `ResourceServerMixin` | OIDC users only |
| `/delete/`  | `ServiceTokenAuthentication`  | Services (bearer token)  |

`ServiceTokenAuthentication` validates the `Authorization: Bearer <token>` header against the
`Service.token` field in the database. It is wired to `IndexDocumentView` and
`DeleteDocumentsView`.

`ResourceServerAuthentication` (from `django-lasuite`) validates OIDC access tokens issued by
the configured identity provider. It is wired to `SearchDocumentView` via `ResourceServerMixin`.

## What happens when a service tries to search

A service bearer token posted to `/search/` returns **HTTP 401 Unauthorized**.

`ResourceServerAuthentication` does not recognise service bearer tokens. The request is rejected
before any OpenSearch query runs.

## Why this contract exists

Services write to and delete from their own isolated index. They have no business reading across
other services' indices. Cross-service fan-out is a user-facing feature: when a user searches,
Find queries all active service indices and merges the results, filtered by the user's identity
(`sub` claim).

Allowing services to search would break the access-control model: a service could read documents
belonging to users it has no relationship with.

## Test coverage

The following test scenarios lock this contract in:

- `test_api_documents_index.py` verifies that `/index/` rejects OIDC tokens (HTTP 401).
- `test_api_documents_search.py` verifies that `/search/` rejects service bearer tokens (HTTP 401).
- `test_api_documents_delete.py` verifies that `/delete/` accepts service bearer tokens and rejects
  OIDC user tokens.
- `test_integration_per_service_indices.py` verifies the full round-trip: services index and delete
  documents from their own indices, users search and find their accessible documents.

If you add a new endpoint that should be user-only, wire `ResourceServerAuthentication` and
`ResourceServerMixin` to it. Do not add `ServiceTokenAuthentication` to search paths.
