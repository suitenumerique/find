# Contract: Services Cannot Search

Services registered in Find can index documents, but they cannot search or delete. Only users
authenticated via OIDC tokens can call `/search/` and `/delete/`.

## Authentication model

Find exposes three endpoints, each with a distinct authentication requirement:

| Endpoint    | Auth class                    | Who can call it          |
|-------------|-------------------------------|--------------------------|
| `/index/`   | `ServiceTokenAuthentication`  | Services (bearer token)  |
| `/search/`  | `ResourceServerAuthentication` + `ResourceServerMixin` | OIDC users only |
| `/delete/`  | `ResourceServerAuthentication` + `ResourceServerMixin` | OIDC users only |

`ServiceTokenAuthentication` validates the `Authorization: Bearer <token>` header against the
`Service.token` field in the database. It is only wired to `IndexDocumentView`.

`ResourceServerAuthentication` (from `django-lasuite`) validates OIDC access tokens issued by
the configured identity provider. It is wired to `SearchDocumentView` and `DeleteDocumentsView`
via `ResourceServerMixin`.

## What happens when a service tries to search

A service bearer token posted to `/search/` or `/delete/` returns **HTTP 401 Unauthorized**.

`ResourceServerAuthentication` does not recognise service bearer tokens. The request is rejected
before any OpenSearch query runs.

## Why this contract exists

Services write to their own isolated index. They have no business reading across other services'
indices. Cross-service fan-out is a user-facing feature: when a user searches, Find queries all
active service indices and merges the results, filtered by the user's identity (`sub` claim).

Allowing services to search would break the access-control model: a service could read documents
belonging to users it has no relationship with.

## Test coverage

The following test scenarios lock this contract in:

- `test_api_documents_index.py` verifies that `/index/` rejects OIDC tokens (HTTP 401).
- `test_api_documents_search.py` verifies that `/search/` rejects service bearer tokens (HTTP 401).
- `test_integration_per_service_indices.py` verifies the full round-trip: service indexes a
  document, user searches and finds it, another user does not.

If you add a new endpoint that should be user-only, wire `ResourceServerAuthentication` and
`ResourceServerMixin` to it. Do not add `ServiceTokenAuthentication` to search or delete paths.
